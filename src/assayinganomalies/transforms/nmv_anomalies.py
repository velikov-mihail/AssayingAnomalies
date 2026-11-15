"""
Novy-Marx and Velikov (RFS, 2016) anomaly signals.

MATLAB equivalent: makeNovyMarxVelikovAnomalies.m

Computes 23 anomaly signals from CRSP/COMPUSTAT data stored in ccm_panel
and raw compustat tables.  Each signal is a monthly stock-level variable
signed so that *higher* values predict *higher* returns (long side).

References:
    Novy-Marx, R. and M. Velikov, 2016, A taxonomy of anomalies and their
        trading costs, Review of Financial Studies 29(1): 104-147.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .compustat import ANNUAL_VALIDITY_MONTHS, ANNUAL_VALUE_COLS

LOGGER = logging.getLogger("assayinganomalies.transforms.nmv_anomalies")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _cross_rank(s: pd.Series, panel: pd.DataFrame) -> pd.Series:
    """Cross-sectional tied rank within each month (date)."""
    df = panel[["date"]].copy()
    df["_val"] = s.values
    df["_rank"] = df.groupby("date")["_val"].rank(method="average")
    return df["_rank"]


def _cross_rank_unit(s: pd.Series, panel: pd.DataFrame) -> pd.Series:
    """Cross-sectional tied rank within each month, mapped into ``(0, 1)``.

    Divides by one more than the number of ranked values in the month, so the
    result is strictly below 1 whatever the cross-section size and can be added
    to an integer score as a tiebreaker without ever crossing a whole level.
    """
    df = panel[["date"]].copy()
    df["_val"] = np.asarray(s, dtype=float)
    grp = df.groupby("date")["_val"]
    return grp.rank(method="average") / (grp.transform("count") + 1)


def _month_key(panel: pd.DataFrame) -> np.ndarray:
    """Unique int64 key permno*10^5 + (year*12 + month) for month-aware lags."""
    mcode = panel["date"].dt.year.to_numpy() * 12 + panel["date"].dt.month.to_numpy()
    return panel["permno"].to_numpy(dtype=np.int64) * 100_000 + mcode


def _lag_panel(s: pd.Series, panel: pd.DataFrame, months: int) -> pd.Series:
    """
    Lag a panel series by `months` calendar months within each permno.

    Month-aware (MATLAB matrices are dense on the monthly calendar, so
    ``lag(x, k)`` is always k calendar months; a row shift would slip
    whenever a permno has gaps in the panel).
    """
    key = _month_key(panel)
    src = pd.Series(np.asarray(s, dtype=float), index=key)
    out = src.reindex(key - months).to_numpy()
    return pd.Series(out, index=panel.index)


def _matlab_prctile(values: np.ndarray, pcts: list[float]) -> list[float]:
    """MATLAB prctile: sorted midpoints (i-0.5)/n, linear interp, clamped ends."""
    x = np.sort(values[np.isfinite(values)])
    n = x.size
    if n == 0:
        return [np.nan for _ in pcts]
    pos = 100.0 * (np.arange(1, n + 1) - 0.5) / n
    return [float(np.interp(q, pos, x)) for q in pcts]


def _winsorize_xs(s: pd.Series, panel: pd.DataFrame, pct: float = 5.0) -> pd.Series:
    """Winsorize cross-sectionally within each month at `pct` / (100-pct).

    Uses MATLAB `prctile` interpolation (winsorize.m).
    """
    df = panel[["date"]].copy()
    df["_val"] = np.asarray(s, dtype=float)

    def _clip(grp: pd.Series) -> pd.Series:
        lo, hi = _matlab_prctile(grp.to_numpy(), [pct, 100.0 - pct])
        if not np.isfinite(lo):
            return grp
        return grp.clip(lo, hi)

    return df.groupby("date")["_val"].transform(_clip)


def _scale_to_unit(s: pd.Series, panel: pd.DataFrame) -> pd.Series:
    """Scale to [0, 1] within each month by dividing by monthly max."""
    df = panel[["date"]].copy()
    df["_val"] = s.values
    mx = df.groupby("date")["_val"].transform("max")
    return df["_val"] / mx.replace(0, np.nan)


def _months_since(p: pd.DataFrame, col: str) -> pd.Series:
    """Calendar months from the dates in ``col`` to the panel date (NaN if NaT)."""
    since = pd.to_datetime(p[col])
    return ((p["date"].dt.year - since.dt.year) * 12
            + (p["date"].dt.month - since.dt.month))


def _enforce_annual_validity(p: pd.DataFrame) -> pd.DataFrame:
    """
    Blank annual Compustat inputs that are not on their record's June row.

    ``merge_compustat_crsp`` puts each annual record on the panel row of the
    June in which it becomes available and nowhere else, so on a panel it built
    this changes nothing. It guards the signals against a panel that was
    assembled or edited some other way, or built when the columns were filled
    June to May: an annual value on a row whose date is not the record's
    availability date (or that has none) is set to NaN. ``be``/``bm`` are
    checked against ``be_avail_date`` (their source may be Davis-Fama-French),
    every other annual column against ``comp_avail_date``. The signals that
    need the values every month fill them afterwards (``_filled``).

    A panel without the provenance columns (built before they existed) cannot
    be checked; a warning is logged and the panel is used as is.
    """
    present = [c for c in ANNUAL_VALUE_COLS if c in p.columns]
    if not present:
        return p
    if "comp_avail_date" not in p.columns:
        LOGGER.warning(
            "Panel has annual Compustat columns but no comp_avail_date; it predates "
            "annual record expiry, so June signals may use expired accounting data. "
            "Rebuild transform-compustat."
        )
        return p

    def on_june_row(col: str) -> pd.Series:
        return _months_since(p, col) == 0

    comp_ok = on_june_row("comp_avail_date")
    be_ok = on_june_row("be_avail_date") if "be_avail_date" in p.columns else comp_ok
    n_blanked = 0
    for col in present:
        stale = p[col].notna() & ~(be_ok if col in ("be", "bm") else comp_ok)
        if stale.any():
            p.loc[stale, col] = np.nan
            n_blanked += int(stale.sum())
    if n_blanked:
        LOGGER.warning(
            "Blanked %d annual Compustat values that were not on the row of their "
            "availability June (a panel with annual columns filled June to May, or "
            "an edited one)", n_blanked,
        )
    return p


def _filled(values: pd.Series, p: pd.DataFrame) -> pd.Series:
    """A June-only annual series spread over June to May (``fill_months``, 11 months).

    ``values`` is aligned to the rows of ``p``. MATLAB's ``FillMonths`` on a
    June-only matrix: a value stops after the following May, and a stock with
    no row in the June has none.
    """
    from ..analytics.sorts import fill_months

    idx = pd.MultiIndex.from_arrays([p["date"], p["permno"]], names=["date", "permno"])
    keyed = pd.Series(np.asarray(values, dtype=float), index=idx)
    out = fill_months(keyed, ANNUAL_VALIDITY_MONTHS - 1)
    return pd.Series(out.to_numpy(), index=p.index)


def _safe_col(p: pd.DataFrame, col: str) -> pd.Series:
    """Return column if it exists, else NaN series."""
    if col in p.columns:
        return p[col]
    return pd.Series(np.nan, index=p.index)


def _june_only(sig: pd.Series, p: pd.DataFrame) -> pd.Series:
    """
    Restrict an annual Compustat signal to June months (NaN elsewhere).

    MATLAB's annual matrices (bm, AT, GP, ...) are June-only by construction,
    so the CSV's annual signals are traded once a year. The panel stores the
    annual columns the same way, so for a signal built from them alone the
    mask changes nothing; it matters where a monthly column enters (``me``,
    ``shrout_adj``, ``fin_firm``). A June value is always the record that
    became available that June, and a 12-month lag the previous June's
    record, never an older one carried across a missing year.
    """
    out = sig.copy()
    out[p["date"].dt.month != 6] = np.nan
    return out


# ---------------------------------------------------------------------------
# Individual signal functions
# ---------------------------------------------------------------------------

def _signal_size(p: pd.DataFrame) -> pd.Series:
    """1. Size: -ME, June only (NaN for non-June months)."""
    me = _safe_col(p, "me")
    is_june = p["date"].dt.month == 6
    sig = -me.copy()
    sig[sig == 0] = np.nan
    sig[~is_june] = np.nan
    return sig


def _signal_value(p: pd.DataFrame) -> pd.Series:
    """2. Value: book-to-market (June-only, annual rebalance)."""
    return _june_only(_safe_col(p, "bm").copy(), p)


def _gp_at(p: pd.DataFrame, *, monthly: bool = False) -> pd.Series:
    """GP/AT, excl. financials.

    ``gp`` and ``at`` are on the June rows only, so the ratio is too.
    ``monthly=True`` carries it through the following May (``_filled``) before
    financial firms are dropped, so the financial-firm flag is each month's own.
    """
    gp = _safe_col(p, "gp")
    at = _safe_col(p, "at")
    gp_at = gp / at.replace(0, np.nan)
    if monthly:
        gp_at = _filled(gp_at, p)
    fin = _safe_col(p, "fin_firm")
    gp_at[fin == 1] = np.nan
    return gp_at


def _signal_gross_profitability(p: pd.DataFrame) -> pd.Series:
    """3. Gross profitability: GP/AT, excl. financials (June-only)."""
    return _june_only(_gp_at(p), p)


def _signal_val_prof(p: pd.DataFrame) -> pd.Series:
    """4. ValProf: rank(GP/AT) + rank(BM) (June-only)."""
    gp_at = _gp_at(p)
    bm = _safe_col(p, "bm").copy()
    bm[bm == 0] = np.nan
    r_gp = _cross_rank(gp_at, p)
    r_bm = _cross_rank(bm, p)
    return _june_only(r_gp + r_bm, p)


def _signal_accruals(p: pd.DataFrame) -> pd.Series:
    """5. Accruals: Sloan (1996) accruals, sign-flipped (June-only).

    MATLAB: Accruals = (dCA - dCash) - (dCL - dSTD - dTP) - Dep;
            accruals = -2*Accruals ./ (AT + lag(AT,12)).
    NaN in any input propagates (plain arithmetic, no nansum).
    """
    needed = ["act", "che", "lct", "dlc", "txp", "dp", "at"]
    missing = [c for c in needed if c not in p.columns]
    if missing:
        LOGGER.warning("Missing panel columns for accruals: %s", missing)
        return pd.Series(np.nan, index=p.index)

    at_ = p["at"]
    at_lag = _lag_panel(at_, p, 12)
    dCA = p["act"] - _lag_panel(p["act"], p, 12)
    dCash = p["che"] - _lag_panel(p["che"], p, 12)
    dCL = p["lct"] - _lag_panel(p["lct"], p, 12)
    dSTD = p["dlc"] - _lag_panel(p["dlc"], p, 12)
    dTP = p["txp"] - _lag_panel(p["txp"], p, 12)
    dep = p["dp"]
    raw_acc = (dCA - dCash) - (dCL - dSTD - dTP) - dep
    accruals = -2 * raw_acc / (at_ + at_lag).replace(0, np.nan)
    return _june_only(accruals, p)


def _signal_asset_growth(p: pd.DataFrame) -> pd.Series:
    """6. Asset growth: -AT/lag(AT), excl. financials."""
    at = _safe_col(p, "at")
    at_lag = _lag_panel(at, p, 12)
    sig = -(at / at_lag.replace(0, np.nan))
    fin = _safe_col(p, "fin_firm")
    sig[fin == 1] = np.nan
    return _june_only(sig, p)


def _signal_investment(p: pd.DataFrame) -> pd.Series:
    """7. Investment: -(ΔPPEGT + ΔINVT) / lag(AT), excl. financials."""
    at = _safe_col(p, "at")
    at_lag = _lag_panel(at, p, 12)
    fin = _safe_col(p, "fin_firm")

    if "ppegt" not in p.columns or "invt" not in p.columns:
        if "inv_capital" in p.columns:
            ic_lag = _lag_panel(p["inv_capital"], p, 12)
            sig = -(p["inv_capital"] - ic_lag) / at_lag.replace(0, np.nan)
            sig[fin == 1] = np.nan
            return _june_only(sig, p)
        return pd.Series(np.nan, index=p.index)

    ppegt_lag = _lag_panel(p["ppegt"], p, 12)
    invt_lag = _lag_panel(p["invt"], p, 12)
    sig = -((p["ppegt"] - ppegt_lag) + (p["invt"] - invt_lag)) / at_lag.replace(0, np.nan)
    sig[fin == 1] = np.nan
    return _june_only(sig, p)


def _signal_piotroski(p: pd.DataFrame) -> pd.Series:
    """8. Piotroski F-score (9 binary indicators) + small BM tiebreaker.

    MATLAB makeNovyMarxVelikovAnomalies.m lines 140-200:
    - indicators are (x > 0)*1, so NaN comparisons contribute 0;
    - availability a1..a9 is finiteness of the underlying inputs/differences,
      and the score is NaN unless all 9 are available;
    - EqIss is the June-only annual log growth of split-adjusted shares
      (shrout./ADJEX == shrout_adj), which restricts the score to June;
    - the tiebreaker ranks bm across stocks within the month. MATLAB's
      tiedrank(bm)/1000 leaves bm untransposed and so ranks each stock against
      its own history instead.
    """
    ib = _safe_col(p, "ib")
    cfo = _safe_col(p, "cfo")
    at = _safe_col(p, "at")
    bm = _safe_col(p, "bm")

    if ib.isna().all() or at.isna().all():
        return pd.Series(np.nan, index=p.index)

    at_lag = _lag_panel(at, p, 12)

    # Profitability
    ROA = ib / at_lag.replace(0, np.nan)
    ROA_lag = _lag_panel(ROA, p, 12)
    F_ROA = (ib > 0).astype(float)
    F_CFO = (cfo > 0).astype(float)
    F_DROA = (ROA - ROA_lag > 0).astype(float)
    F_ACCR = (cfo - ib > 0).astype(float)

    # Leverage / liquidity
    dltt = _safe_col(p, "dltt")
    dltt_lag = _lag_panel(dltt, p, 12)
    DTA = dltt / at.replace(0, np.nan)
    DTA_lag = _lag_panel(DTA, p, 12)
    F_DLEV = ((DTA - DTA_lag < 0) | ((dltt == 0) & (dltt_lag == 0))).astype(float)

    act = _safe_col(p, "act")
    lct = _safe_col(p, "lct")
    ATL = act / lct.replace(0, np.nan)
    ATL_lag = _lag_panel(ATL, p, 12)
    F_ATL = (ATL - ATL_lag > 0).astype(float)

    # Equity issuance: annual log growth of split-adjusted shares, June only
    sa = _safe_col(p, "shrout_adj")
    sa_ratio = sa / _lag_panel(sa, p, 12)
    sa_ratio[sa_ratio <= 0] = np.nan
    EqIss = _june_only(np.log(sa_ratio), p)
    F_EQ = (EqIss <= 0).astype(float)

    # Operating efficiency
    revt = _safe_col(p, "revt")
    cogs_col = _safe_col(p, "cogs")
    GM = 1 - cogs_col / revt.replace(0, np.nan)
    GM_lag = _lag_panel(GM, p, 12)
    F_GM = (GM - GM_lag > 0).astype(float)

    ATO = revt / at_lag.replace(0, np.nan)
    ATO_lag = _lag_panel(ATO, p, 12)
    F_ATO = (ATO - ATO_lag > 0).astype(float)

    fscore = (
        F_ROA + F_CFO + F_DROA + F_ACCR + F_DLEV + F_ATL + F_EQ + F_GM + F_ATO
    )

    # Availability: finiteness of the underlying quantities (MATLAB a1..a9)
    avail = (
        ib.notna().astype(int)
        + cfo.notna().astype(int)
        + (ROA - ROA_lag).notna().astype(int)
        + (cfo - ib).notna().astype(int)
        + (DTA - DTA_lag).notna().astype(int)
        + (ATL - ATL_lag).notna().astype(int)
        + EqIss.notna().astype(int)
        + (GM - GM_lag).notna().astype(int)
        + (ATO - ATO_lag).notna().astype(int)
    )
    fscore[avail < 9] = np.nan

    # Tiebreaker: cross-sectional tiedrank of June bm, scaled into (0, 1) so
    # value orders stocks within an F-score level and never across levels.
    return fscore + _cross_rank_unit(_june_only(bm, p), p)


def _signal_issuance(p: pd.DataFrame) -> pd.Series:
    """9. Issuance: -dashrout = -log annual growth of split-adjusted shares.

    MATLAB makeCRSPDerivedVariables.m: ashrout = shrout.*cfacshr;
    dashrout = log(ashrout./lag(ashrout,12)). Monthly.
    """
    sa = _safe_col(p, "shrout_adj")
    ratio = sa / _lag_panel(sa, p, 12)
    ratio[ratio <= 0] = np.nan
    return -np.log(ratio)


def _signal_roe(p: pd.DataFrame) -> pd.Series:
    """10. ROE: IBQ / lag(BEQ, 3 months).

    Both ibq and beq are RDQ-placed + forward-filled quarterly grids
    (MATLAB IBQ/BEQ matrices).
    """
    ibq = _safe_col(p, "ibq")
    beq = _safe_col(p, "beq")
    beq_lag = _lag_panel(beq, p, 3)
    return ibq / beq_lag.replace(0, np.nan)


def _signal_distress(p: pd.DataFrame, factors: pd.DataFrame | None = None) -> pd.Series:
    """
    11. Distress: Campbell-Hilscher-Szilagyi failure probability, sign-flipped.

    Faithful port of makeNovyMarxVelikovAnomalies.m lines 224-295. All eight
    winsorized components enter with plain addition, so a NaN in any component
    makes the score NaN (no fillna(0)).
    """
    required = ["me", "ret", "idiovol", "prc"]
    if not all(c in p.columns for c in required):
        return pd.Series(np.nan, index=p.index)

    # Coefficients from Campbell, Hilscher, and Szilagyi (2008)
    coefs = [-20.264, 1.416, -7.129, 1.411, -0.045, -2.132, 0.075, -0.058]
    c = 2 ** (-1 / 3)

    niq = _safe_col(p, "niq")
    ltq = _safe_col(p, "ltq")
    if niq.isna().all() or ltq.isna().all():
        LOGGER.info("Missing NIQ/LTQ for distress; skipping")
        return pd.Series(np.nan, index=p.index)

    denom = (ltq + p["me"]).replace(0, np.nan)

    # NIMTAAVG: exponentially weighted quarterly NIMTA (NaN propagates)
    nimta = niq / denom
    NIfac = (1 - c**3) / (1 - c**12)
    NIMTAAVG = NIfac * (
        nimta
        + c**3 * _lag_panel(nimta, p, 3)
        + c**6 * _lag_panel(nimta, p, 6)
        + c**9 * _lag_panel(nimta, p, 9)
    )

    TLMTA = ltq / denom

    # EXRET: log(1+ret) - log(1+mkt+rf), market total return from FF factors
    if factors is not None and {"mktrf", "rf"}.issubset(factors.columns):
        f = factors.copy()
        f["date"] = pd.to_datetime(f["date"])
        mkt_tot = pd.Series(
            (f["mktrf"] + f["rf"]).to_numpy(), index=f["date"].dt.to_period("M")
        )
        mkt_ts = p["date"].dt.to_period("M").map(mkt_tot)
    else:
        LOGGER.warning("No FF factors passed to distress; EXRETAVG will be NaN")
        mkt_ts = pd.Series(np.nan, index=p.index)
    EXRET = np.log1p(p["ret"]) - np.log1p(mkt_ts)

    # EXRETAVG: MATLAB weights lag 1 with 1 (not c) then c^j for j=2..12
    XRfac = (1 - c) / (1 - c**12)
    exret_sum = _lag_panel(EXRET, p, 1)
    for j in range(2, 13):
        exret_sum = exret_sum + (c**j) * _lag_panel(EXRET, p, j)
    EXRETAVG = XRfac * exret_sum

    # SIGMA: annualized 1-month CAPM idio vol (MATLAB IVOL)
    SIGMA = np.sqrt(252) * p["idiovol"]

    # RSIZE: log(ME / total market ME)
    total_me = p.groupby("date")["me"].transform("sum")
    RSIZE = np.log(p["me"] / total_me.replace(0, np.nan))

    CASHMTA = _safe_col(p, "cheq") / denom

    # MB: lag(me,6)/adjBE at June (BE is June-only), held for the next 11
    # months (MATLAB copies each June row forward 11 rows). The June mask is
    # for ``me`` in adjBE; the lookup below is the fill.
    be_june = _june_only(_safe_col(p, "be"), p)
    adjBE = 0.9 * be_june + 0.1 * p["me"]
    adjBE[adjBE <= 0] = 0.001
    MB_june = _lag_panel(p["me"], p, 6) / adjBE
    year = p["date"].dt.year.to_numpy()
    month = p["date"].dt.month.to_numpy()
    june_mcode = np.where(month >= 6, year, year - 1) * 12 + 6
    june_key = p["permno"].to_numpy(dtype=np.int64) * 100_000 + june_mcode
    MB_src = pd.Series(MB_june.to_numpy(), index=_month_key(p))
    MB = pd.Series(MB_src.reindex(june_key).to_numpy(), index=p.index)

    # PRICE: min(|prc|, 15); below 1 (or missing prc) -> NaN
    PRICE = p["prc"].abs().clip(upper=15)
    PRICE[PRICE < 1] = np.nan

    components = [NIMTAAVG, TLMTA, EXRETAVG, SIGMA, RSIZE, CASHMTA, MB, PRICE]
    distress = pd.Series(0.0, index=p.index)
    for coef, comp in zip(coefs, components):
        distress = distress + coef * _winsorize_xs(comp, p, 5.0)

    return -distress  # sign-flip: high = less distressed


def _signal_val_mom(p: pd.DataFrame) -> pd.Series:
    """13. ValMom: rank(R12_2) + rank(BM).

    Monthly: the June ``bm`` is carried through the following May
    (MATLAB ``FillMonths``) and ranked every month.
    """
    r = _safe_col(p, "R12_2")
    bm = _filled(_safe_col(p, "bm"), p)
    bm[bm == 0] = np.nan
    r_mom = _cross_rank(r, p)
    r_bm = _cross_rank(bm, p)
    return r_mom + r_bm


def _signal_val_mom_prof(p: pd.DataFrame) -> pd.Series:
    """12. ValMomProf: rank(R12_2) + rank(GP/AT) + rank(BM).

    Monthly (MATLAB fills the annual gp/bm ranks with `FillMonths`): the June
    GP/AT and ``bm`` are carried through the following May and ranked every
    month. They expire with their annual record, as `FillMonths` stops after
    11 months.
    """
    r = _safe_col(p, "R12_2")
    gp_at = _gp_at(p, monthly=True)
    bm = _filled(_safe_col(p, "bm"), p)
    bm[bm == 0] = np.nan
    r_mom = _cross_rank(r, p)
    r_gp = _cross_rank(gp_at, p)
    r_bm = _cross_rank(bm, p)
    return r_mom + r_gp + r_bm


def _signal_idio_vol(p: pd.DataFrame) -> pd.Series:
    """14. Idiosyncratic volatility: -IffVOL3 (3-month FF3 residual vol)."""
    return -_safe_col(p, "idiovol_ff_3m")


def _signal_momentum(p: pd.DataFrame) -> pd.Series:
    """15. Momentum: R12_2 (12-2 month cumulative return)."""
    return _safe_col(p, "R12_2")


def _signal_pead_sue(p: pd.DataFrame) -> pd.Series:
    """16. PEAD (SUE): standardized unexpected earnings (SUE2 variant)."""
    sue2 = _safe_col(p, "sue2")
    if sue2.notna().any():
        return sue2
    return _safe_col(p, "sue")


def _signal_pead_car3(p: pd.DataFrame) -> pd.Series:
    """
    17. PEAD (CAR3): cumulative abnormal return around earnings announcement.

    Requires daily data around announcement dates. Returns NaN if not
    precomputed in the panel (can be added later from daily transforms).
    """
    car3 = _safe_col(p, "car3")
    if car3.notna().any():
        return car3
    LOGGER.info("CAR3 not in panel; peadCAR3 signal will be NaN")
    return pd.Series(np.nan, index=p.index)


def _compute_ff49_industry_returns(p: pd.DataFrame) -> tuple[pd.DataFrame | None, pd.Series]:
    """
    Compute FF49 value-weighted industry returns (MATLAB makeIndustryReturns.m).

    MATLAB runs runUnivSort(ret, FF49, dates, me) — i.e. value-weighted with
    the industry assignment and market cap lagged one month — then assigns
    each stock its *contemporaneous* industry's return.

    Returns
    -------
    iret : pd.DataFrame or None
        Industry returns, index=date, columns=industry code (1..49).
    ireta : pd.Series
        Each stock's industry return (aligned to `p`), NaN if unclassified.
    """
    if "ff49" not in p.columns:
        return None, pd.Series(np.nan, index=p.index)

    from ..analytics.sorts import calc_ptf_rets

    idx = pd.MultiIndex.from_arrays(
        [p["date"], p["permno"]], names=["date", "permno"]
    )
    ret = pd.Series(p["ret"].to_numpy(dtype=float), index=idx)
    ind = pd.Series(
        pd.to_numeric(p["ff49"], errors="coerce").fillna(0).to_numpy(), index=idx
    )
    me = pd.Series(p["me"].to_numpy(dtype=float), index=idx)
    iret, _, _ = calc_ptf_rets(ret, ind, me, holding_period=1, weighting="v")

    # Assign each stock its contemporaneous industry's return.
    # calc_ptf_rets returns index = sorted unique dates, matching factorize.
    date_code = pd.factorize(p["date"], sort=True)[0]
    iret_pos = iret.copy()
    iret_pos.index = range(len(iret_pos))
    long = iret_pos.stack()
    key = pd.MultiIndex.from_arrays(
        [date_code, pd.to_numeric(p["ff49"], errors="coerce").fillna(-1).astype(int)]
    )
    ireta = pd.Series(long.reindex(key).to_numpy(), index=p.index)
    return iret, ireta


def _industry_momentum_raw(p: pd.DataFrame, iret: pd.DataFrame | None, ireta: pd.Series) -> pd.Series:
    """
    Industry momentum: MATLAB assignToPtf(iFF49reta, sort(iFF49ret,2)),
    zeros to NaN, then divide by the per-month max across stocks.

    assignToPtf against the sorted industry returns gives each stock
    1 + (number of industries with return <= its industry's return),
    i.e. 1 + rank(method='max') of its industry's return.
    """
    if iret is None or ireta.isna().all():
        return pd.Series(np.nan, index=p.index)

    rank_max = iret.rank(axis=1, method="max") + 1.0

    date_code = pd.factorize(p["date"], sort=True)[0]
    rank_pos = rank_max.copy()
    rank_pos.index = range(len(rank_pos))
    long = rank_pos.stack()
    key = pd.MultiIndex.from_arrays(
        [date_code, pd.to_numeric(p["ff49"], errors="coerce").fillna(-1).astype(int)]
    )
    imom = pd.Series(long.reindex(key).to_numpy(), index=p.index)
    # Stocks whose industry return is NaN get 0 in assignToPtf -> NaN
    imom[ireta.isna()] = np.nan
    return _scale_to_unit(imom, p)


def _signal_industry_momentum(p: pd.DataFrame, iret: pd.DataFrame | None, ireta: pd.Series) -> pd.Series:
    """18. Industry momentum: rank of the stock's industry VW return."""
    return _industry_momentum_raw(p, iret, ireta)


def _signal_industry_relative_reversal(p: pd.DataFrame, ireta: pd.Series) -> pd.Series:
    """
    19. Industry-relative reversal: tiedrank(iFF49reta - ret) across stocks
    each month, divided by the per-month max rank.
    """
    if ireta.isna().all():
        return pd.Series(np.nan, index=p.index)

    r = _cross_rank(ireta - _safe_col(p, "ret"), p)
    df = p[["date"]].copy()
    df["_r"] = r.values
    mx = df.groupby("date")["_r"].transform("max")
    return r / mx


def _signal_high_freq_combo(p: pd.DataFrame, iret: pd.DataFrame | None, ireta: pd.Series) -> pd.Series:
    """20. High-frequency combo: IRR + industry momentum."""
    irr = _signal_industry_relative_reversal(p, ireta)
    imom = _industry_momentum_raw(p, iret, ireta)
    return irr + imom


def _signal_reversals(p: pd.DataFrame) -> pd.Series:
    """21. Reversals: -ret (short-term reversal)."""
    return -_safe_col(p, "ret")


def _signal_seasonality(p: pd.DataFrame) -> pd.Series:
    """
    22. Seasonality: Heston-Sadka, sum of returns at lags 11, 23, 35, 47, 59.

    Same-calendar-month returns over the past 5 years. MATLAB uses a plain
    sum of lags, so a NaN at any of the five lags makes the signal NaN
    (all five years of history required).
    """
    ret = _safe_col(p, "ret")
    sig = pd.Series(0.0, index=p.index)
    for i in range(1, 6):
        lag_months = 12 * i - 1  # 11, 23, 35, 47, 59
        sig = sig + _lag_panel(ret, p, lag_months)
    sig[sig == 0] = np.nan
    return sig


def _signal_irr_low_vol(p: pd.DataFrame, ireta: pd.Series) -> pd.Series:
    """
    23. Industry-relative reversal, low-volatility stocks only.

    MATLAB: ind = makeUnivSortInd(IffVOL3, 2, NYSE); IRR(ind==2) = nan.
    High-vol = IffVOL3 >= NYSE median (assignToPtf assigns bin 2 at
    x >= breakpoint); stocks with NaN IffVOL3 or months without a
    breakpoint keep their IRR (ind stays 0).
    """
    irr = _signal_industry_relative_reversal(p, ireta)

    ivol = _safe_col(p, "idiovol_ff_3m")
    if ivol.isna().all():
        return irr

    df_tmp = p[["date"]].copy()
    df_tmp["ivol"] = ivol.values
    if "nyse_flag" in p.columns:
        df_tmp.loc[p["nyse_flag"] != 1, "ivol"] = np.nan
    median_bp = df_tmp.groupby("date")["ivol"].transform(
        lambda g: _matlab_prctile(g.to_numpy(), [50.0])[0]
    )

    high_vol = ivol >= median_bp
    irr[high_vol] = np.nan
    return irr


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

# Signal labels (order matches MATLAB)
NMV_LABELS = [
    "size",
    "value",
    "grossProfitability",
    "valProf",
    "accruals",
    "assetGrowth",
    "investment",
    "piotroski",
    "issuance",
    "roe",
    "distress",
    "valMomProf",
    "valMom",
    "idiosyncraticVolatility",
    "momentum",
    "peadSUE",
    "peadCAR3",
    "industryMomentum",
    "industryRelativeReversal",
    "highFrequencyCombo",
    "reversals",
    "seasonality",
    "industryRelativeReversalLowVol",
]


def compute_nmv_anomalies(
    panel: pd.DataFrame,
    funda: pd.DataFrame | None = None,
    factors: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Compute the 23 Novy-Marx & Velikov (2016) anomaly signals.

    Parameters
    ----------
    panel : pd.DataFrame
        ccm_panel with columns: date, permno, ret, me, bm, gp, at,
        fin_firm, R12_2, idiovol, sue2, etc.  Must have date as a column
        (not index).
    funda : pd.DataFrame, optional
        Unused (kept for call compatibility); all inputs now come from
        ccm_panel.
    factors : pd.DataFrame, optional
        Monthly FF factors with columns date, mktrf, rf. Needed for the
        distress signal's EXRET component (market total return).

    Returns
    -------
    pd.DataFrame
        Columns: date, permno, and 23 signal columns.
    """
    LOGGER.info("Computing NMV anomalies: %d rows in panel", len(panel))

    # Ensure date is a column, not index
    p = panel.copy()
    if isinstance(p.index, pd.MultiIndex):
        p = p.reset_index()
    if "date" not in p.columns:
        raise ValueError("Panel must have 'date' column")
    p["date"] = pd.to_datetime(p["date"])
    p = p.sort_values(["permno", "date"]).reset_index(drop=True)
    p = _enforce_annual_validity(p)

    # Precompute FF49 industry returns (used by signals 18-20, 23)
    iff49ret, iff49reta = _compute_ff49_industry_returns(p)

    # Compute all 23 signals
    signals = {}

    signals["size"] = _signal_size(p)
    signals["value"] = _signal_value(p)
    signals["grossProfitability"] = _signal_gross_profitability(p)
    signals["valProf"] = _signal_val_prof(p)
    signals["accruals"] = _signal_accruals(p)
    signals["assetGrowth"] = _signal_asset_growth(p)
    signals["investment"] = _signal_investment(p)
    signals["piotroski"] = _signal_piotroski(p)
    signals["issuance"] = _signal_issuance(p)
    signals["roe"] = _signal_roe(p)
    signals["distress"] = _signal_distress(p, factors)
    signals["valMomProf"] = _signal_val_mom_prof(p)
    signals["valMom"] = _signal_val_mom(p)
    signals["idiosyncraticVolatility"] = _signal_idio_vol(p)
    signals["momentum"] = _signal_momentum(p)
    signals["peadSUE"] = _signal_pead_sue(p)
    signals["peadCAR3"] = _signal_pead_car3(p)
    signals["industryMomentum"] = _signal_industry_momentum(p, iff49ret, iff49reta)
    signals["industryRelativeReversal"] = _signal_industry_relative_reversal(p, iff49reta)
    signals["highFrequencyCombo"] = _signal_high_freq_combo(p, iff49ret, iff49reta)
    signals["reversals"] = _signal_reversals(p)
    signals["seasonality"] = _signal_seasonality(p)
    signals["industryRelativeReversalLowVol"] = _signal_irr_low_vol(p, iff49reta)

    # Build output DataFrame
    result = p[["date", "permno"]].copy()
    for label in NMV_LABELS:
        result[label] = signals[label].values

    # Drop rows where ALL signals are NaN (matches MATLAB behavior)
    signal_cols = NMV_LABELS
    all_nan = result[signal_cols].isna().all(axis=1)
    result = result[~all_nan].reset_index(drop=True)

    n_valid = {lab: result[lab].notna().sum() for lab in NMV_LABELS}
    LOGGER.info(
        "NMV anomalies computed: %d rows, signal coverage: %s",
        len(result),
        {k: v for k, v in n_valid.items() if v > 0},
    )
    return result


__all__ = [
    "NMV_LABELS",
    "compute_nmv_anomalies",
]
