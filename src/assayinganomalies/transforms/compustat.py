"""
COMPUSTAT transformations: CCM merge and derived variables.

This module implements the MATLAB equivalents:
- mergeCRSPCOMP.m: Link COMPUSTAT to CRSP via CCM
- makeCOMPUSTATDerivedVariables.m: Compute book equity, BM, etc.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import AssayConfig
from ..run_manifest import note_input

LOGGER = logging.getLogger("assayinganomalies.transforms.compustat")

# Raw quarterly COMPUSTAT inputs that feed the derived quarterly variables.
# makeCOMPUSTATVariables.m forward-fills every quarterly column onto the CRSP
# monthly calendar; these are the ones the derived variables read.
QUARTERLY_FFILL_VARS = (
    "seqq", "ceqq", "pstkq", "atq", "ltq", "txditcq",
    "revtq", "cogsq", "ibq", "epspxq", "niq", "cheq",
    "mibq", "xrdq",
)

# Columns merged from the quarterly monthly grid into ccm_panel. The first
# eight are derived; ibq/niq/ltq/cheq are the raw RDQ-placed + forward-filled
# inputs themselves (MATLAB's IBQ/NIQ/LTQ/CHEQ matrices), needed by the NMV
# roe and distress signals. mibq/xrdq are carried the same way for user
# signals; no MATLAB transform reads them.
QUARTERLY_DERIVED_COLS = (
    "beq", "gpq", "roa", "sue", "droe", "sue2", "droa", "amonth",
    "ibq", "niq", "ltq", "cheq",
    "mibq", "xrdq",
)

# makeCOMPUSTATVariables.m:104 -- the forward fill runs to ``lastR + 2``, i.e.
# a quarterly observation persists for two months past its last announcement.
# FillMonths.m uses the same ``persist = 2`` default.
QUARTERLY_FILL_HORIZON = 2

# Annual columns merged from the June-aligned filings into ccm_panel. Each has a
# value only on the row of the June in which its record becomes available and
# is NULL in the other eleven months (see ``attach_annual_records``); all of a
# row's values come from the same filing, except that be/bm may be
# Davis-Fama-French book equity instead. ``aa.fill_months`` spreads them.
ANNUAL_VALUE_COLS = (
    "be", "bm",
    "at", "lt", "gp", "revt", "sale", "ib", "ni", "oancf", "capx", "sich",
    # act/che/lct/dlc/txp/dp feed the NMV accruals signal; dltt/cogs/ppegt/invt
    # feed piotroski and investment.
    "act", "che", "lct", "dlc", "txp", "dp", "dltt", "cogs", "ppegt", "invt",
    "oc", "d", "inv_capital", "fcf", "div", "wcap", "cfo",
    # mib (noncontrolling interest) is carried for user signals; no MATLAB
    # transform reads it.
    "mib",
)

# Provenance of the annual columns, on the same June row as the values.
# ``comp_datadate`` is the fiscal period end of the Compustat filing and
# ``comp_avail_date`` the June month-end it became available, which is the
# row's own date (both NaT on a row without a filing). ``be_source`` says where
# ``be`` (and so ``bm``) came from, ``"compustat"`` or ``"dff"``
# (Davis-Fama-French historical book equity), and ``be_avail_date`` is the June
# it became available (NULL / NaT when ``be`` is missing).
ANNUAL_PROVENANCE_COLS = ("comp_datadate", "comp_avail_date", "be_source", "be_avail_date")

# makeCOMPUSTATVariables.m keeps annual matrices June-only and FillMonths.m
# (annual branch) copies each June row over the next 11 rows: a filing is valid
# from its availability June through the following May, and never longer. The
# panel stores the June-only layout; ``fill_months`` carries a value
# ``ANNUAL_VALIDITY_MONTHS - 1`` months forward.
ANNUAL_VALIDITY_MONTHS = 12

# ``metadata`` key under which the stage that writes the annual columns records
# their layout, and its value for June-only storage. A database without the
# record was built when the columns were filled June to May.
ANNUAL_LAYOUT_KEY = "annual_layout"
ANNUAL_LAYOUT_JUNE = "june"

# makeCOMPUSTATDerivedVariables.m:342 -- the announcement-lag lookback loop
# runs ``for i = 1:60``, so a prior report month more than 60 monthly rows back
# is unreachable.
QUARTERLY_LAG_WINDOW = 60

# makeCOMPUSTATDerivedVariables.m:361 -- ``qmin`` for the SUE denominator.
SUE_MIN_OBS = 6

# makeCOMPUSTATDerivedVariables.m:362/402/415 -- SUE, SUE2 and dROA all start at
# the first monthly row with ``dates >= 197101``. SUE2's extra ``max(..., 25)``
# clause never binds: the CRSP calendar starts in the 1920s, so row 25 predates
# 1971-01 by decades.
QUARTERLY_START = pd.Timestamp("1971-01-31")


def _as_numeric(s: pd.Series) -> pd.Series:
    """
    ``s`` as a numeric series, whatever dtype the extract arrived with.

    A Compustat item that is entirely NULL over the requested window comes back
    from WRDS as a *string* column — pyarrow has no values to infer a type from
    — and arithmetic on it fails deep inside pandas with
    ``TypeError: Cannot set non-string value '0' into a StringArray``. That is
    not hypothetical: ``funda.wcapch`` (a long-discontinued item) is all-NULL
    on any window after the early 1990s, so every short-window build hit it.
    Coercing here rather than at each call site keeps the fix in the one place
    every arithmetic helper below funnels through. A column that is already
    numeric passes through untouched, so a full-window build is unaffected;
    anything else lands on plain ``float64`` rather than a nullable dtype,
    because the missing value downstream code tests for is ``NaN``, not
    ``pd.NA`` (``np.isnan(pd.NA)`` raises).
    """
    if pd.api.types.is_numeric_dtype(s):
        return s
    return pd.to_numeric(s, errors="coerce").astype("float64")


def _nansum(*arrays: pd.Series) -> pd.Series:
    """Sum arrays treating NaN as 0 (like MATLAB nanmatsum)."""
    arrays = tuple(_as_numeric(a) for a in arrays)
    result = arrays[0].copy()
    for arr in arrays[1:]:
        # Where both are NaN, result stays NaN; otherwise sum ignoring NaN
        both_nan = result.isna() & arr.isna()
        result = result.fillna(0) + arr.fillna(0)
        result[both_nan] = np.nan
    return result


def compute_book_equity(funda: pd.DataFrame) -> pd.Series:
    """
    Compute book equity following Fama-French / MATLAB methodology.

    Faithful port of makeCOMPUSTATDerivedVariables.m:124-153:

        SE = SEQ;
        temp = CEQ + PSTK;                 % plain addition — NaN propagates
        SE(isnan(SE)) = temp(isnan(SE));
        temp = AT - LT;
        SE(isnan(SE)) = temp(isnan(SE));
        PS = PSTKRV / PSTKL / PSTK;        % first non-NaN in hierarchy
        DT = TXDITC; else nanmatsum(TXDB, ITCB);
        BE = nanmatsum(SE, nanmatsum(DT, -PS));

    Critical: CEQ+PSTK must NOT fillna(0). If both are NaN, MATLAB's
    ``CEQ + PSTK`` is NaN and SE falls through to AT-LT. Filling with 0
    would set SE=0 and block that fallback, flipping the sign of BE when
    preferred stock is positive (observed on early Compustat coverage).
    """
    idx = funda.index

    # Shareholders' equity (SE) — NaN-propagating CEQ+PSTK, then AT-LT
    se = funda.get("seq", pd.Series(np.nan, index=idx))
    if "ceq" in funda.columns and "pstk" in funda.columns:
        alt_se = funda["ceq"] + funda["pstk"]
        se = se.fillna(alt_se)
    if "at" in funda.columns and "lt" in funda.columns:
        alt_se2 = funda["at"] - funda["lt"]
        se = se.fillna(alt_se2)

    # Preferred stock (PS) — leave NaN if all measures missing
    ps = funda.get("pstkrv", pd.Series(np.nan, index=idx))
    if "pstkl" in funda.columns:
        ps = ps.fillna(funda["pstkl"])
    if "pstk" in funda.columns:
        ps = ps.fillna(funda["pstk"])

    # Deferred taxes (DT) — TXDITC, else nanmatsum(TXDB, ITCB)
    dt = funda.get("txditc", pd.Series(np.nan, index=idx))
    if "txdb" in funda.columns:
        itcb = funda.get("itcb", pd.Series(np.nan, index=idx))
        alt_dt = _nansum(funda["txdb"], itcb)
        dt = dt.fillna(alt_dt)

    # BE = nanmatsum(SE, nanmatsum(DT, -PS))
    return _nansum(se, dt, -ps)


def compute_operating_costs(funda: pd.DataFrame) -> pd.Series:
    """OC = COGS + XSGA (MATLAB line 46)."""
    return _nansum(
        funda.get("cogs", pd.Series(np.nan, index=funda.index)),
        funda.get("xsga", pd.Series(np.nan, index=funda.index)),
    )


def compute_total_debt(funda: pd.DataFrame) -> pd.Series:
    """D = DLC + DLTT (MATLAB line 53)."""
    return _nansum(
        funda.get("dlc", pd.Series(np.nan, index=funda.index)),
        funda.get("dltt", pd.Series(np.nan, index=funda.index)),
    )


def compute_investment(funda: pd.DataFrame) -> pd.Series:
    """INV_CAPITAL = PPEGT + INVT (MATLAB line 61)."""
    return _nansum(
        funda.get("ppegt", pd.Series(np.nan, index=funda.index)),
        funda.get("invt", pd.Series(np.nan, index=funda.index)),
    )


def compute_free_cash_flow(funda: pd.DataFrame) -> pd.Series:
    """FCF = NI + DP - WCAPCH - CAPX (MATLAB line 71).

    MATLAB computes this via nested ``nanmatsum`` calls, which treat NaN
    as 0 except when ALL operands at a given cell are NaN. A straight
    ``_nansum(ni, dp) - _nansum(wcapch, capx)`` breaks that semantics:
    if WCAPCH and CAPX are both NaN but NI (or DP) is finite, the
    subtraction yields NaN even though MATLAB returns the finite partial
    sum. We therefore collapse all four terms into a single ``_nansum``
    call (negating WCAPCH/CAPX first; negating NaN stays NaN) so the
    output is NaN only when every input is NaN — matching MATLAB.
    """
    ni = funda.get("ni", pd.Series(np.nan, index=funda.index))
    dp = funda.get("dp", pd.Series(np.nan, index=funda.index))
    wcapch = funda.get("wcapch", pd.Series(np.nan, index=funda.index))
    capx = funda.get("capx", pd.Series(np.nan, index=funda.index))
    return _nansum(ni, dp, -wcapch, -capx)


def compute_dividends(funda: pd.DataFrame) -> pd.Series:
    """
    DIV = DVC + PRSTKCC, with fallback DVC + (PRSTKC - PRSTKPC).

    MATLAB lines 75-84.
    """
    dvc = funda.get("dvc", pd.Series(np.nan, index=funda.index))
    prstkcc = funda.get("prstkcc", pd.Series(np.nan, index=funda.index))

    # Primary: DVC + PRSTKCC (only when PRSTKCC is available)
    primary = dvc.fillna(0) + prstkcc
    # primary is NaN where prstkcc is NaN

    # Fallback: DVC + (PRSTKC - PRSTKPC)
    prstkc = funda.get("prstkc", pd.Series(np.nan, index=funda.index))
    prstkpc = funda.get("prstkpc", pd.Series(np.nan, index=funda.index))
    net_repurchase = prstkc.fillna(0) - prstkpc.fillna(0)
    fallback = _nansum(dvc, net_repurchase)

    result = primary.fillna(fallback)
    return result


def compute_working_capital(funda: pd.DataFrame) -> pd.Series:
    """WCAP = ACT - LCT (MATLAB line 90).

    Plain subtraction so NaN propagates when either ACT or LCT is missing,
    matching MATLAB ``WCAP = ACT - LCT`` (not ``nanmatsum``).
    """
    act = funda.get("act", pd.Series(np.nan, index=funda.index))
    lct = funda.get("lct", pd.Series(np.nan, index=funda.index))
    return act - lct


def compute_cfo(funda: pd.DataFrame) -> pd.Series:
    """
    Cash flow from operations (MATLAB lines 94-121).

    Primary: 12-component sum (IB + XIDO + DP + TXDC + ESUBC - SPPIV + FOPO
             + RECCH + INVCH + APALCH + TXACH + AOLOCH).
    SPPIV enters with a minus sign (MATLAB line 112: gain on sale is
    subtracted when reconstructing operating cash flow).
    Fallback: OANCF where primary is NaN.
    """
    idx = funda.index

    def _col(name: str) -> pd.Series:
        return funda.get(name, pd.Series(np.nan, index=idx))

    components = _nansum(
        _col("ib"),
        _col("xido"),
        _col("dp"),
        _col("txdc"),
        _col("esubc"),
        -_col("sppiv"),  # MATLAB line 112: nanmatsum(temp, -SPPIV)
        _col("fopo"),
        _col("recch"),
        _col("invch"),
        _col("apalch"),
        _col("txach"),
        _col("aoloch"),
    )

    oancf = _col("oancf")
    result = components.copy()
    result = result.fillna(oancf)
    return result


def _month_index(dates: pd.Series) -> pd.Series:
    """Monotone integer month counter, so differences are month counts."""
    d = pd.to_datetime(dates)
    return d.dt.year * 12 + d.dt.month


def _nan_moments(
    samples: list[np.ndarray],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Element-wise (count, mean, std) across ``samples``, ignoring NaN, with
    MATLAB's ddof=1 normalisation.

    ``samples`` is a list of equally shaped arrays -- one per element of the
    sample -- and they are accumulated **sequentially**, the order MATLAB's
    ``sum`` uses along a matrix dimension. NumPy's vectorised ``sum`` uses
    pairwise summation instead, which is more accurate but not what MATLAB
    computes: for a constant sample, sequential accumulation leaves roundoff so
    ``std`` is ~1e-17 rather than exactly 0. SUE2 divides by that std with no
    zero guard, so the difference decides whether ~20k cells come out as 0
    (MATLAB) or NaN from 0/0.
    """
    shape = samples[0].shape
    n = np.zeros(shape, dtype=np.int64)
    total = np.zeros(shape, dtype=float)
    for sample in samples:
        finite = np.isfinite(sample)
        n += finite
        total = total + np.where(finite, sample, 0.0)

    mean = np.divide(total, n, out=np.full(shape, np.nan), where=n > 0)

    sum_sq = np.zeros(shape, dtype=float)
    for sample in samples:
        dev = np.where(np.isfinite(sample), sample - mean, 0.0)
        sum_sq = sum_sq + dev * dev

    var = np.divide(sum_sq, n - 1, out=np.full(shape, np.nan), where=n > 1)
    return n, mean, np.sqrt(var)


def _fill_months(
    monthly: pd.DataFrame,
    values: pd.Series,
    *,
    persist: int = QUARTERLY_FILL_HORIZON,
) -> pd.Series:
    """
    Port of ``FillMonths.m`` (quarterly branch).

    Forward-fills within each permno, then blanks everything more than
    ``persist`` months past that permno's last finite input value
    (``FillMonths.m:69-75`` runs the fill loop only up to ``MM + persist``).
    """
    frame = pd.DataFrame(
        {
            "permno": monthly["permno"].to_numpy(),
            "mi": _month_index(monthly["date"]).to_numpy(),
            "v": pd.to_numeric(values, errors="coerce").to_numpy(dtype=float),
        },
        index=monthly.index,
    )
    last_mi = frame.loc[frame["v"].notna()].groupby("permno")["mi"].max()
    filled = frame.groupby("permno", sort=False)["v"].ffill()
    cap = frame["permno"].map(last_mi)
    return filled.where(frame["mi"] <= cap + persist)


def build_quarterly_monthly_panel(
    fundq_linked: pd.DataFrame,
    panel_dates,
    *,
    permnos=None,
    variables=QUARTERLY_FFILL_VARS,
) -> pd.DataFrame:
    """
    Expand linked quarterly COMPUSTAT rows onto the CRSP monthly calendar.

    Port of ``mergeCRSPCOMP.m:134-197`` plus the quarterly branch of
    ``makeCOMPUSTATVariables.m:86-112``:

    - drop rows with a missing RDQ (``mergeCRSPCOMP.m:135``);
    - date each row at the end of its RDQ month (``mergeCRSPCOMP.m:156-157``);
    - keep the latest fiscal quarter per permno-RDQ month, sorting on
      ``(permno, rdq, datadate)`` (``mergeCRSPCOMP.m:172-175``);
    - place values on the dense CRSP ``dates`` x ``permno`` grid and forward-fill
      each variable independently from its own first announcement to its own
      last announcement plus ``QUARTERLY_FILL_HORIZON`` months.

    The per-variable fill is what makes MATLAB's derived quarterly variables
    mix vintages across quarters: when a quarter reports ATQ but not SEQQ, BEQ
    for that month combines the new ATQ with the stale SEQQ. Deriving on the
    quarterly rows first and forward-filling the *outputs* cannot reproduce it.

    ``variables`` are the raw columns filled (``QUARTERLY_FFILL_VARS`` by
    default; ``align_extra_quarterly`` passes a user's own columns). The grid
    depends only on the announcement dates, not on which columns are filled.

    Returns a frame with ``permno``, ``date`` and the forward-filled raw inputs,
    sorted by ``(permno, date)`` with a contiguous monthly grid per permno.
    """
    variables = tuple(variables)
    calendar = pd.DatetimeIndex(pd.unique(pd.to_datetime(pd.Series(panel_dates)))).sort_values()
    empty = pd.DataFrame(columns=["permno", "date", *variables])
    if len(calendar) == 0 or fundq_linked.empty:
        return empty

    df = fundq_linked.copy()
    df.columns = df.columns.str.lower()
    if "rdq" not in df.columns or "permno" not in df.columns:
        LOGGER.warning("Linked fundq lacks rdq/permno; skipping quarterly monthly panel")
        return empty

    df["rdq"] = pd.to_datetime(df["rdq"], errors="coerce")
    df["datadate"] = pd.to_datetime(df.get("datadate"), errors="coerce")
    n_before = len(df)
    df = df[df["rdq"].notna()].copy()
    LOGGER.info(
        "Dropped %d quarterly rows with missing RDQ (mergeCRSPCOMP.m:135)",
        n_before - len(df),
    )

    df["date"] = df["rdq"] + pd.offsets.MonthEnd(0)
    # MATLAB left-joins the announcements onto the dense CRSP grid, so RDQ
    # months outside the CRSP calendar (e.g. announcements past SAMPLE_END)
    # are dropped rather than extending the panel.
    df = df[df["date"].isin(calendar)].copy()
    df["permno"] = df["permno"].astype(np.int64)
    if permnos is not None:
        df = df[df["permno"].isin(pd.Index(permnos).astype(np.int64))].copy()
    if df.empty:
        return empty

    df = df.sort_values(["permno", "rdq", "datadate"])
    df = df.drop_duplicates(subset=["permno", "date"], keep="last")

    value_cols = [c for c in variables if c in df.columns]
    pos_of = pd.Series(np.arange(len(calendar)), index=calendar)
    ann = df[["permno", *value_cols]].copy()
    ann["pos"] = df["date"].map(pos_of).to_numpy()

    bounds = ann.groupby("permno", sort=True)["pos"].agg(["min", "max"])
    starts = bounds["min"].to_numpy()
    stops = np.minimum(bounds["max"].to_numpy() + QUARTERLY_FILL_HORIZON, len(calendar) - 1)
    lengths = (stops - starts + 1).astype(np.int64)
    group_start = np.cumsum(lengths) - lengths
    offsets = np.arange(int(lengths.sum())) - np.repeat(group_start, lengths)
    positions = np.repeat(starts, lengths) + offsets

    grid = pd.DataFrame(
        {
            "permno": np.repeat(bounds.index.to_numpy(), lengths),
            "pos": positions,
            "date": calendar.to_numpy()[positions],
        }
    )
    grid = grid.merge(ann, on=["permno", "pos"], how="left")
    grid = grid.sort_values(["permno", "pos"]).reset_index(drop=True)

    # MATLAB matrices are plain doubles with NaN. The WRDS extract arrives with
    # pandas nullable dtypes, where ``x != NA`` is NA rather than MATLAB's
    # ``x ~= NaN`` -> true, so cast before any comparison or arithmetic.
    for col in value_cols:
        grid[col] = pd.to_numeric(grid[col], errors="coerce").astype("float64")

    filled: dict[str, pd.Series] = {}
    for col in value_cols:
        announced = grid.loc[grid[col].notna()]
        last_pos = announced.groupby("permno")["pos"].max()
        series = grid.groupby("permno", sort=False)[col].ffill()
        cap = grid["permno"].map(last_pos)
        filled[col] = series.where(grid["pos"] <= cap + QUARTERLY_FILL_HORIZON)
    for col, series in filled.items():
        grid[col] = series

    LOGGER.info(
        "Built quarterly monthly panel: %d permno-months, %d permnos, cols=%s",
        len(grid), grid["permno"].nunique(), value_cols,
    )
    return grid.drop(columns=["pos"])


def compute_quarterly_book_equity(fundq: pd.DataFrame) -> pd.Series:
    """
    Quarterly book equity (BEQ).

    Faithful port of MATLAB makeCOMPUSTATDerivedVariables.m:275-296:

        SE = SEQQ;
        temp = CEQQ + PSTKQ;                       % plain addition, NaN propagates
        SE(isnan(SE)) = temp(isnan(SE));
        temp = ATQ - LTQ;
        SE(isnan(SE)) = temp(isnan(SE));
        PS = PSTKQ;                                % no PSTKRQ/PSTKL hierarchy
        DT = TXDITCQ;                              % no TXDBQ+ITCB fallback
        BEQ = nanmatsum(SE, nanmatsum(DT, -PS));
    """
    idx = fundq.index

    # SE = SEQQ, with CEQQ+PSTKQ then ATQ-LTQ as NaN-propagating fallbacks
    se = fundq.get("seqq", pd.Series(np.nan, index=idx))
    if "ceqq" in fundq.columns and "pstkq" in fundq.columns:
        alt_se = fundq["ceqq"] + fundq["pstkq"]
        se = se.fillna(alt_se)
    if "atq" in fundq.columns and "ltq" in fundq.columns:
        alt_se2 = fundq["atq"] - fundq["ltq"]
        se = se.fillna(alt_se2)

    # DT = TXDITCQ (no fallback; stays NaN when TXDITCQ is NaN)
    dt = fundq.get("txditcq", pd.Series(np.nan, index=idx))

    # PS = PSTKQ (no PSTKRQ preference; stays NaN when PSTKQ is NaN)
    ps = fundq.get("pstkq", pd.Series(np.nan, index=idx))

    # BEQ = nanmatsum(SE, nanmatsum(DT, -PS))
    return _nansum(se, dt, -ps)


def compute_quarterly_gross_profit(fundq: pd.DataFrame) -> pd.Series:
    """
    GPQ = REVTQ - COGSQ (MATLAB makeCOMPUSTATDerivedVariables.m:300-304).

    MATLAB line 303 is plain elementwise subtraction (``GPQ = REVTQ - COGSQ;``),
    not ``nanmatsum``: the cell is NaN whenever either REVTQ or COGSQ is NaN.
    """
    idx = fundq.index
    revtq = fundq.get("revtq", pd.Series(np.nan, index=idx))
    cogsq = fundq.get("cogsq", pd.Series(np.nan, index=idx))
    return revtq - cogsq


def compute_quarterly_roa(monthly: pd.DataFrame) -> pd.Series:
    """
    ROA = IBQ / lag(ATQ, 3) on the monthly grid.

    MATLAB lines 307-311: ``roa = IBQ ./ lag(ATQ, 3, nan)``. ``IBQ`` and ``ATQ``
    are (nMonths x nStocks) matrices whose quarterly values are forward-filled
    across months, so ``lag(...,3)`` is a **three-month** shift and ROA moves
    within a quarter whenever the ATQ vintage three months back differs. There
    is no zero guard in MATLAB: ATQ == 0 yields Inf.
    """
    atq_lag3 = monthly.groupby("permno", sort=False)["atq"].shift(3)
    return monthly["ibq"] / atq_lag3


def compute_quarterly_report_month(monthly: pd.DataFrame) -> pd.Series:
    """
    ``idxRprtDate`` from MATLAB line 322:
    ``(IBQ ~= lag(IBQ,1,nan)) .* isfinite(IBQ)``.

    True on months where the forward-filled IBQ is finite and differs from the
    previous month. Because IBQ is forward-filled, that is the announcement
    month -- unless the new quarter reports exactly the same IBQ, in which case
    MATLAB does not treat it as a report month at all.

    MATLAB's ``IBQ ~= lag(IBQ,1,nan)`` is *true* when the previous month is NaN,
    so the first month of a firm's history is always a report month. Comparisons
    against a missing value must be forced to True rather than left as NA.
    """
    ibq = monthly["ibq"]
    prev = monthly.groupby("permno", sort=False)["ibq"].shift(1)
    changed = (ibq != prev).fillna(True)
    return (ibq.notna() & changed).fillna(False).astype(bool)


def compute_amonth(monthly: pd.DataFrame) -> pd.Series:
    """
    Announcement month indicator (MATLAB lines 430-431).

    ``amonth = isfinite(IBQ) .* (IBQ ~= lag(IBQ,1,nan))`` -- a dense 0/1 matrix,
    never NaN.
    """
    return compute_quarterly_report_month(monthly).astype(float)


def _report_lag_frame(
    monthly: pd.DataFrame,
    report_month: pd.Series,
    n_lags: int,
    columns: list[str],
) -> pd.DataFrame:
    """
    Values of ``columns`` at the k-th prior *report* month, for k = 1..n_lags.

    Port of the accumulator loop at MATLAB lines 324-358. There, ``numLagIdx``
    counts report months between row ``r`` and row ``r-i``, and a value is
    assigned when that count identifies row ``r-i`` as the k-th prior report
    month. Restricting to report rows and shifting by k within permno gives the
    same mapping; the ``for i = 1:60`` bound becomes an explicit check that the
    k-th prior report month is at most ``QUARTERLY_LAG_WINDOW`` months back.
    """
    rpt = monthly.loc[report_month, ["permno", *columns]].copy()
    rpt["_mi"] = _month_index(monthly.loc[report_month, "date"])
    grouped = rpt.groupby("permno", sort=False)

    out = pd.DataFrame(index=rpt.index)
    for k in range(1, n_lags + 1):
        gap = rpt["_mi"] - grouped["_mi"].shift(k)
        within = gap <= QUARTERLY_LAG_WINDOW
        for col in columns:
            out[f"{col}_l{k}"] = grouped[col].shift(k).where(within)
    return out


def _scatter(monthly: pd.DataFrame, values: pd.Series) -> pd.Series:
    """Place report-month values back onto the full monthly index as NaN elsewhere."""
    out = pd.Series(np.nan, index=monthly.index, dtype=float)
    out.loc[values.index] = values.to_numpy(dtype=float)
    return out


def compute_sue(
    monthly: pd.DataFrame,
    *,
    report_month: pd.Series | None = None,
) -> pd.Series:
    """
    Standardized unexpected earnings (MATLAB lines 314-389).

    At each report month, MATLAB forms eight seasonal EPS differences from the
    *prior* report months -- ``lagEPS_j - lagEPS_{j+4}`` for j = 1..8, hence the
    twelve lag buffers -- takes their ``std(..., 'omitnan')`` (ddof=1), requires
    at least ``qmin = 6`` finite differences, discards a zero denominator, and
    divides ``EPSPXQ_t - lagEPS_4`` by it. Months before 1971-01 are skipped.
    The result exists only at report months and is then spread forward by
    ``FillMonths``.
    """
    if report_month is None:
        report_month = compute_quarterly_report_month(monthly)

    lags = _report_lag_frame(monthly, report_month, 12, ["epspxq"])
    deps = [
        (lags[f"epspxq_l{j}"] - lags[f"epspxq_l{j + 4}"]).to_numpy(dtype=float)
        for j in range(1, 9)
    ]
    n_obs, _, std = _nan_moments(deps)
    std = np.where(n_obs < SUE_MIN_OBS, np.nan, std)
    std = np.where(std == 0, np.nan, std)

    eps_now = monthly.loc[report_month, "epspxq"].to_numpy(dtype=float)
    numerator = eps_now - lags["epspxq_l4"].to_numpy(dtype=float)
    sue_at_report = pd.Series(numerator / std, index=lags.index)
    started = monthly.loc[report_month, "date"] >= QUARTERLY_START
    sue_at_report = sue_at_report.where(started.to_numpy())

    return _fill_months(monthly, _scatter(monthly, sue_at_report))


def compute_droe(
    monthly: pd.DataFrame,
    beq: pd.Series | None = None,
    *,
    report_month: pd.Series | None = None,
) -> pd.Series:
    """
    Change in return on equity (MATLAB line 392):
    ``dROE = FillMonths((IBQL0 - IBQL4) ./ BEQL1)``.

    ``IBQL0`` is IBQ blanked outside report months, ``IBQL4`` is IBQ at the
    fourth prior report month and ``BEQL1`` is BEQ at the previous report month,
    so dROE is defined only at report months and then spread forward. MATLAB has
    no zero guard on BEQL1.
    """
    frame = monthly
    if beq is not None:
        frame = monthly.copy()
        frame["beq"] = pd.to_numeric(beq, errors="coerce").to_numpy(dtype=float)
    if report_month is None:
        report_month = compute_quarterly_report_month(frame)

    lags = _report_lag_frame(frame, report_month, 4, ["ibq", "beq"])
    ibq_now = frame.loc[report_month, "ibq"].to_numpy(dtype=float)
    droe_at_report = pd.Series(
        (ibq_now - lags["ibq_l4"].to_numpy(dtype=float))
        / lags["beq_l1"].to_numpy(dtype=float),
        index=lags.index,
    )
    return _fill_months(frame, _scatter(frame, droe_at_report))


def compute_sue2(monthly: pd.DataFrame) -> pd.Series:
    """
    Simpler SUE variant (MATLAB lines 396-405):
    ``SUE2(i,:) = (IBQ(i,:) - IBQ(i-12,:)) ./ std(IBQ(i-24:3:i-3,:), 'omitnan')``.

    Everything is monthly-row indexing on the forward-filled IBQ matrix: the
    numerator is a twelve-month change and the denominator the ddof=1 standard
    deviation of the eight values three, six, ... twenty-four months back. There
    is no ``qmin`` and no zero guard, so SUE2 is dense monthly from 1971-01 on.
    """
    ibq = monthly.groupby("permno", sort=False)["ibq"]
    window = [
        ibq.shift(k).to_numpy(dtype=float) for k in (24, 21, 18, 15, 12, 9, 6, 3)
    ]
    _, _, std = _nan_moments(window)
    numerator = (monthly["ibq"] - ibq.shift(12)).to_numpy(dtype=float)
    out = pd.Series(numerator / std, index=monthly.index)
    return out.where(monthly["date"] >= QUARTERLY_START)


def compute_droa(monthly: pd.DataFrame) -> pd.Series:
    """
    Change in ROA (MATLAB lines 408-421):
    ``dROA(i,:) = IBQ(i,:) - mean(IBQ(i-12:i-1,:), 'omitnan')``, then ``./ ATQ``.

    The mean spans the twelve preceding *months* of the forward-filled IBQ
    matrix (roughly four quarterly vintages, each repeated three times), and the
    scaling uses the contemporaneous ATQ with no zero guard.
    """
    ibq = monthly.groupby("permno", sort=False)["ibq"]
    window = [ibq.shift(k).to_numpy(dtype=float) for k in range(1, 13)]
    _, mean, _ = _nan_moments(window)
    out = pd.Series(
        (monthly["ibq"].to_numpy(dtype=float) - mean)
        / monthly["atq"].to_numpy(dtype=float),
        index=monthly.index,
    )
    return out.where(monthly["date"] >= QUARTERLY_START)


def compute_quarterly_derived(monthly: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all quarterly derived variables on the monthly COMPUSTAT grid.

    Parameters
    ----------
    monthly : pd.DataFrame
        Output of :func:`build_quarterly_monthly_panel`: one row per
        permno-month on a contiguous monthly grid, with the forward-filled raw
        quarterly inputs.

    Returns
    -------
    pd.DataFrame
        Input frame augmented with beq, gpq, roa, sue, droe, sue2, droa, amonth.
    """
    result = monthly.copy()
    result.columns = result.columns.str.lower()
    result = result.sort_values(["permno", "date"]).reset_index(drop=True)

    result["beq"] = compute_quarterly_book_equity(result)
    result["gpq"] = compute_quarterly_gross_profit(result)
    result["roa"] = compute_quarterly_roa(result)

    report_month = compute_quarterly_report_month(result)
    result["sue"] = compute_sue(result, report_month=report_month)
    result["droe"] = compute_droe(result, report_month=report_month)
    result["sue2"] = compute_sue2(result)
    result["droa"] = compute_droa(result)
    result["amonth"] = report_month.astype(float)

    LOGGER.info(
        "Computed quarterly derived variables on %d permno-months: %s",
        len(result), list(QUARTERLY_DERIVED_COLS),
    )
    return result


FF_HISTORICAL_BE_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Historical_BE_Data.zip"
)
# Seconds to wait before the second and the third attempt of the download.
FF_HISTORICAL_BE_PAUSES = (5.0, 15.0)
_FF_HISTORICAL_BE_LOCAL = Path("Data") / "FF" / "DFF_BE_With_Nonindust.txt"


class HistoricalBookEquityError(RuntimeError):
    """The Davis-Fama-French historical book-equity file could not be obtained.

    A build without the file has no book equity before Compustat's coverage,
    so it stops instead of going on with a different ``be`` and ``bm``.
    """


def _download_ff_historical_be(url: str) -> pd.DataFrame:
    """The raw table of the historical book-equity zip, after up to three attempts.

    An attempt fails when the download raises or what arrives is not a zip
    with a readable table. The pauses between attempts are
    ``FF_HISTORICAL_BE_PAUSES``.
    """
    import io
    import time
    import zipfile
    from urllib.request import urlopen

    attempts = len(FF_HISTORICAL_BE_PAUSES) + 1
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(url, timeout=30) as resp:  # noqa: S310
                zip_bytes = resp.read()
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                name = zf.namelist()[0]
                with zf.open(name) as f:
                    return pd.read_csv(f, sep=r"\s+", header=None, engine="python")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < attempts:
                pause = FF_HISTORICAL_BE_PAUSES[attempt - 1]
                LOGGER.warning(
                    "Download of FF historical BE failed (attempt %d of %d): %s. "
                    "Trying again in %g seconds.",
                    attempt, attempts, exc, pause,
                )
                time.sleep(pause)
    raise HistoricalBookEquityError(
        f"Could not download the Davis-Fama-French historical book equity from "
        f"{url} in {attempts} attempts (last error: {last_exc}). The build stops "
        "here, because without the file book equity before Compustat's coverage "
        "is missing. Run the command again when the site answers, or place the "
        f"unzipped file as {_FF_HISTORICAL_BE_LOCAL.as_posix()} under the folder "
        "the command is run from."
    ) from last_exc


def fetch_ff_historical_be(config: AssayConfig) -> pd.DataFrame:
    """
    Download historical book equity from Ken French's website (1926-2001).

    MATLAB lines 155-203. The file contains pre-COMPUSTAT book equity values
    compiled by Davis, Fama, and French (2000). These fill in BE for years
    before COMPUSTAT coverage begins.

    Prefers a local copy under ``AssayingAnomalies-MATLAB/Data/FF/`` (or
    ``Data/FF/``) when present so the Python rebuild matches the MATLAB
    vintage used to produce the parity reference bundle.

    Without a local copy the file is downloaded, in up to three attempts
    (``FF_HISTORICAL_BE_PAUSES`` apart).

    Returns
    -------
    pd.DataFrame
        Columns: permno, date (June month-end YYYY-06-30), be.
        Only includes non-NaN observations within the config sample window.

    Raises
    ------
    HistoricalBookEquityError
        If there is no local copy and every download attempt fails. The
        message names the URL.
    """

    def _parse_dff_text(raw: pd.DataFrame) -> pd.DataFrame:
        # Format: PERMNO  FirstYr  LastYr  BE_1926  BE_1927 ... BE_2001
        permno_col = raw.columns[0]
        be_cols = list(raw.columns[3:])
        years = list(range(1926, 1926 + len(be_cols)))
        rows = []
        for _, row in raw.iterrows():
            perm = int(row[permno_col])
            for i, yr in enumerate(years):
                if yr < config.sample_start or yr > config.sample_end:
                    continue
                val = row.iloc[3 + i]
                if pd.notna(val) and abs(float(val) - (-99.99)) > 0.01 and val != -999:
                    # DFF's "BE_YYYY" column stores BE available at June YYYY.
                    # Matches MATLAB: ffDates = (100 * (1926:2001) + 6)'.
                    date = pd.Timestamp(f"{yr}-06-30")
                    rows.append({"permno": perm, "date": date, "be": float(val)})
        return pd.DataFrame(rows)

    # Prefer local DFF text (matched MATLAB vintage) over a fresh download.
    local_candidates = [
        Path("AssayingAnomalies-MATLAB") / "Data" / "FF" / "DFF_BE_With_Nonindust.txt",
        _FF_HISTORICAL_BE_LOCAL,
    ]
    for local in local_candidates:
        if local.exists():
            LOGGER.info("Loading FF historical book equity from local file %s", local)
            note_input(local, "DFF historical book equity")
            raw = pd.read_csv(local, sep=r"\s+", header=None, engine="python")
            result = _parse_dff_text(raw)
            LOGGER.info(
                "FF historical BE: %d observations for sample %d-%d",
                len(result), config.sample_start, config.sample_end,
            )
            return result

    url = FF_HISTORICAL_BE_URL

    LOGGER.info("Downloading FF historical book equity from %s", url)
    note_input(url, "DFF historical book equity")
    raw = _download_ff_historical_be(url)

    result = _parse_dff_text(raw)
    LOGGER.info("FF historical BE: %d observations for sample %d-%d",
                len(result), config.sample_start, config.sample_end)
    return result


# Columns of the cleaned CCM link (``clean_ccm_link``), the ``ccm_link`` table.
CCM_LINK_COLUMNS = (
    "gvkey", "permno", "permco", "linkdt", "linkenddt", "linktype", "linkprim",
)

# dtypes of an empty cleaned link, so DuckDB can type every column of the table.
_CCM_LINK_EMPTY_DTYPES = {
    "gvkey": "string",
    "permno": "int64",
    "permco": "Int64",
    "linkdt": "datetime64[ns]",
    "linkenddt": "datetime64[ns]",
    "linktype": "string",
    "linkprim": "string",
}


def _empty_ccm_link() -> pd.DataFrame:
    return pd.DataFrame({
        col: pd.Series(dtype=dtype) for col, dtype in _CCM_LINK_EMPTY_DTYPES.items()
    })


def clean_ccm_link(
    raw: pd.DataFrame,
    config: AssayConfig | None = None,
) -> pd.DataFrame:
    """
    Clean the raw CCM link history (crsp.ccmxpf_lnkhist) into the ``ccm_link`` table.

    Lower-cases the column names, keeps the primary link types (LC and LU)
    when ``linktype`` is present (and not all missing), renames ``lpermno``/``lpermco`` to
    ``permno``/``permco``, parses the link dates, closes open links
    (missing ``linkenddt``) at the end of the sample year and drops links
    without a permno. Cleaning a cleaned link returns it unchanged.

    Parameters
    ----------
    raw : pd.DataFrame
        Raw CCM link history with gvkey, lpermno, linkdt, linkenddt and
        usually linktype, lpermco, linkprim.
    config : AssayConfig, optional
        Configuration whose ``sample_end`` closes open links; the default
        configuration when omitted. A ``"latest"`` sample end means the year
        the database's last build resolved it to
        (:meth:`AssayConfig.resolved_sample_end`).

    Returns
    -------
    pd.DataFrame
        Columns ``CCM_LINK_COLUMNS`` (those absent from ``raw`` are all
        missing), one row per usable link, ``permno`` int64.
    """
    if config is None:
        config = AssayConfig()
    link = raw.copy()
    link.columns = [str(c).lower() for c in link.columns]

    if link.empty or "gvkey" not in link.columns:
        LOGGER.warning("Link table is empty or missing 'gvkey'; returning an empty link")
        return _empty_ccm_link()

    link = link.rename(columns={"lpermno": "permno", "lpermco": "permco"})
    if "permno" not in link.columns:
        LOGGER.warning("Link table has no 'lpermno'; returning an empty link")
        return _empty_ccm_link()

    link["gvkey"] = link["gvkey"].astype(str)

    # Keep only LC and LU link types (primary links). An all-missing linktype
    # is what cleaning a link without the column leaves behind, so it counts
    # as absent; that keeps the cleaning idempotent.
    if "linktype" in link.columns and link["linktype"].notna().any():
        link = link[link["linktype"].isin(["LC", "LU"])].copy()
        LOGGER.info("After link type filter (LC/LU): %d link rows", len(link))

    for col in CCM_LINK_COLUMNS:
        if col not in link.columns:
            link[col] = pd.NA
    link = link[list(CCM_LINK_COLUMNS)]

    # Dates may be stored as strings; an open link (missing linkenddt) runs
    # to the end of the sample.
    link["linkdt"] = pd.to_datetime(link["linkdt"], errors="coerce")
    link["linkenddt"] = pd.to_datetime(link["linkenddt"], errors="coerce")
    end_year = config.resolved_sample_end()
    link["linkenddt"] = link["linkenddt"].fillna(pd.Timestamp(f"{end_year}-12-31"))

    link = link[link["permno"].notna()].copy()
    link["permno"] = link["permno"].astype(np.int64)
    link["permco"] = pd.to_numeric(link["permco"], errors="coerce").astype("Int64")
    if link.empty:
        return _empty_ccm_link()
    return link.reset_index(drop=True)


def merge_on_link(
    df: pd.DataFrame,
    link: pd.DataFrame,
    *,
    date_col: str = "datadate",
    gvkey_col: str = "gvkey",
) -> pd.DataFrame:
    """
    Attach CRSP permnos to gvkey-keyed data through a cleaned CCM link.

    A row of ``df`` takes the permno of every link of its gvkey whose window
    holds its date (``linkdt <= date <= linkenddt``, both ends inclusive);
    rows no link covers are dropped. The link's own columns do not appear in
    the result.

    Parameters
    ----------
    df : pd.DataFrame
        Data keyed by gvkey and a date, e.g. Compustat filings or your own
        firm-level series.
    link : pd.DataFrame
        Cleaned link: the ``ccm_link`` table or ``clean_ccm_link`` output.
    date_col : str, default "datadate"
        Column of ``df`` the link window is checked against.
    gvkey_col : str, default "gvkey"
        Column of ``df`` holding the gvkey.

    Returns
    -------
    pd.DataFrame
        The linked rows of ``df`` plus an int ``permno`` column.
    """
    LOGGER.info("Linking to CRSP: data=%d rows, link=%d rows", len(df), len(link))

    # Standardize column names to lowercase
    df = df.copy()
    df.columns = df.columns.str.lower()
    date_col = date_col.lower()
    gvkey_col = gvkey_col.lower()

    if link.empty:
        LOGGER.warning("Link table is empty; returning empty DataFrame")
        return pd.DataFrame(columns=list(df.columns) + ["permno"])

    link = link[["gvkey", "permno", "linkdt", "linkenddt"]].rename(
        columns={"gvkey": gvkey_col}
    )
    link[gvkey_col] = link[gvkey_col].astype(str)
    df[gvkey_col] = df[gvkey_col].astype(str)
    df[date_col] = pd.to_datetime(df[date_col])

    merged = df.merge(link, on=gvkey_col, how="left")
    LOGGER.info("After merge with link: %d rows", len(merged))

    # Filter: the date must be within the link date range
    valid_link = (
        (merged[date_col] >= merged["linkdt"]) &
        (merged[date_col] <= merged["linkenddt"])
    )
    merged = merged[valid_link].copy()
    merged["permno"] = merged["permno"].astype(int)
    LOGGER.info("After link date filter: %d rows", len(merged))

    return merged.drop(columns=["linkdt", "linkenddt"])


def link_compustat_to_crsp(
    funda: pd.DataFrame,
    link: pd.DataFrame,
    config: AssayConfig | None = None,
) -> pd.DataFrame:
    """
    Link COMPUSTAT data to CRSP permnos using the CCM link table.

    ``merge_on_link(funda, clean_ccm_link(link, config))``; ``link`` may be raw
    (crsp.ccmxpf_lnkhist) or already clean.

    Parameters
    ----------
    funda : pd.DataFrame
        COMPUSTAT fundamentals with gvkey, datadate, and accounting variables.
    link : pd.DataFrame
        CCM link history table, raw or cleaned.
    config : AssayConfig, optional
        Configuration with sample window.

    Returns
    -------
    pd.DataFrame
        COMPUSTAT data with permno column and filtered to valid links.
    """
    return merge_on_link(funda, clean_ccm_link(link, config))


def align_annual_to_monthly(
    funda_linked: pd.DataFrame,
    config: AssayConfig,
) -> pd.DataFrame:
    """
    Align annual COMPUSTAT data to monthly calendar.

    Following Fama-French convention, fiscal year-end data becomes available
    at the end of June of the following year (6-month lag to ensure availability).

    Parameters
    ----------
    funda_linked : pd.DataFrame
        COMPUSTAT data with permno and datadate.
    config : AssayConfig
        Configuration with sample window.

    Returns
    -------
    pd.DataFrame
        Data with 'date' column (month-end) replacing datadate.
    """
    df = funda_linked.copy()

    # Extract fiscal year from datadate
    df["fyear"] = pd.to_datetime(df["datadate"]).dt.year

    # Align to June of the following year (YYYYMM format then convert to month-end)
    # E.g., FY2020 data (ending Dec 2020) → available June 2021
    df["date"] = pd.to_datetime(
        (df["fyear"] + 1).astype(str) + "-06-30"
    ) + pd.offsets.MonthEnd(0)

    # Handle companies with fiscal year ends that aren't December
    # For simplicity, we use June of year after fiscal year end
    # More sophisticated handling would use actual month of FYE + 6 months

    # Handle duplicate permno-dates by keeping the later fiscal year
    df = df.sort_values(["permno", "date", "datadate"])
    df = df.drop_duplicates(subset=["permno", "date"], keep="last")

    LOGGER.info("After monthly alignment: %d rows", len(df))
    return df


def compute_derived_variables(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute COMPUSTAT-derived variables.

    Adds:
    - be: Book equity

    Note: ``fin_firm`` is NOT computed here. MATLAB builds FinFirms from the
    CRSP ``SIC`` panel (``makeCOMPUSTATDerivedVariables.m:215-216``), so it is
    assigned from ``ccm_panel.sic`` inside ``merge_compustat_crsp``.
    """
    result = df.copy()

    # Book equity
    result["be"] = compute_book_equity(result)

    # Annual derived variables (MATLAB makeCOMPUSTATDerivedVariables.m)
    result["oc"] = compute_operating_costs(result)
    result["d"] = compute_total_debt(result)
    result["inv_capital"] = compute_investment(result)
    result["fcf"] = compute_free_cash_flow(result)
    result["div"] = compute_dividends(result)
    result["wcap"] = compute_working_capital(result)
    result["cfo"] = compute_cfo(result)

    LOGGER.info("Computed derived variables: be, oc, d, inv_capital, fcf, div, wcap, cfo")
    return result


def formation_june(dates) -> pd.Series:
    """June month-end that opens the annual window containing each date.

    A record available at the end of June ``y`` is in force from June ``y``
    through May ``y + 1``: dates in June-December ``y`` map to June ``y`` and
    dates in January-May ``y`` to June ``y - 1``. The panel build no longer
    uses it (annual columns are stored on the June row only); it is kept for
    callers that need the window of a date.
    """
    d = pd.to_datetime(pd.Series(dates))
    year = d.dt.year - (d.dt.month < 6).astype(np.int64)
    return pd.to_datetime(pd.DataFrame({"year": year, "month": 6, "day": 30}))


def attach_annual_records(panel: pd.DataFrame, records: pd.DataFrame) -> pd.DataFrame:
    """
    Left-join each annual record to the panel row of its availability June.

    ``records`` has one row per ``(permno, date)``, where ``date`` is the June
    month-end the record became available; every other column is carried.
    A record lands on the panel row with the same ``permno`` and ``date`` and
    nowhere else: the record columns are NaN in the other eleven months. This
    is MATLAB's June-only annual matrix. ``fill_months`` (``aa.fill_months``)
    spreads a column over the record's window, June through the following May.

    Records are attached whole, so every value on a row comes from one record
    and a field missing from it stays missing. A stock with no panel row in
    the June has no values from that record (a filled column then stays empty
    until the stock's next June). Returns one row per panel row, in panel order.
    """
    avail = pd.to_datetime(records["date"])
    bad = ~(avail.dt.is_month_end & (avail.dt.month == 6) & (avail == avail.dt.normalize()))
    if bad.any():
        raise ValueError(
            "annual records must become available at a June month-end; got "
            f"{int(bad.sum())} other date(s), e.g. {avail[bad].iloc[0]}"
        )
    if records.duplicated(subset=["permno", "date"]).any():
        raise ValueError("annual records have duplicate (permno, date) keys")

    keyed = records.rename(columns={"date": "_avail"})
    keyed["_avail"] = avail.to_numpy()
    out = panel.assign(_avail=pd.to_datetime(panel["date"]).to_numpy())
    out = out.merge(keyed, on=["permno", "_avail"], how="left", validate="many_to_one")
    return out.drop(columns=["_avail"])


def apply_dff_book_equity(records: pd.DataFrame, ff_be: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Davis-Fama-French historical book equity to June-aligned annual records.

    ``records`` are the Compustat filings keyed by ``(permno, date)`` at their
    availability June; ``ff_be`` has ``permno``, ``date`` (the June the DFF
    ``BE_YYYY`` column becomes available) and ``be``.

    - **Precedence.** A DFF value replaces Compustat ``be`` for the same
      permno-June, finite or not. MATLAB makeCOMPUSTATDerivedVariables.m:199
      assigns ``BE(rowsInd, c) = ffData(i, indBE)'`` without checking the
      Compustat value; filling only NaNs would keep Compustat values FF corrected.
    - **Source.** ``be_source`` is ``"compustat"`` or ``"dff"`` (NaN when ``be``
      is missing) and ``be_avail_date`` is the June the value became available.
    - **Window.** A permno-June with DFF book equity but no Compustat filing
      becomes a record of its own holding only ``be``, so the value is valid
      for the same June-to-May window as any annual record. It carries no
      Compustat fields, so it neither refreshes nor extends them, and its
      ``comp_datadate`` / ``comp_avail_date`` stay NaT.

    ``fyear`` of an appended row is the June year minus one, so book-to-market
    divides by the preceding December's market equity.
    """
    out = records.copy()
    has_be = out["be"].notna() if "be" in out.columns else pd.Series(False, index=out.index)
    out["be_source"] = pd.Series(np.where(has_be, "compustat", None), index=out.index, dtype=object)
    out["be_avail_date"] = pd.to_datetime(out["date"]).where(has_be)
    if ff_be is None or ff_be.empty:
        return out

    ff = ff_be[["permno", "date", "be"]].copy()
    ff["date"] = pd.to_datetime(ff["date"]) + pd.offsets.MonthEnd(0)
    ff["permno"] = ff["permno"].astype(np.int64)
    ff["be"] = pd.to_numeric(ff["be"], errors="coerce")
    ff = ff[ff["be"].notna()].drop_duplicates(subset=["permno", "date"], keep="last")

    keys = pd.MultiIndex.from_frame(out[["permno", "date"]].astype({"permno": np.int64}))
    ff_keys = pd.MultiIndex.from_frame(ff[["permno", "date"]])
    ff_be_by_key = pd.Series(ff["be"].to_numpy(), index=ff_keys)

    patched = keys.isin(ff_keys)
    out.loc[patched, "be"] = ff_be_by_key.reindex(keys[patched]).to_numpy()
    out.loc[patched, "be_source"] = "dff"
    out.loc[patched, "be_avail_date"] = pd.to_datetime(out.loc[patched, "date"])

    new = ff[~ff_keys.isin(keys)].copy()
    new["fyear"] = new["date"].dt.year - 1
    new["be_source"] = "dff"
    new["be_avail_date"] = new["date"]
    if not new.empty:
        out = pd.concat([out, new], ignore_index=True)
    LOGGER.info(
        "FF historical BE: replaced %d Compustat values, added %d DFF-only records",
        int(patched.sum()), len(new),
    )
    return out


#: Raw annual fields ``makeFFTcosts.m`` reads straight off the June matrices.
FF_TCOST_RAW_COLS = ("at", "revt", "cogs", "xsga", "xint")


def build_june_annual_panel(
    funda: pd.DataFrame,
    link: pd.DataFrame,
    config: AssayConfig,
    *,
    columns: Sequence[str] = FF_TCOST_RAW_COLS,
    with_book_equity: bool = True,
) -> pd.DataFrame:
    """June-only annual accounting panel, the shape MATLAB's matrices have.

    ``merge_compustat_crsp`` puts each June record on the panel row of that
    June, so a record of a stock with no panel row that month is not on the
    panel. The FF factor trading costs (``makeFFTcosts.m``) read the June
    matrices built here from the filings: every record is kept, and a
    firm-year gap is NaN, so no stale prior year enters the 2x3 sorts.

    Returns
    -------
    pd.DataFrame
        MultiIndex (date, permno) at June month-ends, with ``columns`` plus
        ``be`` (Compustat book equity, overwritten/extended by the
        Davis-Fama-French historical series exactly as the panel build does).
    """
    linked = link_compustat_to_crsp(funda, link, config)
    if linked.empty:
        return pd.DataFrame(columns=["date", "permno", *columns]).set_index(
            ["date", "permno"]
        )

    aligned = align_annual_to_monthly(linked, config)
    keep = [c for c in columns if c in aligned.columns]
    out = aligned[["permno", "date", *keep]].copy()

    if with_book_equity:
        out["be"] = compute_book_equity(aligned)
        # A failed download stops the build (HistoricalBookEquityError).
        ff_be = fetch_ff_historical_be(config)
        if not ff_be.empty:
            ff_be = ff_be.copy()
            ff_be["date"] = pd.to_datetime(ff_be["date"]) + pd.offsets.MonthEnd(0)
            ff_be["permno"] = ff_be["permno"].astype(int)
            out = out.merge(
                ff_be.rename(columns={"be": "be_ff"}),
                on=["permno", "date"],
                how="outer",
            )
            patch = out["be_ff"].notna()
            out.loc[patch, "be"] = out.loc[patch, "be_ff"]
            out = out.drop(columns=["be_ff"])

    out["date"] = pd.to_datetime(out["date"]) + pd.offsets.MonthEnd(0)
    out = out[out["date"].dt.month == 6]
    out = out.drop_duplicates(subset=["permno", "date"], keep="last")
    LOGGER.info(
        "June-only annual panel: %d rows, %s",
        len(out),
        {c: int(out[c].notna().sum()) for c in out.columns if c not in ("permno", "date")},
    )
    return out.set_index(["date", "permno"]).sort_index()


def merge_compustat_crsp(
    funda: pd.DataFrame,
    link: pd.DataFrame,
    ccm_panel: pd.DataFrame,
    config: AssayConfig,
    *,
    fundq: pd.DataFrame | None = None,
    extra_annual: Sequence[str] = (),
    extra_quarterly: Sequence[str] = (),
) -> pd.DataFrame:
    """
    Full COMPUSTAT-CRSP merge pipeline.

    1. Link COMPUSTAT to CRSP via CCM
    2. Align annual data to the June after the fiscal year
    3. Compute derived variables (BE, OC, D, etc.) on each filing
    4. Compute book-to-market using lagged market equity from ccm_panel
    5. Attach each annual record, whole and with its source dates, to the
       panel row of the June in which it becomes available; the annual
       columns are NaN in the other months (``attach_annual_records``)
    6. If fundq provided, compute quarterly derived variables and merge

    Parameters
    ----------
    funda : pd.DataFrame
        Raw COMPUSTAT annual fundamentals.
    link : pd.DataFrame
        CCM link history table, raw or cleaned (``clean_ccm_link``).
    ccm_panel : pd.DataFrame
        Existing CRSP monthly panel with me (market equity).
    config : AssayConfig
        Configuration.
    fundq : pd.DataFrame, optional
        Raw COMPUSTAT quarterly fundamentals.
    extra_annual, extra_quarterly : sequence of str
        Raw columns of ``funda`` / ``fundq`` added by ``aa add-compustat-vars``
        (recorded in the database). They are carried onto the panel like
        ``ANNUAL_VALUE_COLS`` (on the June row only) and the raw quarterly
        columns (RDQ-placed, forward-filled ``QUARTERLY_FILL_HORIZON`` months)
        and replaced on every run. Empty: the panel is built exactly as without
        them.

    Returns
    -------
    pd.DataFrame
        Updated ccm_panel with COMPUSTAT-derived columns.
    """
    LOGGER.info("Starting COMPUSTAT-CRSP merge")
    annual_cols = (*ANNUAL_VALUE_COLS, *(c for c in extra_annual if c not in ANNUAL_VALUE_COLS))
    q_ffill_cols = (
        *QUARTERLY_FFILL_VARS, *(c for c in extra_quarterly if c not in QUARTERLY_FFILL_VARS)
    )
    q_panel_cols = (
        *QUARTERLY_DERIVED_COLS,
        *(c for c in extra_quarterly if c not in QUARTERLY_DERIVED_COLS),
    )

    # Step 1: Link to CRSP (the link is cleaned once, for annual and quarterly)
    link = clean_ccm_link(link, config)
    linked = merge_on_link(funda, link)

    if linked.empty:
        LOGGER.warning("No COMPUSTAT-CRSP links found; returning original panel")
        return ccm_panel

    # Step 2: Align to monthly calendar
    aligned = align_annual_to_monthly(linked, config)

    # Step 3: Compute derived variables
    derived = compute_derived_variables(aligned)
    derived["comp_datadate"] = pd.to_datetime(derived["datadate"])
    derived["comp_avail_date"] = pd.to_datetime(derived["date"])

    # Step 3b: Davis-Fama-French historical book equity (pre-COMPUSTAT era).
    # A failed download stops the build (HistoricalBookEquityError).
    ff_be = fetch_ff_historical_be(config)
    derived = apply_dff_book_equity(derived, ff_be)

    # Step 4: Compute book-to-market
    # BM = BE / ME(Dec of prior year)
    # Following FF: use ME from 6 months before the June alignment date
    # So for June 2021 alignment (FY2020 data), use ME from Dec 2020

    # Ensure ccm_panel has proper date index
    panel = ccm_panel.copy()
    if "date" in panel.columns:
        panel["date"] = pd.to_datetime(panel["date"])

    # Get December ME for each permno-year
    panel["year"] = panel["date"].dt.year
    panel["month"] = panel["date"].dt.month
    dec_me = panel[panel["month"] == 12][["permno", "year", "me"]].copy()
    dec_me = dec_me.rename(columns={"me": "me_dec", "year": "dec_year"})

    # For June t, we need December t-1 ME
    derived["dec_year"] = derived["fyear"]  # FY2020 → Dec 2020 ME
    derived = derived.merge(
        dec_me[["permno", "dec_year", "me_dec"]],
        on=["permno", "dec_year"],
        how="left",
    )

    # Compute BM
    derived["bm"] = derived["be"] / derived["me_dec"]
    # Some keep negative BM, some don't - we keep them for now
    LOGGER.info("Computed book-to-market for %d firm-years", derived["bm"].notna().sum())

    # Step 5: Attach annual records to panel months.
    # fin_firm is assigned from CRSP sic after the merge (not from Compustat).
    value_cols = [c for c in annual_cols if c in derived.columns]
    record_cols = value_cols + list(ANNUAL_PROVENANCE_COLS)

    # Drop duplicates before merge (shouldn't happen but defensive)
    records = derived[["permno", "date", *record_cols]].drop_duplicates(
        subset=["permno", "date"]
    )

    # Drop every pre-existing annual column from the panel so a rebuild
    # replaces them, including columns this extract no longer supplies and the
    # provenance of the previous run. A same-named column left in place would
    # either shadow the new one or come back with a merge suffix.
    stale = [c for c in (*annual_cols, *ANNUAL_PROVENANCE_COLS) if c in panel.columns]
    if stale:
        LOGGER.info(
            "Dropping %d stale Compustat columns before merge: %s",
            len(stale), stale,
        )
        panel = panel.drop(columns=stale)

    # Step 6: each record goes, whole, on the panel row of its availability
    # June. The other months are NaN; nothing is carried forward here.
    result = attach_annual_records(panel, records)
    result = result.sort_values(["permno", "date"])
    n_on_panel = int((result["comp_avail_date"].notna() | result["be_avail_date"].notna()).sum())
    LOGGER.info(
        "Attached %d of %d annual records to their June rows (June-only layout; "
        "%d record(s) of stocks with no panel row in that June are not on the panel)",
        n_on_panel, len(records), len(records) - n_on_panel,
    )

    # FinFirms from CRSP SIC (MATLAB makeCOMPUSTATDerivedVariables.m:215-216).
    # MATLAB: FinFirms = (SIC >= 6000).*(SIC <= 6999) with NaN SIC → 0.
    if "fin_firm" in result.columns:
        result = result.drop(columns=["fin_firm"])
    if "sic" in result.columns:
        sic = pd.to_numeric(result["sic"], errors="coerce")
        result["fin_firm"] = ((sic >= 6000) & (sic <= 6999)).fillna(False).astype(int)
    else:
        result["fin_firm"] = 0
    value_cols = list(value_cols) + ["fin_firm"]
    LOGGER.info("Assigned fin_firm from CRSP sic (%d financial-firm months)",
                int((result["fin_firm"] == 1).sum()))

    # Clean up temporary columns
    result = result.drop(columns=["year", "month", "dec_year"], errors="ignore")

    # Step 7: Quarterly derived variables (if fundq provided)
    quarterly_cols: list[str] = []
    if fundq is not None and not fundq.empty:
        LOGGER.info("Processing quarterly COMPUSTAT data: %d rows", len(fundq))

        # Stale-column guard: this run's quarterly extract replaces every
        # quarterly column, including when none of it links or lands on the
        # panel calendar. Otherwise the previous run's values would survive.
        q_stale = [c for c in q_panel_cols if c in result.columns]
        if q_stale:
            LOGGER.info(
                "Dropping %d stale quarterly Compustat columns before merge: %s",
                len(q_stale), q_stale,
            )
            result = result.drop(columns=q_stale)

        # Link quarterly data to CRSP via same CCM link table
        fundq_linked = merge_on_link(fundq, link)

        if not fundq_linked.empty:
            result["permno"] = result["permno"].astype(np.int64)
            result["date"] = pd.to_datetime(result["date"])
            result = result.sort_values(["permno", "date"]).reset_index(drop=True)

            # MATLAB derives the quarterly variables from dense (nMonths x
            # nStocks) matrices whose raw inputs are already forward-filled onto
            # the CRSP calendar, so build that grid first and derive on it.
            monthly_q = build_quarterly_monthly_panel(
                fundq_linked,
                result["date"].unique(),
                permnos=result["permno"].unique(),
                variables=q_ffill_cols,
            )

            if not monthly_q.empty:
                qderived = compute_quarterly_derived(monthly_q)
                quarterly_cols = [c for c in q_panel_cols if c in qderived.columns]

                aligned = (
                    qderived[["permno", "date", *quarterly_cols]]
                    .drop_duplicates(subset=["permno", "date"], keep="last")
                    .set_index(["permno", "date"])
                    .reindex(pd.MultiIndex.from_frame(result[["permno", "date"]]))
                )
                for col in quarterly_cols:
                    result[col] = aligned[col].to_numpy()

                # amonth is a dense 0/1 matrix in MATLAB: months with no
                # announcement are 0, not missing.
                if "amonth" in quarterly_cols:
                    result["amonth"] = result["amonth"].fillna(0.0)

                LOGGER.info("Merged quarterly derived variables: %s", quarterly_cols)

    all_cols = value_cols + quarterly_cols
    LOGGER.info(
        "Merged COMPUSTAT into ccm_panel: %d rows, added columns: %s",
        len(result),
        [c for c in all_cols if c in result.columns],
    )

    return result


def _panel_keys(panel_keys: pd.DataFrame) -> pd.DataFrame:
    keys = panel_keys[["permno", "date"]].copy()
    keys["permno"] = keys["permno"].astype(np.int64)
    keys["date"] = pd.to_datetime(keys["date"])
    return keys.reset_index(drop=True)


def _numeric_columns(frame: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    for col in columns:
        frame[col] = pd.to_numeric(frame[col], errors="coerce").astype("float64")
    return frame


def align_extra_annual(
    funda_extra: pd.DataFrame,
    link_clean: pd.DataFrame,
    panel_keys: pd.DataFrame,
    config: AssayConfig,
    columns: Sequence[str],
) -> pd.DataFrame:
    """
    Align extra annual Compustat columns to the panel months, like the panel's own.

    The same steps ``merge_compustat_crsp`` takes for ``ANNUAL_VALUE_COLS``:
    link (``link_compustat_to_crsp``), date each filing at the June after its
    fiscal year (``align_annual_to_monthly``) and put it on the panel row of
    that June (``attach_annual_records``). Every other month is NaN.

    Parameters
    ----------
    funda_extra : pd.DataFrame
        Raw funda rows: ``gvkey``, ``datadate`` and ``columns``.
    link_clean : pd.DataFrame
        The CCM link, raw or cleaned (the ``ccm_link`` table).
    panel_keys : pd.DataFrame
        ``permno`` and ``date`` of every ``ccm_panel`` row.
    config : AssayConfig
        Configuration (closes open links when ``link_clean`` is raw).
    columns : sequence of str
        The columns to align.

    Returns
    -------
    pd.DataFrame
        ``permno``, ``date`` and ``columns`` (float64), one row per row of
        ``panel_keys``, in its order.
    """
    columns = list(columns)
    keys = _panel_keys(panel_keys)
    records = pd.DataFrame({
        "permno": pd.Series(dtype="int64"), "date": pd.Series(dtype="datetime64[ns]"),
        **{c: pd.Series(dtype="float64") for c in columns},
    })
    if not funda_extra.empty:
        linked = link_compustat_to_crsp(funda_extra, link_clean, config)
        if not linked.empty:
            aligned = align_annual_to_monthly(linked, config)
            records = aligned[["permno", "date", *columns]].copy()
            records["permno"] = records["permno"].astype(np.int64)
    out = attach_annual_records(keys, _numeric_columns(records, columns))
    return _numeric_columns(out[["permno", "date", *columns]], columns)


def align_extra_quarterly(
    fundq_extra: pd.DataFrame,
    link_clean: pd.DataFrame,
    panel_keys: pd.DataFrame,
    config: AssayConfig,
    columns: Sequence[str],
) -> pd.DataFrame:
    """
    Align extra quarterly Compustat columns to the panel months, like ``ibq``.

    Linked through the CCM link, each quarter is placed at the end of its RDQ
    month and every column is forward-filled on its own until
    ``QUARTERLY_FILL_HORIZON`` months past its last announcement
    (``build_quarterly_monthly_panel(variables=columns)``), as for the raw
    quarterly columns ``merge_compustat_crsp`` carries.

    Parameters
    ----------
    fundq_extra : pd.DataFrame
        Raw fundq rows: ``gvkey``, ``datadate``, ``rdq`` and ``columns``.
    link_clean, panel_keys, config, columns
        As for :func:`align_extra_annual`.

    Returns
    -------
    pd.DataFrame
        ``permno``, ``date`` and ``columns`` (float64), one row per row of
        ``panel_keys``, in its order.
    """
    columns = list(columns)
    keys = _panel_keys(panel_keys)
    out = keys.copy()
    for col in columns:
        out[col] = np.nan
    if fundq_extra.empty:
        return out
    linked = link_compustat_to_crsp(fundq_extra, link_clean, config)
    if linked.empty:
        return out
    monthly = build_quarterly_monthly_panel(
        linked,
        keys["date"].unique(),
        permnos=keys["permno"].unique(),
        variables=columns,
    )
    if monthly.empty:
        return out
    present = [c for c in columns if c in monthly.columns]
    monthly["permno"] = monthly["permno"].astype(np.int64)
    monthly["date"] = pd.to_datetime(monthly["date"])
    aligned = (
        monthly[["permno", "date", *present]]
        .drop_duplicates(subset=["permno", "date"], keep="last")
        .set_index(["permno", "date"])
        .reindex(pd.MultiIndex.from_frame(keys))
    )
    for col in present:
        out[col] = aligned[col].to_numpy()
    return _numeric_columns(out, columns)


def build_placeholder_panel(config: AssayConfig) -> pd.DataFrame:
    """
    Create an empty monthly-aligned COMPUSTAT panel.
    (Legacy placeholder function)
    """
    data = {
        "date": pd.Series(dtype="datetime64[ns]"),
        "permno": pd.Series(dtype="int64"),
        "gvkey": pd.Series(dtype="str"),
        "at": pd.Series(dtype="float64"),
        "be": pd.Series(dtype="float64"),
        "bm": pd.Series(dtype="float64"),
    }
    return pd.DataFrame(data)


__all__ = [
    "compute_book_equity",
    "compute_operating_costs",
    "compute_total_debt",
    "compute_investment",
    "compute_free_cash_flow",
    "compute_dividends",
    "compute_working_capital",
    "compute_cfo",
    "compute_quarterly_book_equity",
    "compute_quarterly_gross_profit",
    "compute_quarterly_roa",
    "compute_sue",
    "compute_droe",
    "compute_sue2",
    "compute_droa",
    "compute_amonth",
    "compute_quarterly_derived",
    "fetch_ff_historical_be",
    "HistoricalBookEquityError",
    "CCM_LINK_COLUMNS",
    "clean_ccm_link",
    "merge_on_link",
    "link_compustat_to_crsp",
    "align_annual_to_monthly",
    "compute_derived_variables",
    "apply_dff_book_equity",
    "ANNUAL_LAYOUT_KEY",
    "ANNUAL_LAYOUT_JUNE",
    "formation_june",
    "attach_annual_records",
    "merge_compustat_crsp",
    "align_extra_annual",
    "align_extra_quarterly",
    "build_placeholder_panel",
]
