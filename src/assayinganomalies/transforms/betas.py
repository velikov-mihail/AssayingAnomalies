"""
Beta estimation for asset pricing.

MATLAB equivalent: makeBetas.m

Computes 6 beta variants used in Novy-Marx and Velikov (2022):
- bfp:  Frazzini-Pedersen (2014) — correlation-based with shrinkage
- bols: OLS benchmark — 1yr daily, no shrinkage
- bdim: Dimson — OLS with 1 lag of market, sum of coefficients
- bsw:  Welch — OLS with winsorized returns
- bvck: Vasicek — OLS with cross-sectional shrinkage toward mean
- bstd: Standard — Dimson with 60/40 shrinkage toward 1

References:
    Frazzini, A. and L. Pedersen, 2014, Betting against beta, JFE 111(1): 1-25.
    Novy-Marx, R. and M. Velikov, 2022, Betting against betting against beta,
        JFE 143(1): 80-106.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from .crsp_daily import coerce_nullable_dtypes

LOGGER = logging.getLogger("assayinganomalies.transforms.betas")


# ---------------------------------------------------------------------------
# MATLAB dlret placement (makeCRSPDailyDerivedVariables.m:82–110)
# ---------------------------------------------------------------------------

def _insert_matlab_dlret_rows(
    daily: pd.DataFrame,
    delist: pd.DataFrame,
    factors: pd.DataFrame,
) -> pd.DataFrame:
    """
    Insert synthetic delisting-return rows matching MATLAB's dense ``dret`` panel.

    MATLAB places each ``dlret`` at calendar index ``r+1`` where:
    - if ``dret`` on ``dlstdt`` is NaN and the prior trading day is finite:
      ``r = dlstdt_idx`` → placement at ``dlstdt_idx + 1``
    - else: ``r = last_finite_idx + 1`` → placement at ``last_finite_idx + 2``

    The trading-day calendar is the union of the daily panel's dates and the
    factor dates. MATLAB's ``ddates`` comes straight from the daily CRSP file
    (makeCRSPDailyData.m), which starts 1925-12-31 and includes pre-1953
    Saturdays; the FF factor calendar alone starts 1926-07-01, silently
    dropping placements for delistings before that date.

    Every row is addressed by one packed ``permno * stride + calendar
    position`` integer rather than a ``(permno, date)`` MultiIndex: three
    pipeline stages run this over the ~100M-row daily panel, where building
    that index and probing it cost far more than the ~20k placements it
    resolves.
    """
    if delist is None or delist.empty or daily.empty:
        return daily

    dl = delist.copy()
    dl.columns = dl.columns.str.lower()
    if not {"permno", "dlstdt", "dlret"}.issubset(dl.columns):
        LOGGER.warning("delist missing permno/dlstdt/dlret; skipping dlret insertion")
        return daily
    # MATLAB drops the file-wide max dlstdt (still-listed placeholder rows)
    # and active codes (makeCRSPDailyDerivedVariables.m:68-72). Only applied
    # to real CRSP extracts (identified by dlstcd) — the max-drop is
    # meaningless on minimal frames without the vintage placeholder rows.
    if "dlstcd" in dl.columns:
        if dl["dlstdt"].notna().any():
            dl = dl[dl["dlstdt"] != dl["dlstdt"].max()]
        dl = dl[dl["dlstcd"].fillna(0) != 100]
    dl = dl[["permno", "dlstdt", "dlret"]].dropna(subset=["dlret"]).copy()
    if dl.empty:
        return daily

    dl["permno"] = dl["permno"].astype(int)
    dl["dlstdt"] = pd.to_datetime(dl["dlstdt"])
    coerce_nullable_dtypes(dl)

    cal = pd.concat(
        [pd.to_datetime(factors["date"]), pd.to_datetime(daily["date"])]
    ).dropna().drop_duplicates().sort_values()
    if cal.empty:
        return daily
    cal = pd.DatetimeIndex(cal)
    cal_i8 = cal.asi8
    n_cal = len(cal)
    # One past the last calendar slot, reserved for rows with no usable date so
    # they sort after that permno's dated rows exactly as `sort_values` puts
    # NaT last. `stride` keeps that slot from colliding with the next permno.
    stride = n_cal + 1

    ret_col = "ret_adj" if "ret_adj" in daily.columns else "ret"
    permnos = daily["permno"].astype("int64").to_numpy()
    day_i8 = pd.to_datetime(daily["date"]).to_numpy("datetime64[ns]").view("int64")
    rets = daily[ret_col].astype("float64").to_numpy()

    day_pos = np.searchsorted(cal_i8, day_i8)
    np.clip(day_pos, 0, n_cal - 1, out=day_pos)
    on_cal = cal_i8[day_pos] == day_i8
    key = permnos * stride + np.where(on_cal, day_pos, n_cal)

    if np.all(key[1:] >= key[:-1]):
        key_sorted, ret_sorted, dated_sorted = key, rets, on_cal
    else:
        # Stable, so a duplicated (permno, date) still resolves to the row the
        # MultiIndex lookup would have taken first.
        row_order = np.argsort(key, kind="stable")
        key_sorted = key[row_order]
        ret_sorted = rets[row_order]
        dated_sorted = on_cal[row_order]

    def _ret_at(lookup: np.ndarray) -> np.ndarray:
        """Return column value at each packed key, NaN where there is no row."""
        pos = np.searchsorted(key_sorted, lookup)
        np.clip(pos, 0, key_sorted.size - 1, out=pos)
        return np.where(key_sorted[pos] == lookup, ret_sorted[pos], np.nan)

    # Last calendar position with a finite return, per permno. Sorted keys make
    # this the final finite row of each permno's block.
    finite = np.isfinite(ret_sorted) & dated_sorted
    finite_key = key_sorted[finite]
    if finite_key.size:
        finite_permno = finite_key // stride
        block_end = np.empty(finite_key.size, dtype=bool)
        block_end[-1] = True
        np.not_equal(finite_permno[1:], finite_permno[:-1], out=block_end[:-1])
        last_permno = finite_permno[block_end]
        last_pos = finite_key[block_end] - last_permno * stride
    else:
        last_permno = np.empty(0, dtype=np.int64)
        last_pos = np.empty(0, dtype=np.int64)

    dl_permno = dl["permno"].to_numpy("int64")
    dl_i8 = dl["dlstdt"].to_numpy("datetime64[ns]").view("int64")
    dl_ret = dl["dlret"].astype("float64").to_numpy()

    r_dt = np.searchsorted(cal_i8, dl_i8)
    np.clip(r_dt, 0, n_cal - 1, out=r_dt)
    dated = (cal_i8[r_dt] == dl_i8) & (r_dt >= 1)

    # Branch 1: no return on dlstdt but a finite one the trading day before.
    on_dl = _ret_at(np.where(dated, dl_permno * stride + r_dt, -1))
    before = _ret_at(np.where(dated, dl_permno * stride + r_dt - 1, -1))
    use_dlstdt = dated & ~np.isfinite(on_dl) & np.isfinite(before)

    # Branch 2: the trading day after the last finite return.
    if last_permno.size:
        at = np.searchsorted(last_permno, dl_permno)
        np.clip(at, 0, last_permno.size - 1, out=at)
        has_finite = last_permno[at] == dl_permno
        after_last = np.where(has_finite, last_pos[at] + 1, n_cal)
    else:
        has_finite = np.zeros(dl_permno.size, dtype=bool)
        after_last = np.full(dl_permno.size, n_cal, dtype=np.int64)
    use_last = ~use_dlstdt & has_finite & (after_last < n_cal)

    r = np.where(use_dlstdt, r_dt, after_last)
    place = r + 1
    placed = np.isfinite(dl_ret) & (use_dlstdt | use_last) & (place < n_cal)
    if not placed.any():
        return daily

    synth = pd.DataFrame({
        "permno": dl_permno[placed],
        "place": place[placed],
        ret_col: dl_ret[placed],
    }).drop_duplicates(subset=["permno", "place"], keep="last")
    LOGGER.info(
        "Inserted %d MATLAB-style dlret placement rows into daily panel",
        len(synth),
    )

    # MATLAB only overwrites the dret cell (dret(r+1, j) = dlret); other
    # daily columns (vol, prc, ...) at that cell keep their values. Override
    # ret in place on existing rows and append rows only where none exist.
    out = daily.copy()
    out["date"] = pd.to_datetime(out["date"])
    out["permno"] = out["permno"].astype(int)

    synth_key = synth["permno"].to_numpy("int64") * stride + synth["place"].to_numpy("int64")
    synth_val = synth[ret_col].to_numpy("float64")
    synth_order = np.argsort(synth_key, kind="stable")
    synth_key = synth_key[synth_order]
    synth_val = synth_val[synth_order]

    hit = np.searchsorted(synth_key, key)
    np.clip(hit, 0, synth_key.size - 1, out=hit)
    exists = synth_key[hit] == key
    if exists.any():
        out.loc[exists, ret_col] = synth_val[hit[exists]]

    seen = np.searchsorted(key_sorted, synth_key)
    np.clip(seen, 0, key_sorted.size - 1, out=seen)
    is_new = key_sorted[seen] != synth_key
    all_key = key
    if is_new.any():
        new_key = synth_key[is_new]
        new = pd.DataFrame({
            # Same width as `out["permno"]` above, so the concat cannot widen it.
            "permno": (new_key // stride).astype(int),
            "date": cal[new_key % stride],
            ret_col: synth_val[is_new],
        })
        for col in daily.columns:
            if col not in new.columns:
                new[col] = np.nan
        new = new[daily.columns]
        out = pd.concat([out, new], ignore_index=True)
        all_key = np.concatenate([key, new_key])

    if not np.all(all_key[1:] >= all_key[:-1]):
        out = out.take(np.argsort(all_key, kind="stable"))
    return out.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Helper: NaN-aware OLS (equivalent to MATLAB nanols)
# ---------------------------------------------------------------------------

def _nanols(y: np.ndarray, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    OLS regression dropping rows with NaN in y or X.

    Parameters
    ----------
    y : (T,) array
    X : (T, K) array — must include intercept column if desired.

    Returns
    -------
    beta : (K,) coefficient vector
    se   : (K,) standard errors of coefficients
    """
    mask = np.isfinite(y) & np.all(np.isfinite(X), axis=1)
    yc = y[mask]
    Xc = X[mask]
    n = len(yc)
    k = Xc.shape[1]
    if n < k + 1:
        return np.full(k, np.nan), np.full(k, np.nan)

    # OLS: beta = (X'X)^{-1} X'y
    try:
        XtX = Xc.T @ Xc
        Xty = Xc.T @ yc
        beta = np.linalg.solve(XtX, Xty)
    except np.linalg.LinAlgError:
        return np.full(k, np.nan), np.full(k, np.nan)

    resid = yc - Xc @ beta
    s2 = (resid @ resid) / (n - k)
    try:
        var_beta = s2 * np.linalg.inv(XtX)
        se = np.sqrt(np.maximum(np.diag(var_beta), 0.0))
    except np.linalg.LinAlgError:
        se = np.full(k, np.nan)

    return beta, se


def _batched_solve(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """
    Solve a stack of tiny linear systems, returning NaN for the singular ones.

    ``np.linalg.solve`` on stacked inputs runs the same LAPACK routine per
    matrix as the one-at-a-time call in :func:`_nanols`, but it raises for the
    whole batch as soon as one matrix is singular. ``_nanols`` answers NaN in
    that case, so retry on the subset with a non-zero determinant and leave
    the rest NaN.

    Parameters
    ----------
    A : (M, K, K) array
    B : (M, K) or (M, K, R) array

    Returns
    -------
    Same shape as ``B``.
    """
    if A.shape[0] == 0:
        return np.empty_like(B)
    squeeze = B.ndim == A.ndim - 1
    rhs = B[..., np.newaxis] if squeeze else B
    try:
        out = np.linalg.solve(A, rhs)
    except np.linalg.LinAlgError:
        out = np.full(rhs.shape, np.nan, dtype=np.float64)
        det = np.linalg.det(A)
        ok = np.isfinite(det) & (det != 0.0)
        if ok.any():
            try:
                out[ok] = np.linalg.solve(A[ok], rhs[ok])
            except np.linalg.LinAlgError:
                for i in np.flatnonzero(ok):
                    try:
                        out[i] = np.linalg.solve(A[i], rhs[i])
                    except np.linalg.LinAlgError:
                        continue
    return out[..., 0] if squeeze else out


def _trailing_month_sums(
    values: np.ndarray,
    group: np.ndarray,
    month: np.ndarray,
    window: int,
    *,
    compensated: bool = False,
) -> np.ndarray:
    """
    Sum each row's own cell plus the ``window - 1`` months of history behind it.

    ``values`` is one row per ``(group, month)`` cell, sorted by group then
    month, with months strictly increasing inside a group. A cell's trailing
    window therefore spans at most ``window`` rows, so ``window - 1`` shifted
    adds cover it exactly — no dense per-group calendar and no prefix-sum
    differencing, which is what keeps the arithmetic identical to summing the
    window's months directly.

    ``compensated`` carries a Neumaier correction term alongside the running
    total, which callers whose result runs through a cancelling subtraction
    need; see :func:`_segment_sums`.
    """
    acc = values.copy()
    n = values.shape[0]
    if not compensated:
        for lag in range(1, window):
            if lag >= n:
                break
            src = (
                (group[:-lag] == group[lag:])
                & (month[:-lag] >= month[lag:] - (window - 1))
            )
            idx = np.flatnonzero(src)
            if idx.size == 0:
                # Months increase strictly inside a group, so if no cell
                # reaches back `lag` months none reaches back further either.
                break
            acc[idx + lag] += values[idx]
        return acc

    comp = np.zeros_like(values)
    for lag in range(1, window):
        if lag >= n:
            break
        src = (group[:-lag] == group[lag:]) & (month[:-lag] >= month[lag:] - (window - 1))
        if not src.any():
            break
        # Cells outside the window contribute an exact zero, which lets every
        # step below run on contiguous slices instead of gathering a subset.
        v = np.where(src[:, None], values[:-lag], 0.0)
        a = acc[lag:]
        t, err = _two_sum(a, v)
        comp[lag:] += err
        acc[lag:] = t
    return acc + comp


def _two_sum(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Knuth's exact two-sum: ``a + b`` rounded, and the rounding error."""
    t = a + b
    b_hi = t - a
    a_hi = t - b_hi
    return t, (a - a_hi) + (b - b_hi)


def _segment_sums(
    values: np.ndarray, starts: np.ndarray, lengths: np.ndarray
) -> np.ndarray:
    """
    Compensated sum of each contiguous segment of ``values``.

    ``np.add.reduceat`` adds a segment's rows one at a time, so a month of
    identical daily values lands a few ULPs off the correctly rounded total.
    That is invisible until a caller subtracts two such sums: Frazzini-Pedersen
    takes ``sqrt(sxx/n - (sx/n)^2)``, and for a stock whose excess return did
    not move all year the exact answer is 0, so the square root turns those
    ULPs into a sigma of ~1e-10 and a beta of ~1e-9 where there should be
    none. Carrying the rounding error alongside the running total makes each
    segment sum correctly rounded — what ``math.fsum`` returns for those cells.

    Vectorized across segments rather than within one: lane ``k`` takes the
    k-th row of every segment, so the loop runs ``max(lengths)`` times however
    many segments there are. Segments that have run out read their last row
    again and contribute an exact zero, which keeps every lane a contiguous
    full-width pass rather than a gather onto a shrinking subset.

    Parameters
    ----------
    values : (N, K) array
    starts, lengths : (M,) arrays — segment offsets into ``values`` and sizes.

    Returns
    -------
    (M, K) array
    """
    acc = np.zeros((starts.size, values.shape[1]), dtype=np.float64)
    if starts.size == 0:
        return acc
    comp = np.zeros_like(acc)
    last = np.maximum(lengths - 1, 0)
    for lane in range(int(lengths.max())):
        v = values[starts + np.minimum(lane, last)]
        np.copyto(v, 0.0, where=(lengths <= lane)[:, None])
        acc, err = _two_sum(acc, v)
        comp += err
    return acc + comp


# Daily rows reduced per pass. Bounds the temporaries the reduction allocates
# without making the per-chunk numpy calls too small to amortize.
_REDUCE_CHUNK_ROWS = 4_000_000


# ---------------------------------------------------------------------------
# Frazzini-Pedersen beta
# ---------------------------------------------------------------------------

# Sufficient statistics accumulated per (stock, month) cell, in two blocks
# because the correlation and the standard deviations roll over different
# windows: 3-day log returns for the correlation, daily ones for the stds.
_FN3 = 0
_FSX3 = 1
_FSY3 = 2
_FSXX3 = 3
_FSYY3 = 4
_FSXY3 = 5
_N_CORR_STATS = 6

_FND = 0
_FSXD = 1
_FSXXD = 2
_FSYD = 3
_FSYYD = 4
_N_STD_STATS = 5


def compute_fp_beta(
    daily: pd.DataFrame,
    factors: pd.DataFrame,
    month_ends: np.ndarray,
    *,
    corr_months: int = 60,
    std_months: int = 12,
    min_3day: int = 750,
    min_daily: int = 120,
    shrinkage: float = 0.6,
) -> pd.DataFrame:
    """
    Frazzini-Pedersen (2014) beta.

    For each month-end:
    - Correlation estimated from 5 years of 3-day compounded log returns
    - Std estimated from 1 year of daily log returns
    - beta = rho * sigma_stock / sigma_mkt
    - Shrunk: 0.6*beta + 0.4*1

    Every quantity is a sum over the window's daily rows, so the daily panel is
    reduced once to one cell of 11 sufficient statistics per ``(stock, month)``
    and each trailing window is the sum of at most ``corr_months`` (or
    ``std_months``) of those cells. A cell only ever produces output when the
    stock traded on the month's last calendar day, which no filled month can
    do, so the windows are summed over the observed cells directly rather than
    over a per-stock dense month grid.

    Parameters
    ----------
    daily : pd.DataFrame
        Daily data with columns: permno, date, ret (or ret_adj).
    factors : pd.DataFrame
        Daily FF factors with columns: date, mktrf, rf.
    month_ends : array of Timestamps
        Month-end dates at which to compute betas.
    corr_months : int
        Lookback months for correlation window (default 60).
    std_months : int
        Lookback months for std window (default 12).
    min_3day : int
        Minimum 3-day observations for correlation (default 750).
    min_daily : int
        Minimum daily observations for std (default 120).
    shrinkage : float
        Weight on raw beta (default 0.6); remainder goes to 1.

    Returns
    -------
    pd.DataFrame
        Columns: date (month-end), permno, bfp.
    """
    LOGGER.info("Computing Frazzini-Pedersen betas for %d months", len(month_ends))

    out_cols = ["date", "permno", "bfp"]
    ret_col = "ret_adj" if "ret_adj" in daily.columns else "ret"

    # -- Trading-day calendar and the market series defined on it ----------
    fac = factors[["date", "mktrf", "rf"]].copy()
    fac["date"] = pd.to_datetime(fac["date"])
    coerce_nullable_dtypes(fac)
    # One row per trading day: a repeated factor date would fan out every
    # stock row it joins.
    fac = (
        fac.dropna(subset=["date"])
        .sort_values("date")
        .drop_duplicates(subset=["date"])
        .reset_index(drop=True)
    )
    if fac.empty or daily.empty:
        return pd.DataFrame(columns=out_cols)

    fac_dates = fac["date"].to_numpy("datetime64[ns]")
    mktrf = fac["mktrf"].astype("float64").to_numpy()
    fac_x = np.where(np.isnan(mktrf), 0.0, mktrf)
    rf = fac["rf"].astype("float64").to_numpy()
    fac_rf = np.where(np.isnan(rf), 0.0, rf)

    fac_ym = (
        fac["date"].dt.year.to_numpy(dtype=np.int64) * 12
        + fac["date"].dt.month.to_numpy(dtype=np.int64)
    )
    ym_lo = int(fac_ym[0])
    n_grid = int(fac_ym[-1]) - ym_lo + 1
    # MATLAB gate (makeBetas.m:88): finite dxret on the *global* last trading
    # day of the month — not the stock's own last row within the month. The
    # last write into each month's slot is that month's last trading day.
    month_last_day = np.full(n_grid, -1, dtype=np.int64)
    month_last_day[fac_ym - ym_lo] = np.arange(fac_dates.size)

    # Target month-end periods, and the month-end date each one prints as.
    me_periods = sorted(set(pd.Timestamp(m).to_period("M") for m in month_ends))
    if not me_periods:
        return pd.DataFrame(columns=out_cols)
    me_int = np.array([p.year * 12 + p.month for p in me_periods], dtype=np.int64)
    me_dates = np.array(
        [np.datetime64(p.to_timestamp() + pd.offsets.MonthEnd(0), "ns")
         for p in me_periods],
        dtype="datetime64[ns]",
    )

    # -- Daily panel, joined to the calendar by position -------------------
    permno = daily["permno"].to_numpy(dtype=np.int64)
    day = pd.to_datetime(daily["date"]).to_numpy("datetime64[ns]")
    rets = daily[ret_col].astype("float64").to_numpy()

    pos = np.searchsorted(fac_dates, day)
    np.clip(pos, 0, fac_dates.size - 1, out=pos)
    on_calendar = fac_dates[pos] == day
    del day
    if not on_calendar.all():
        permno = permno[on_calendar]
        pos = pos[on_calendar]
        rets = rets[on_calendar]
    del on_calendar
    n_rows = permno.size
    if n_rows == 0:
        return pd.DataFrame(columns=out_cols)

    ordered = bool(
        np.all(permno[1:] >= permno[:-1])
        and np.all((permno[1:] != permno[:-1]) | (pos[1:] > pos[:-1]))
    )
    if not ordered:
        order = np.lexsort((pos, permno))
        permno = permno[order]
        pos = pos[order]
        rets = rets[order]
        del order

    xret = rets - fac_rf[pos]
    dmkt = fac_x[pos]
    del rets

    # -- 3-day compounded returns on the trading-day calendar --------------
    # A lag that jumps over a day the stock did not trade is NaN, matching
    # MATLAB's row-wise lag on dxret/dmkt where a non-trading day for stock j
    # produces dxret(t-k, j) = NaN. Rows are sorted by (stock, calendar
    # position), so the k-th previous row is the k-th previous trading day
    # exactly when it belongs to the same stock and sits k positions back.
    def _compound3(x: np.ndarray) -> np.ndarray:
        out = 1.0 + x
        lag = np.full(n_rows, np.nan)
        lag[1:] = np.where(
            # noqa below: pyflakes sees the later `del ym, permno`; the closure
            # only runs before that line.
            (permno[1:] == permno[:-1]) & (pos[1:] - pos[:-1] == 1),  # noqa: F821
            1.0 + x[:-1], np.nan,
        )
        out *= lag
        lag[:] = np.nan
        if n_rows > 2:
            lag[2:] = np.where(
                (permno[2:] == permno[:-2]) & (pos[2:] - pos[:-2] == 2),  # noqa: F821
                1.0 + x[:-2], np.nan,
            )
        out *= lag
        out -= 1.0
        return out

    xret3 = _compound3(xret)
    dmkt3 = _compound3(dmkt)

    # -- Reduce the daily rows to one cell per (stock, month) --------------
    ym = fac_ym[pos]
    new_cell = np.empty(n_rows, dtype=bool)
    new_cell[0] = True
    np.not_equal(permno[1:], permno[:-1], out=new_cell[1:])
    new_cell[1:] |= ym[1:] != ym[:-1]
    starts = np.flatnonzero(new_cell)
    del new_cell
    n_cells = starts.size
    cell_permno = permno[starts]
    cell_ym = ym[starts]
    del ym, permno
    ends = np.empty(n_cells, dtype=np.int64)
    ends[:-1] = starts[1:]
    ends[-1] = n_rows

    last_row = ends - 1
    cell_has_last = (
        (pos[last_row] == month_last_day[cell_ym - ym_lo])
        & np.isfinite(xret[last_row])
    )
    del last_row, pos

    # Pearson corr from sums: rho = (n*sxy - sx*sy) / sqrt((n*sxx-sx^2)(n*syy-sy^2))
    # Population std from sums: std = sqrt(sxx/n - (sx/n)^2)
    corr_stats = np.zeros((n_cells, _N_CORR_STATS), dtype=np.float64)
    std_stats = np.zeros((n_cells, _N_STD_STATS), dtype=np.float64)
    cell_len = ends - starts
    c0 = 0
    while c0 < n_cells:
        c1 = int(np.searchsorted(starts, starts[c0] + _REDUCE_CHUNK_ROWS, side="right"))
        c1 = min(max(c1, c0 + 1), n_cells)
        r0 = int(starts[c0])
        r1 = int(ends[c1 - 1])
        cell_start = starts[c0:c1] - r0
        n_chunk = r1 - r0

        a3 = xret3[r0:r1]
        b3 = dmkt3[r0:r1]
        # MATLAB drops rows where log(1+x) is complex (x < -1, e.g. a -100%
        # delisting return makes dxret = -1 - rf < -1) from BOTH columns of
        # the daily series (makeBetas.m:110-113). Without the > -1 gate,
        # log1p yields NaN which the stock-side sum silently skips while nd
        # and the market sums still count the day.
        v3 = np.isfinite(a3) & np.isfinite(b3) & (a3 > -1) & (b3 > -1)
        # Log returns, left at 0 where invalid so the sums ignore them.
        lx = np.zeros(n_chunk)
        ly = np.zeros(n_chunk)
        np.log1p(a3, out=lx, where=v3)
        np.log1p(b3, out=ly, where=v3)
        contrib = np.empty((n_chunk, _N_CORR_STATS))
        contrib[:, _FN3] = v3
        contrib[:, _FSX3] = lx
        contrib[:, _FSY3] = ly
        contrib[:, _FSXX3] = lx * lx
        contrib[:, _FSYY3] = ly * ly
        contrib[:, _FSXY3] = lx * ly
        corr_stats[c0:c1] = _segment_sums(contrib, cell_start, cell_len[c0:c1])

        ad = xret[r0:r1]
        bd = dmkt[r0:r1]
        vd = np.isfinite(ad) & np.isfinite(bd) & (ad > -1) & (bd > -1)
        lx[:] = 0.0
        ly[:] = 0.0
        np.log1p(ad, out=lx, where=vd)
        np.log1p(bd, out=ly, where=vd)
        contrib = np.empty((n_chunk, _N_STD_STATS))
        contrib[:, _FND] = vd
        contrib[:, _FSXD] = lx
        contrib[:, _FSXXD] = lx * lx
        contrib[:, _FSYD] = ly
        contrib[:, _FSYYD] = ly * ly
        std_stats[c0:c1] = _segment_sums(contrib, cell_start, cell_len[c0:c1])
        c0 = c1

    del xret, dmkt, xret3, dmkt3, starts, ends
    n_stocks = int((cell_permno[1:] != cell_permno[:-1]).sum()) + 1
    LOGGER.info(
        "FP beta: %d daily rows aggregated to %d stock-months across %d stocks; "
        "rolling %d/%d months for corr/std",
        n_rows, n_cells, n_stocks, corr_months, std_months,
    )

    # -- Trailing windows over the (stock, month) cells --------------------
    # A month a stock sat out contributes nothing to either window and can
    # never produce output itself (it has no row on the month's last trading
    # day), so summing the observed cells is the same as rolling over a dense
    # per-stock month grid.
    r60 = _trailing_month_sums(
        corr_stats, cell_permno, cell_ym, corr_months, compensated=True
    )
    del corr_stats
    r12 = _trailing_month_sums(
        std_stats, cell_permno, cell_ym, std_months, compensated=True
    )
    del std_stats

    n = r60[:, _FN3]
    sx = r60[:, _FSX3]
    sy = r60[:, _FSY3]
    sxx = r60[:, _FSXX3]
    syy = r60[:, _FSYY3]
    sxy = r60[:, _FSXY3]

    num = n * sxy - sx * sy
    den_x = n * sxx - sx ** 2
    den_y = n * syy - sy ** 2
    den = np.sqrt(np.maximum(den_x, 0.0) * np.maximum(den_y, 0.0))
    with np.errstate(invalid="ignore", divide="ignore"):
        rho = np.where(den > 0, num / den, np.nan)

    nd = r12[:, _FND]
    with np.errstate(invalid="ignore", divide="ignore"):
        std_s = np.where(
            nd > 0,
            np.sqrt(np.maximum(
                r12[:, _FSXXD] / nd - (r12[:, _FSXD] / nd) ** 2, 0.0
            )),
            np.nan,
        )
        std_m = np.where(
            nd > 0,
            np.sqrt(np.maximum(
                r12[:, _FSYYD] / nd - (r12[:, _FSYD] / nd) ** 2, 0.0
            )),
            np.nan,
        )

        # Beta = rho * sigma_stock / sigma_mkt, then shrink
        raw_beta = rho * std_s / np.where(np.abs(std_m) > 1e-12, std_m, np.nan)
    bfp = shrinkage * raw_beta + (1 - shrinkage)

    # Validity: enough observations, stock active, finite result, and a
    # month-end the caller asked for.
    mask = (
        (n >= min_3day)
        & (nd >= min_daily)
        & cell_has_last
        & np.isfinite(bfp)
        & np.isin(cell_ym, me_int)
    )
    if not mask.any():
        LOGGER.info("Frazzini-Pedersen betas: 0 stock-month observations")
        return pd.DataFrame(columns=out_cols)

    result = pd.DataFrame({
        "date": me_dates[np.searchsorted(me_int, cell_ym[mask])],
        "permno": cell_permno[mask],
        "bfp": bfp[mask],
    })
    LOGGER.info("Frazzini-Pedersen betas: %d stock-month observations", len(result))
    return result


# ---------------------------------------------------------------------------
# OLS-family betas (bols, bdim, bsw, bvck, bstd)
# ---------------------------------------------------------------------------

# Sufficient statistics accumulated per (stock, month) cell. Each of the three
# regressions behind bols/bdim/bsw is a 2x2 or 3x3 normal-equation solve whose
# every entry is a sum over the window's daily rows, so the whole
# stock x month-end loop collapses to summing these cells over each trailing
# window and solving the stacked systems in one shot.
_NY = 0     # days with a finite excess return (the >= min_daily gate)
_N1 = 1     # rows entering the bols design (finite xret and dmkt)
_S1Y = 2
_S1X = 3
_S1YY = 4
_S1XX = 5
_S1XY = 6
_N2 = 7     # rows entering the bdim design (also a finite lagged dmkt)
_S2Y = 8
_S2X = 9
_S2Z = 10
_S2XX = 11
_S2ZZ = 12
_S2XZ = 13
_S2XY = 14
_S2YZ = 15
_SD = 16    # Welch: sum of (winsorized xret - lower bound) on traded days
_SXD = 17
_N_CELL_STATS = 18


def compute_ols_betas(
    daily: pd.DataFrame,
    factors: pd.DataFrame,
    month_ends: np.ndarray,
    *,
    lookback_months: int = 12,
    min_daily: int = 120,
) -> pd.DataFrame:
    """
    Compute OLS-family betas: bols, bdim, bsw, bvck, bstd.

    For each month-end and eligible stock (>= 120 daily obs in trailing year):
    - bols: OLS of xret on [1, mktrf]
    - bdim: OLS of xret on [1, mktrf, lag(mktrf)]; beta = b_mkt + b_lag
    - bsw:  OLS of winsorized xret on [1, mktrf] (Welch bounds)
    - bvck: Vasicek shrinkage of bols toward cross-sectional mean
    - bstd: 0.6 * bdim + 0.4

    All three regressions are solved in one batch. The daily rows are reduced
    to per-(stock, month) sufficient statistics, each trailing window is the
    sum of at most ``lookback_months`` of those cells, and the resulting stacks
    of 2x2 and 3x3 normal equations go through ``np.linalg.solve`` — the same
    LAPACK routine :func:`_nanols` calls one window at a time.

    The Welch leg regresses on the dense factor calendar with the lower Welch
    bound standing in for every day the stock did not trade, so its design
    matrix is the same for every stock and only the traded days' deviation
    from that bound (``_SD``, ``_SXD``) is stock-specific.

    Parameters
    ----------
    daily : pd.DataFrame
        Daily data with columns: permno, date, ret (or ret_adj).
    factors : pd.DataFrame
        Daily FF factors with columns: date, mktrf, rf.
    month_ends : array of Timestamps
        Month-end dates at which to compute betas.
    lookback_months : int
        Trailing months for estimation window (default 12).
    min_daily : int
        Minimum daily observations required (default 120).

    Returns
    -------
    pd.DataFrame
        Columns: date, permno, bols, bdim, bsw, bvck, bstd.
    """
    LOGGER.info("Computing OLS-family betas for %d months", len(month_ends))

    out_cols = ["date", "permno", "bols", "bdim", "bsw", "bvck", "bstd"]
    ret_col = "ret_adj" if "ret_adj" in daily.columns else "ret"

    # -- Trading-day calendar and the market series defined on it ----------
    fac = factors[["date", "mktrf", "rf"]].copy()
    fac["date"] = pd.to_datetime(fac["date"])
    coerce_nullable_dtypes(fac)
    # One row per trading day: MATLAB's dense panel has a single row per date,
    # and a repeated factor date would fan out every stock row it joins.
    fac = (
        fac.dropna(subset=["date"])
        .sort_values("date")
        .drop_duplicates(subset=["date"])
        .reset_index(drop=True)
    )
    if fac.empty or daily.empty:
        return pd.DataFrame(columns=out_cols)

    fac_dates = fac["date"].to_numpy("datetime64[ns]")
    mktrf = fac["mktrf"].astype("float64").to_numpy()
    fac_x = np.where(np.isnan(mktrf), 0.0, mktrf)
    rf = fac["rf"].astype("float64").to_numpy()
    fac_rf = np.where(np.isnan(rf), 0.0, rf)
    # MATLAB dmktL1 = lag(dmkt, 1) on the *global* trading calendar
    # (makeBetas.m:138): a stock row on day t always pairs with the market
    # return of the previous calendar trading day, even across stock gaps.
    fac_z = np.empty_like(fac_x)
    fac_z[0] = np.nan
    fac_z[1:] = fac_x[:-1]
    # Welch bounds: MATLAB max/min ignore NaN (max(NaN, lo) = lo), so a day the
    # stock did not trade regresses at the lower bound (makeBetas.m:141-145).
    fac_lo = np.minimum(-2.0 * fac_x, 4.0 * fac_x)
    fac_hi = np.maximum(-2.0 * fac_x, 4.0 * fac_x)

    fac_ym = (
        fac["date"].dt.year.to_numpy(dtype=np.int64) * 12
        + fac["date"].dt.month.to_numpy(dtype=np.int64)
    )
    ym_lo = int(fac_ym[0])
    n_grid = int(fac_ym[-1]) - ym_lo + 1
    grid_of_day = fac_ym - ym_lo

    # -- Welch's design matrix is the same for every stock -----------------
    # It runs on the dense calendar, so its X'X and the lower-bound part of
    # X'y depend only on the month, not on the stock.
    month_n = np.bincount(grid_of_day, minlength=n_grid).astype(np.float64)
    month_x = np.bincount(grid_of_day, weights=fac_x, minlength=n_grid)
    month_xx = np.bincount(grid_of_day, weights=fac_x * fac_x, minlength=n_grid)
    month_lo = np.bincount(grid_of_day, weights=fac_lo, minlength=n_grid)
    month_xlo = np.bincount(grid_of_day, weights=fac_x * fac_lo, minlength=n_grid)
    # Global last trading day of each month (MATLAB daysPastYear(end)): the
    # eligibility gate requires a finite stock return on this exact day.
    month_last_day = np.full(n_grid, -1, dtype=np.int64)
    month_last_day[grid_of_day] = np.arange(fac_dates.size)

    def _roll_grid(arr: np.ndarray) -> np.ndarray:
        """Trailing ``lookback_months`` sum along the dense month grid."""
        out = arr.copy()
        for lag in range(1, lookback_months):
            out[lag:] += arr[:-lag]
        return out

    win_n = _roll_grid(month_n)
    win_x = _roll_grid(month_x)
    win_xx = _roll_grid(month_xx)
    win_lo = _roll_grid(month_lo)
    win_xlo = _roll_grid(month_xlo)

    # -- Daily panel, joined to the calendar by position -------------------
    permno = daily["permno"].to_numpy(dtype=np.int64)
    day = pd.to_datetime(daily["date"]).to_numpy("datetime64[ns]")
    rets = daily[ret_col].astype("float64").to_numpy()

    fpos = np.searchsorted(fac_dates, day)
    np.clip(fpos, 0, fac_dates.size - 1, out=fpos)
    on_calendar = fac_dates[fpos] == day
    del day
    if not on_calendar.all():
        permno = permno[on_calendar]
        fpos = fpos[on_calendar]
        rets = rets[on_calendar]
    del on_calendar
    n_rows = permno.size
    if n_rows == 0:
        return pd.DataFrame(columns=out_cols)

    # `compute_betas` hands over a (permno, date)-sorted panel; only a direct
    # caller can make this false.
    ordered = bool(
        np.all(permno[1:] >= permno[:-1])
        and np.all((permno[1:] != permno[:-1]) | (fpos[1:] > fpos[:-1]))
    )
    if not ordered:
        order = np.lexsort((fpos, permno))
        permno = permno[order]
        fpos = fpos[order]
        rets = rets[order]
        del order

    # -- Reduce the daily rows to one cell per (stock, month) --------------
    ym = fac_ym[fpos]
    new_cell = np.empty(n_rows, dtype=bool)
    new_cell[0] = True
    np.not_equal(permno[1:], permno[:-1], out=new_cell[1:])
    new_cell[1:] |= ym[1:] != ym[:-1]
    starts = np.flatnonzero(new_cell)
    del new_cell
    n_cells = starts.size
    cell_permno = permno[starts]
    cell_ym = ym[starts]
    del ym, permno
    ends = np.empty(n_cells, dtype=np.int64)
    ends[:-1] = starts[1:]
    ends[-1] = n_rows

    # The gate reads the stock's last row of the month, not a window sum.
    last_row = ends - 1
    cell_last_day = fpos[last_row]
    cell_last_finite = np.isfinite(rets[last_row] - fac_rf[cell_last_day])
    del last_row

    stats = np.zeros((n_cells, _N_CELL_STATS), dtype=np.float64)
    c0 = 0
    while c0 < n_cells:
        c1 = int(np.searchsorted(starts, starts[c0] + _REDUCE_CHUNK_ROWS, side="right"))
        c1 = min(max(c1, c0 + 1), n_cells)
        r0 = int(starts[c0])
        r1 = int(ends[c1 - 1])
        cell_start = starts[c0:c1] - r0

        f = fpos[r0:r1]
        y = rets[r0:r1] - fac_rf[f]
        x = fac_x[f]
        z = fac_z[f]
        # `_nanols` drops rows with a non-finite entry anywhere in y or X, and
        # the Dimson design carries one more column than the others.
        y_finite = np.isfinite(y)
        m1 = y_finite & np.isfinite(x)
        m2 = m1 & np.isfinite(z)

        y1 = np.where(m1, y, 0.0)
        x1 = np.where(m1, x, 0.0)
        stats[c0:c1, _NY] = np.add.reduceat(y_finite.astype(np.float64), cell_start)
        stats[c0:c1, _N1] = np.add.reduceat(m1.astype(np.float64), cell_start)
        stats[c0:c1, _S1Y] = np.add.reduceat(y1, cell_start)
        stats[c0:c1, _S1X] = np.add.reduceat(x1, cell_start)
        stats[c0:c1, _S1YY] = np.add.reduceat(y1 * y1, cell_start)
        stats[c0:c1, _S1XX] = np.add.reduceat(x1 * x1, cell_start)
        stats[c0:c1, _S1XY] = np.add.reduceat(y1 * x1, cell_start)

        y2 = np.where(m2, y, 0.0)
        x2 = np.where(m2, x, 0.0)
        z2 = np.where(m2, z, 0.0)
        stats[c0:c1, _N2] = np.add.reduceat(m2.astype(np.float64), cell_start)
        stats[c0:c1, _S2Y] = np.add.reduceat(y2, cell_start)
        stats[c0:c1, _S2X] = np.add.reduceat(x2, cell_start)
        stats[c0:c1, _S2Z] = np.add.reduceat(z2, cell_start)
        stats[c0:c1, _S2XX] = np.add.reduceat(x2 * x2, cell_start)
        stats[c0:c1, _S2ZZ] = np.add.reduceat(z2 * z2, cell_start)
        stats[c0:c1, _S2XZ] = np.add.reduceat(x2 * z2, cell_start)
        stats[c0:c1, _S2XY] = np.add.reduceat(y2 * x2, cell_start)
        stats[c0:c1, _S2YZ] = np.add.reduceat(y2 * z2, cell_start)

        lo = fac_lo[f]
        deviation = np.fmin(np.fmax(y, lo), fac_hi[f]) - lo
        stats[c0:c1, _SD] = np.add.reduceat(deviation, cell_start)
        stats[c0:c1, _SXD] = np.add.reduceat(x * deviation, cell_start)
        c0 = c1

    del fpos, rets, starts, ends
    n_stocks = int((cell_permno[1:] != cell_permno[:-1]).sum()) + 1
    LOGGER.info(
        "OLS beta: %d daily rows reduced to %d (stock, month) cells across %d stocks",
        n_rows, n_cells, n_stocks,
    )

    window = _trailing_month_sums(stats, cell_permno, cell_ym, lookback_months)
    del stats

    # -- Eligible (stock, month-end) cells ---------------------------------
    me_periods = sorted(set(pd.Timestamp(m).to_period("M") for m in month_ends))
    if not me_periods:
        return pd.DataFrame(columns=out_cols)
    me_ts_map = {pd.Timestamp(m).to_period("M"): pd.Timestamp(m) for m in month_ends}
    me_int = np.array([p.year * 12 + p.month for p in me_periods], dtype=np.int64)

    grid = cell_ym - ym_lo
    rows = np.flatnonzero(
        np.isin(cell_ym, me_int)
        & (window[:, _NY] >= min_daily)
        & cell_last_finite
        & (cell_last_day == month_last_day[grid])
    )
    if rows.size == 0:
        LOGGER.info("OLS-family betas: 0 stock-month observations")
        return pd.DataFrame(columns=out_cols)

    stat = window[rows]
    grid = grid[rows]
    n_out = rows.size

    # -- bols: xret ~ 1 + dmkt, plus the standard error Vasicek needs -------
    # The second right-hand side is the unit vector, so the solve also returns
    # inv(X'X)[1, 1] -- `np.linalg.inv` on a stack this size costs 50x a solve.
    n1 = stat[:, _N1]
    A1 = np.empty((n_out, 2, 2))
    A1[:, 0, 0] = n1
    A1[:, 0, 1] = A1[:, 1, 0] = stat[:, _S1X]
    A1[:, 1, 1] = stat[:, _S1XX]
    B1 = np.zeros((n_out, 2, 2))
    B1[:, 0, 0] = stat[:, _S1Y]
    B1[:, 1, 0] = stat[:, _S1XY]
    B1[:, 1, 1] = 1.0
    ok1 = n1 >= 3  # `_nanols` requires n >= k + 1
    sol1 = np.full((n_out, 2, 2), np.nan)
    sol1[ok1] = _batched_solve(A1[ok1], B1[ok1])
    beta1 = sol1[:, :, 0]
    bols = beta1[:, 1]
    resid_ss = (
        stat[:, _S1YY]
        - 2.0 * np.einsum("ij,ij->i", beta1, B1[:, :, 0])
        + np.einsum("ij,ijk,ik->i", beta1, A1, beta1)
    )
    with np.errstate(invalid="ignore", divide="ignore"):
        bols_se = np.sqrt(np.maximum(resid_ss / (n1 - 2.0) * sol1[:, 1, 1], 0.0))
    del A1, B1, sol1, beta1

    # -- bdim: xret ~ 1 + dmkt + lag(dmkt), summed coefficients ------------
    n2 = stat[:, _N2]
    A2 = np.empty((n_out, 3, 3))
    A2[:, 0, 0] = n2
    A2[:, 0, 1] = A2[:, 1, 0] = stat[:, _S2X]
    A2[:, 0, 2] = A2[:, 2, 0] = stat[:, _S2Z]
    A2[:, 1, 1] = stat[:, _S2XX]
    A2[:, 1, 2] = A2[:, 2, 1] = stat[:, _S2XZ]
    A2[:, 2, 2] = stat[:, _S2ZZ]
    B2 = np.stack([stat[:, _S2Y], stat[:, _S2XY], stat[:, _S2YZ]], axis=1)
    ok2 = n2 >= 4
    sol2 = np.full((n_out, 3), np.nan)
    sol2[ok2] = _batched_solve(A2[ok2], B2[ok2])
    bdim = sol2[:, 1] + sol2[:, 2]
    del A2, B2, sol2

    # -- bsw: Welch on the dense calendar ----------------------------------
    nw = win_n[grid]
    A3 = np.empty((n_out, 2, 2))
    A3[:, 0, 0] = nw
    A3[:, 0, 1] = A3[:, 1, 0] = win_x[grid]
    A3[:, 1, 1] = win_xx[grid]
    B3 = np.stack([win_lo[grid] + stat[:, _SD], win_xlo[grid] + stat[:, _SXD]], axis=1)
    ok3 = nw >= 3
    sol3 = np.full((n_out, 2), np.nan)
    sol3[ok3] = _batched_solve(A3[ok3], B3[ok3])
    bsw = sol3[:, 1]
    del A3, B3, sol3

    date_of_grid = np.full(n_grid, np.datetime64("NaT", "ns"), dtype="datetime64[ns]")
    for period in me_periods:
        gi = period.year * 12 + period.month - ym_lo
        if 0 <= gi < n_grid:
            date_of_grid[gi] = np.datetime64(me_ts_map[period], "ns")

    # -- Vasicek shrinkage (cross-sectional, per month) --------------------
    # Output is one block per month-end, stocks ascending inside it. The rows
    # arrive ordered by (stock, month), so one lexsort puts them in that order
    # and each month becomes a contiguous slice.
    out_date = date_of_grid[grid]
    out_permno = cell_permno[rows]
    order = np.lexsort((out_permno, out_date.view("int64")))
    out_date = out_date[order]
    out_permno = out_permno[order]
    bols = bols[order]
    bols_se = bols_se[order]
    bdim = bdim[order]
    bsw = bsw[order]

    blk_start = np.flatnonzero(
        np.concatenate(([True], out_date[1:] != out_date[:-1]))
    )
    blk_stop = np.append(blk_start[1:], n_out)
    # The cross-sectional mean and variance stay per-month `np.nanmean` /
    # `np.nanvar` calls on the same values in the same order: they are one
    # reduction per month over a few thousand stocks, so nothing is gained by
    # reassociating them into a grouped sum.
    sigma_T2 = np.empty(blk_start.size)
    bols_mean = np.empty(blk_start.size)
    for i, (s, e) in enumerate(zip(blk_start, blk_stop)):
        valid_b = bols[s:e][np.isfinite(bols[s:e])]
        if valid_b.size > 1:
            # MATLAB std(bols(i,:),'omitnan') is the sample std (ddof=1)
            sigma_T2[i] = np.nanvar(valid_b, ddof=1)
            bols_mean[i] = np.nanmean(valid_b)
        else:
            sigma_T2[i] = 0.0
            bols_mean[i] = np.nanmean(valid_b) if valid_b.size > 0 else 1.0

    counts = blk_stop - blk_start
    sigma_T2 = np.repeat(sigma_T2, counts)
    bols_mean = np.repeat(bols_mean, counts)

    denom = sigma_T2 + bols_se ** 2
    with np.errstate(invalid="ignore"):
        w = np.where(np.isfinite(denom) & (denom > 0), sigma_T2 / denom, np.nan)
    bvck = np.where(np.isfinite(w), w * bols + (1 - w) * bols_mean, np.nan)
    bstd = np.where(np.isfinite(bdim), 0.6 * bdim + 0.4, np.nan)

    out = pd.DataFrame({
        "date": out_date,
        "permno": out_permno,
        "bols": bols,
        "bdim": bdim,
        "bsw": bsw,
        "bvck": bvck,
        "bstd": bstd,
    })
    LOGGER.info("OLS-family betas: %d stock-month observations", len(out))
    return out


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_betas(
    daily: pd.DataFrame,
    factors: pd.DataFrame,
    month_ends: np.ndarray,
    *,
    sample_start: int = 1963,
    delist: pd.DataFrame | None = None,
    universe_permnos: np.ndarray | pd.Series | list | None = None,
) -> pd.DataFrame:
    """
    Compute all 6 beta variants and return a single DataFrame.

    Parameters
    ----------
    daily : pd.DataFrame
        Daily stock data with columns: permno, date, ret (or ret_adj).
    factors : pd.DataFrame
        Daily FF factors with columns: date, mktrf, smb, hml, rf.
    month_ends : array-like of Timestamps
        Month-end dates defining the panel.
    sample_start : int
        First calendar year of the sample (used to skip early months
        that lack sufficient lookback).
    delist : pd.DataFrame, optional
        CRSP msedelist with permno, dlstdt, dlret. When supplied, synthetic
        ``dlret`` rows are inserted via ``_insert_matlab_dlret_rows`` before
        estimation (matches makeCRSPDailyDerivedVariables.m:82–110).
    universe_permnos : array-like, optional
        Main-universe permnos (typically domestic common, shrcd 10/11).
        Restricts the daily panel so Vasicek cross-section means match MATLAB.

    Returns
    -------
    pd.DataFrame
        Columns: date, permno, bfp, bols, bdim, bsw, bvck, bstd.
    """
    month_ends = pd.DatetimeIndex(month_ends).sort_values()

    if universe_permnos is not None:
        univ = set(pd.Series(universe_permnos).astype(int))
        n_before = daily["permno"].nunique()
        daily = daily[daily["permno"].astype(int).isin(univ)].copy()
        LOGGER.info(
            "Universe filter: %d → %d stocks",
            n_before, daily["permno"].nunique(),
        )

    if delist is not None and not delist.empty:
        daily = _insert_matlab_dlret_rows(daily, delist, factors)

    # FP needs 3 years of history (60 months of 3-day returns)
    fp_start = pd.Timestamp(f"{sample_start + 3}-01-31") + pd.offsets.MonthEnd(0)
    fp_months = month_ends[month_ends >= fp_start]

    # OLS family needs 1 year
    ols_start = pd.Timestamp(f"{sample_start + 1}-01-31") + pd.offsets.MonthEnd(0)
    ols_months = month_ends[month_ends >= ols_start]

    LOGGER.info(
        "Beta estimation: %d FP months (from %s), %d OLS months (from %s)",
        len(fp_months), fp_start.strftime("%Y-%m"),
        len(ols_months), ols_start.strftime("%Y-%m"),
    )

    # Compute FP betas
    fp_df = compute_fp_beta(daily, factors, fp_months)

    # Compute OLS-family betas
    ols_df = compute_ols_betas(daily, factors, ols_months)

    # Merge
    if fp_df.empty and ols_df.empty:
        return pd.DataFrame(columns=["date", "permno", "bfp", "bols", "bdim", "bsw", "bvck", "bstd"])

    if fp_df.empty:
        ols_df["bfp"] = np.nan
        return ols_df
    if ols_df.empty:
        for col in ["bols", "bdim", "bsw", "bvck", "bstd"]:
            fp_df[col] = np.nan
        return fp_df

    merged = ols_df.merge(fp_df, on=["date", "permno"], how="outer")
    return merged


# ---------------------------------------------------------------------------
# Aggregate betas to monthly for ccm_panel merge
# ---------------------------------------------------------------------------

def aggregate_betas_to_monthly(betas: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure beta DataFrame has month-end dates for merging into ccm_panel.

    The compute functions already produce month-end dates, so this is
    mostly a pass-through with date normalization.

    Parameters
    ----------
    betas : pd.DataFrame
        Output of compute_betas().

    Returns
    -------
    pd.DataFrame
        Same columns, dates normalized to month-end.
    """
    if betas.empty:
        return betas
    out = betas.copy()
    out["date"] = pd.to_datetime(out["date"]) + pd.offsets.MonthEnd(0)
    return out


__all__ = [
    "_insert_matlab_dlret_rows",
    "compute_fp_beta",
    "compute_ols_betas",
    "compute_betas",
    "aggregate_betas_to_monthly",
]
