"""
CRSP monthly transformations.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING
import numpy as np
import pandas as pd
import warnings

from ..config import AssayConfig

if TYPE_CHECKING:  # pragma: no cover - import cycle: crsp_source imports this module
    from ..ingest.crsp_source import CRSPSource

LOGGER = logging.getLogger("assayinganomalies.transforms.crsp_monthly")


def _month_end(ts: pd.Series) -> pd.Series:
    """
    Normalize datetimes to month-end (00:00:00) to match CRSP monthly keys.
    """
    dt = pd.to_datetime(ts, errors="coerce")
    return (dt + pd.offsets.MonthEnd(0)).dt.normalize()


def _date_yyyymm(dt: pd.Series) -> pd.Series:
    d = pd.to_datetime(dt, errors="coerce")
    return (d.dt.year * 100 + d.dt.month).astype("Int64")


def _apply_matlab_delisting_adjustment(
    df: pd.DataFrame,
    *,
    msedelist: pd.DataFrame,
    months_yyyymm: pd.Series,
) -> pd.DataFrame:
    """
    Apply delisting adjustment to match MATLAB exactly (makeCRSPDerivedVariables.m).

    MATLAB logic (conceptually, on a balanced [month x permno] matrix):
      - Start with ret = ret_x_dl.
      - For each delist record (permno, yyyymm, dlret):
          r_dt   = index of delist month in the global month vector
          r_last = (index of last finite ret for this permno) + 1
          if ret(r_dt) is NaN and ret(r_dt-1) is finite: assign dlret at r_dt
          else: assign dlret at min(r_dt, r_last)
          ret(r, permno) = dlret   (note: replacement, not multiplicative combine)

    This function reproduces the same behavior on a long DataFrame, creating the
    (permno, date) row if it doesn't exist (other fields remain NA).
    """

    if msedelist.empty:
        out = df.copy()
        out["ret"] = out.get("ret_x_dl", pd.NA)
        out["dlret"] = pd.NA if "dlret" not in out.columns else out["dlret"]
        return out

    out = df.copy()

    # Base: raw returns (not delisting-adjusted).
    out["ret_x_dl"] = pd.to_numeric(out.get("ret_x_dl", pd.NA), errors="coerce")
    out["ret"] = out["ret_x_dl"]

    # Build global month position map (MATLAB uses the global numeric `dates` vector: YYYYMM),
    # which is bounded to the sample window. We should NOT extend this vector using msedelist,
    # because MATLAB only assigns delisting returns within `dates`.
    base_months = pd.Series(months_yyyymm).dropna().astype("int64").drop_duplicates().sort_values().reset_index(drop=True)
    months_yyyymm = base_months
    month_to_pos = {int(v): i for i, v in enumerate(months_yyyymm.to_list())}

    # Map each row to a global month position via YYYYMM.
    if "yyyymm" not in out.columns:
        raise ValueError("Expected column 'yyyymm' on monthly panel before delisting adjustment.")
    out["__month_pos"] = out["yyyymm"].map(month_to_pos).astype("Int64")

    # Base return lookup: (permno, month_pos) -> ret_x_dl (missing rows behave as NaN, like MATLAB matrices).
    base = out[["permno", "__month_pos", "ret_x_dl"]].copy()
    base["permno"] = pd.to_numeric(base["permno"], errors="coerce").astype("Int64")
    base = base.dropna(subset=["permno", "__month_pos"])
    base["__month_pos"] = base["__month_pos"].astype("int64")
    base = base.drop_duplicates(subset=["permno", "__month_pos"], keep="last")
    base_idx = pd.MultiIndex.from_frame(base[["permno", "__month_pos"]])
    base_ret = pd.Series(base["ret_x_dl"].to_numpy(), index=base_idx)

    # MATLAB recomputes r_last inside the loop, but since assignments only ever set values (finite)
    # and never remove finiteness, the "last finite month" is monotone. We can maintain it incrementally.
    is_finite_base = np.isfinite(pd.to_numeric(base_ret, errors="coerce").to_numpy(dtype="float64", copy=False))
    if is_finite_base.any():
        last_finite_pos = (
            pd.DataFrame(
                {
                    "permno": base_idx.get_level_values(0).to_numpy(),
                    "__month_pos": base_idx.get_level_values(1).to_numpy(),
                    "__finite": is_finite_base,
                }
            )
            .loc[lambda x: x["__finite"], ["permno", "__month_pos"]]
            .groupby("permno", sort=False)["__month_pos"]
            .max()
        )
    else:
        last_finite_pos = pd.Series(dtype="int64")

    # Prepare delisting records (match MATLAB filters).
    d = msedelist.copy()
    if "dlstdt" not in d.columns or "permno" not in d.columns:
        # Can't apply without keys; keep ret as ret_x_dl.
        out["dlret"] = pd.NA if "dlret" not in out.columns else out["dlret"]
        out = out.drop(columns=["__month_pos"])
        return out

    d["permno"] = pd.to_numeric(d["permno"], errors="coerce").astype("Int64")
    d["dlstdt"] = pd.to_datetime(d["dlstdt"], errors="coerce")
    d["dlret"] = pd.to_numeric(d.get("dlret", pd.NA), errors="coerce")

    # MATLAB drops the max dlstdt row (often a placeholder).
    if d["dlstdt"].notna().any():
        max_dlstdt = d["dlstdt"].max()
        d = d[d["dlstdt"] != max_dlstdt]

    # Keep only permnos present in the panel.
    permnos_in_panel = pd.Index(pd.to_numeric(out["permno"], errors="coerce").dropna().astype("int64").unique())
    d = d[d["permno"].isin(permnos_in_panel)]

    # Align to YYYYMM (MATLAB uses month-of-date, not calendar month-end).
    # Use scratch columns without leading/double underscores to avoid pandas.itertuples() mangling.
    d["dl_yyyymm"] = _date_yyyymm(d["dlstdt"])
    d["dl_pos"] = d["dl_yyyymm"].map(month_to_pos).astype("Int64")
    d = d.dropna(subset=["permno", "dl_pos", "dlret"])

    if d.empty:
        out["dlret"] = pd.NA if "dlret" not in out.columns else out["dlret"]
        out = out.drop(columns=["__month_pos"])
        return out

    # IMPORTANT: MATLAB loops in the table's existing order. To match it exactly,
    # we do NOT re-sort the delisting table here.
    d = d.reset_index(drop=True).copy()

    assigned: dict[tuple[int, int], float] = {}

    # Helper for current ret_x_dl at (permno, pos): assignment overrides base.
    def _cur_ret(pn: int, pos: int) -> float:
        if (pn, pos) in assigned:
            return assigned[(pn, pos)]
        try:
            v = base_ret.loc[(pn, pos)]
        except KeyError:
            return float("nan")
        return float(pd.to_numeric(v, errors="coerce"))

    # Apply MATLAB rule per record.
    for row in d.itertuples(index=False):
        pn = int(row.permno)
        dl_pos = int(row.dl_pos)
        dlret_val = float(row.dlret)

        # MATLAB skips permnos with no finite history: r_last = [] => no assignment.
        if pn not in last_finite_pos.index:
            continue

        # r_last = last finite + 1 (global month positions).
        r_last = int(last_finite_pos.loc[pn]) + 1

        # ret at delist month and previous month (previous month = dl_pos-1 in global calendar).
        ret_dt = _cur_ret(pn, dl_pos)
        ret_prev = _cur_ret(pn, dl_pos - 1) if dl_pos - 1 >= 0 else float("nan")

        # MATLAB chooses where to assign:
        # 1) If ret at delist month is NaN and previous month is finite -> assign to delist month.
        # 2) Else assign to r_last IF r_last < length(dates) (strict), i.e. never assign into the
        #    final month of the dates vector.
        max_assign_pos = len(months_yyyymm) - 2  # last allowed 0-based position (MATLAB strict <)
        assign_pos: int | None
        if np.isnan(ret_dt) and np.isfinite(ret_prev):
            assign_pos = dl_pos
        elif r_last <= max_assign_pos:
            assign_pos = r_last
        else:
            assign_pos = None

        if assign_pos is not None:
            assigned[(pn, assign_pos)] = dlret_val
            if np.isfinite(dlret_val) and assign_pos > int(last_finite_pos.loc[pn]):
                last_finite_pos.loc[pn] = assign_pos

    if not assigned:
        out["dlret"] = out.get("dlret", pd.NA)
        out = out.drop(columns=["__month_pos"])
        return out

    assigns_df = pd.DataFrame(
        [(pn, pos, val) for (pn, pos), val in assigned.items()],
        columns=["permno", "__month_pos", "__dlret_assign"],
    )
    assigns_df["yyyymm"] = assigns_df["__month_pos"].map(lambda i: int(months_yyyymm.iloc[int(i)]))
    assigns_df = assigns_df.drop(columns=["__month_pos"])

    # Update existing rows (match MATLAB's matrix overwrite at the YYYYMM cell).
    out = out.merge(assigns_df, on=["permno", "yyyymm"], how="left")
    mask = out["__dlret_assign"].notna()
    out.loc[mask, "ret"] = out.loc[mask, "__dlret_assign"]
    out["dlret"] = out.get("dlret", pd.NA)
    out.loc[mask, "dlret"] = out.loc[mask, "__dlret_assign"]
    out = out.drop(columns=["__dlret_assign"])

    # Add rows for assignment months that didn't exist in the raw long data (MATLAB balanced matrix effect).
    out_key = out[["permno", "yyyymm"]].dropna()
    missing = assigns_df.merge(out_key, on=["permno", "yyyymm"], how="left", indicator=True)
    missing = missing[missing["_merge"] == "left_only"].drop(columns=["_merge"]).reset_index(drop=True)
    if not missing.empty:
        new_rows = pd.DataFrame({col: pd.NA for col in out.columns}, index=range(len(missing)))
        # IMPORTANT: assign via numpy arrays to avoid pandas index-alignment bugs when `missing`
        # has non-contiguous indices (which would otherwise create NULL permno/date rows).
        new_rows["permno"] = missing["permno"].astype("Int64").to_numpy()
        new_rows["yyyymm"] = pd.to_numeric(missing["yyyymm"], errors="coerce").astype("Int64").to_numpy()
        # Canonical month-end date for the monthly panel (stable single row per month).
        new_rows["date"] = pd.to_datetime(new_rows["yyyymm"].astype(str) + "01", format="%Y%m%d", errors="coerce") + pd.offsets.MonthEnd(0)
        new_rows["ret_x_dl"] = pd.NA
        new_rows["ret"] = pd.to_numeric(missing["__dlret_assign"], errors="coerce").to_numpy()
        new_rows["dlret"] = pd.to_numeric(missing["__dlret_assign"], errors="coerce").to_numpy()
        # Inherit shrcd from permno's existing data (so synthetic rows pass downstream shrcd filters).
        if "shrcd" in out.columns:
            permno_shrcd = out.groupby("permno")["shrcd"].first().dropna()
            new_rows["shrcd"] = new_rows["permno"].map(permno_shrcd)
        # Pandas emits a FutureWarning about concat dtype inference when one side is empty/all-NA.
        # This concat is intentional (MATLAB balanced-matrix behavior); suppress the warning to
        # keep the setup output readable without changing calculations.
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                category=FutureWarning,
                message=r"The behavior of DataFrame concatenation with empty or all-NA entries is deprecated\\..*",
            )
            out = pd.concat([out, new_rows], ignore_index=True)

    out = out.drop(columns=["__month_pos"])
    return out


def _attach_informational_dlret(
    df: pd.DataFrame,
    *,
    delists: pd.DataFrame,
) -> pd.DataFrame:
    """
    The no-overlay counterpart of `_apply_matlab_delisting_adjustment`.

    On a tape whose ``ret`` already contains the delisting payoff (CIZ --
    ``mthret`` is daily-compounded and the payoff arrives as an extra daily row
    on ``stkdelists.deldlydt``), MATLAB's
    overlay must not run: replacing ``ret`` with ``dlret`` there would count the
    payoff twice, once inside ``mthret`` and once on top of it.

    But ``dlret`` should not simply vanish from the panel either. Users read it,
    the SIZ-vs-CIZ report needs it, and a column silently full of NaN under one
    tape and populated under the other is the kind of difference that gets
    discovered by a broken regression six months later. So this attaches
    ``dlret`` as *information*:

    * ``ret`` is set to ``ret_x_dl`` -- an identity, not an adjustment. Under
      this tape ``ret == ret_x_dl`` by construction, and stating it here means
      no caller has to know which tape produced the panel.
    * ``dlret`` is filled from the delisting record on the **delisting month
      only**, matched on ``(permno, yyyymm)``. Every other month stays NaN. It
      is never carried forward, never applied, never compounded.

    A permno delists once, so the match cannot fan out; a defensive
    ``drop_duplicates`` keeps that true even on a malformed extract.

    Contrast with the SIZ path: there, ``dlret`` is both an input *and* an
    output of the overlay (it can be moved to a neighbouring month, and it can
    create a whole new panel row for a permno whose last return is missing).
    Here it is only ever an annotation on a row that already exists.
    """
    out = df.copy()
    out["ret_x_dl"] = pd.to_numeric(out.get("ret_x_dl", pd.NA), errors="coerce")
    out["ret"] = out["ret_x_dl"]
    out["dlret"] = np.nan

    if delists is None or getattr(delists, "empty", True):
        return out
    d = delists.copy()
    d.columns = [str(c).lower() for c in d.columns]
    if not {"permno", "dlstdt", "dlret"} <= set(d.columns):
        return out

    d["permno"] = pd.to_numeric(d["permno"], errors="coerce")
    d["dlret"] = pd.to_numeric(d["dlret"], errors="coerce")
    d["yyyymm"] = _date_yyyymm(pd.to_datetime(d["dlstdt"], errors="coerce"))
    d = d.dropna(subset=["permno", "yyyymm", "dlret"])
    if d.empty:
        return out
    d["permno"] = d["permno"].astype("int64")
    # One record per (permno, month). ``keep="last"`` mirrors the SIZ overlay's
    # sort-then-apply order, where a later record wins.
    d = d[["permno", "yyyymm", "dlret"]].drop_duplicates(
        subset=["permno", "yyyymm"], keep="last"
    )

    # ``-1`` for an unusable permno rather than a raise: it matches nothing in
    # ``d``, so such a row simply keeps its NaN ``dlret``.
    keys = pd.DataFrame({
        "permno": pd.to_numeric(out["permno"], errors="coerce").fillna(-1).astype("int64"),
        "yyyymm": pd.to_numeric(out["yyyymm"], errors="coerce"),
    })
    merged = keys.merge(d, on=["permno", "yyyymm"], how="left")
    out["dlret"] = merged["dlret"].to_numpy()
    return out


def _merge_on_interval(
    base: pd.DataFrame,
    aux: pd.DataFrame,
    start_col: str,
    end_col: str,
    cols: list[str],
    *,
    drop_outside: bool = False,
) -> pd.DataFrame:
    """Helper to merge aux records where base.date is within [start, end].

    Day-level comparison matching MATLAB ``date ∈ [namedt, nameendt]``
    (MSEEXCHDATES / ``makeCRSPMonthlyData.m``).

    If multiple aux records match, keeps the one with the latest start date.

    When ``drop_outside=True`` (MATLAB MSEEXCHDATES behavior), rows whose date
    falls outside every interval for that permno are dropped (except rows with
    NaT interval bounds, which are kept with merged values cleared).
    """
    if aux.empty:
        return base
    if start_col not in aux.columns or end_col not in aux.columns:
        return base

    aux = aux.copy()
    aux["__start"] = pd.to_datetime(aux[start_col], errors="coerce")
    aux["__end"] = pd.to_datetime(aux[end_col], errors="coerce")

    base = base.copy()
    base["__row_id"] = range(len(base))  # preserve original row identity
    base["__date_dt"] = pd.to_datetime(base["date"], errors="coerce")

    merged = base.merge(aux[["permno", "__start", "__end", *cols]], on="permno", how="left")

    # Exact day-level date comparison (MATLAB date ∈ [namedt, nameendt]).
    mask = (merged["__date_dt"] >= merged["__start"]) & (merged["__date_dt"] <= merged["__end"])

    if drop_outside:
        # Keep rows where we lack an interval (NaT boundaries).
        keep = mask | merged["__start"].isna() | merged["__end"].isna()
        merged = merged.loc[keep].copy()
        # Recompute mask on filtered dataframe for the "clear non-matching values" step below.
        # Rows kept due to NaT bounds should have their merged values cleared.
        mask = mask.loc[keep].copy()

    # For remaining non-matching rows (including NaT bounds), clear merged values.
    merged.loc[~mask, cols] = pd.NA
    merged.loc[~mask, "__start"] = pd.NaT

    # Deduplicate: for each original row, keep the record with the latest valid start date
    merged = merged.sort_values("__start", ascending=False, na_position="last")
    merged = merged.drop_duplicates(subset=["__row_id"], keep="first")
    merged = merged.sort_values("__row_id").reset_index(drop=True)

    merged = merged.drop(columns=["__start", "__end", "__date_dt", "__row_id"])
    return merged


def _cumret_window(group: pd.DataFrame, window: int, lag: int, col: str) -> pd.Series:
    """
    Compute rolling *gross* past-performance over `window` months, skipping the last `lag` months.
    
    Matches MATLAB `makePastPerformance.m`:
    - Treat NaN returns as 0% during calculation (i.e., multiply by 1.0 for that month).
    - Set the output to NaN where the *original* return at the same time index was NaN.

    IMPORTANT:
    - The MATLAB function returns a *gross* return (product of 1+ret), not net (minus 1).
    - In the analytics layer, signals are lagged by 1 month before sorting, so callers
      should define `lag`/`window` to match MATLAB’s raw signal timing.
    """
    ret_raw = pd.to_numeric(group[col], errors="coerce")
    is_nan = ret_raw.isna()
    
    # Temporarily fill NaN with 0 for calculation (like MATLAB)
    vals = 1 + ret_raw.fillna(0.0)
    shifted = vals.shift(lag)
    prod = shifted.rolling(window, min_periods=window).apply(np.prod, raw=True)
    result = prod
    
    # Set result to NaN where original return was NaN (like MATLAB: R(isNanInd) = nan)
    result[is_nan] = np.nan
    return result


def _cumret_window_global_months(
    group: pd.DataFrame,
    window: int,
    lag: int,
    col: str,
    *,
    start_year: int,
    start_month: int,
    n_months: int,
    data_start_pos: int = 0,
) -> pd.Series:
    """
    MATLAB-parity past-performance on a *global* month grid.

    MATLAB `makePastPerformance(ret, from, to)` operates on a balanced [T x N] matrix where:
    - Missing returns are treated as 0% inside the window
    - Output is set to NaN wherever ret(t, i) is NaN
    - Output is set to NaN for the first (from-1) months of the *global* sample:
        R(1:from-1,:) = nan
      MATLAB's matrix starts at the first month with CRSP data (192512), so
      `data_start_pos` shifts the mask to that month on our calendar grid
      (which starts at January of `start_year`) — a full window must exist
      *within the data sample*, so e.g. R12_2 is NaN through 1926-10.

    Implemented for a long DataFrame group (one permno):
    - Expand into a length-n_months vector on the global calendar
    - Compute the gross window (product of 1+ret) with lag/window
    - Project back to the observed rows for this permno
    """
    g = group.sort_values("date")
    dates = pd.to_datetime(g["date"], errors="coerce")
    y = dates.dt.year.to_numpy()
    m = dates.dt.month.to_numpy()
    pos = (y - int(start_year)) * 12 + (m - int(start_month))

    ret_raw = pd.to_numeric(g[col], errors="coerce").to_numpy(dtype="float64", copy=False)
    ret_full = np.full(int(n_months), np.nan, dtype="float64")
    # Fill observed months
    valid = (pos >= 0) & (pos < n_months)
    ret_full[pos[valid]] = ret_raw[valid]

    is_nan = np.isnan(ret_full)
    # Missing returns treated as 0% (log(1+0)=0 => multiplicative 1.0)
    #
    # RuntimeWarnings here (divide-by-zero/invalid) are expected in real CRSP data due to
    # -100% returns (log1p(-1)=-inf) and are handled downstream; suppress to keep logs clean.
    with np.errstate(divide="ignore", invalid="ignore", over="ignore", under="ignore"):
        log1p = np.log1p(np.where(is_nan, 0.0, ret_full))

    # Apply lag (to=lag): RR = lag(tret, to, nan)
    shifted = np.full_like(log1p, np.nan)
    if lag > 0:
        shifted[lag:] = log1p[:-lag]
    else:
        shifted[:] = log1p

    # Rolling sum over `window` months (from-to = window)
    shifted_filled = np.where(np.isnan(shifted), 0.0, shifted)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore", under="ignore"):
        c = np.concatenate([[0.0], np.cumsum(shifted_filled)])
        sums = c[window:] - c[:-window]  # aligns to end positions window-1..N-1
    rr = np.full(int(n_months), np.nan, dtype="float64")
    rr[window - 1 :] = sums

    # Global sample mask: first (from-1) months *of the data sample* are NaN
    from_ = int(lag + window)
    rr[: int(data_start_pos) + from_ - 1] = np.nan

    gross = np.exp(rr)
    gross[is_nan] = np.nan

    out = pd.Series(gross[pos[valid]], index=g.index[valid])
    # Preserve original index shape for assignment
    out = out.reindex(g.index)
    return out


def _assign_ff_buckets(sic: pd.Series, ranges: list[tuple[int, int, int]]) -> pd.Series:
    """Map SIC to FF bucket id given list of (low, high, bucket_id)."""
    sic_int = pd.to_numeric(sic, errors="coerce").astype("Int64")
    out = pd.Series(pd.NA, index=sic.index, dtype="Int64")
    for lo, hi, code in ranges:
        mask = sic_int.ge(lo) & sic_int.le(hi)
        out = out.mask(mask, code)
    return out


# FF10 ranges per makeFF10Indus.m
FF10_RANGES: list[tuple[int, int, int]] = [
    # 1 NoDur
    (100, 999, 1), (2000, 2399, 1), (2700, 2749, 1), (2770, 2799, 1),
    (3100, 3199, 1), (3940, 3989, 1),
    # 2 Durbl
    (2500, 2519, 2), (2590, 2599, 2), (3630, 3659, 2), (3710, 3711, 2),
    (3714, 3714, 2), (3716, 3716, 2), (3750, 3751, 2), (3792, 3792, 2),
    (3900, 3939, 2), (3990, 3999, 2),
    # 3 Manuf
    (2520, 2589, 3), (2600, 2699, 3), (2750, 2769, 3), (2800, 2829, 3),
    (2840, 2899, 3), (3000, 3099, 3), (3200, 3569, 3), (3580, 3621, 3),
    (3623, 3629, 3), (3700, 3709, 3), (3712, 3713, 3), (3715, 3715, 3),
    (3717, 3749, 3), (3752, 3791, 3), (3793, 3799, 3), (3860, 3899, 3),
    # 4 Enrgy
    (1200, 1399, 4), (2900, 2999, 4),
    # 5 HiTec
    (3570, 3579, 5), (3622, 3622, 5), (3660, 3692, 5), (3694, 3699, 5),
    (3810, 3839, 5), (7370, 7372, 5), (7373, 7373, 5), (7374, 7374, 5),
    (7375, 7375, 5), (7376, 7376, 5), (7377, 7377, 5), (7378, 7378, 5),
    (7379, 7379, 5), (7391, 7391, 5), (8730, 8734, 5),
    # 6 Telcm
    (4800, 4899, 6),
    # 7 Shops
    (5000, 5999, 7), (7200, 7299, 7), (7600, 7699, 7),
    # 8 Hlth
    (2830, 2839, 8), (3693, 3693, 8), (3840, 3859, 8), (8000, 8099, 8),
    # 9 Utils
    (4900, 4949, 9),
    # 10 Other (catch-all handled separately)
]


# FF17 ranges per makeFF17Indus.m
FF17_RANGES: list[tuple[int, int, int]] = [
    # 1 Food
    (100, 199, 1), (200, 299, 1), (700, 799, 1), (900, 999, 1),
    (2000, 2009, 1), (2010, 2019, 1), (2020, 2029, 1), (2030, 2039, 1),
    (2040, 2046, 1), (2047, 2047, 1), (2048, 2048, 1), (2050, 2059, 1),
    (2060, 2063, 1), (2064, 2068, 1), (2070, 2079, 1), (2080, 2080, 1),
    (2082, 2082, 1), (2083, 2083, 1), (2084, 2084, 1), (2085, 2085, 1),
    (2086, 2086, 1), (2087, 2087, 1), (2090, 2092, 1), (2095, 2095, 1),
    (2096, 2096, 1), (2097, 2097, 1), (2098, 2099, 1),
    (5140, 5149, 1), (5150, 5159, 1), (5180, 5182, 1), (5191, 5191, 1),
    # 2 Mines
    (1000, 1009, 2), (1010, 1019, 2), (1020, 1029, 2), (1030, 1039, 2),
    (1040, 1049, 2), (1060, 1069, 2), (1080, 1089, 2), (1090, 1099, 2),
    (1200, 1299, 2), (1400, 1499, 2), (5050, 5052, 2),
    # 3 Oil
    (1300, 1300, 3), (1310, 1319, 3), (1320, 1329, 3), (1380, 1380, 3),
    (1381, 1381, 3), (1382, 1382, 3), (1389, 1389, 3), (2900, 2912, 3),
    (5170, 5172, 3),
    # 4 Clths
    (2200, 2269, 4), (2270, 2279, 4), (2280, 2284, 4), (2290, 2295, 4),
    (2296, 2296, 4), (2297, 2297, 4), (2298, 2298, 4), (2299, 2299, 4),
    (2300, 2390, 4), (2391, 2392, 4), (2393, 2395, 4), (2396, 2396, 4),
    (2397, 2399, 4), (3020, 3021, 4), (3100, 3111, 4), (3130, 3131, 4),
    (3140, 3149, 4), (3150, 3151, 4), (3963, 3965, 4), (5130, 5139, 4),
    # 5 Durbl
    (2510, 2519, 5), (2590, 2599, 5), (3060, 3069, 5), (3070, 3079, 5),
    (3080, 3089, 5), (3090, 3099, 5), (3630, 3639, 5), (3650, 3651, 5),
    (3652, 3652, 5), (3860, 3861, 5), (3870, 3873, 5), (3910, 3911, 5),
    (3914, 3914, 5), (3915, 3915, 5), (3930, 3931, 5), (3940, 3949, 5),
    (3960, 3962, 5), (5020, 5023, 5), (5064, 5064, 5), (5094, 5094, 5),
    (5099, 5099, 5),
    # 6 Chems
    (2800, 2809, 6), (2810, 2819, 6), (2820, 2829, 6), (2860, 2869, 6),
    (2870, 2879, 6), (2890, 2899, 6), (5160, 5169, 6),
    # 7 Cnsum
    (2100, 2199, 7), (2830, 2830, 7), (2831, 2831, 7), (2833, 2833, 7),
    (2834, 2834, 7), (2840, 2843, 7), (2844, 2844, 7), (5120, 5122, 7),
    (5194, 5194, 7),
    # 8 Cnstr
    (800, 899, 8), (1500, 1511, 8), (1520, 1529, 8), (1530, 1539, 8),
    (1540, 1549, 8), (1600, 1699, 8), (1700, 1799, 8), (2400, 2439, 8),
    (2440, 2449, 8), (2450, 2459, 8), (2490, 2499, 8), (2850, 2859, 8),
    (2950, 2952, 8), (3200, 3200, 8), (3210, 3211, 8), (3240, 3241, 8),
    (3250, 3259, 8), (3261, 3261, 8), (3264, 3264, 8), (3270, 3275, 8),
    (3280, 3281, 8), (3290, 3293, 8), (3420, 3429, 8), (3430, 3433, 8),
    (3440, 3441, 8), (3442, 3442, 8), (3446, 3446, 8), (3448, 3448, 8),
    (3449, 3449, 8), (3450, 3451, 8), (3452, 3452, 8), (3490, 3499, 8),
    (5030, 5039, 8), (5070, 5078, 8), (5198, 5198, 8), (5210, 5211, 8),
    (5230, 5231, 8), (5250, 5251, 8),
    # 9 Steel
    (3300, 3300, 9), (3310, 3317, 9), (3320, 3325, 9), (3330, 3339, 9),
    (3340, 3341, 9), (3350, 3357, 9), (3360, 3369, 9), (3390, 3399, 9),
    # 10 FabPr
    (3410, 3412, 10), (3443, 3443, 10), (3444, 3444, 10), (3460, 3469, 10),
    (3470, 3479, 10), (3480, 3489, 10), (3490, 3499, 10),
    # 11 Machn
    (3510, 3519, 11), (3520, 3529, 11), (3530, 3530, 11), (3531, 3531, 11),
    (3532, 3532, 11), (3533, 3533, 11), (3534, 3534, 11), (3535, 3535, 11),
    (3536, 3536, 11), (3540, 3549, 11), (3550, 3559, 11), (3560, 3569, 11),
    (3570, 3579, 11), (3580, 3580, 11), (3581, 3581, 11), (3582, 3582, 11),
    (3585, 3585, 11), (3586, 3586, 11), (3589, 3589, 11), (3590, 3599, 11),
    (3600, 3600, 11), (3610, 3613, 11), (3620, 3621, 11), (3622, 3622, 11),
    (3623, 3629, 11), (3670, 3679, 11), (3680, 3680, 11), (3681, 3681, 11),
    (3682, 3682, 11), (3683, 3683, 11), (3684, 3684, 11), (3685, 3685, 11),
    (3686, 3686, 11), (3687, 3687, 11), (3688, 3688, 11), (3689, 3689, 11),
    (3690, 3690, 11), (3691, 3692, 11), (3693, 3693, 11), (3694, 3694, 11),
    (3695, 3695, 11), (3699, 3699, 11), (3810, 3810, 11), (3811, 3811, 11),
    (3812, 3812, 11), (3820, 3820, 11), (3821, 3821, 11), (3822, 3822, 11),
    (3823, 3823, 11), (3824, 3824, 11), (3825, 3825, 11), (3826, 3826, 11),
    (3827, 3827, 11), (3829, 3829, 11), (3830, 3839, 11), (3950, 3955, 11),
    (5060, 5060, 11), (5063, 5063, 11), (5065, 5065, 11), (5080, 5080, 11),
    (5081, 5081, 11),
    # 12 Cars
    (3710, 3710, 12), (3711, 3711, 12), (3714, 3714, 12), (3716, 3716, 12),
    (3750, 3751, 12), (3792, 3792, 12), (5010, 5015, 12), (5510, 5521, 12),
    (5530, 5531, 12), (5560, 5561, 12), (5570, 5571, 12), (5590, 5599, 12),
    # 13 Trans
    (3713, 3713, 13), (3715, 3715, 13), (3720, 3720, 13), (3721, 3721, 13),
    (3724, 3724, 13), (3725, 3725, 13), (3728, 3728, 13), (3730, 3731, 13),
    (3732, 3732, 13), (3740, 3743, 13), (3760, 3769, 13), (3790, 3790, 13),
    (3795, 3795, 13), (3799, 3799, 13), (4000, 4013, 13), (4100, 4100, 13),
    (4110, 4119, 13), (4120, 4121, 13), (4130, 4131, 13), (4140, 4142, 13),
    (4150, 4151, 13), (4170, 4173, 13), (4190, 4199, 13), (4200, 4200, 13),
    (4210, 4219, 13), (4220, 4229, 13), (4230, 4231, 13), (4400, 4499, 13),
    (4500, 4599, 13), (4600, 4699, 13), (4700, 4700, 13), (4710, 4712, 13),
    (4720, 4729, 13), (4730, 4739, 13), (4740, 4742, 13), (4780, 4780, 13),
    (4783, 4783, 13), (4785, 4785, 13), (4789, 4789, 13),
    # 14 Utils
    (4900, 4900, 14), (4910, 4911, 14), (4920, 4922, 14), (4923, 4923, 14),
    (4924, 4925, 14), (4930, 4931, 14), (4932, 4932, 14), (4939, 4939, 14),
    (4940, 4942, 14),
    # 15 Rtail
    (5260, 5261, 15), (5270, 5271, 15), (5300, 5300, 15), (5310, 5311, 15),
    (5320, 5320, 15), (5330, 5331, 15), (5334, 5334, 15), (5390, 5399, 15),
    (5400, 5400, 15), (5410, 5411, 15), (5412, 5412, 15), (5420, 5421, 15),
    (5430, 5431, 15), (5440, 5441, 15), (5450, 5451, 15), (5460, 5461, 15),
    (5490, 5499, 15), (5540, 5541, 15), (5550, 5551, 15), (5600, 5699, 15),
    (5700, 5700, 15), (5710, 5719, 15), (5720, 5722, 15), (5730, 5736, 15),
    (5750, 5799, 15), (5800, 5813, 15), (5890, 5890, 15), (5900, 5900, 15),
    (5910, 5912, 15), (5920, 5921, 15), (5930, 5932, 15), (5940, 5940, 15),
    (5941, 5941, 15), (5942, 5942, 15), (5943, 5943, 15), (5944, 5944, 15),
    (5945, 5945, 15), (5946, 5946, 15), (5947, 5947, 15), (5948, 5948, 15),
    (5949, 5949, 15), (5960, 5963, 15), (5980, 5989, 15), (5990, 5990, 15),
    (5992, 5992, 15), (5993, 5993, 15), (5994, 5994, 15), (5995, 5995, 15),
    (5999, 5999, 15),
    # 16 Finan
    (6010, 6019, 16), (6020, 6020, 16), (6021, 6021, 16), (6022, 6022, 16),
    (6023, 6023, 16), (6025, 6025, 16), (6026, 6026, 16), (6028, 6029, 16),
    (6030, 6036, 16), (6040, 6049, 16), (6050, 6059, 16), (6060, 6062, 16),
    (6080, 6082, 16), (6090, 6099, 16), (6100, 6100, 16), (6110, 6111, 16),
    (6112, 6112, 16), (6120, 6129, 16), (6140, 6149, 16), (6150, 6159, 16),
    (6160, 6163, 16), (6172, 6172, 16), (6199, 6199, 16), (6200, 6299, 16),
    (6300, 6300, 16), (6310, 6312, 16), (6320, 6324, 16), (6330, 6331, 16),
    (6350, 6351, 16), (6360, 6361, 16), (6370, 6371, 16), (6390, 6399, 16),
    (6400, 6411, 16), (6500, 6500, 16), (6510, 6510, 16), (6512, 6512, 16),
    (6513, 6513, 16), (6514, 6514, 16), (6515, 6515, 16), (6517, 6519, 16),
    (6530, 6531, 16), (6532, 6532, 16), (6540, 6541, 16), (6550, 6553, 16),
    (6611, 6611, 16), (6700, 6700, 16), (6710, 6719, 16), (6720, 6722, 16),
    (6723, 6723, 16), (6724, 6724, 16), (6725, 6725, 16), (6726, 6726, 16),
    (6730, 6733, 16), (6790, 6790, 16), (6792, 6792, 16), (6794, 6794, 16),
    (6795, 6795, 16), (6798, 6798, 16), (6799, 6799, 16),
    # 17 Other handled later
]

# FF49 ranges per makeFF49Indus.m (abbreviated mapping)
FF49_RANGES: list[tuple[int, int, int]] = [
    # 1 Agric
    (100, 299, 1), (700, 799, 1), (910, 919, 1), (2048, 2048, 1),
    # 2 Food
    (2000, 2046, 2), (2050, 2063, 2), (2070, 2079, 2), (2090, 2092, 2),
    (2095, 2095, 2), (2098, 2099, 2),
    # 3 Soda
    (2064, 2068, 3), (2086, 2087, 3), (2096, 2097, 3),
    # 4 Beer
    (2080, 2080, 4), (2082, 2085, 4),
    # 5 Smoke
    (2100, 2199, 5),
    # 6 Toys
    (920, 999, 6), (3650, 3652, 6), (3732, 3732, 6), (3930, 3931, 6), (3940, 3949, 6),
    # 7 Fun
    (7800, 7833, 7), (7840, 7841, 7), (7900, 7900, 7), (7910, 7911, 7), (7920, 7933, 7),
    (7940, 7949, 7), (7980, 7980, 7), (7990, 7999, 7),
    # 8 Books
    (2700, 2749, 8), (2770, 2771, 8), (2780, 2799, 8),
    # 9 Hshld
    (2047, 2047, 9), (2391, 2392, 9), (2510, 2519, 9), (2590, 2599, 9),
    (2840, 2844, 9), (3160, 3161, 9), (3170, 3172, 9), (3190, 3199, 9),
    (3229, 3229, 9), (3260, 3260, 9), (3262, 3263, 9), (3269, 3269, 9),
    (3230, 3231, 9), (3630, 3639, 9), (3750, 3751, 9), (3800, 3800, 9),
    (3860, 3861, 9), (3870, 3873, 9), (3910, 3911, 9), (3914, 3914, 9),
    (3915, 3915, 9), (3960, 3962, 9), (3991, 3991, 9), (3995, 3995, 9),
    # 10 Clths
    (2300, 2390, 10), (3020, 3021, 10), (3100, 3111, 10), (3130, 3131, 10),
    (3140, 3151, 10), (3963, 3965, 10),
    # 11 Hlth
    (8000, 8099, 11),
    # 12 MedEq
    (3693, 3693, 12), (3840, 3851, 12),
    # 13 Drugs
    (2830, 2831, 13), (2833, 2836, 13),
    # 14 Chems
    (2800, 2829, 14), (2850, 2879, 14), (2890, 2899, 14),
    # 15 Rubbr
    (3031, 3031, 15), (3041, 3041, 15), (3050, 3053, 15), (3060, 3099, 15),
    # 16 Txtls
    (2200, 2284, 16), (2290, 2295, 16), (2297, 2299, 16), (2393, 2395, 16),
    (2397, 2399, 16),
    # 17 BldMt
    (800, 899, 17), (2400, 2439, 17), (2450, 2459, 17), (2490, 2499, 17),
    (2660, 2661, 17), (2950, 2952, 17), (3200, 3200, 17), (3210, 3211, 17),
    (3240, 3241, 17), (3250, 3259, 17), (3261, 3261, 17), (3264, 3264, 17),
    (3270, 3275, 17), (3280, 3281, 17), (3290, 3293, 17), (3295, 3299, 17),
    (3420, 3433, 17), (3440, 3442, 17), (3446, 3446, 17), (3448, 3452, 17),
    (3490, 3499, 17), (3996, 3996, 17),
    # 18 Cnstr
    (1500, 1511, 18), (1520, 1549, 18), (1600, 1799, 18),
    # 19 Steel
    (3300, 3300, 19), (3310, 3317, 19), (3320, 3325, 19), (3330, 3341, 19),
    (3350, 3357, 19), (3360, 3379, 19), (3390, 3399, 19),
    # 20 FabPr
    (3400, 3400, 20), (3443, 3444, 20), (3460, 3479, 20),
    # 21 Mach
    (3510, 3536, 21), (3538, 3538, 21), (3540, 3569, 21), (3580, 3582, 21),
    (3585, 3586, 21), (3589, 3599, 21), (3600, 3600, 21), (3610, 3613, 21),
    (3620, 3621, 21), (3623, 3629, 21), (3670, 3679, 21), (3680, 3680, 21),
    (3681, 3681, 21), (3682, 3682, 21), (3683, 3683, 21), (3684, 3684, 21),
    (3685, 3685, 21), (3686, 3686, 21), (3687, 3687, 21), (3688, 3688, 21),
    (3689, 3689, 21), (3690, 3692, 21), (3699, 3699, 21),
    (3810, 3810, 21), (3811, 3811, 21), (3812, 3812, 21),
    (3820, 3820, 21), (3821, 3821, 21), (3822, 3822, 21), (3823, 3823, 21),
    (3824, 3824, 21), (3825, 3825, 21), (3826, 3826, 21), (3827, 3827, 21),
    (3829, 3829, 21), (3830, 3839, 21), (3950, 3955, 21),
    (5060, 5060, 21), (5063, 5063, 21), (5065, 5065, 21), (5080, 5080, 21),
    (5081, 5081, 21),
    # 22 ElcEq
    (3600, 3600, 22), (3610, 3613, 22), (3620, 3621, 22), (3623, 3629, 22),
    (3640, 3646, 22), (3648, 3649, 22), (3660, 3660, 22), (3690, 3692, 22),
    (3699, 3699, 22),
    # 23 Autos
    (2296, 2296, 23), (2396, 2396, 23), (3010, 3011, 23), (3537, 3537, 23),
    (3647, 3647, 23), (3694, 3694, 23), (3700, 3700, 23), (3710, 3711, 23),
    (3713, 3716, 23), (3790, 3792, 23), (3799, 3799, 23),
    # 24 Aero
    (3720, 3721, 24), (3723, 3725, 24), (3728, 3729, 24),
    # 25 Ships
    (3730, 3731, 25), (3740, 3743, 25),
    # 26 Guns
    (3760, 3769, 26), (3795, 3795, 26), (3480, 3489, 26),
    # 27 Gold
    (1040, 1049, 27),
    # 28 Mines
    (1000, 1039, 28), (1050, 1119, 28), (1400, 1499, 28),
    # 29 Coal
    (1200, 1299, 29),
    # 30 Oil
    (1300, 1300, 30), (1310, 1339, 30), (1370, 1382, 30), (1389, 1389, 30),
    (2900, 2912, 30), (2990, 2999, 30),
    # 31 Util
    (4900, 4900, 31), (4910, 4911, 31), (4920, 4925, 31), (4930, 4932, 31),
    (4939, 4939, 31), (4940, 4942, 31),
    # 32 Telcm
    (4800, 4800, 32), (4810, 4813, 32), (4820, 4822, 32), (4830, 4841, 32),
    (4880, 4892, 32), (4899, 4899, 32),
    # 33 PerSv
    (7020, 7021, 33), (7030, 7033, 33), (7200, 7200, 33), (7210, 7212, 33),
    (7214, 7217, 33), (7219, 7221, 33), (7230, 7231, 33), (7240, 7241, 33),
    (7250, 7251, 33), (7260, 7299, 33), (7395, 7395, 33), (7500, 7500, 33),
    (7520, 7549, 33), (7600, 7600, 33), (7620, 7620, 33), (7622, 7623, 33),
    (7629, 7631, 33), (7640, 7641, 33), (7690, 7699, 33), (8100, 8499, 33),
    (8600, 8699, 33), (8800, 8899, 33), (7510, 7515, 33),
    # 34 BusSv
    (2750, 2759, 34), (3993, 3993, 34), (7218, 7218, 34), (7300, 7300, 34),
    (7310, 7342, 34), (7349, 7353, 34), (7359, 7369, 34), (7374, 7374, 34),
    (7376, 7385, 34), (7389, 7394, 34), (7396, 7397, 34), (7399, 7399, 34),
    (7519, 7519, 34), (8700, 8700, 34), (8710, 8713, 34), (8720, 8721, 34),
    (8730, 8734, 34), (8740, 8748, 34), (8900, 8910, 34), (8911, 8911, 34),
    (8920, 8999, 34), (4220, 4229, 34),
    # 35 Hardw
    (3570, 3579, 35), (3680, 3689, 35), (3695, 3695, 35),
    # 36 Softw
    (7370, 7372, 36), (7373, 7373, 36), (7375, 7375, 36),
    # 37 Chips
    (3622, 3622, 37), (3661, 3666, 37), (3669, 3669, 37), (3670, 3679, 37),
    (3810, 3810, 37), (3812, 3812, 37),
    # 38 LabEq
    (3811, 3811, 38), (3820, 3827, 38), (3829, 3839, 38),
    # 39 Paper
    (2520, 2549, 39), (2600, 2639, 39), (2670, 2699, 39), (2760, 2761, 39),
    (3950, 3955, 39),
    # 40 Boxes
    (2440, 2449, 40), (2640, 2659, 40), (3220, 3221, 40), (3410, 3412, 40),
    # 41 Trans
    (4000, 4013, 41), (4040, 4049, 41), (4100, 4100, 41), (4110, 4121, 41),
    (4130, 4131, 41), (4140, 4142, 41), (4150, 4151, 41), (4170, 4173, 41),
    (4190, 4200, 41), (4210, 4219, 41), (4230, 4231, 41), (4240, 4249, 41),
    (4400, 4700, 41), (4710, 4712, 41), (4720, 4749, 41), (4780, 4780, 41),
    (4782, 4785, 41), (4789, 4789, 41),
    # 42 Whlsl
    (5000, 5000, 42), (5010, 5015, 42), (5020, 5023, 42), (5030, 5060, 42),
    (5063, 5065, 42), (5070, 5078, 42), (5080, 5088, 42), (5090, 5113, 42),
    (5120, 5122, 42), (5130, 5172, 42), (5180, 5182, 42), (5190, 5199, 42),
    # 43 Rtail
    (5200, 5200, 43), (5210, 5231, 43), (5250, 5251, 43), (5260, 5261, 43),
    (5270, 5271, 43), (5300, 5300, 43), (5310, 5311, 43), (5320, 5320, 43),
    (5330, 5331, 43), (5334, 5334, 43), (5340, 5349, 43), (5390, 5400, 43),
    (5410, 5412, 43), (5420, 5469, 43), (5490, 5500, 43), (5510, 5579, 43),
    (5590, 5700, 43), (5710, 5722, 43), (5730, 5736, 43), (5750, 5799, 43),
    (5900, 5900, 43), (5910, 5912, 43), (5920, 5932, 43), (5940, 5990, 43),
    (5992, 5995, 43), (5999, 5999, 43),
    # 44 Meals
    (5800, 5829, 44), (5890, 5899, 44), (7000, 7000, 44), (7010, 7019, 44),
    (7040, 7049, 44), (7213, 7213, 44),
    # 45 Banks
    (6000, 6000, 45), (6010, 6036, 45), (6040, 6062, 45), (6080, 6082, 45),
    (6090, 6100, 45), (6110, 6113, 45), (6120, 6179, 45), (6190, 6199, 45),
    # 46 Insur
    (6300, 6300, 46), (6310, 6331, 46), (6350, 6351, 46), (6360, 6361, 46),
    (6370, 6379, 46), (6390, 6411, 46),
    # 47 RlEst
    (6500, 6500, 47), (6510, 6510, 47), (6512, 6515, 47), (6517, 6532, 47),
    (6540, 6541, 47), (6550, 6553, 47), (6590, 6599, 47), (6610, 6611, 47),
    # 48 Fin
    (6200, 6299, 48), (6700, 6700, 48), (6710, 6726, 48), (6730, 6733, 48),
    (6740, 6779, 48), (6790, 6795, 48), (6798, 6799, 48),
    # 49 Other
    (4950, 4959, 49), (4960, 4961, 49), (4970, 4971, 49), (4990, 4991, 49),
]


def transform_monthly(
    raw: pd.DataFrame,
    config: AssayConfig,
    *,
    aux: dict[str, pd.DataFrame] | None = None,
    source: "CRSPSource | None" = None,
) -> pd.DataFrame:
    """
    Transform raw CRSP MSF data into the schema expected by analytics.

    Inputs:
        raw: raw MSF frame, already mapped onto the canonical column names by
            ``source.normalize_monthly``
        aux: optional dict of auxiliary frames (msedelist, mseexchdates, stocknames, etc.)
        source: which CRSP tape ``raw`` came from. Two steps below are the
            tape's call rather than this function's: the name-window join
            (``needs_name_window``) and the delisting overlay
            (``apply_delisting_overlay``). Defaults to the legacy SIZ tape, so
            existing callers keep MATLAB parity behaviour.
    Outputs:
        A normalized monthly panel with adjusted returns and selected raw fields.
    """

    t0 = time.perf_counter()
    if source is None:
        from ..ingest.crsp_source import crsp_source_for

        source = crsp_source_for("siz")
    aux = aux or {}
    df = raw.copy()
    LOGGER.info(
        "CRSP monthly transform starting: raw_shape=%s sample=%s..%s dom_com_eq=%s aux=%s",
        df.shape,
        config.sample_start,
        config.sample_end,
        config.dom_com_eq,
        {k: tuple(v.shape) for k, v in aux.items()},
    )

    # Normalize to date only (CRSP MSF uses last trading day, not calendar month-end).
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    df["permno"] = df["permno"].astype("int64")
    df["yyyymm"] = _date_yyyymm(df["date"])

    # MATLAB-style sample filter.
    lo = config.sample_start * 100 + 1
    hi = config.sample_end * 100 + 12
    df = df[df["yyyymm"].between(lo, hi)]
    LOGGER.info("After sample filter: shape=%s yyyymm_range=[%s,%s]", df.shape, lo, hi)

    # Bring in shrcd/exchcd/siccd from mseexchdates and drop observations outside the interval
    # (matches MATLAB makeCRSPMonthlyData.m). Tapes that carry the as-of codes
    # on the monthly row itself have no window table to join.
    mseexch = aux.get("mseexchdates", pd.DataFrame())
    if source.needs_name_window and not mseexch.empty:
        # Prefer MATLAB's interval columns when available.
        if {"namedt", "nameendt"}.issubset(mseexch.columns):
            start_col, end_col = "namedt", "nameendt"
        elif {"begexchdate", "endexchdate"}.issubset(mseexch.columns):
            start_col, end_col = "begexchdate", "endexchdate"
        else:
            start_col = end_col = ""

        cols: list[str] = []
        for c in ("shrcd", "exchcd", "siccd", "hsiccd"):
            if c in mseexch.columns:
                cols.append(c)

        if start_col and end_col and cols:
            df = _merge_on_interval(df, mseexch, start_col, end_col, cols, drop_outside=True)

    # If exchcd is still missing but hexcd exists in raw, fallback.
    if "exchcd" not in df or df["exchcd"].isna().all():
        if "hexcd" in df.columns:
            df["exchcd"] = df["hexcd"]

    # SIC from raw; fallback to siccd/hsiccd (mseexchdates) or stocknames.
    if "siccd" not in df.columns:
        df["siccd"] = pd.NA
    if df["siccd"].isna().all():
        if "hsiccd" in df.columns and df["hsiccd"].notna().any():
            df["siccd"] = df["hsiccd"]
    if df["siccd"].isna().all():
        stocknames = aux.get("stocknames", pd.DataFrame())
        if not stocknames.empty:
            df = _merge_on_interval(
                df,
                stocknames.rename(columns={"siccd": "siccd_sn"}),
                "namedt",
                "nameendt",
                ["siccd_sn"],
            )
            if "siccd_sn" in df.columns:
                df["siccd"] = df["siccd"].fillna(df["siccd_sn"])
                df = df.drop(columns=["siccd_sn"])

    # Rename SIC to sic for downstream use.
    df["sic"] = pd.to_numeric(df["siccd"], errors="coerce").astype("Int64")
    df = df.drop(columns=["siccd"])

    # Match MATLAB Params.domComEqFlag: keep only shrcd 10 or 11 if enabled.
    if config.dom_com_eq and "shrcd" in df.columns:
        df["shrcd"] = pd.to_numeric(df["shrcd"], errors="coerce")
        df = df[df["shrcd"].isin([10, 11])]
        LOGGER.info("After dom_com_eq shrcd filter: shape=%s", df.shape)

    # After interval filtering, collapse the time key to a canonical month-end date so we have
    # exactly one row per (permno, yyyymm), matching MATLAB's matrix representation.
    df["date"] = pd.to_datetime(df["yyyymm"].astype(str) + "01", format="%Y%m%d", errors="coerce") + pd.offsets.MonthEnd(0)

    # Raw returns (not delisting-adjusted).
    if "ret" in df.columns:
        df["ret_x_dl"] = pd.to_numeric(df["ret"], errors="coerce")
    else:
        df["ret_x_dl"] = pd.NA

    # Apply delisting adjustment exactly like MATLAB, on tapes whose `ret`
    # excludes the delisting payoff. CIZ's `mthret` already contains it, so
    # running the overlay there would double-count it and `ret_x_dl == ret`.
    # MATLAB's global `dates` vector is the set of unique YYYYMM months present after filtering MSF.
    if source.apply_delisting_overlay:
        msedelist = source.delist_events(aux)
        months_yyyymm = pd.Series(df["yyyymm"]).dropna().sort_values().unique()
        df = _apply_matlab_delisting_adjustment(df, msedelist=msedelist, months_yyyymm=pd.Series(months_yyyymm))
        LOGGER.info("After delisting adjustment: shape=%s", df.shape)
    else:
        df = _attach_informational_dlret(df, delists=source.delist_events(aux))
        LOGGER.info(
            "Skipping the MATLAB delisting overlay (%s tape: ret already "
            "delisting-adjusted); dlret attached as information on %d "
            "delisting months, ret == ret_x_dl",
            source.name,
            int(pd.to_numeric(df["dlret"], errors="coerce").notna().sum()),
        )

    # retx (returns without dividends) preserved if present.
    if "retx" in df.columns:
        df["retx"] = df["retx"].astype(float)
    else:
        df["retx"] = pd.NA

    # Market equity: compute if not already present.
    # makeCRSPDerivedVariables.m:132-133 -- shrout is in thousands of shares,
    # so divide by 1000 to express me in millions of USD; then map me==0 to
    # NaN (MATLAB treats zero market-cap as missing).
    if "me" not in df.columns:
        df["me"] = (df["prc"].abs() * df["shrout"] / 1000.0).astype("float64")
    else:
        df["me"] = df["me"].astype("float64")
    df.loc[df["me"].eq(0), "me"] = np.nan

    # Split-adjusted shares for issuance metrics.
    if "cfacshr" in df.columns:
        df["shrout_adj"] = pd.to_numeric(df["shrout"], errors="coerce") * pd.to_numeric(df["cfacshr"], errors="coerce")
    else:
        df["shrout_adj"] = pd.to_numeric(df["shrout"], errors="coerce")

    # Momentum / past-performance windows (MATLAB-style, using delisting-adjusted returns):
    # These are stored as *gross* returns (products of 1+ret), matching `makePastPerformance.m`.
    #
    # NOTE: The analytics sorting code lags signals by 1 month before forming portfolios.
    # So we store the MATLAB "raw" signal at month t, and the sort at month t uses signal(t-1).
    #
    # R12_2: MATLAB `R = makePastPerformance(ret, 12, 1)` => lags 1..11 at month t.
    #        After the sort's 1-month lag, the effective window for month t is t-12..t-2.
    # R60_13: intended long-horizon past performance (lags 12..59 at month t); after sort lag => t-60..t-13.
    # R6_1: recent-horizon past performance (lags 1..5 at month t); after sort lag => t-6..t-2.
    df = df.sort_values(["permno", "date"]).reset_index(drop=True)
    # Full MATLAB parity: compute on a global month grid (balanced-matrix behavior).
    # The global month range is defined by the configured sample window (Jan..Dec).
    start_year = int(config.sample_start)
    start_month = 1
    n_months = int((int(config.sample_end) - start_year + 1) * 12)
    # MATLAB's balanced matrix starts at the first month with data (192512),
    # so the "first from-1 months are NaN" mask is anchored there, not at
    # January of the configured start year.
    _first_date = pd.to_datetime(df["date"]).min()
    data_start_pos = max(
        0, (_first_date.year - start_year) * 12 + (_first_date.month - start_month)
    )

    r12 = df.groupby("permno", group_keys=False).apply(
        _cumret_window_global_months,
        window=11,
        lag=1,
        col="ret",
        start_year=start_year,
        start_month=start_month,
        n_months=n_months,
        data_start_pos=data_start_pos,
    )
    if isinstance(r12.index, pd.MultiIndex):
        r12 = r12.reset_index(level=0, drop=True)
    df["R12_2"] = r12.reindex(df.index).to_numpy()

    r6013 = df.groupby("permno", group_keys=False).apply(
        _cumret_window_global_months,
        window=48,
        lag=12,
        col="ret",
        start_year=start_year,
        start_month=start_month,
        n_months=n_months,
        data_start_pos=data_start_pos,
    )
    if isinstance(r6013.index, pd.MultiIndex):
        r6013 = r6013.reset_index(level=0, drop=True)
    df["R60_13"] = r6013.reindex(df.index).to_numpy()

    r61 = df.groupby("permno", group_keys=False).apply(
        _cumret_window_global_months,
        window=5,
        lag=1,
        col="ret",
        start_year=start_year,
        start_month=start_month,
        n_months=n_months,
        data_start_pos=data_start_pos,
    )
    if isinstance(r61.index, pd.MultiIndex):
        r61 = r61.reset_index(level=0, drop=True)
    df["R6_1"] = r61.reindex(df.index).to_numpy()

    # Issuance: change in split-adjusted shares (level and pct).
    df["shrout_adj_lag1"] = df.groupby("permno")["shrout_adj"].shift(1)
    df["issuance_delta"] = df["shrout_adj"] - df["shrout_adj_lag1"]
    df["issuance_pct"] = df["issuance_delta"] / df["shrout_adj_lag1"]

    # Volume adjustment (split-adjusted volume).
    if "vol" in df.columns:
        if "cfacshr" in df.columns:
            df["vol_x_adj"] = (df["vol"] * df["cfacshr"]).astype("float64")
        else:
            df["vol_x_adj"] = df["vol"].astype("float64")
    else:
        df["vol_x_adj"] = pd.NA

    # Bid/ask spread if available.
    if "bid" in df.columns and "ask" in df.columns:
        df["spread"] = df["ask"] - df["bid"]
    else:
        df["spread"] = pd.NA

    # Exchange flag: NYSE = exchcd==1.
    # MATLAB NYSE = (exchcd == 1)*1 on a dense (T,N) double matrix where
    # NaN == 1 evaluates to False (0), not NaN. Collapse the pandas nullable
    # boolean {True, False, NA} to plain bool by mapping NA -> False.
    if "exchcd" in df.columns:
        exch = df["exchcd"]
    else:
        exch = pd.Series(False, index=df.index)
    df["nyse_flag"] = (
        pd.to_numeric(exch, errors="coerce").eq(1).fillna(False).astype(bool)
    )

    # Industry buckets (FF10/17/49) using SIC ranges per attached MATLAB mappings.
    df["ff10"] = _assign_ff_buckets(df["sic"], FF10_RANGES).fillna(10).astype("Int64")
    df["ff17"] = _assign_ff_buckets(df["sic"], FF17_RANGES).fillna(17).astype("Int64")
    df["ff49"] = _assign_ff_buckets(df["sic"], FF49_RANGES).fillna(49).astype("Int64")

    # Keep requested raw fields plus adjusted return/me/flag and deriveds.
    wanted = [
        "date",
        "permno",
        "ret",       # adjusted for delisting
        "ret_x_dl",  # raw return
        "retx",
        "dlret",
        "prc",
        "bid",
        "ask",
        "bidlo",
        "askhi",
        "vol_x_adj",
        "shrout",
        "cfacpr",
        "cfacshr",
        "spread",
        "sic",
        "shrcd",
        "exchcd",
        "me",
        "nyse_flag",
        "ff10",
        "ff17",
        "ff49",
        "R12_2",
        "R60_13",
        "R6_1",
        "issuance_delta",
        "issuance_pct",
        "shrout_adj",
    ]
    # Ensure columns exist
    for col in wanted:
        if col not in df.columns:
            df[col] = pd.NA

    out = df[wanted]
    out = out[["date", "permno"] + [c for c in out.columns if c not in ("date", "permno")]]
    LOGGER.info("CRSP monthly transform finished: out_shape=%s in %.2fs", out.shape, time.perf_counter() - t0)
    return out


__all__ = ["transform_monthly"]

