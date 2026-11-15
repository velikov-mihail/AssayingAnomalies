"""
Transaction cost estimation: low-frequency effective spread measures.

MATLAB equivalents:
- makeCorwinSchultz.m: High-low spread (Corwin & Schultz, JF 2012)
- makeAbdiRanaldi.m: Close-high-low spread (Abdi & Ranaldo, RFS 2017)
- makeKyleObizhaeva.m: Volume-over-volatility (Kyle & Obizhaeva, ECTA 2016)
- makeGibbs.m: Hasbrouck Gibbs (Hasbrouck, JF 2009)
- makeHighFreqEffSpreads.m: TAQ/ISSM effective spreads
- fillMissingTcosts.m: Gap-filling via nearest-neighbor matching
- makeTradingCosts.m: Orchestration, winsorization, combination

References:
  Corwin, S. and P. Schultz, 2012, JF, 67(2): 719-760
  Abdi, F. and A. Ranaldo, 2017, RFS, 30(12): 4437-4480
  Kyle, A. and A. Obizhaeva, 2016, Econometrica, 84(4): 1345-1404
  Hasbrouck, J., 2009, JF, 64(3): 1445-1477
  Chen, A. and M. Velikov, 2021, JFQA
  Novy-Marx, R. and M. Velikov, 2016, RFS, 29(1): 104-147
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from ..ingest.gibbs import gibbs_manual_hint
from ..provenance import MissingInputError
from ..run_manifest import note_input

LOGGER = logging.getLogger("assayinganomalies.transforms.tcosts")


# ---------------------------------------------------------------------------
# Corwin-Schultz high-low spread estimator
# ---------------------------------------------------------------------------

def _cs_spread(
    hi: np.ndarray, lo: np.ndarray, lhi: np.ndarray, llo: np.ndarray
) -> np.ndarray:
    """
    Corwin-Schultz daily spread from (adjusted) high/low and lagged values.

    Accepts float64 or complex128 arrays. With complex inputs, MATLAB's
    propagation of complex logs (negative ratios from bad ticks) is
    reproduced; relational gates use real parts, matching MATLAB semantics.
    """
    is_complex = np.iscomplexobj(hi)
    nan_val = complex(np.nan, np.nan) if is_complex else np.nan
    re = (lambda x: x.real) if is_complex else (lambda x: x)

    # Equation (7): beta
    beta = np.log(hi / lo) ** 2 + np.log(lhi / llo) ** 2
    beta[(re(hi) <= 0) | (re(lo) <= 0)] = nan_val

    # Equation (10): gamma
    min_lo = np.minimum(lo, llo)
    gamma = np.log(np.maximum(hi, lhi) / min_lo) ** 2
    gamma[re(min_lo) <= 0] = nan_val

    const = 3 - 2 * np.sqrt(2)
    # Equation (18) / (14)
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / const - np.sqrt(gamma / const)
    s = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))

    # Section II.C: set negative spreads to zero (real-part comparison)
    s[re(s) < 0] = 0
    return s


def compute_corwin_schultz(daily: pd.DataFrame, min_days: int = 12) -> pd.DataFrame:
    """
    Corwin-Schultz (2012) high-low spread estimator.

    Uses daily ask-high and bid-low prices to estimate effective spreads.
    Adjusts for overnight price changes per Section II.A of the paper.

    Parameters
    ----------
    daily : pd.DataFrame
        Daily data with columns: permno, date, prc, askhi, bidlo, cfacpr.
    min_days : int
        Minimum valid daily observations per month (default: 12).

    Returns
    -------
    pd.DataFrame
        Monthly: permno, date (month-end), hl (effective spread estimate).
    """
    df = daily[["permno", "date", "prc", "askhi", "bidlo"]].copy()
    if "cfacpr" in daily.columns:
        df["cfacpr"] = daily["cfacpr"]
    else:
        df["cfacpr"] = 1.0

    df = df.sort_values(["permno", "date"]).reset_index(drop=True)

    # Use absolute price; set hi/lo to NaN when prc < 0 (non-trading days)
    neg_prc = df["prc"] < 0
    df.loc[neg_prc, "askhi"] = np.nan
    df.loc[neg_prc, "bidlo"] = np.nan
    df["prc"] = df["prc"].abs()

    hi = df["askhi"].copy()
    lo = df["bidlo"].copy()

    # Split-adjusted lagged close: lclose = lag(prc) * cfacpr / lag(cfacpr)
    df["prc_lag"] = df.groupby("permno")["prc"].shift(1)
    df["cfacpr_lag"] = df.groupby("permno")["cfacpr"].shift(1)
    lclose = df["prc_lag"] * df["cfacpr"] / df["cfacpr_lag"]

    # Overnight price change adjustment (Section II.A, p.726)
    pchg = pd.Series(0.0, index=df.index)
    up = df["bidlo"] > lclose
    down = df["askhi"] < lclose
    pchg[up] = df.loc[up, "bidlo"] - lclose[up]
    pchg[down] = df.loc[down, "askhi"] - lclose[down]
    lo = lo - pchg
    hi = hi - pchg

    # Split-adjusted lagged hi/lo
    lhi = df.groupby("permno")["askhi"].shift(1) * df["cfacpr"] / df["cfacpr_lag"]
    llo = df.groupby("permno")["bidlo"].shift(1) * df["cfacpr"] / df["cfacpr_lag"]
    # Apply same overnight adj to lagged (actually MATLAB lags after adj, let me re-read)
    # MATLAB: adjusts hi/lo first, then lags. Let me fix:
    # Actually in MATLAB, hi and lo are adjusted, THEN lagged. So:
    df["hi_adj"] = hi
    df["lo_adj"] = lo
    lhi = df.groupby("permno")["hi_adj"].shift(1) * df["cfacpr"] / df["cfacpr_lag"]
    llo = df.groupby("permno")["lo_adj"].shift(1) * df["cfacpr"] / df["cfacpr_lag"]

    hi_np = hi.to_numpy(dtype="float64")
    lo_np = lo.to_numpy(dtype="float64")
    lhi_np = lhi.to_numpy(dtype="float64")
    llo_np = llo.to_numpy(dtype="float64")

    with np.errstate(invalid="ignore", divide="ignore"):
        s = _cs_spread(hi_np, lo_np, lhi_np, llo_np)
        s_finite = np.isfinite(s)

        # MATLAB's log of a negative ratio (e.g. a bad tick where the
        # overnight adjustment pushes the lagged adjusted high below zero)
        # yields a COMPLEX value that flows through the monthly mean; real()
        # is only taken at the very end (makeCorwinSchultz.m:119). Re-run the
        # affected stocks in complex arithmetic; since the mean is linear,
        # keeping real(s) with the complex finiteness mask is exact.
        neg_ratio = ((hi_np / lo_np) < 0) | ((lhi_np / llo_np) < 0)
    if neg_ratio.any():
        bad_permnos = set(df.loc[neg_ratio, "permno"].unique())
        rows = df["permno"].isin(bad_permnos).to_numpy()
        with np.errstate(invalid="ignore", divide="ignore"):
            s_c = _cs_spread(
                hi_np[rows].astype(np.complex128),
                lo_np[rows].astype(np.complex128),
                lhi_np[rows].astype(np.complex128),
                llo_np[rows].astype(np.complex128),
            )
        s[rows] = s_c.real
        s_finite[rows] = np.isfinite(s_c)

    # Monthly averages with min_days threshold
    df["s"] = np.where(s_finite, s, np.nan)
    df["ym"] = df["date"].dt.to_period("M")
    df["s_valid"] = s_finite

    # Count valid days per permno-month
    counts = df.groupby(["permno", "ym"])["s_valid"].sum()
    means = df.groupby(["permno", "ym"])["s"].mean()

    monthly = pd.DataFrame({"hl": means, "n_days": counts}).reset_index()
    monthly.loc[monthly["n_days"] < min_days, "hl"] = np.nan

    # Convert period to month-end
    monthly["date"] = monthly["ym"].dt.to_timestamp(how="end").dt.normalize()
    monthly["date"] = monthly["date"] + pd.offsets.MonthEnd(0)
    monthly = monthly[["permno", "date", "hl"]].copy()

    LOGGER.info(
        "Corwin-Schultz: %d monthly obs, %.1f%% non-NaN",
        len(monthly), monthly["hl"].notna().mean() * 100,
    )
    return monthly


# ---------------------------------------------------------------------------
# Abdi-Ranaldi close-high-low spread estimator
# ---------------------------------------------------------------------------

#: Dense calendar rows an Abdi-Ranaldo batch materializes at once. Stocks are
#: never split across batches, so every (stock, month) group stays contiguous.
_AR_BATCH_ROWS = 4_000_000


def _batches(sizes: np.ndarray, budget: int) -> list[tuple[int, int]]:
    """Split consecutive items into runs whose sizes sum to at most ``budget``.

    A single item wider than the budget gets a batch to itself rather than
    being split, which is what keeps every stock whole.
    """
    out: list[tuple[int, int]] = []
    start = 0
    total = 0
    for i, size in enumerate(sizes):
        if total and total + size > budget:
            out.append((start, i))
            start, total = i, 0
        total += int(size)
    if start < sizes.size:
        out.append((start, sizes.size))
    return out


def _sorted_by_stock_and_date(permno: np.ndarray, dates: np.ndarray) -> bool:
    """Is the panel already in ``sort_values(["permno", "date"])`` order?

    Checking costs two passes; re-sorting a hundred million rows that the
    pipeline already handed over in order costs a great deal more.
    """
    if permno.size < 2:
        return True
    step = np.diff(permno)
    if (step < 0).any():
        return False
    return not ((step == 0) & (np.diff(dates) < np.timedelta64(0, "ns"))).any()


def _float_col(frame: pd.DataFrame, name: str) -> np.ndarray:
    """One column as float64, without copying when it already is one."""
    col = frame[name]
    if col.dtype == np.float64:
        return col.to_numpy()
    return col.astype("float64").to_numpy()


def _carry_forward_rows(
    dest: np.ndarray,
    rows: np.ndarray,
    n_dense: int,
    seg_of_row: np.ndarray,
) -> np.ndarray:
    """Source row each dense position inherits under a segmented forward fill.

    ``dest[i]`` is the dense position holding source row ``rows[i]``. The
    result gives, per dense position, the last source row at or before it
    *within the same segment*, or -1 when nothing precedes it — which is what
    a per-stock ``Series.ffill`` on a reindexed calendar produces.
    """
    src = np.full(n_dense, -1, dtype=np.int32)
    src[dest] = rows
    marker = np.where(
        src >= 0, np.arange(n_dense, dtype=np.int32), np.int32(-1)
    )
    np.maximum.accumulate(marker, out=marker)
    inside = marker >= seg_of_row
    return np.where(inside, src[marker], np.int32(-1))


def _carry_forward(
    values: np.ndarray,
    mask: np.ndarray,
    dest: np.ndarray,
    n_dense: int,
    seg_of_cell: np.ndarray,
) -> np.ndarray:
    """``values`` forward-filled onto the stacked dense calendar.

    Only rows selected by ``mask`` seed the fill, mirroring pandas ``ffill``,
    which carries the last *non-NaN* value rather than the last row.
    """
    idx = np.flatnonzero(mask).astype(np.int32)
    src = _carry_forward_rows(dest[idx], idx, n_dense, seg_of_cell)
    out = values[np.maximum(src, 0)]
    out[src < 0] = np.nan
    return out


def compute_abdi_ranaldi(daily: pd.DataFrame, min_days: int = 12) -> pd.DataFrame:
    """
    Abdi-Ranaldo (2017) close-high-low spread estimator.

    Uses closing price, daily high, and daily low to estimate spreads.

    Parameters
    ----------
    daily : pd.DataFrame
        Daily data with columns: permno, date, prc, askhi, bidlo.
    min_days : int
        Minimum valid daily observations per month.

    Returns
    -------
    pd.DataFrame
        Monthly: permno, date (month-end), chl (effective spread estimate).
    """
    # Columns, not a copy of the frame: this panel runs to ~10^8 rows and the
    # estimator never writes back into them.
    permno = daily["permno"].to_numpy()
    dates = pd.to_datetime(daily["date"]).to_numpy()
    prc = _float_col(daily, "prc")
    askhi = _float_col(daily, "askhi")
    bidlo = _float_col(daily, "bidlo")

    if not _sorted_by_stock_and_date(permno, dates):
        order = np.lexsort((dates, permno))
        permno, dates = permno[order], dates[order]
        prc, askhi, bidlo = prc[order], askhi[order], bidlo[order]

    # MATLAB operates on dense (ddates x permno) matrices: carried prices
    # extend across calendar trading days a stock has no row for (and past
    # its last row), the lead is the next *calendar* trading day, and the
    # monthly mean includes carried days. Every stock therefore lives on a
    # contiguous slice of the global trading calendar, from its first row's
    # month start through its last row's month end.
    # Hash the ~10^8 dates down to the ~10^4 trading days, then sort those;
    # sorting the whole column to find them costs three times as much.
    cal = pd.DatetimeIndex(np.sort(pd.unique(dates)))
    cal_ym = cal.to_period("M")
    n_cal = len(cal)
    if n_cal == 0:
        return pd.DataFrame(columns=["permno", "date", "chl"])

    # Calendar position -> month index, and each month's first/last position.
    month_start = np.flatnonzero(np.r_[True, cal_ym[1:] != cal_ym[:-1]])
    month_of_day = np.repeat(
        np.arange(month_start.size, dtype=np.int64),
        np.diff(np.r_[month_start, n_cal]),
    )
    month_end = np.r_[month_start[1:] - 1, n_cal - 1]

    cpos = cal.searchsorted(dates).astype(np.int64)

    # MATLAB's matrix has one cell per (stock, day); a repeated date collapses
    # onto the first row, as `drop_duplicates(subset="date")` did.
    keep = np.r_[True, (permno[1:] != permno[:-1]) | (cpos[1:] != cpos[:-1])]
    if not keep.all():
        permno, cpos = permno[keep], cpos[keep]
        prc, askhi, bidlo = prc[keep], askhi[keep], bidlo[keep]

    # Per-row masks, evaluated on the raw columns exactly as the loop did.
    with np.errstate(invalid="ignore"):
        has_prc = ~np.isnan(prc)
        traded = has_prc & ~(prc < 0)
        has_hi = traded & ~np.isnan(askhi)
        has_lo = traded & ~np.isnan(bidlo)
        row_valid = (
            (prc > 0)
            & ~np.isnan(askhi)
            & ~np.isnan(bidlo)
            & ((askhi - bidlo) != 0)
        )

    stock_start = np.flatnonzero(np.r_[True, permno[1:] != permno[:-1]])
    stock_end = np.r_[stock_start[1:], permno.size]
    span_lo = month_start[month_of_day[cpos[stock_start]]]
    span_hi = month_end[month_of_day[cpos[stock_end - 1]]] + 1
    span_len = span_hi - span_lo

    chunks = []
    for b_lo, b_hi in _batches(span_len, _AR_BATCH_ROWS):
        s_lo = span_lo[b_lo:b_hi]
        s_len = span_len[b_lo:b_hi]
        offsets = np.r_[0, np.cumsum(s_len)]
        n_dense = int(offsets[-1])

        stock_of_cell = np.repeat(np.arange(b_hi - b_lo, dtype=np.int32), s_len)
        seg_of_cell = offsets[:-1][stock_of_cell].astype(np.int32)
        dense_pos = (
            np.arange(n_dense, dtype=np.int64) - seg_of_cell + s_lo[stock_of_cell]
        )

        r_lo, r_hi = stock_start[b_lo], stock_end[b_hi - 1]
        rows = slice(r_lo, r_hi)
        stock_of_row = np.repeat(
            np.arange(b_hi - b_lo), stock_end[b_lo:b_hi] - stock_start[b_lo:b_hi]
        )
        dest = (offsets[stock_of_row] + cpos[rows] - s_lo[stock_of_row]).astype(np.int32)

        # Non-trading day: prc < 0 (bid/ask midpoint) or NaN -> hi/lo NaN,
        # then carry close/high/low forward (Abdi-Ranaldo, p.4454)
        args = (dest, n_dense, seg_of_cell)
        prc_c = np.abs(_carry_forward(prc[rows], has_prc[rows], *args))
        hi_c = _carry_forward(askhi[rows], has_hi[rows], *args)
        lo_c = _carry_forward(bidlo[rows], has_lo[rows], *args)

        with np.errstate(invalid="ignore", divide="ignore"):
            midpoint = (np.log(lo_c) + np.log(hi_c)) / 2
            c_t = np.log(prc_c)

        # Lead by one calendar trading day; MATLAB's dense matrix carries the
        # midpoint past the span end, so the lead at the span's last day is
        # the carried (same) value — unless the span ends at the dataset end.
        mid_tp1 = np.empty(n_dense)
        mid_tp1[:-1] = midpoint[1:]
        mid_tp1[-1] = np.nan
        last = offsets[1:] - 1
        mid_tp1[last] = np.where(span_hi[b_lo:b_hi] < n_cal, midpoint[last], np.nan)

        # MATLAB max(x, 0) ignores NaN: sqrt(max(NaN, 0)) = 0, so days with
        # missing inputs contribute *zeros* to the monthly mean (np.fmax).
        with np.errstate(invalid="ignore"):
            s_hat = np.sqrt(np.fmax(4 * (c_t - midpoint) * (c_t - mid_tp1), 0))

        # Gate: >= 12 days in the month with prc > 0 and finite hi/lo that
        # differ (makeAbdiRanaldi.m:106-111), all on the *raw* columns.
        valid = np.zeros(n_dense, dtype=bool)
        valid[dest] = row_valid[rows]

        month = month_of_day[dense_pos]
        # One group per (stock, month). Both keys only ever step forward along
        # the stacked array, so the groups are its contiguous runs and their
        # order is the per-stock loop's order. Aggregating with pandas keeps
        # the loop's arithmetic, Kahan-compensated mean included.
        head = np.flatnonzero(
            np.r_[
                True,
                (month[1:] != month[:-1]) | (stock_of_cell[1:] != stock_of_cell[:-1]),
            ]
        )
        group = np.zeros(n_dense, dtype=np.int64)
        group[head[1:]] = 1
        np.cumsum(group, out=group)
        chunks.append(pd.DataFrame({
            "permno": permno[stock_start[b_lo:b_hi]][stock_of_cell[head]],
            "month": month[head],
            "chl": pd.Series(s_hat).groupby(group, sort=False).mean().to_numpy(),
            # The day count is an exact integer sum, so it needs none of the
            # compensated summation the mean is kept in pandas for.
            "n_days": np.add.reduceat(valid.astype(np.int32), head),
        }))

    if not chunks:
        return pd.DataFrame(columns=["permno", "date", "chl"])

    monthly = pd.concat(chunks, ignore_index=True)
    monthly.loc[monthly["n_days"] < min_days, "chl"] = np.nan

    month_ends = (
        cal_ym[month_start].to_timestamp(how="end").normalize() + pd.offsets.MonthEnd(0)
    )
    monthly["date"] = month_ends[monthly["month"].to_numpy()]
    monthly = monthly[["permno", "date", "chl"]].copy()

    LOGGER.info(
        "Abdi-Ranaldi: %d monthly obs, %.1f%% non-NaN",
        len(monthly), monthly["chl"].notna().mean() * 100,
    )
    return monthly


# ---------------------------------------------------------------------------
# Kyle-Obizhaeva volume-over-volatility
# ---------------------------------------------------------------------------

def compute_kyle_obizhaeva(
    daily: pd.DataFrame,
    cpi: pd.Series | None = None,
    min_vol_days: int = 5,
    min_ret_days: int = 11,
    exchcd: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Kyle-Obizhaeva (2016) VoV effective spread following Fong, Holden, Tobek (2018).

    MATLAB ``makeKyleObizhaeva.m``:
    ``VoV = 8 * (ret_std_ddof1^(2/3)) / (mean(dvol)/CPI_norm)^(1/3)``
    where ``CPI_norm = CPIAUCNS / CPIAUCNS(2000-01)`` and ``dvol`` is
    Gao-Ritter-adjusted share volume times ``|prc|``. Monthly mean of ``dvol``
    includes zero-volume days (``omitnan`` only).
    """
    from .crsp_daily import adjust_nasdaq_volume, coerce_nullable_dtypes

    ret_col = "ret_adj" if "ret_adj" in daily.columns else "ret"
    df = daily[["permno", "date", ret_col, "prc", "vol"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    coerce_nullable_dtypes(df)

    vol_adj = adjust_nasdaq_volume(df, exchcd=exchcd)
    df["dvol"] = vol_adj.to_numpy(dtype="float64") * df["prc"].abs().to_numpy(dtype="float64")
    df["ym"] = df["date"].dt.to_period("M")
    df["pos_vol"] = df["dvol"] > 0
    df["nz_ret"] = df[ret_col].abs() > 0

    # Constants from Kyle-Obizhaeva / FHT
    a, b, c = 8.0, 2 / 3, 1 / 3

    LOGGER.info("Starting Kyle-Obizhaeva on %d daily rows", len(df))
    g = df.groupby(["permno", "ym"], sort=False)
    # MATLAB: mean(dvol, 'omitnan') includes zeros; std(dret, 0, 1, 'omitnan')
    # has weight w=0 = *sample* std (normalize by N-1), i.e. ddof=1.
    agg = g.agg(
        n_vol=("pos_vol", "sum"),
        n_ret=("nz_ret", "sum"),
        ret_std=(ret_col, lambda s: s.std(ddof=1)),
        vol_mean=("dvol", "mean"),
    )

    # CPIAUCNS / CPIAUCNS(2000-01) — MATLAB makeKyleObizhaeva.m:75-76
    if cpi is None:
        cpi = load_cpi_aucns()
    month_ends = (
        agg.index.get_level_values("ym")
        .to_timestamp(how="end")
        .normalize()
    )
    if cpi is not None and not cpi.empty:
        cpi = cpi.copy()
        cpi.index = pd.to_datetime(cpi.index).normalize()
        # Prefer explicit Jan 2000; else nearest available
        base_candidates = cpi.reindex([pd.Timestamp("2000-01-31")])
        if base_candidates.isna().all():
            base = cpi[cpi.index.to_period("M") == "2000-01"]
            cpi_base = float(base.iloc[0]) if len(base) else np.nan
        else:
            cpi_base = float(base_candidates.iloc[0])
        if np.isfinite(cpi_base) and cpi_base > 0:
            cpi = cpi / cpi_base
        cpi_map = cpi
        cpi_vals = cpi_map.reindex(month_ends).to_numpy(dtype="float64")
        # Month-end CPI may miss; try period-end alignment via ym
        if np.any(~np.isfinite(cpi_vals)):
            cpi_by_ym = cpi.copy()
            cpi_by_ym.index = cpi_by_ym.index.to_period("M")
            ym_idx = agg.index.get_level_values("ym")
            cpi_vals = cpi_by_ym.reindex(ym_idx).to_numpy(dtype="float64")
        valid_cpi = np.isfinite(cpi_vals) & (cpi_vals > 0)
        vol = agg["vol_mean"].to_numpy(dtype="float64", copy=True)
        vol[valid_cpi] = vol[valid_cpi] / cpi_vals[valid_cpi]
        agg["vol_mean"] = vol

    ok = (
        (agg["n_vol"] >= min_vol_days)
        & (agg["n_ret"] >= min_ret_days)
        & agg["ret_std"].notna()
        & (agg["vol_mean"] > 0)
    )
    vov = pd.Series(np.nan, index=agg.index, dtype="float64")
    if ok.any():
        rs = agg.loc[ok, "ret_std"].to_numpy(dtype="float64")
        vm = agg.loc[ok, "vol_mean"].to_numpy(dtype="float64")
        vov.loc[ok] = a * (rs ** b) / (vm ** c)

    monthly = vov.rename("vov").reset_index()
    if monthly.empty:
        return pd.DataFrame(columns=["permno", "date", "vov"])

    monthly["date"] = (
        monthly["ym"].dt.to_timestamp(how="end").dt.normalize()
    )
    monthly["date"] = monthly["date"] + pd.offsets.MonthEnd(0)
    monthly = monthly[["permno", "date", "vov"]].copy()

    LOGGER.info(
        "Kyle-Obizhaeva: %d monthly obs, %.1f%% non-NaN",
        len(monthly), monthly["vov"].notna().mean() * 100,
    )
    return monthly


def load_cpi_aucns(
    cache_path: str | Path | None = None,
) -> pd.Series | None:
    """
    Load monthly CPIAUCNS, indexed by month-end dates.

    Tries (1) local cache CSV, (2) FRED fredgraph CSV download.
    Returns None if unavailable.
    """
    candidates: list[Path] = []
    if cache_path is not None:
        candidates.append(Path(cache_path))
    root = Path(__file__).resolve().parents[3]
    candidates.extend([
        root / "Data" / "CPIAUCNS.csv",
        root / "AssayingAnomalies-MATLAB" / "Library Update" / "Inputs" / "CPIAUCNS.csv",
    ])
    for path in candidates:
        if path.exists():
            try:
                raw = pd.read_csv(path)
                cols = {c.lower(): c for c in raw.columns}
                date_col = cols.get("date") or cols.get("observation_date") or raw.columns[0]
                val_col = cols.get("cpiaucns") or raw.columns[1]
                s = pd.Series(
                    pd.to_numeric(raw[val_col], errors="coerce").to_numpy(),
                    index=pd.to_datetime(raw[date_col]),
                    name="cpi",
                ).dropna()
                s.index = s.index + pd.offsets.MonthEnd(0)
                s = s[~s.index.duplicated(keep="last")].sort_index()
                LOGGER.info("Loaded CPIAUCNS from %s (%d months)", path, len(s))
                note_input(path, "CPIAUCNS")
                return s
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Failed reading CPI cache %s: %s", path, exc)

    url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCNS"
    try:
        raw = pd.read_csv(url)
        s = pd.Series(
            pd.to_numeric(raw["CPIAUCNS"], errors="coerce").to_numpy(),
            index=pd.to_datetime(raw["observation_date"]),
            name="cpi",
        ).dropna()
        s.index = s.index + pd.offsets.MonthEnd(0)
        s = s[~s.index.duplicated(keep="last")].sort_index()
        cache = root / "Data" / "CPIAUCNS.csv"
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            out = pd.DataFrame({"observation_date": s.index, "CPIAUCNS": s.to_numpy()})
            out.to_csv(cache, index=False)
            LOGGER.info("Fetched CPIAUCNS from FRED; cached to %s", cache)
            note_input(cache, "CPIAUCNS (fetched from FRED)")
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Could not cache CPIAUCNS: %s", exc)
            note_input(url, "CPIAUCNS")
        return s
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("CPIAUCNS unavailable (%s); VoV will skip CPI scaling", exc)
        return None


# ---------------------------------------------------------------------------
# Fill missing transaction costs (nearest-neighbor matching)
# ---------------------------------------------------------------------------

#: Sentinel for "no donor" in the min-position tie-break reductions below.
_NO_DONOR = np.iinfo(np.int64).max

#: Donors examined either side of a target's market-equity rank before the
#: exact-coverage test decides whether a full scan is still needed.
_NN_BAND = 128

#: Cap on the (targets x donors) block a full scan materializes at once.
_NN_BLOCK = 4_000_000


def _nn_match_me(
    t_me: np.ndarray, d_me: np.ndarray, d_pos: np.ndarray
) -> np.ndarray:
    """Pass-2 nearest neighbour: closest donor in market-equity rank.

    Returns each target's donor *position*. MATLAB/`argmin` break a distance
    tie by taking the first donor in permno order, which is the smallest
    position — so collapsing donors onto distinct rank values and carrying each
    value's smallest position reproduces the loop exactly while turning the
    scan into a binary search.
    """
    order = np.argsort(d_me, kind="stable")
    s_me = d_me[order]
    s_pos = d_pos[order]

    starts = np.flatnonzero(np.r_[True, s_me[1:] != s_me[:-1]])
    u_me = s_me[starts]
    u_pos = np.minimum.reduceat(s_pos, starts)
    n_u = u_me.size

    j = np.searchsorted(u_me, t_me)
    jl = np.maximum(j - 1, 0)
    jr = np.minimum(j, n_u - 1)
    # Distances are formed exactly as the loop formed them: donor minus target.
    d_left = np.where(j > 0, np.abs(u_me[jl] - t_me), np.inf)
    d_right = np.where(j < n_u, np.abs(u_me[jr] - t_me), np.inf)

    sel = np.where(d_left < d_right, u_pos[jl], u_pos[jr])
    tied = d_left == d_right
    if tied.any():
        sel[tied] = np.minimum(u_pos[jl][tied], u_pos[jr][tied])
    return sel


def _nn_match_full(
    t_me: np.ndarray,
    t_iv: np.ndarray,
    d_me: np.ndarray,
    d_iv: np.ndarray,
    d_pos: np.ndarray,
) -> np.ndarray:
    """Exhaustive (targets x donors) pass-1 match, blocked to bound memory."""
    out = np.empty(t_me.size, dtype=np.int64)
    step = max(1, _NN_BLOCK // max(d_me.size, 1))
    for i in range(0, t_me.size, step):
        sl = slice(i, i + step)
        dm = d_me[None, :] - t_me[sl, None]
        di = d_iv[None, :] - t_iv[sl, None]
        dist = np.sqrt(dm * dm + di * di)
        best = dist.min(axis=1)
        out[sl] = np.where(
            dist == best[:, None], d_pos[None, :], _NO_DONOR
        ).min(axis=1)
    return out


def _nn_match_me_ivol(
    t_me: np.ndarray,
    t_iv: np.ndarray,
    d_me: np.ndarray,
    d_iv: np.ndarray,
    d_pos: np.ndarray,
) -> np.ndarray:
    """Pass-1 nearest neighbour in (me_rank, ivol_rank) space.

    Scanning every donor for every target is quadratic and most of it is
    wasted: the match almost always sits within a few dozen donors of the
    target's own market-equity rank. So each target is first matched against a
    band of ``2 * _NN_BAND`` donors around its rank, and the band's best
    distance ``r`` is then *proved* sufficient — a donor outside the band has
    ``|me_d - me_t| > r`` and therefore cannot tie, let alone win. Targets that
    fail the proof fall back to the exhaustive scan.

    Ties are broken on the smallest donor position rather than on scan order,
    which is what makes the band and the full scan interchangeable: both return
    the first donor in permno order among the equidistant ones, exactly as
    ``np.argmin`` over the whole donor array did.
    """
    n = d_me.size
    if n <= 2 * _NN_BAND:
        return _nn_match_full(t_me, t_iv, d_me, d_iv, d_pos)

    order = np.argsort(d_me, kind="stable")
    s_me = d_me[order]
    s_iv = d_iv[order]
    s_pos = d_pos[order]

    width = 2 * _NN_BAND
    start = np.clip(np.searchsorted(s_me, t_me) - _NN_BAND, 0, n - width)
    offsets = np.arange(width)

    out = np.empty(t_me.size, dtype=np.int64)
    covered = np.empty(t_me.size, dtype=bool)
    step = max(1, _NN_BLOCK // width)
    for i in range(0, t_me.size, step):
        sl = slice(i, i + step)
        cols = start[sl, None] + offsets[None, :]
        dm = s_me[cols] - t_me[sl, None]
        di = s_iv[cols] - t_iv[sl, None]
        dist = np.sqrt(dm * dm + di * di)
        best = dist.min(axis=1)
        out[sl] = np.where(dist == best[:, None], s_pos[cols], _NO_DONOR).min(axis=1)

        lo = start[sl]
        hi = lo + width
        left_ok = (lo == 0) | (s_me[np.maximum(lo - 1, 0)] < t_me[sl] - best)
        right_ok = (hi == n) | (s_me[np.minimum(hi, n - 1)] > t_me[sl] + best)
        covered[sl] = left_ok & right_ok

    if not covered.all():
        rest = ~covered
        out[rest] = _nn_match_full(
            t_me[rest], t_iv[rest], d_me, d_iv, d_pos
        )
    return out


def fill_missing_tcosts(
    tcosts_raw: pd.DataFrame,
    me: pd.DataFrame,
    ivol: pd.DataFrame | None = None,
    universe_permnos: np.ndarray | None = None,
) -> pd.DataFrame:
    """
    Fill missing transaction costs via nearest-neighbor matching in rank space.

    Following Novy-Marx and Velikov (RFS 2016) / MATLAB ``fillMissingTcosts.m``:
    Pass 1: Match on (me_rank, ivol_rank) Euclidean distance.
    Pass 2: Match on me_rank only (for remaining NaN).

    Both passes draw donors from the *raw* finite tcost pool (MATLAB uses
    ``tcosts_raw`` for ``idxToMatch`` in both passes — pass-1 fills are not
    eligible donors in pass 2). Idiosyncratic vol should be MATLAB
    ``IffVOL3`` (``idiovol_ff_3m``) when available.

    Parameters
    ----------
    tcosts_raw : pd.DataFrame
        Monthly tcosts with columns: permno, date, tcost.
    me : pd.DataFrame
        Market equity with columns: permno, date, me.
    ivol : pd.DataFrame, optional
        Idiosyncratic volatility with columns: permno, date, and either
        ``idiovol_ff_3m`` (preferred, MATLAB IffVOL3) or ``idiovol``.
    universe_permnos : array-like, optional
        Restrict the dense grid to these permnos (MATLAB's matrices span the
        monthly domestic-common universe; daily-derived inputs cover more
        permnos, which would pollute ranks, donors, and fill targets).

    Returns
    -------
    pd.DataFrame
        Filled tcosts: permno, date, tcost.
    """
    # MATLAB fillMissingTcosts.m operates on dense (month x permno) matrices:
    # tiedrank spans every stock with finite me / IffVOL3 that month — even
    # stocks with no raw-tcost row — and fill targets are dense cells with
    # finite me (+ivol in pass 1) regardless of raw coverage. Build the union
    # universe of all three inputs so ranks and targets match the dense grid.
    tc = tcosts_raw[["permno", "date", "tcost"]].copy()
    me_sub = me[["permno", "date", "me"]]
    if universe_permnos is not None:
        univ = set(int(p) for p in universe_permnos)
        tc = tc[tc["permno"].isin(univ)]
        me_sub = me_sub[me_sub["permno"].isin(univ)]
        if ivol is not None:
            ivol = ivol[ivol["permno"].isin(univ)]
    ivol_sub = None
    if ivol is not None:
        ivol_col = (
            "idiovol_ff_3m" if "idiovol_ff_3m" in ivol.columns
            else "idiovol" if "idiovol" in ivol.columns
            else None
        )
        if ivol_col is not None:
            ivol_sub = ivol[["permno", "date", ivol_col]].rename(
                columns={ivol_col: "idiovol"}
            )

    frames = [
        tc[["permno", "date"]],
        me_sub.loc[me_sub["me"].notna(), ["permno", "date"]],
    ]
    if ivol_sub is not None:
        frames.append(ivol_sub.loc[ivol_sub["idiovol"].notna(), ["permno", "date"]])
    universe = pd.concat(frames, ignore_index=True).drop_duplicates()

    panel = universe.merge(tc, on=["permno", "date"], how="left")
    panel = panel.merge(me_sub, on=["permno", "date"], how="left")
    if ivol_sub is not None:
        panel = panel.merge(ivol_sub, on=["permno", "date"], how="left")
    else:
        panel["idiovol"] = np.nan

    # Stable within-month order (MATLAB column order ≈ sorted permno)
    panel = panel.sort_values(["date", "permno"]).reset_index(drop=True)

    # tiedrank across the month's stocks, taken once for the whole panel; a
    # NaN input keeps a NaN rank, so the rank's finiteness *is* the has-me /
    # has-ivol gate the loop tested on the raw columns.
    by_date = panel.groupby("date", sort=False)
    me_rank = by_date["me"].rank(method="average").to_numpy(dtype="float64")
    iv_rank = by_date["idiovol"].rank(method="average").to_numpy(dtype="float64")
    has_me = ~np.isnan(me_rank)
    has_ivol = ~np.isnan(iv_rank)

    tcost = pd.to_numeric(panel["tcost"], errors="coerce").to_numpy(dtype="float64")
    has_raw = ~np.isnan(tcost)
    result = tcost.copy()
    n_filled = 0

    # Sorted by date, so each month is a contiguous block.
    dates = panel["date"].to_numpy()
    starts = np.flatnonzero(np.r_[True, dates[1:] != dates[:-1]])
    ends = np.r_[starts[1:], len(panel)]

    for lo, hi in zip(starts, ends):
        block = slice(lo, hi)
        m_me = me_rank[block]
        m_iv = iv_rank[block]
        m_tc = tcost[block]
        m_res = result[block]
        m_has_me = has_me[block]
        m_has_raw = has_raw[block]

        # Pass 1: match on (me_rank, ivol_rank); donors = raw finite only
        both = m_has_me & has_ivol[block]
        donors = np.flatnonzero(both & m_has_raw)
        targets = np.flatnonzero(both & np.isnan(m_res))
        if donors.size and targets.size:
            sel = _nn_match_me_ivol(
                m_me[targets], m_iv[targets], m_me[donors], m_iv[donors], donors
            )
            m_res[targets] = m_tc[sel]
            n_filled += targets.size

        # Pass 2: match on me_rank only; donors still RAW finite (MATLAB L83)
        donors2 = np.flatnonzero(m_has_me & m_has_raw)
        targets2 = np.flatnonzero(m_has_me & np.isnan(m_res))
        if donors2.size and targets2.size:
            sel = _nn_match_me(m_me[targets2], m_me[donors2], donors2)
            m_res[targets2] = m_tc[sel]
            n_filled += targets2.size

    panel["tcost"] = result
    LOGGER.info("Filled %d missing tcost observations", n_filled)
    return panel[["permno", "date", "tcost"]].copy()


# ---------------------------------------------------------------------------
# Winsorize helper
# ---------------------------------------------------------------------------

def _winsorize(s: pd.Series, upper_pct: float = 99.9) -> pd.Series:
    """Winsorize at the upper percentile (leave lower unchanged)."""
    finite = s[s.notna() & np.isfinite(s)]
    if finite.empty:
        return s
    upper = np.percentile(finite, upper_pct)
    result = s.astype(float).copy()
    result[result > upper] = upper
    return result


# ---------------------------------------------------------------------------
# Combine low-frequency measures
# ---------------------------------------------------------------------------

def combine_lf_spreads(
    hl: pd.DataFrame | None = None,
    chl: pd.DataFrame | None = None,
    vov: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Combine low-frequency spread measures into a single effective spread.

    Takes the mean across available measures (omitting NaN).
    Result is the full effective spread (divide by 2 for half-spread / tcost).

    Parameters
    ----------
    hl : pd.DataFrame, optional
        Corwin-Schultz with columns: permno, date, hl.
    chl : pd.DataFrame, optional
        Abdi-Ranaldi with columns: permno, date, chl.
    vov : pd.DataFrame, optional
        Kyle-Obizhaeva with columns: permno, date, vov.

    Returns
    -------
    pd.DataFrame
        Combined: permno, date, eff_spread, tcost (= eff_spread / 2).
    """
    dfs = []
    for name, df in [("hl", hl), ("chl", chl), ("vov", vov)]:
        if df is not None and not df.empty:
            sub = df[["permno", "date", name]].copy()
            sub[name] = _winsorize(sub[name], upper_pct=99.9)
            dfs.append(sub)

    if not dfs:
        return pd.DataFrame(columns=["permno", "date", "eff_spread", "tcost"])

    # Merge all measures
    result = dfs[0]
    for d in dfs[1:]:
        result = result.merge(d, on=["permno", "date"], how="outer")

    # Average across measures (omitting NaN)
    spread_cols = [c for c in result.columns if c not in ("permno", "date")]
    result["eff_spread"] = result[spread_cols].mean(axis=1, skipna=True)

    # Half-spread = transaction cost
    result["tcost"] = result["eff_spread"] / 2

    result = result[["permno", "date", "eff_spread", "tcost"]].copy()

    LOGGER.info(
        "Combined %d spread measures: %d monthly obs, %.1f%% non-NaN tcost",
        len(spread_cols), len(result), result["tcost"].notna().mean() * 100,
    )
    return result


# ---------------------------------------------------------------------------
# Gibbs effective spread (Hasbrouck, JF 2009)
# ---------------------------------------------------------------------------

def load_gibbs(filepath: str | Path) -> pd.DataFrame:
    """
    Load Hasbrouck (2009) Gibbs effective spread estimates from CSV.

    MATLAB equivalent: makeGibbs.m

    The CSV has columns: permno, year, c, ...
    Returns monthly panel with columns: permno, date, gibbs.
    The 'c' values are averaged within (permno, year), then multiplied by 2
    (full effective spread) to be consistent with other measures.

    Parameters
    ----------
    filepath : str or Path
        Path to crspgibbs*.csv file.

    Returns
    -------
    pd.DataFrame
        Yearly: permno, year, gibbs (full effective spread = 2 * c).
    """
    df = pd.read_csv(filepath)

    # Normalize column names
    df.columns = df.columns.str.lower().str.strip()

    # Keep permno, year, c
    required = {"permno", "year", "c"}
    if not required.issubset(set(df.columns)):
        raise ValueError(f"Gibbs CSV missing columns: {required - set(df.columns)}")

    df = df[["permno", "year", "c"]].dropna(subset=["c"])

    # Average multiple estimates per (permno, year)
    df = df.groupby(["permno", "year"], as_index=False)["c"].mean()

    # Multiply by 2 to get full effective spread (MATLAB line 69)
    df["gibbs"] = 2 * df["c"]
    df = df.drop(columns=["c"])

    LOGGER.info("Loaded Gibbs: %d permno-year obs from %s", len(df), filepath)
    return df


# ---------------------------------------------------------------------------
# High-frequency effective spreads (TAQ + ISSM)
# ---------------------------------------------------------------------------

def load_hf_spreads(filepath: str | Path) -> pd.DataFrame:
    """
    Load high-frequency effective spread estimates from CSV.

    MATLAB equivalent: makeHighFreqEffSpreads.m

    The CSV has columns: permno, yearm, espread_pct_mean, espread_pct_month_end, espread_n.
    Returns monthly panel: permno, date (month-end), hf_ave, hf_monthend, hf_n.

    Parameters
    ----------
    filepath : str or Path
        Path to hf_monthly.csv file.

    Returns
    -------
    pd.DataFrame
        Monthly: permno, date (month-end), hf_ave, hf_monthend, hf_n.
    """
    df = pd.read_csv(filepath)
    df.columns = df.columns.str.lower().str.strip()

    # Rename columns to match MATLAB
    rename = {
        "espread_pct_mean": "hf_ave",
        "espread_pct_month_end": "hf_monthend",
        "espread_n": "hf_n",
    }
    df = df.rename(columns=rename)

    # Convert yearm (YYYYMM) to month-end date
    df["yearm"] = df["yearm"].astype(int)
    df["date"] = pd.to_datetime(df["yearm"].astype(str), format="%Y%m") + pd.offsets.MonthEnd(0)

    # Convert from pct to decimal (MATLAB divides by 100 on line 63)
    df["hf_ave"] = df["hf_ave"] / 100

    # Use permno column (the last one, not permno_wrds)
    if "permno" not in df.columns and "permno_wrds" in df.columns:
        df = df.rename(columns={"permno_wrds": "permno"})

    df = df[["permno", "date", "hf_ave", "hf_monthend", "hf_n"]].copy()
    df = df.dropna(subset=["permno"])
    df["permno"] = df["permno"].astype(int)

    LOGGER.info("Loaded HF spreads: %d monthly obs from %s", len(df), filepath)
    return df


# ---------------------------------------------------------------------------
# make_trading_costs: full orchestrator (MATLAB makeTradingCosts.m)
# ---------------------------------------------------------------------------

def make_trading_costs(
    daily: pd.DataFrame,
    me: pd.DataFrame,
    ivol: pd.DataFrame | None = None,
    exchcd: pd.DataFrame | None = None,
    tcosts_type: Literal["full", "lf_combo", "gibbs"] = "lf_combo",
    gibbs_path: str | Path | None = None,
    hf_path: str | Path | None = None,
    cpi: pd.Series | None = None,
    universe_permnos: np.ndarray | None = None,
    link_keys: pd.DataFrame | None = None,
    demo: bool = False,
) -> pd.DataFrame:
    """
    Full trading cost construction following MATLAB makeTradingCosts.m.

    Orchestrates all spread estimators, applies exchange/date exclusions,
    winsorizes, averages, fills missing, and returns half-spread tcost.

    Parameters
    ----------
    daily : pd.DataFrame
        CRSP daily data with columns: permno, date, prc, askhi, bidlo, vol, ret, cfacpr.
    me : pd.DataFrame
        Market equity: permno, date, me (monthly).
    ivol : pd.DataFrame, optional
        Idiosyncratic vol: permno, date, idiovol (monthly).
    exchcd : pd.DataFrame, optional
        Exchange code: permno, date, exchcd (monthly). Used for NASDAQ/AMEX exclusions.
    tcosts_type : str
        'gibbs' = Gibbs only; 'lf_combo' = 4 LF measures; 'full' = LF + HF TAQ.
    gibbs_path : str or Path, optional
        Path to crspgibbs*.csv. Required for all tcosts_type values: without
        it this raises :class:`~assayinganomalies.provenance.MissingInputError`
        (MATLAB makeTradingCosts.m:53-58 errors too), unless ``demo=True``.
    hf_path : str or Path, optional
        Path to hf_monthly.csv. Required when tcosts_type='full'.
    cpi : pd.Series, optional
        Monthly CPI for Kyle-Obizhaeva adjustment.
    link_keys : pd.DataFrame, optional
        (permno, date) rows replicating MATLAB's crsp_link (the monthly stock
        file restricted to valid name windows and, when configured, shrcd
        10/11). Used as the expansion grid for yearly Gibbs estimates; falls
        back to the ME panel keys when absent.
    demo : bool
        Synthetic-data run: a missing ``gibbs_path`` is a warning, and the
        trading costs are built without the Gibbs measure.

    Returns
    -------
    pd.DataFrame
        Monthly: permno, date, tcost (half-spread). When Gibbs is available,
        also includes ``tcost_gibbs`` (filled Gibbs-only half-spread matching
        MATLAB ``gibbs_filled.mat``).
    """
    if tcosts_type not in ("full", "lf_combo", "gibbs"):
        raise ValueError(f"tcosts_type must be 'full', 'lf_combo', or 'gibbs'; got '{tcosts_type}'")

    # Normalize nullable dtypes from WRDS parquet files
    from .crsp_daily import coerce_nullable_dtypes

    daily = daily.copy()
    daily["date"] = pd.to_datetime(daily["date"])
    coerce_nullable_dtypes(daily)

    # --- Gibbs (always computed) ---
    gibbs_df = None
    gibbs_raw = None  # pre-winsorize copy for gibbs_filled parity
    if gibbs_path is not None:
        gibbs_yearly = load_gibbs(gibbs_path)
        grid = link_keys if link_keys is not None else me
        gibbs_df = _expand_gibbs_to_monthly(gibbs_yearly, grid)
        gibbs_raw = gibbs_df.copy()
    elif demo:
        LOGGER.warning("No Gibbs path provided (demo run); Gibbs measure will be omitted")
    else:
        raise MissingInputError(
            f"make_trading_costs got no gibbs_path.\n{gibbs_manual_hint()}"
        )

    # MATLAB makeTradingCosts.m:96-97 — fillMissingTcosts(gibbs/2) before winsorize
    tcost_gibbs_filled = None
    if gibbs_raw is not None and not gibbs_raw.empty:
        gibbs_half = gibbs_raw[["permno", "date"]].copy()
        gibbs_half["tcost"] = gibbs_raw["gibbs"] / 2.0
        tcost_gibbs_filled = fill_missing_tcosts(
            gibbs_half, me, ivol=ivol, universe_permnos=universe_permnos
        )
        tcost_gibbs_filled = tcost_gibbs_filled.rename(columns={"tcost": "tcost_gibbs"})

    # --- Low-frequency measures ---
    hl_df = chl_df = vov_df = None
    if tcosts_type in ("lf_combo", "full"):
        hl_df = compute_corwin_schultz(daily)
        chl_df = compute_abdi_ranaldi(daily)
        vov_df = compute_kyle_obizhaeva(daily, cpi=cpi, exchcd=exchcd)

    # --- High-frequency measures ---
    hf_df = None
    if tcosts_type == "full":
        if hf_path is None:
            raise ValueError("hf_path required when tcosts_type='full'")
        hf_df = load_hf_spreads(hf_path)

    # --- Restrict to the MATLAB matrix universe before winsorizing ---
    # MATLAB pools the dense (nMonths x nStocks) matrix over permno_v (the
    # domestic-common universe) to find the 99.9th percentile; rows for
    # permnos outside that universe shift the cap and leave extreme cells
    # uncapped (makeTradingCosts.m:105-125).
    if universe_permnos is not None:
        _univ = set(int(p) for p in universe_permnos)

        def _restrict(df: pd.DataFrame | None) -> pd.DataFrame | None:
            if df is None or df.empty:
                return df
            return df[df["permno"].astype(int).isin(_univ)].copy()

        gibbs_df = _restrict(gibbs_df)
        hl_df = _restrict(hl_df)
        chl_df = _restrict(chl_df)
        vov_df = _restrict(vov_df)
        hf_df = _restrict(hf_df)

    # --- Winsorize each measure at 99.9% ---
    measures: dict[str, pd.DataFrame] = {}
    if gibbs_df is not None:
        gibbs_df = gibbs_df.copy()
        gibbs_df["gibbs"] = _winsorize(gibbs_df["gibbs"])
        measures["gibbs"] = gibbs_df
    if hl_df is not None:
        hl_df["hl"] = _winsorize(hl_df["hl"])
        measures["hl"] = hl_df
    if chl_df is not None:
        chl_df["chl"] = _winsorize(chl_df["chl"])
        measures["chl"] = chl_df
    if vov_df is not None:
        vov_df["vov"] = _winsorize(vov_df["vov"])
        measures["vov"] = vov_df
    if hf_df is not None and not hf_df.empty and "hf_ave" in hf_df.columns:
        # MATLAB winsorizes hf_spreads_ave alongside the LF measures
        hf_df = hf_df.copy()
        hf_df["hf_ave"] = _winsorize(hf_df["hf_ave"])

    # --- Exchange/date exclusions (MATLAB lines 139-154) ---
    if exchcd is not None and tcosts_type != "gibbs":
        _apply_exchange_exclusions(measures, exchcd)

    # --- Combine measures ---
    if tcosts_type == "gibbs":
        if gibbs_df is None or gibbs_df.empty:
            empty = pd.DataFrame(columns=["permno", "date", "tcost", "tcost_gibbs"])
            return empty
        combined = gibbs_df.rename(columns={"gibbs": "eff_spread"})
    else:
        # Merge all LF measures into one panel
        all_measures = None
        for name, mdf in measures.items():
            val_col = name
            sub = mdf[["permno", "date", val_col]].copy()
            if all_measures is None:
                all_measures = sub
            else:
                all_measures = all_measures.merge(sub, on=["permno", "date"], how="outer")

        if all_measures is None or all_measures.empty:
            empty = pd.DataFrame(columns=["permno", "date", "tcost", "tcost_gibbs"])
            return empty

        # Average across LF measures (omit NaN)
        lf_cols = [c for c in all_measures.columns if c not in ("permno", "date")]
        all_measures["eff_spread"] = all_measures[lf_cols].mean(axis=1, skipna=True)

        # If full, overlay HF spreads where available. Outer merge: MATLAB
        # assigns HF at every finite cell of its dense matrix, including
        # permno-months with no LF measure row at all.
        if tcosts_type == "full" and hf_df is not None and not hf_df.empty:
            hf_sub = hf_df[["permno", "date", "hf_ave"]].copy()
            hf_sub["date"] = pd.to_datetime(hf_sub["date"])
            all_measures = all_measures.merge(
                hf_sub, on=["permno", "date"], how="outer"
            )
            hf_mask = all_measures["hf_ave"].notna()
            all_measures.loc[hf_mask, "eff_spread"] = all_measures.loc[hf_mask, "hf_ave"]
            all_measures = all_measures.drop(columns=["hf_ave"])

        combined = all_measures[["permno", "date", "eff_spread"]].copy()

    # Half-spread = tcost
    combined["tcost"] = combined["eff_spread"] / 2
    combined = combined[["permno", "date", "tcost"]].copy()

    # Fill missing
    filled = fill_missing_tcosts(
        combined, me, ivol=ivol, universe_permnos=universe_permnos
    )

    # Attach Gibbs-only filled half-spread for tcosts_gibbs parity
    if tcost_gibbs_filled is not None and not tcost_gibbs_filled.empty:
        filled = filled.merge(
            tcost_gibbs_filled[["permno", "date", "tcost_gibbs"]],
            on=["permno", "date"],
            how="left",
        )
    else:
        filled["tcost_gibbs"] = np.nan

    LOGGER.info(
        "make_trading_costs(%s): %d obs, %.1f%% non-NaN",
        tcosts_type, len(filled), filled["tcost"].notna().mean() * 100,
    )
    return filled


def _expand_gibbs_to_monthly(
    gibbs_yearly: pd.DataFrame, me: pd.DataFrame
) -> pd.DataFrame:
    """
    Expand yearly Gibbs estimates to monthly by merging on (permno, year).

    MATLAB makeGibbs.m left-joins the estimates onto crsp_link, which is the
    monthly stock file restricted to valid mseexchdates name windows and (when
    domComEqFlag) shrcd 10/11 (makeCRSPMonthlyData.m:60-95). Pass those keys
    as ``me`` for exact parity: expanding onto the ccm_panel/ME keys instead
    overshot MATLAB's grid by ~13k cells (rows outside name windows or share
    codes, where ME is NaN so the NN fill never removes them).
    """
    me_monthly = me[["permno", "date"]].copy()
    me_monthly["date"] = pd.to_datetime(me_monthly["date"])
    me_monthly["year"] = me_monthly["date"].dt.year

    merged = me_monthly.merge(gibbs_yearly, on=["permno", "year"], how="left")
    return merged[["permno", "date", "gibbs"]].copy()


def _apply_exchange_exclusions(
    measures: dict[str, pd.DataFrame],
    exchcd: pd.DataFrame,
) -> None:
    """
    Apply MATLAB-style exchange/date exclusions in-place.

    MATLAB ``makeTradingCosts.m`` uses YYYYMM integer thresholds:
    - Gibbs/VoV NASDAQ: ``dates <= 198212`` (Dec 1982). MATLAB writes
      ``1982212``, a typo that no valid YYYYMM can exceed, so it drops every
      NASDAQ Gibbs/VoV observation instead of just the pre-1983 ones. Corrected
      here.
    - HL/CHL NASDAQ: ``dates <= 199212`` (Dec 1992)
    - All measures AMEX: ``dates <= 196112`` (Dec 1961)
    """
    exchcd = exchcd.copy()
    exchcd["date"] = pd.to_datetime(exchcd["date"])

    for name, mdf in measures.items():
        mdf = mdf.merge(exchcd[["permno", "date", "exchcd"]], on=["permno", "date"], how="left")
        val_col = name
        yyyymm = mdf["date"].dt.year * 100 + mdf["date"].dt.month

        # AMEX through 1961-12 for all
        amex_pre62 = (yyyymm <= 196112) & (mdf["exchcd"] == 2)
        mdf.loc[amex_pre62, val_col] = np.nan

        # NASDAQ Gibbs/VoV through 1982-12 (MATLAB writes 1982212)
        if name in ("gibbs", "vov"):
            nasdaq_pre83 = (yyyymm <= 198212) & (mdf["exchcd"] == 3)
            mdf.loc[nasdaq_pre83, val_col] = np.nan

        # NASDAQ HL/CHL through 1992-12
        if name in ("hl", "chl"):
            nasdaq_pre93 = (yyyymm <= 199212) & (mdf["exchcd"] == 3)
            mdf.loc[nasdaq_pre93, val_col] = np.nan

        measures[name] = mdf.drop(columns=["exchcd"], errors="ignore")


# ---------------------------------------------------------------------------
# make_ff_tcosts: FF factor trading costs on held legs
# (the 2x3 sorts are those of MATLAB makeFFTcosts.m; the costs are not)
# ---------------------------------------------------------------------------

#: The factor costs under the default convention, ``"dollar"``: each side goes
#: back to $1 at a trade.
FF_TC_COLS = ("mkt_tc", "smb_tc", "hml_tc", "rmw_tc", "cma_tc", "umd_tc")

#: The same costs with both sides set to the factor's capital at a trade
#: (``convention="capital"``). ``mkt_tc`` is zero under both conventions and
#: has no second column.
FF_TC_CAPITAL_COLS = tuple(f"{c}_capital" for c in FF_TC_COLS[1:])

#: Under ``"capital"``, the cost of each factor held short: the same two sides
#: exchanged, with their own capital (``analytics/held.py``, "The strategy
#: held short"). Under ``"dollar"`` a factor held short costs what it costs
#: held long, so there is no such column for the plain set.
FF_TC_CAPITAL_SHORT_COLS = tuple(f"{c}_short" for c in FF_TC_CAPITAL_COLS)

#: Every factor-cost column the stage ``compute-ff-tcosts`` writes to ``ts_data``.
FF_TC_STORED_COLS = FF_TC_COLS + FF_TC_CAPITAL_COLS + FF_TC_CAPITAL_SHORT_COLS

#: ``metadata`` key under which ``compute-ff-tcosts`` records how the stored
#: factor costs were computed, and the value's ``calculation`` for held legs.
FF_TC_RECORD_KEY = "ff_tcosts"
FF_TC_HELD = "held"
#: Version of the stored factor costs, written into the record. 2: the first
#: purchase is not in the cost series (it is recorded as ``entry_cost``), and
#: the plain columns (``smb_tc`` ..) are the ``"dollar"`` costs, with the
#: ``"capital"`` costs in ``smb_tc_capital`` .. and those of the factors held
#: short in ``smb_tc_capital_short`` ... A record without this version is that
#: of an older held-leg build, whose plain columns were ``"capital"``.
FF_TC_RECORD_VERSION = 2

_FF_TC_CONVENTIONS = ("capital", "dollar")


def ff_tc_columns(convention: str = "dollar") -> dict[str, str]:
    """Stored column -> canonical name (``mkt_tc`` .. ``umd_tc``) for ``convention``.

    ``"dollar"`` (the default) reads ``smb_tc`` .. ``umd_tc``; ``"capital"``
    reads ``smb_tc_capital`` .. ``umd_tc_capital``. ``mkt_tc`` serves both.
    """
    if convention not in _FF_TC_CONVENTIONS:
        raise ValueError(f"convention must be 'capital' or 'dollar'; got {convention!r}")
    if convention == "dollar":
        return {c: c for c in FF_TC_COLS}
    return {"mkt_tc": "mkt_tc", **{f"{c}_capital": c for c in FF_TC_COLS[1:]}}


def ff_tc_short_columns(convention: str = "dollar") -> dict[str, str]:
    """Stored column -> ``smb_tc_short`` .. ``umd_tc_short`` for ``convention``.

    The costs of the factors held short, which the generalized alpha charges
    when its net MVE portfolio is short a factor. ``"capital"`` reads
    ``smb_tc_capital_short`` ..; ``"dollar"`` has none (empty mapping): there
    a factor held short costs its ordinary cost.
    """
    if convention not in _FF_TC_CONVENTIONS:
        raise ValueError(f"convention must be 'capital' or 'dollar'; got {convention!r}")
    if convention == "dollar":
        return {}
    return {f"{c}_capital_short": f"{c}_short" for c in FF_TC_COLS[1:]}

#: June-only annual accounting matrices ``makeFFTcosts.m`` loads.
FF_TC_ANNUAL_COLS = ("be", "at", "revt", "cogs", "xsga", "xint")

_FF_TC_MOM_ALIASES = ("R12_2", "r12_2", "R", "mom")


def _row_lag(x: np.ndarray, n: int) -> np.ndarray:
    """MATLAB ``lag(x, n, nan)`` on a dense (month x stock) grid."""
    out = np.full_like(x, np.nan)
    if 0 < n < x.shape[0]:
        out[n:] = x[:-n]
    return out


def _nanmatsum(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """MATLAB ``nanmatsum``: NaN only where *both* inputs are NaN."""
    nx, ny = np.isnan(x), np.isnan(y)
    out = np.where(nx, 0.0, x) + np.where(ny, 0.0, y)
    out[nx & ny] = np.nan
    return out


def _matlab_prctile_rows(x: np.ndarray, pcts: np.ndarray) -> np.ndarray:
    """Row-wise MATLAB ``prctile``: plot positions ``(i-0.5)/n``, NaN dropped.

    Only NaN is dropped — MATLAB keeps +/-Inf as ordinary observations, and
    ``OpProf = OP / BE`` is genuinely infinite for the ~370 firm-years with
    ``BE == 0``. Treating those as missing shifts the RMW tertile breaks.
    """
    p = np.atleast_1d(np.asarray(pcts, dtype=float))
    n_rows = x.shape[0]
    out = np.full((n_rows, p.size), np.nan)
    xs = np.sort(x, axis=1)  # -inf < finite < inf < NaN
    counts = (~np.isnan(x)).sum(axis=1)
    for i in range(n_rows):
        n = int(counts[i])
        if n == 0:
            continue
        if n == 1:
            out[i, :] = xs[i, 0]
            continue
        pos = (np.arange(1, n + 1) - 0.5) * 100.0 / n
        out[i, :] = np.interp(p, pos, xs[i, :n])
    return out


def _assign_to_ptf(x: np.ndarray, bpts: np.ndarray) -> np.ndarray:
    """Port of ``assignToPtf.m``; 0 = not held (NaN comparisons stay 0)."""
    ind = np.zeros(x.shape, dtype=np.int16)
    with np.errstate(invalid="ignore"):
        ind[x < bpts[:, [0]]] = 1
        for j in range(bpts.shape[1]):
            ind[x >= bpts[:, [j]]] = j + 2
    return ind


def _make_univ_sort_ind(
    var: np.ndarray,
    ptf_num_thresh: int | Sequence[float],
    breaks_filter: np.ndarray | None = None,
) -> np.ndarray:
    """Port of ``makeUnivSortInd.m`` (name/filtered breaks; no cap weighting)."""
    thresh = np.atleast_1d(np.asarray(ptf_num_thresh, dtype=float))
    if thresh.size > 1:
        bpts = thresh
    else:
        n_ptf = int(thresh[0])
        bpts = np.array([i * 100.0 / n_ptf for i in range(1, n_ptf)], dtype=float)

    if breaks_filter is None:
        filtered = var
    else:
        # MATLAB: breaksFilterInd(breaksFilterInd == 0) = nan
        filt = np.where(np.asarray(breaks_filter, dtype=float) != 0, 1.0, np.nan)
        filtered = var * filt

    return _assign_to_ptf(var, _matlab_prctile_rows(filtered, bpts))


def _make_biv_sort_ind(
    var1: np.ndarray,
    ptf_num_thresh1: int | Sequence[float],
    var2: np.ndarray,
    ptf_num_thresh2: int | Sequence[float],
    breaks_filter: np.ndarray | None = None,
) -> np.ndarray:
    """Port of ``makeBivSortInd.m`` for ``sortType = 'unconditional'``."""
    ind1 = _make_univ_sort_ind(var1, ptf_num_thresh1, breaks_filter)
    ind2 = _make_univ_sort_ind(var2, ptf_num_thresh2, breaks_filter)
    n2 = int(ind2.max())
    both = (ind1 > 0) & (ind2 > 0)
    ind = np.zeros(ind1.shape, dtype=np.int16)
    ind[both] = (ind1[both] - 1) * n2 + ind2[both]
    return ind


def _month_rows(dates: pd.DatetimeIndex) -> np.ndarray:
    """Row of each date on a complete monthly calendar that starts at ``dates[0]``."""
    months = dates.year.to_numpy() * 12 + dates.month.to_numpy()
    if (np.diff(months) <= 0).any():
        raise ValueError("dates must be increasing, one per calendar month")
    return (months - months[0]).astype(np.int64)


def ff_tcosts_from_matrices(
    dates: pd.DatetimeIndex,
    *,
    tcosts: np.ndarray,
    me: np.ndarray,
    ret: np.ndarray,
    be: np.ndarray,
    at: np.ndarray,
    revt: np.ndarray,
    cogs: np.ndarray,
    xsga: np.ndarray,
    xint: np.ndarray,
    mom: np.ndarray,
    nyse: np.ndarray,
) -> pd.DataFrame:
    """Trading costs of SMB, HML, RMW, CMA and UMD on held legs.

    The portfolios are those of ``makeFFTcosts.m``: 2x3 sorts on size and
    book-to-market, operating profitability, investment or prior return, with
    NYSE breakpoints. Every accounting matrix (``be``/``at``/``revt``/
    ``cogs``/``xsga``/``xint``) must be June-only, so those sorts exist in
    June only; ``mom`` (MATLAB ``R``) is monthly.

    Each factor is a long/short pair of sides, and a side is the equal-share
    average of the two or three value-weighted 2x3 portfolios the factor is
    long (or short), as in the published factor returns
    (:func:`assayinganomalies.analytics.held.held_composite_long_short`):

    - each 2x3 portfolio is bought in a month in which its sort exists and
      left alone until the next such month (each June for SMB, HML, RMW and
      CMA, every month for UMD); positions grow with ``ret``;
    - at the end of every other month the side brings its portfolios back to
      equal shares, which is what averaging their returns every month assumes,
      and pays that month's half-spreads on the dollars moved;
    - at a trade the side moves in one netted step to the new portfolios;
    - a cost is the half-spreads paid over the side's value entering the
      month. The first purchase is not in the cost series; its cost is
      returned separately (``attrs["entry_cost"]``).

    Returns
    -------
    pd.DataFrame
        Date-indexed. ``mkt_tc`` (0 by construction); ``smb_tc`` .. ``umd_tc``,
        with each side set back to $1 at a trade (``convention="dollar"``,
        the default); ``smb_tc_capital`` .. ``umd_tc_capital``, with both
        sides set to the factor's capital (``"capital"``);
        ``smb_tc_capital_short`` .., the ``"capital"`` cost of the factor held
        short (its sides exchanged); the two sides'
        turnover under each (``smb_to_short``, ``smb_to_long``,
        ``smb_to_short_capital``, ...); the part of each cost that comes from
        the monthly re-splits (``smb_tc_resplit``, the same under both
        conventions); and the long-minus-short return of the held sides
        (``smb_held`` ..), for comparison with the published factor. Costs and
        turnover are 0, never NaN, in a month without a trade or a re-split.
        ``attrs["capital_restarts"]`` counts, per factor, the trades at which
        the capital was zero or negative and the factor restarted with $1
        sides (``"capital"`` only). ``attrs["entry_cost"]`` is, per factor,
        the cost of its first purchase (a decimal, both sides; the same under
        both conventions), which is in none of the cost columns.
    """
    from ..analytics.held import held_composite_long_short, held_legs

    btm = be / _row_lag(me, 6)
    # OP = REVT + nanmatsum(-COGS, -nanmatsum(XSGA, XINT))
    op = revt + _nanmatsum(-cogs, -_nanmatsum(xsga, xint))
    with np.errstate(invalid="ignore", divide="ignore"):
        op_prof = op / be
        inv = -at / _row_lag(at, 12)

    # The 2x3 portfolios: 1..3 small (low, middle, high), 4..6 big. (MATLAB
    # takes the number of portfolios from indFF93 for all four sorts; each
    # has six here, which is the same on CRSP.)
    tertiles = (30.0, 70.0)
    sorts = {
        "ff93": _make_biv_sort_ind(me, 2, btm, tertiles, nyse),
        "op": _make_biv_sort_ind(me, 2, op_prof, tertiles, nyse),
        "inv": _make_biv_sort_ind(me, 2, inv, tertiles, nyse),
        "mom": _make_biv_sort_ind(me, 2, mom, tertiles, nyse),
    }
    # factor: (sort, short portfolios, long portfolios)
    specs = {
        "smb": ("ff93", (4, 5, 6), (1, 2, 3)),
        "hml": ("ff93", (1, 4), (3, 6)),
        "rmw": ("op", (1, 4), (3, 6)),
        "cma": ("inv", (1, 4), (3, 6)),
        "umd": ("mom", (1, 4), (3, 6)),
    }

    # The core needs a complete monthly calendar: a month absent from `dates`
    # becomes an empty row.
    rows = _month_rows(pd.DatetimeIndex(dates))
    n_rows = int(rows[-1]) + 1 if rows.size else 0
    complete = n_rows == rows.size

    def calendar(x: np.ndarray, fill: float = np.nan) -> np.ndarray:
        if complete:
            return x
        out = np.full((n_rows, x.shape[1]), fill)
        out[rows] = x
        return out

    ret_c, me_c, tc_c = calendar(ret), calendar(me), calendar(tcosts)

    out = pd.DataFrame(index=dates)
    out["mkt_tc"] = 0.0
    restarts: dict[str, int] = {}
    entry: dict[str, float] = {}
    cached: tuple[str, Any] | None = None
    for name, (sort, short, long) in specs.items():
        restarts[name] = 0
        entry[name] = 0.0
        ind = sorts[sort]
        if not (ind > 0).any():
            # No sort in any month (no accounting data, or no momentum).
            out[f"{name}_tc_capital_short"] = 0.0
            for suffix in ("", "_capital"):
                out[f"{name}_tc{suffix}"] = 0.0
                out[f"{name}_to_short{suffix}"] = 0.0
                out[f"{name}_to_long{suffix}"] = 0.0
            out[f"{name}_tc_resplit"] = 0.0
            out[f"{name}_held"] = np.nan
            continue
        if cached is None or cached[0] != sort:  # SMB and HML share the size x B/M portfolios
            cached = None  # free the previous sort's legs first
            cached = (
                sort,
                held_legs(ret_c, me_c, tc_c, calendar(ind, 0.0), "v", n_ptfs=6, monthly_holdings=True),
            )
        legs = cached[1]
        for convention, suffix in (("dollar", ""), ("capital", "_capital")):
            ls = held_composite_long_short(
                legs, short, long, convention=convention, label=f"factor {name.upper()}"
            )
            out[f"{name}_tc{suffix}"] = ls.cost[rows]
            out[f"{name}_to_short{suffix}"] = ls.turnover_short[rows]
            out[f"{name}_to_long{suffix}"] = ls.turnover_long[rows]
            if convention == "capital":
                restarts[name] = int((ls.capital <= 0).sum())  # NaN compares False
                out[f"{name}_tc_capital_short"] = ls.cost_exchanged[rows]
        out[f"{name}_tc_resplit"] = ls.resplit_cost[rows]
        out[f"{name}_held"] = ls.gross[rows]
        entry[name] = float(ls.entry_cost)
        LOGGER.info(
            "FF factor tcosts %s: mean=%.6f max=%.6f (capital: mean=%.6f; monthly re-splits: "
            "mean=%.6f; entry cost, not in the series: %.6f)",
            name,
            float(out[f"{name}_tc"].mean()),
            float(out[f"{name}_tc"].max()),
            float(out[f"{name}_tc_capital"].mean()),
            float(out[f"{name}_tc_resplit"].mean()),
            entry[name],
        )
    out.attrs["capital_restarts"] = restarts
    out.attrs["entry_cost"] = entry
    return out


def _wide(panel: pd.DataFrame, col: str, dates: pd.Index, permnos: pd.Index) -> np.ndarray:
    """(date x permno) float matrix for one panel column, on a fixed grid."""
    values = pd.to_numeric(panel[col], errors="coerce")
    wide = values.unstack("permno")
    return wide.reindex(index=dates, columns=permnos).to_numpy(dtype=float)


def _panel_dates(panel: pd.DataFrame) -> pd.Index:
    if isinstance(panel.index, pd.MultiIndex):
        return panel.index.get_level_values("date").unique().sort_values()
    if "date" in getattr(panel, "columns", []):
        return pd.Index(sorted(pd.to_datetime(panel["date"]).unique()))
    raise ValueError("panel must have MultiIndex(date, permno) or a date column")


def make_ff_tcosts_table(
    panel: pd.DataFrame,
    tcost_series: pd.Series,
    annual: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """The factor-cost columns the build stores, under both conventions.

    Inputs as in :func:`make_ff_tcosts`. Returns a date-indexed frame with
    ``FF_TC_STORED_COLS``: ``mkt_tc``, ``smb_tc`` .. ``umd_tc``
    (``"dollar"``), ``smb_tc_capital`` .. ``umd_tc_capital`` (``"capital"``) and
    ``smb_tc_capital_short`` .. (``"capital"``, the factor held short).
    ``attrs["capital_restarts"]`` is the per-factor count described in
    :func:`ff_tcosts_from_matrices`, and ``attrs["entry_cost"]`` each factor's
    entry cost. Two frames that are not stored ride
    along in ``attrs`` (``None`` when the costs are zeros for want of inputs):
    ``held_returns``, the long-minus-short return of each factor's held sides,
    and ``resplit_costs``, the part of each cost that comes from the monthly
    re-splits.
    """
    return _ff_tcosts_or_zeros(panel, tcost_series, annual, _panel_dates(panel))


def make_ff_tcosts(
    panel: pd.DataFrame,
    tcost_series: pd.Series,
    annual: pd.DataFrame | None = None,
    *,
    convention: str = "dollar",
) -> pd.DataFrame:
    """
    Fama-French factor trading costs (Detzel, Novy-Marx, Velikov) on held legs.

    The portfolios are those of MATLAB ``makeFFTcosts.m`` (2x3 sorts with NYSE
    breakpoints; a factor side is the equal-share average of its
    value-weighted 2x3 portfolios). The costs are those of
    :func:`ff_tcosts_from_matrices`: each 2x3 portfolio is bought when its
    sort exists (each June for SMB, HML, RMW, CMA; every month for UMD) and
    held until the next trade, as the univariate sort does for a test signal,
    and in the months between trades each side pays to bring its portfolios
    back to equal shares, as the published factor returns assume. They do not
    reproduce MATLAB's factor costs.

    ``mkt_tc`` is zero by construction.

    Parameters
    ----------
    panel : pd.DataFrame
        MultiIndex (date, permno) with ``ret``, ``me``, ``nyse_flag`` and a
        momentum column (``R12_2``, MATLAB ``R``).
    tcost_series : pd.Series
        Stock-level effective half-spreads, MultiIndex (date, permno).
    annual : pd.DataFrame, optional
        MultiIndex (date, permno) June-only accounting inputs: ``be``, ``at``,
        ``revt``, ``cogs``, ``xsga``, ``xint``. When omitted they are read from
        ``panel`` and masked to June. If any input is unavailable the
        non-market costs are zero, with a warning.
    convention : {"capital", "dollar"}
        The size of a factor's two sides after a trade: $1 each (the
        default) or the factor's capital. The same choice as in
        ``run_univariate_sort``.

    Returns
    -------
    pd.DataFrame
        Date-indexed: mkt_tc, smb_tc, hml_tc, rmw_tc, cma_tc, umd_tc under
        ``convention``, plus stacked ff3_tc .. ff6_tc; under ``"capital"``
        also smb_tc_short .. umd_tc_short, the cost of each factor held short
        (for ``calc_gen_alpha(..., factor_tcosts_short=)``).
    """
    columns = ff_tc_columns(convention)
    table = make_ff_tcosts_table(panel, tcost_series, annual)
    result = table[list(columns)].rename(columns=columns)
    result.attrs = {}
    if convention == "capital":
        result.attrs["capital_restarts"] = table.attrs.get("capital_restarts", {})

    short = ff_tc_short_columns(convention)
    for stored, name in short.items():
        result[name] = table[stored]

    for cols, name in [
        (["mkt_tc", "smb_tc", "hml_tc"], "ff3_tc"),
        (["mkt_tc", "smb_tc", "hml_tc", "umd_tc"], "ff4_tc"),
        (["mkt_tc", "smb_tc", "hml_tc", "rmw_tc", "cma_tc"], "ff5_tc"),
        (["mkt_tc", "smb_tc", "hml_tc", "rmw_tc", "cma_tc", "umd_tc"], "ff6_tc"),
    ]:
        result[name] = result[cols].sum(axis=1)

    return result


def _ff_tcosts_or_zeros(
    panel: pd.DataFrame,
    tcost_series: pd.Series | None,
    annual: pd.DataFrame | None,
    dates: pd.Index,
) -> pd.DataFrame:
    """Compute the costs when every input is present; else zeros, loudly."""
    def _zeros(reason: str) -> pd.DataFrame:
        LOGGER.warning(
            "FF factor trading costs: %s; non-market factor costs set to zero "
            "(mkt_tc is 0 by construction)", reason,
        )
        out = pd.DataFrame(index=dates)
        for col in FF_TC_STORED_COLS:
            out[col] = 0.0
        out.attrs["capital_restarts"] = {}
        out.attrs["entry_cost"] = {}
        out.attrs["held_returns"] = None
        out.attrs["resplit_costs"] = None
        return out

    if not isinstance(panel.index, pd.MultiIndex):
        return _zeros("panel is not a (date, permno) panel")
    if tcost_series is None or tcost_series.dropna().empty:
        return _zeros("no stock-level tcosts")

    mom_col = next((c for c in _FF_TC_MOM_ALIASES if c in panel.columns), None)
    missing = [c for c in ("ret", "me", "nyse_flag") if c not in panel.columns]
    if mom_col is None:
        missing.append("R12_2")
    if missing:
        return _zeros(f"panel missing {missing}")

    if annual is None:
        annual_missing = [c for c in FF_TC_ANNUAL_COLS if c not in panel.columns]
        if annual_missing:
            return _zeros(f"annual accounting inputs missing {annual_missing}")
        june = panel.index.get_level_values("date").month == 6
        annual = panel.loc[june, list(FF_TC_ANNUAL_COLS)]
    else:
        annual_missing = [c for c in FF_TC_ANNUAL_COLS if c not in annual.columns]
        if annual_missing:
            return _zeros(f"annual accounting inputs missing {annual_missing}")

    # MATLAB's grid is the CRSP universe; a permno with accounting data but no
    # market cap can never be assigned to a portfolio, so panel permnos suffice.
    permnos = panel.index.get_level_values("permno").unique().sort_values()
    tc = tcost_series.rename("tcost").to_frame()
    tc.index = tc.index.set_names(["date", "permno"])

    kwargs = {
        "tcosts": _wide(tc, "tcost", dates, permnos),
        "me": _wide(panel, "me", dates, permnos),
        "ret": _wide(panel, "ret", dates, permnos),
        "mom": _wide(panel, mom_col, dates, permnos),
        "nyse": _wide(panel, "nyse_flag", dates, permnos),
    }
    for col in FF_TC_ANNUAL_COLS:
        kwargs[col] = _wide(annual, col, dates, permnos)

    kwargs["nyse"] = np.nan_to_num(kwargs["nyse"], nan=0.0)

    res = ff_tcosts_from_matrices(pd.DatetimeIndex(dates), **kwargs)
    LOGGER.info(
        "FF factor trading costs: %d months x %d stocks (mkt_tc=0 by construction)",
        len(dates), len(permnos),
    )
    factors = [c[: -len("_tc")] for c in FF_TC_COLS[1:]]
    out = res[list(FF_TC_STORED_COLS)]
    out.attrs["capital_restarts"] = res.attrs.get("capital_restarts", {})
    out.attrs["entry_cost"] = res.attrs.get("entry_cost", {})
    out.attrs["held_returns"] = res[[f"{f}_held" for f in factors]].rename(
        columns=lambda c: c[: -len("_held")]
    )
    out.attrs["resplit_costs"] = res[[f"{f}_tc_resplit" for f in factors]].rename(
        columns=lambda c: c[: -len("_tc_resplit")]
    )
    return out


__all__ = [
    "compute_corwin_schultz",
    "compute_abdi_ranaldi",
    "compute_kyle_obizhaeva",
    "load_cpi_aucns",
    "load_gibbs",
    "load_hf_spreads",
    "fill_missing_tcosts",
    "combine_lf_spreads",
    "make_trading_costs",
    "make_ff_tcosts",
    "ff_tcosts_from_matrices",
    "make_ff_tcosts_table",
    "ff_tc_columns",
    "ff_tc_short_columns",
    "FF_TC_COLS",
    "FF_TC_CAPITAL_COLS",
    "FF_TC_CAPITAL_SHORT_COLS",
    "FF_TC_STORED_COLS",
    "FF_TC_ANNUAL_COLS",
    "FF_TC_RECORD_KEY",
    "FF_TC_HELD",
    "FF_TC_RECORD_VERSION",
]
