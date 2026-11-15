"""
CRSP daily derived variables.

MATLAB equivalents:
- makeCRSPDailyData.m (delisting adjustment)
- makeCRSPDailyDerivedVariables.m (rvol, amihud, maxret, idiovol)

Derived variables (monthly frequency, produced in aggregate_daily_to_monthly):
- rvol_1m/3m/6m/12m/36m/60m: calendar-month std of daily returns (MATLAB RVOL*)
- amihud: 12-calendar-month mean of |ret|/dollar_vol with >=200 obs and prc>5
- maxret: max daily return within month (Bali/Cakici/Whitelaw MAX). MATLAB's
  L246 takes max share volume here.
- idiovol: 1-month CAPM residual vol, ddof=0 (MATLAB IVOL);
  also idiovol_3m / idiovol_ff / idiovol_ff_3m (IVOL3 / IffVOL / IffVOL3)
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from ..config import AssayConfig

LOGGER = logging.getLogger("assayinganomalies.transforms.crsp_daily")

# Calendar-month windows matching MATLAB RVOL1/3/6/12/36/60
RVOL_WINDOWS_MONTHS: tuple[int, ...] = (1, 3, 6, 12, 36, 60)


def coerce_nullable_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert pandas nullable extension dtypes to numpy dtypes in-place.

    WRDS parquet files use nullable ``Float64`` / ``Int64`` (capital letters).
    When ``.values`` is called on these columns the result is an ``object``
    array, which breaks numpy ufuncs like ``np.isfinite``.  This helper
    converts them to standard ``float64`` / ``int64``.
    """
    for col in df.columns:
        if pd.api.types.is_extension_array_dtype(df[col]):
            if pd.api.types.is_float_dtype(df[col]):
                df[col] = df[col].astype("float64")
            elif pd.api.types.is_integer_dtype(df[col]):
                if df[col].isna().any():
                    df[col] = df[col].astype("float64")
                else:
                    df[col] = df[col].astype("int64")
    return df


def _normalize_daily(raw: pd.DataFrame, config: AssayConfig) -> pd.DataFrame:
    """
    Normalize raw CRSP daily data: lowercase columns, parse dates,
    filter to sample window, convert nullable dtypes to numpy dtypes.
    """
    df = raw.copy()
    df.columns = df.columns.str.lower()

    df["date"] = pd.to_datetime(df["date"])
    df["permno"] = df["permno"].astype(int)
    coerce_nullable_dtypes(df)

    # Filter to sample window
    lo = pd.Timestamp(f"{config.sample_start}-01-01")
    hi = pd.Timestamp(f"{config.sample_end}-12-31")
    df = df[(df["date"] >= lo) & (df["date"] <= hi)].copy()

    df = df.sort_values(["permno", "date"]).reset_index(drop=True)
    LOGGER.info("Normalized daily data: %d rows, %d stocks", len(df), df["permno"].nunique())
    return df


def compute_daily_delisting_adj(
    df: pd.DataFrame,
    delist: pd.DataFrame | None = None,
) -> pd.Series:
    """
    Apply delisting return adjustment to daily returns.

    If the stock's last trading day return is NaN and a dlret is available,
    substitute dlret. If the last day has a valid return, compound it with dlret.

    Parameters
    ----------
    df : pd.DataFrame
        Daily data with columns: permno, date, ret.
    delist : pd.DataFrame, optional
        Delisting events with columns: permno, dlstdt, dlret.

    Returns
    -------
    pd.Series
        Adjusted returns (same index as df).
    """
    ret_adj = df["ret"].copy()

    if delist is None or delist.empty:
        return ret_adj

    dl = delist[["permno", "dlstdt", "dlret"]].dropna(subset=["dlret"]).copy()
    if dl.empty:
        return ret_adj

    dl["dlstdt"] = pd.to_datetime(dl["dlstdt"])
    dl["permno"] = dl["permno"].astype(int)

    # Merge delisting info onto the daily panel
    merged = df[["permno", "date", "ret"]].merge(
        dl,
        left_on=["permno", "date"],
        right_on=["permno", "dlstdt"],
        how="left",
    )

    has_dlret = merged["dlret"].notna()
    has_ret = merged["ret"].notna()

    # Case 1: both ret and dlret exist → compound
    both = has_ret & has_dlret
    ret_adj.loc[both] = (1 + merged.loc[both, "ret"]) * (1 + merged.loc[both, "dlret"]) - 1

    # Case 2: ret is NaN but dlret exists → substitute
    only_dl = ~has_ret & has_dlret
    ret_adj.loc[only_dl] = merged.loc[only_dl, "dlret"]

    n_adj = int(both.sum() + only_dl.sum())
    if n_adj > 0:
        LOGGER.info("Applied daily delisting adjustment to %d observations", n_adj)
    return ret_adj


def _ym_int_to_period(x: int) -> pd.Period:
    """Decode ym_int = year*12 + month (month in 1..12) to a monthly Period."""
    month = ((int(x) - 1) % 12) + 1
    year = (int(x) - month) // 12
    return pd.Period(year=year, month=month, freq="M")


def _month_ends_from_ym_int(ym_int: pd.Series) -> pd.Series:
    """Convert ym_int series to month-end Timestamps."""
    dates = [
        _ym_int_to_period(int(x)).to_timestamp(how="end").normalize()
        for x in ym_int
    ]
    return pd.to_datetime(dates) + pd.offsets.MonthEnd(0)


def _month_end_from_period(ym: pd.Series) -> pd.Series:
    """Convert Period[M] series to month-end Timestamps."""
    dates = ym.dt.to_timestamp(how="end").dt.normalize()
    return dates + pd.offsets.MonthEnd(0)


def _matlab_std(values: np.ndarray) -> float:
    """
    Match MATLAB ``std(x, 0)``: sample std (ddof=1), with the 1-element
    special case returning 0 (MATLAB does; NumPy returns NaN).
    """
    x = values[np.isfinite(values)]
    n = len(x)
    if n == 0:
        return np.nan
    if n == 1:
        return 0.0
    return float(np.std(x, ddof=1))


def _lagged_cells(values: np.ndarray, lag: int, within: np.ndarray) -> np.ndarray:
    """
    ``values`` shifted ``lag`` months down the stacked month grid, zeroed
    where the shift would reach back past the stock's own first month.

    ``within`` is each cell's month offset inside its stock, so ``within <
    lag`` marks exactly the cells whose source lies in the previous stock.
    """
    out = np.zeros_like(values)
    out[lag:] = values[:-lag]
    out[within < lag] = 0
    return out


def _ret_col(df: pd.DataFrame) -> str:
    return "ret_adj" if "ret_adj" in df.columns else "ret"


def adjust_nasdaq_volume(
    daily: pd.DataFrame,
    exchcd: pd.DataFrame | None = None,
) -> pd.Series:
    """
    Gao-Ritter (2010) NASDAQ share-volume adjustment.

    Faithful port of ``makeCRSPDailyDerivedVariables.m:113-145``:
    for ``exchcd == 3`` (NASDAQ), divide volume by 2 / 1.8 / 1.6 in the
    pre-2001-02 / 2001 / 2002-2003 windows respectively.

    Parameters
    ----------
    daily : DataFrame
        Must contain ``permno``, ``date``, ``vol``.
    exchcd : DataFrame, optional
        Monthly ``permno, date, exchcd``. When omitted (or empty), returns
        the unadjusted ``vol`` series.

    Returns
    -------
    pd.Series
        Adjusted volume aligned to ``daily.index``.
    """
    vol = daily["vol"].astype("float64").copy()
    if exchcd is None or exchcd.empty or "exchcd" not in (exchcd.columns if exchcd is not None else []):
        return vol

    d = daily[["permno", "date"]].copy()
    d["date"] = pd.to_datetime(d["date"])

    # MATLAB dexchcd (makeCRSPDailyDerivedVariables.m:119-130): month-end
    # trading days carry their own month's exchcd; every other day carries
    # the exchcd of the *previous* month-end trading day. Equivalently, day t
    # uses the month of the latest month-end trading day <= t. Days before
    # the first month-end stay NaN (no adjustment). No ffill across months
    # with missing exchcd.
    cal = np.sort(d["date"].unique())
    cal_ym = pd.DatetimeIndex(cal).to_period("M")
    is_eom = np.r_[cal_ym[:-1] != cal_ym[1:], True]  # last trading day per month
    eom_dates = cal[is_eom]
    eom_month_end = pd.DatetimeIndex(eom_dates) + pd.offsets.MonthEnd(0)

    # For each daily date, the applicable month-end (searchsorted right - 1)
    pos = np.searchsorted(eom_dates, d["date"].to_numpy(), side="right") - 1
    applicable = pd.Series(pd.NaT, index=d.index)
    valid = pos >= 0
    applicable[valid] = eom_month_end[pos[valid]]
    d["month_end"] = applicable

    ex = exchcd[["permno", "date", "exchcd"]].copy()
    ex["date"] = pd.to_datetime(ex["date"])
    ex = ex.rename(columns={"date": "month_end"})
    ex = ex.drop_duplicates(subset=["permno", "month_end"], keep="last")

    merged = d.merge(ex, on=["permno", "month_end"], how="left")
    merged = merged.set_index(daily.index)
    nasdaq = merged["exchcd"] == 3
    dates = merged["date"]

    m = nasdaq & (dates < pd.Timestamp("2001-02-01"))
    vol.loc[m] = vol.loc[m] / 2.0
    m = nasdaq & (dates >= pd.Timestamp("2001-02-01")) & (dates < pd.Timestamp("2002-01-01"))
    vol.loc[m] = vol.loc[m] / 1.8
    m = nasdaq & (dates >= pd.Timestamp("2002-01-01")) & (dates < pd.Timestamp("2004-01-01"))
    vol.loc[m] = vol.loc[m] / 1.6
    return vol


# ---------------------------------------------------------------------------
# Realized volatility — monthly calendar-month windows (MATLAB RVOL*)
# ---------------------------------------------------------------------------

def compute_monthly_rvol(
    daily: pd.DataFrame,
    windows_months: tuple[int, ...] = RVOL_WINDOWS_MONTHS,
) -> pd.DataFrame:
    """
    Calendar-month realized volatility at monthly frequency.

    Matches MATLAB ``makeCRSPDailyDerivedVariables.m`` RVOL1/3/6/12/36/60:
    ``RVOLw(i,:) = std(dret(indW,:), 0, 1)`` on the dense (day x stock)
    matrix. MATLAB ``std`` propagates NaN, so a stock-month is finite only
    when the stock has a finite return on *every* trading day of the whole
    trailing ``w``-month window (global daily calendar); ddof=1.

    Implementation note: the loop this replaces walked every stock, every
    month of that stock's life and every window in Python, which cost 35
    minutes on the full daily panel. The reduction below collapses the daily
    rows onto one (stock, month) cell each — observation count, mean and
    within-month sum of squared deviations — and then merges the cells of
    each trailing window pairwise. It carries deviations rather than a sum of
    squares throughout, because a quiet month inside a volatile stock's
    history has a variance many orders of magnitude below anything the
    sum-of-squares identity would have to difference. ``_matlab_std`` remains
    the scalar statement of the per-window rule this reproduces.

    Returns
    -------
    pd.DataFrame
        Columns: permno, date (month-end), rvol_1m, rvol_3m, ...
    """
    LOGGER.info("Starting monthly rvol")
    ret_col = _ret_col(daily)
    rvol_cols = [f"rvol_{w}m" for w in windows_months]
    empty_cols = ["permno", "date"] + rvol_cols

    if len(daily) == 0:
        return pd.DataFrame(columns=empty_cols)

    dates = pd.to_datetime(daily["date"])
    ym_row = dates.dt.year.to_numpy(dtype=np.int64) * 12 + dates.dt.month.to_numpy(dtype=np.int64)

    # Global trading calendar (MATLAB ddates): month -> trading-day count,
    # from all panel rows (incl. NaN returns) so the dense-day denominator
    # matches MATLAB.
    cal_dates = pd.DatetimeIndex(pd.unique(dates.to_numpy()))
    cal_ym = cal_dates.year.to_numpy(dtype=np.int64) * 12 + cal_dates.month.to_numpy(dtype=np.int64)
    cal_first_ym = int(cal_ym.min())
    n_cal_months = int(cal_ym.max()) - cal_first_ym + 1
    cal_days = np.bincount(cal_ym - cal_first_ym, minlength=n_cal_months)
    cal_cum = np.concatenate([[0], np.cumsum(cal_days)])

    # required[w][m] = trading days in the w-month window ending at calendar
    # month m, clipped at the start of the calendar (MATLAB's `_window_days`).
    m_idx = np.arange(n_cal_months, dtype=np.int64)
    required = {
        w: cal_cum[m_idx + 1] - cal_cum[np.maximum(m_idx - w + 1, 0)]
        for w in windows_months
    }

    # Only rows carrying a return count toward window completeness.
    ret_row = daily[ret_col].astype("float64").to_numpy()
    keep = ~np.isnan(ret_row)
    if not keep.any():
        return pd.DataFrame(columns=empty_cols)
    permno_row = daily["permno"].to_numpy()[keep]
    ym_row = ym_row[keep]
    ret_row = ret_row[keep]
    n_rows = len(ret_row)
    all_ym = np.unique(ym_row)

    codes, permnos = pd.factorize(permno_row, sort=True)
    codes = codes.astype(np.int64, copy=False)
    n_stocks = len(permnos)
    LOGGER.info("  monthly rvol: %d stocks, %d daily rows", n_stocks, n_rows)

    # Each stock contributes every month between its first and last daily
    # observation, trading months and silent ones alike. `seen` is one bit per
    # (stock, calendar month) — a few tens of MB at CRSP scale — and its first
    # and last set bit per row give that span without sorting 100M rows.
    chunk = 10_000_000
    seen = np.zeros(n_stocks * n_cal_months, dtype=bool)
    for a in range(0, n_rows, chunk):
        b = min(a + chunk, n_rows)
        seen[codes[a:b] * n_cal_months + (ym_row[a:b] - cal_first_ym)] = True
    seen = seen.reshape(n_stocks, n_cal_months)
    first_ym = cal_first_ym + seen.argmax(axis=1).astype(np.int64)
    last_ym = cal_first_ym + (n_cal_months - 1 - seen[:, ::-1].argmax(axis=1).astype(np.int64))
    del seen

    # Stack those spans into one flat month grid, stock-major.
    n_months = last_ym - first_ym + 1
    offsets = np.concatenate([[0], np.cumsum(n_months)])
    n_cells = int(offsets[-1])
    stock_of_cell = np.repeat(np.arange(n_stocks, dtype=np.int64), n_months)
    within = np.arange(n_cells, dtype=np.int64) - offsets[stock_of_cell]
    month_of_cell = first_ym[stock_of_cell] + within

    def cells_of(a: int, b: int) -> np.ndarray:
        c = codes[a:b]
        return offsets[c] + (ym_row[a:b] - first_ym[c])

    # Collapse the daily rows onto that grid. A non-NaN return fills its slot
    # in the dense-window count even if it is +/-inf, but `_matlab_std` drops
    # it before taking deviations, so infinities need a count of their own.
    # They never occur in practice.
    all_finite = bool(np.isfinite(ret_row).all())
    cell_cnt = np.zeros(n_cells, dtype=np.int64)
    cell_n = np.zeros(n_cells, dtype=np.int64)
    cell_sum = np.zeros(n_cells, dtype=np.float64)
    for a in range(0, n_rows, chunk):
        b = min(a + chunk, n_rows)
        cell = cells_of(a, b)
        r = ret_row[a:b]
        cell_cnt += np.bincount(cell, minlength=n_cells)
        if all_finite:
            cell_sum += np.bincount(cell, weights=r, minlength=n_cells)
        else:
            finite = np.isfinite(r)
            cell_n += np.bincount(cell[finite], minlength=n_cells)
            cell_sum += np.bincount(cell, weights=np.where(finite, r, 0.0), minlength=n_cells)
    if all_finite:
        cell_n = cell_cnt
    cell_mean = np.divide(
        cell_sum, cell_n, out=np.zeros(n_cells, dtype=np.float64), where=cell_n > 0
    )

    # Second pass for each month's sum of squared deviations about its own
    # mean — the same two-pass numpy.std itself takes, so the one-month window
    # comes back to the last bit.
    cell_m2 = np.zeros(n_cells, dtype=np.float64)
    for a in range(0, n_rows, chunk):
        b = min(a + chunk, n_rows)
        cell = cells_of(a, b)
        r = ret_row[a:b]
        if not all_finite:
            finite = np.isfinite(r)
            cell, r = cell[finite], r[finite]
        dev = r - cell_mean[cell]
        cell_m2 += np.bincount(cell, weights=dev * dev, minlength=n_cells)

    cell_n_f = cell_n.astype(np.float64)
    columns: dict[str, np.ndarray] = {}
    for w in windows_months:
        # Chan/Golub/LeVeque pairwise merge of the window's months, newest
        # first. Accumulating deviations forward beats differencing a running
        # total backward out of one: the window never sees the rest of the
        # stock's history, so its own scale sets the precision.
        acc_cnt = cell_cnt.copy()
        acc_n = cell_n_f.copy()
        acc_mean = cell_mean.copy()
        acc_m2 = cell_m2.copy()
        for lag in range(1, w):
            add_cnt = _lagged_cells(cell_cnt, lag, within)
            add_n = _lagged_cells(cell_n_f, lag, within)
            add_mean = _lagged_cells(cell_mean, lag, within)
            add_m2 = _lagged_cells(cell_m2, lag, within)
            total = acc_n + add_n
            safe = np.where(total > 0.0, total, 1.0)
            delta = add_mean - acc_mean
            acc_m2 += add_m2 + delta * delta * (acc_n * add_n / safe)
            acc_mean += delta * (add_n / safe)
            acc_n = total
            acc_cnt += add_cnt

        # MATLAB's std propagates NaN, so the window must be dense: the stock
        # needs a return on every trading day of the whole trailing window.
        req = required[w][month_of_cell - cal_first_ym]
        complete = (req > 0) & (acc_cnt == req)

        with np.errstate(invalid="ignore", divide="ignore"):
            std = np.sqrt(acc_m2 / (acc_n - 1.0))
        # `_matlab_std`: no finite observation is NaN, exactly one is 0.
        std = np.where(acc_n >= 2, std, np.where(acc_n == 1, 0.0, np.nan))
        columns[f"rvol_{w}m"] = np.where(complete, std, np.nan)

    # Keep only months that appear in the global calendar of observed yms
    grid_keep = np.isin(month_of_cell, all_ym)
    out = pd.DataFrame({"permno": permnos[stock_of_cell[grid_keep]]})
    for col in rvol_cols:
        out[col] = columns[col][grid_keep]
    kept_months = month_of_cell[grid_keep]
    month_lut, inverse = np.unique(kept_months, return_inverse=True)
    out["date"] = pd.DatetimeIndex(_month_ends_from_ym_int(pd.Series(month_lut)))[inverse]
    LOGGER.info("Monthly rvol: %d stock-months", len(out))
    return out


def compute_realized_volatility(
    daily: pd.DataFrame,
    window: int = 1,
    min_obs: int | None = None,  # noqa: ARG001 — kept for API compat; unused
) -> pd.DataFrame:
    """
    Compatibility wrapper: ``window`` is interpreted as calendar months.

    Prefer ``compute_monthly_rvol``. Returns monthly DataFrame with a single
    ``rvol_{window}m`` column plus permno/date.
    """
    return compute_monthly_rvol(daily, windows_months=(int(window),))


# ---------------------------------------------------------------------------
# Amihud — monthly 12-calendar-month mean (MATLAB amihud)
# ---------------------------------------------------------------------------

def compute_amihud(
    daily: pd.DataFrame,
    *,
    window_months: int = 12,
    min_obs: int = 200,
    min_prc: float = 5.0,
    exchcd: pd.DataFrame | None = None,
    monthly_prc: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Amihud (2002) illiquidity at monthly frequency.

    Matches MATLAB ``makeCRSPDailyDerivedVariables.m`` lines 155–194:
    - daily ratio = |ret| / (|prc| * |vol|), zero-vol days masked to NaN first
    - volume is Gao-Ritter adjusted when ``exchcd`` is provided
    - NO 1e6 scaling
    - monthly value = nanmean over trailing ``window_months`` calendar months
    - drop if < ``min_obs`` finite daily ratios OR monthly |prc| <= ``min_prc``.
      The price filter uses the *monthly CRSP* price (MATLAB ``prc.mat``,
      pass via ``monthly_prc``); a NaN monthly price passes the filter
      (MATLAB ``prc(i,:) <= 5`` is false for NaN).
    - first ``window_months - 1`` months are NaN (MATLAB loop starts at i=12)
    - a month with no daily rows for the stock still gets a value from the
      trailing window (MATLAB computes every (i, stock) cell), so values
      extend up to ``window_months - 1`` months past the last daily row.

    Implementation note: the loop this replaces walked every stock against the
    *global* month list, re-masking the stock's whole daily history once per
    month and reading the price filter out of a Python dict — 20 minutes on
    the real daily panel. It now reduces the daily ratios onto one cell per
    (stock, month) — finite count, non-NaN count, non-NaN sum — and merges
    each trailing window's months by adding lagged cells. Summing month totals
    instead of the window's raw rows is safe here in a way it was not for
    RVOL (see ``compute_monthly_rvol``): the ratios are non-negative, so
    nothing cancels. Nothing is ever differenced out of a running total.

    Returns
    -------
    pd.DataFrame
        Columns: permno, date (month-end), amihud.
    """
    LOGGER.info("Starting amihud")
    ret_col = _ret_col(daily)
    need = {"permno", "date", "prc", "vol"}
    empty = pd.DataFrame(columns=["permno", "date", "amihud"])
    if not need.issubset(daily.columns) or ret_col not in daily.columns:
        LOGGER.warning("Amihud requires prc and vol; returning empty")
        return empty
    if len(daily) == 0:
        return empty

    tmp = daily[["permno", "date", ret_col, "prc", "vol"]].copy()
    tmp["date"] = pd.to_datetime(tmp["date"])
    ym_row = (
        tmp["date"].dt.year.to_numpy(dtype=np.int64) * 12
        + tmp["date"].dt.month.to_numpy(dtype=np.int64)
    )
    tmp["ym_int"] = ym_row

    # Gao-Ritter NASDAQ adjustment (MATLAB dvol), then mask zeros
    vol = adjust_nasdaq_volume(tmp, exchcd=exchcd)
    vol = vol.where(vol != 0.0)
    dvol = tmp["prc"].abs() * vol.abs()
    dvol = dvol.replace(0, np.nan)
    pi_row = (tmp[ret_col].abs() / dvol).to_numpy(dtype="float64")  # no 1e6 scaling
    del vol, dvol

    # Monthly |prc| lookup: prefer the monthly CRSP panel (MATLAB prc.mat);
    # fall back to last daily prc per month when not provided.
    if monthly_prc is not None and not monthly_prc.empty and "prc" in monthly_prc.columns:
        mp = monthly_prc[["permno", "date", "prc"]].copy()
        mp["date"] = pd.to_datetime(mp["date"])
        mp["ym_int"] = mp["date"].dt.year * 12 + mp["date"].dt.month
        month_prc = mp[["permno", "ym_int"]].copy()
        month_prc["month_prc"] = pd.to_numeric(mp["prc"], errors="coerce").abs()
    else:
        prc_sorted = tmp.sort_values("date", kind="mergesort")
        prc_sorted = prc_sorted[prc_sorted["prc"].notna()]
        month_prc = (
            prc_sorted.groupby(["permno", "ym_int"], sort=False)["prc"]
            .last()
            .abs()
            .rename("month_prc")
            .reset_index()
        )

    all_ym = np.unique(ym_row)
    n_all = len(all_ym)
    if n_all < window_months:
        LOGGER.info("Amihud: fewer than %d months of data; all NaN", window_months)
        return empty

    codes, permnos = pd.factorize(tmp["permno"].to_numpy(), sort=False)
    codes = codes.astype(np.int64, copy=False)
    n_stocks = len(permnos)
    n_rows = len(ym_row)
    LOGGER.info("  amihud: %d stocks, %d daily rows", n_stocks, n_rows)

    # First and last month each stock is observed, as positions in `all_ym`.
    # One bit per (stock, month) — a few tens of MB at CRSP scale.
    chunk = 10_000_000
    seen = np.zeros(n_stocks * n_all, dtype=bool)
    for a in range(0, n_rows, chunk):
        b = min(a + chunk, n_rows)
        seen[codes[a:b] * n_all + np.searchsorted(all_ym, ym_row[a:b])] = True
    seen = seen.reshape(n_stocks, n_all)
    g_first = seen.argmax(axis=1).astype(np.int64)
    g_last = (n_all - 1 - seen[:, ::-1].argmax(axis=1)).astype(np.int64)
    del seen

    # MATLAB computes every (month, stock) cell, so each stock's grid runs
    # window_months-1 months past its last daily row. That end is a calendar
    # month, not a position, so it is resolved by value against `all_ym`.
    g_end = np.searchsorted(
        all_ym, all_ym[g_last] + window_months - 1, side="right",
    ).astype(np.int64) - 1
    np.minimum(g_end, n_all - 1, out=g_end)

    n_months = g_end - g_first + 1
    offsets = np.concatenate([[0], np.cumsum(n_months)])
    n_cells = int(offsets[-1])
    stock_of_cell = np.repeat(np.arange(n_stocks, dtype=np.int64), n_months)
    within = np.arange(n_cells, dtype=np.int64) - offsets[stock_of_cell]
    month_of_cell = g_first[stock_of_cell] + within

    # Collapse the daily ratios onto that grid. The >=min_obs gate counts
    # finite ratios while MATLAB's nanmean averages every non-NaN one, so
    # +/-Inf would enter the mean but not the count; the two counts are the
    # same array unless an infinite ratio actually occurs.
    has_inf = bool(np.isinf(pi_row).any())
    cell_fin = np.zeros(n_cells, dtype=np.int64)
    cell_obs = np.zeros(n_cells, dtype=np.int64)
    cell_sum = np.zeros(n_cells, dtype=np.float64)
    for a in range(0, n_rows, chunk):
        b = min(a + chunk, n_rows)
        c = codes[a:b]
        cell = offsets[c] + (np.searchsorted(all_ym, ym_row[a:b]) - g_first[c])
        p = pi_row[a:b]
        obs = ~np.isnan(p)
        cell_obs += np.bincount(cell[obs], minlength=n_cells)
        cell_sum += np.bincount(cell, weights=np.where(obs, p, 0.0), minlength=n_cells)
        if has_inf:
            cell_fin += np.bincount(cell[np.isfinite(p)], minlength=n_cells)
    if not has_inf:
        cell_fin = cell_obs

    # Trailing window: add the window_months-1 preceding months of the same
    # stock. `_lagged_cells` zeroes anything reaching back past the stock's
    # own first month, which is exactly where it has no daily rows.
    win_fin = cell_fin.copy()
    win_obs = cell_obs.copy()
    win_sum = cell_sum.copy()
    for lag in range(1, window_months):
        win_fin += _lagged_cells(cell_fin, lag, within)
        win_obs += _lagged_cells(cell_obs, lag, within)
        win_sum += _lagged_cells(cell_sum, lag, within)

    # Monthly price filter, scattered onto the same grid. Duplicate
    # (permno, month) prices keep the last one, as the dict lookup did.
    prc_cell = np.full(n_cells, np.nan, dtype=np.float64)
    if not month_prc.empty:
        mp_stock = pd.Index(np.asarray(permnos).astype(np.int64)).get_indexer(
            month_prc["permno"].to_numpy(dtype=np.int64)
        )
        mp_ym = month_prc["ym_int"].to_numpy(dtype=np.int64)
        mp_pos = np.clip(np.searchsorted(all_ym, mp_ym), 0, n_all - 1)
        on_grid = (mp_stock >= 0) & (all_ym[mp_pos] == mp_ym)
        s, g = mp_stock[on_grid], mp_pos[on_grid]
        inside = (g >= g_first[s]) & (g <= g_end[s])
        s, g = s[inside], g[inside]
        prc_cell[offsets[s] + (g - g_first[s])] = (
            month_prc["month_prc"].to_numpy(dtype="float64")[on_grid][inside]
        )

    mean = np.divide(
        win_sum, win_obs,
        out=np.full(n_cells, np.nan, dtype=np.float64),
        where=win_obs > 0,
    )
    # A NaN monthly price passes the filter (MATLAB `prc(i,:) <= 5` is false
    # for NaN).
    drop = (win_fin < min_obs) | (np.isfinite(prc_cell) & (prc_cell <= min_prc))
    values = np.where(drop, np.nan, mean)

    # MATLAB's loop starts at i = window_months, so the calendar's first
    # window_months-1 months produce nothing.
    keep = month_of_cell >= window_months - 1
    if not keep.any():
        return empty

    out = pd.DataFrame({
        "permno": permnos[stock_of_cell[keep]],
        "amihud": values[keep],
    })
    kept_months = all_ym[month_of_cell[keep]]
    month_lut, inverse = np.unique(kept_months, return_inverse=True)
    out["date"] = pd.DatetimeIndex(_month_ends_from_ym_int(pd.Series(month_lut)))[inverse]
    LOGGER.info("Amihud monthly: %d stock-months", len(out))
    return out


# ---------------------------------------------------------------------------
# Maxret — within-month maximum daily return (Bali/Cakici/Whitelaw MAX)
# ---------------------------------------------------------------------------

def compute_maxret(daily: pd.DataFrame) -> pd.DataFrame:
    """
    Within-month maximum daily return, at monthly frequency.

    MATLAB ``makeCRSPDailyDerivedVariables.m:246`` indexes the daily *share
    volume* matrix here while naming, commenting and saving the result as
    ``dretmax``, so its `maxret` is a volume measure. This port takes the
    maximum of the daily return series instead, making ``maxret`` the
    Bali/Cakici/Whitelaw (2011) MAX signal its name promises. The volume
    series MATLAB actually produced is not carried.
    """
    LOGGER.info("Starting maxret")
    ret_col = _ret_col(daily)
    tmp = daily[["permno", "date", ret_col]].copy()
    tmp["date"] = pd.to_datetime(tmp["date"])
    tmp["ym"] = tmp["date"].dt.to_period("M")

    monthly = (
        tmp.groupby(["permno", "ym"])[ret_col]
        .max()
        .rename("maxret")
        .reset_index()
    )
    monthly["date"] = _month_end_from_period(monthly["ym"])
    monthly = monthly.drop(columns=["ym"])
    LOGGER.info("Maxret monthly: %d stock-months", len(monthly))
    return monthly


# ---------------------------------------------------------------------------
# Idiosyncratic vol — monthly CAPM / FF3 (MATLAB IVOL family)
# ---------------------------------------------------------------------------

def _nanols_resid_rms(y: np.ndarray, X: np.ndarray) -> float:
    """
    OLS residual RMS (ddof=0): ``sqrt(mean(resid^2))``, matching MATLAB
    ``sqrt(mean(res.resid.^2))`` after ``nanols``.
    """
    mask = np.isfinite(y) & np.all(np.isfinite(X), axis=1)
    yc = y[mask]
    Xc = X[mask]
    n, k = Xc.shape
    if n < k + 1:
        return np.nan
    try:
        beta = np.linalg.lstsq(Xc, yc, rcond=None)[0]
    except np.linalg.LinAlgError:
        return np.nan
    resid = yc - Xc @ beta
    return float(np.sqrt(np.mean(resid ** 2)))


def compute_idiovol(
    daily: pd.DataFrame,
    factors: pd.DataFrame | None = None,
    *,
    windows_months: tuple[int, ...] = (1, 3),
) -> pd.DataFrame:
    """
    Monthly idiosyncratic volatility matching MATLAB IVOL family.

    Column mapping (MATLAB → Python):
    - IVOL     → ``idiovol``       (1-month CAPM residual RMS, ddof=0)
    - IVOL3    → ``idiovol_3m``    (3-month CAPM)
    - IffVOL   → ``idiovol_ff``    (1-month FF3)
    - IffVOL3  → ``idiovol_ff_3m`` (3-month FF3)

    Each value is ``sqrt(mean(resid^2))`` from ``nanols`` of excess returns
    on [const, mktrf] (CAPM) or [const, mktrf, smb, hml] (FF3) over the
    trailing W calendar months of daily observations.

    MATLAB gate (``makeCRSPDailyDerivedVariables.m`` ``hor_ind``): a stock-month
    is eligible only when *every* trading day in that month's factor calendar
    has a finite excess return (``isfinite(sum(dxret(ind1,:)))``). Partial-month
    coverage must leave IVOL/IffVOL/IVOL3/IffVOL3 as NaN.
    """
    LOGGER.info("Starting idiovol")
    ret_col = _ret_col(daily)
    empty_cols = ["permno", "date", "idiovol", "idiovol_3m", "idiovol_ff", "idiovol_ff_3m"]

    if factors is None or factors.empty:
        LOGGER.info("No daily factors; idiovol columns will be empty")
        return pd.DataFrame(columns=empty_cols)

    fac = factors.copy()
    fac["date"] = pd.to_datetime(fac["date"])
    coerce_nullable_dtypes(fac)
    fac_cols = [c for c in ["mktrf", "smb", "hml", "rf"] if c in fac.columns]
    merged = daily[["permno", "date", ret_col]].merge(
        fac[["date"] + fac_cols], on="date", how="inner",
    )
    if merged.empty:
        return pd.DataFrame(columns=empty_cols)

    rf = merged["rf"].fillna(0) if "rf" in merged.columns else 0.0
    merged["xret"] = merged[ret_col] - rf
    merged["ym"] = merged["date"].dt.to_period("M")
    merged["ym_int"] = merged["ym"].dt.year * 12 + merged["ym"].dt.month

    has_ff3 = all(c in merged.columns for c in ("mktrf", "smb", "hml"))
    has_capm = "mktrf" in merged.columns
    if not has_capm:
        LOGGER.warning("No mktrf in factors; idiovol empty")
        return pd.DataFrame(columns=empty_cols)

    want_w1 = 1 in windows_months
    want_w3 = 3 in windows_months

    # Trading-day counts per calendar month (MATLAB ind1 length).
    fac_ym = fac["date"].dt.year * 12 + fac["date"].dt.month
    cal_days_per_ym = fac_ym.value_counts().to_dict()

    # Sort once so each stock's daily rows are contiguous and date-ordered.
    merged = merged.sort_values(["permno", "date"], kind="mergesort").reset_index(drop=True)
    n_stocks = int(merged["permno"].nunique())
    LOGGER.info("  idiovol: %d stocks, %d daily rows", n_stocks, len(merged))

    permno_arr = merged["permno"].to_numpy()
    ym_int_all = merged["ym_int"].to_numpy(dtype=np.int64)
    xret_all = merged["xret"].to_numpy(dtype="float64")
    mkt_all = merged["mktrf"].to_numpy(dtype="float64")
    smb_all = (
        merged["smb"].to_numpy(dtype="float64") if has_ff3
        else np.empty(0, dtype="float64")
    )
    hml_all = (
        merged["hml"].to_numpy(dtype="float64") if has_ff3
        else np.empty(0, dtype="float64")
    )

    # Contiguous permno blocks (data already sorted by permno).
    change = np.flatnonzero(np.r_[True, permno_arr[1:] != permno_arr[:-1], True])
    n_blocks = len(change) - 1

    out_permno: list[np.ndarray] = []
    out_ym: list[np.ndarray] = []
    out_iv: list[np.ndarray] = []
    out_iv3: list[np.ndarray] = []
    out_iff: list[np.ndarray] = []
    out_iff3: list[np.ndarray] = []

    for i in range(n_blocks):
        lo, hi = int(change[i]), int(change[i + 1])
        permno = int(permno_arr[lo])
        ym_int = ym_int_all[lo:hi]
        xret = xret_all[lo:hi]
        mkt = mkt_all[lo:hi]
        smb = smb_all[lo:hi] if has_ff3 else None
        hml = hml_all[lo:hi] if has_ff3 else None

        # Month start/end indices for O(1) window slices (ym_int sorted within stock).
        stock_yms, start_idx, counts = np.unique(
            ym_int, return_index=True, return_counts=True,
        )
        end_idx = start_idx + counts
        n_m = len(stock_yms)
        first_ym = int(stock_yms[0])

        iv = np.full(n_m, np.nan)
        iv3 = np.full(n_m, np.nan)
        iff = np.full(n_m, np.nan)
        iff3 = np.full(n_m, np.nan)

        for k in range(n_m):
            me = int(stock_yms[k])
            s1, e1 = int(start_idx[k]), int(end_idx[k])
            y1 = xret[s1:e1]
            # MATLAB hor_ind: finite excess return on every trading day in month.
            n_cal = int(cal_days_per_ym.get(me, -1))
            complete_month = (
                n_cal > 0
                and (e1 - s1) == n_cal
                and bool(np.all(np.isfinite(y1)))
            )
            if not complete_month:
                continue

            if want_w1:
                ones = np.ones(e1 - s1)
                X_capm = np.column_stack([ones, mkt[s1:e1]])
                iv[k] = _nanols_resid_rms(y1, X_capm)
                if has_ff3:
                    X_ff = np.column_stack([ones, mkt[s1:e1], smb[s1:e1], hml[s1:e1]])
                    iff[k] = _nanols_resid_rms(y1, X_ff)

            if want_w3:
                win_start = max(me - 2, first_ym)
                j0 = int(np.searchsorted(stock_yms, win_start, side="left"))
                s, e = int(start_idx[j0]), int(end_idx[k])
                y = xret[s:e]
                ones = np.ones(e - s)
                X_capm = np.column_stack([ones, mkt[s:e]])
                iv3[k] = _nanols_resid_rms(y, X_capm)
                if has_ff3:
                    X_ff = np.column_stack([ones, mkt[s:e], smb[s:e], hml[s:e]])
                    iff3[k] = _nanols_resid_rms(y, X_ff)

        out_permno.append(np.full(n_m, permno, dtype=np.int64))
        out_ym.append(stock_yms.astype(np.int64, copy=False))
        out_iv.append(iv)
        out_iv3.append(iv3)
        out_iff.append(iff)
        out_iff3.append(iff3)

        if (i + 1) % 2000 == 0:
            LOGGER.info("  idiovol progress: %d / %d stocks", i + 1, n_stocks)

    if not out_permno:
        return pd.DataFrame(columns=empty_cols)

    out = pd.DataFrame({
        "permno": np.concatenate(out_permno),
        "ym_int": np.concatenate(out_ym),
        "idiovol": np.concatenate(out_iv),
        "idiovol_3m": np.concatenate(out_iv3),
        "idiovol_ff": np.concatenate(out_iff),
        "idiovol_ff_3m": np.concatenate(out_iff3),
    })
    out["date"] = _month_ends_from_ym_int(out["ym_int"])
    out = out.drop(columns=["ym_int"])
    LOGGER.info("Monthly idiovol: %d stock-months", len(out))
    return out


# ---------------------------------------------------------------------------
# Pipeline entry points
# ---------------------------------------------------------------------------

def transform_daily(
    raw: pd.DataFrame,
    config: AssayConfig,
    *,
    delist: pd.DataFrame | None = None,
    factors: pd.DataFrame | None = None,  # noqa: ARG001 — kept for call-site compat
) -> pd.DataFrame:
    """
    Daily CRSP transforms: normalize, delisting adjustment, daily ME.

    Monthly measures (rvol, amihud, idiovol, maxret) are produced in
    ``aggregate_daily_to_monthly``, not written onto the daily panel.
    """
    LOGGER.info("Starting daily CRSP transforms: %d raw rows", len(raw))

    df = _normalize_daily(raw, config)
    df["ret_adj"] = compute_daily_delisting_adj(df, delist=delist)

    if "prc" in df.columns and "shrout" in df.columns:
        df["me"] = df["prc"].abs() * df["shrout"]

    df = df.drop(columns=["cfacpr", "cfacshr"], errors="ignore")

    LOGGER.info(
        "Daily transforms complete: %d rows, %d columns, %d stocks",
        len(df), len(df.columns), df["permno"].nunique(),
    )
    return df


def aggregate_daily_to_monthly(
    daily: pd.DataFrame,
    factors: pd.DataFrame | None = None,
    exchcd: pd.DataFrame | None = None,
    monthly_prc: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Produce monthly-frequency daily-derived variables for ccm_panel merge.

    Computes calendar-month rvol / amihud / idiovol / maxret directly at
    monthly frequency (MATLAB design). No end-of-month snapshot of a daily
    rolling series.

    ``exchcd`` (monthly permno/date/exchcd) is used for the Gao-Ritter
    NASDAQ volume adjustment in Amihud. ``monthly_prc`` (permno/date/prc from
    the monthly CRSP file) feeds the Amihud price filter (MATLAB ``prc.mat``).

    Parity note: ``daily`` should carry the MATLAB-style ``dret`` series
    (raw ret + placed dlret rows) as its return column — pass a frame
    without ``ret_adj`` so ``_ret_col`` picks ``ret``.
    """
    LOGGER.info("Aggregating daily -> monthly derived measures")

    pieces: list[pd.DataFrame] = []

    rvol = compute_monthly_rvol(daily)
    if not rvol.empty:
        pieces.append(rvol)

    if "prc" in daily.columns and "vol" in daily.columns:
        amihud = compute_amihud(daily, exchcd=exchcd, monthly_prc=monthly_prc)
        if not amihud.empty:
            pieces.append(amihud)

    maxret = compute_maxret(daily)
    if not maxret.empty:
        pieces.append(maxret)

    idiovol = compute_idiovol(daily, factors=factors)
    if not idiovol.empty:
        pieces.append(idiovol)

    if not pieces:
        return pd.DataFrame(columns=["permno", "date"])

    result = pieces[0]
    for piece in pieces[1:]:
        result = result.merge(piece, on=["permno", "date"], how="outer")

    LOGGER.info(
        "Aggregated daily to monthly: %d rows, columns: %s",
        len(result), list(result.columns),
    )
    return result


def compute_car3(
    daily: pd.DataFrame,
    fundq: pd.DataFrame,
    factors: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Cumulative abnormal return in the 3-day window around earnings announcements.

    MATLAB equivalent: ``makeCRSPDailyDerivedVariables.m`` lines 324-379.

    Semantics (traced against the MATLAB source):

    1. ``dxret = 1 + dret - (dmkt + drf)`` on the dense (day x stock) matrix.
       NaN daily returns propagate — MATLAB never zero-fills, so a window with
       a missing return yields NaN and the previous quarter's CAR3 survives
       via ``FillMonths``.
    2. The window is indexed on the *global* trading-day calendar (``ddates``):
       ``CAR3 = prod(dxret(r-1:r+1)) - 1`` where ``r`` is the exact calendar
       position of RDQ. A stock missing one of those calendar days contributes
       NaN — not its nearest observed row.
    3. ``RDQ(isnan(FQTR)) = nan`` means raw CAR3 exists only at announcement
       months (one row per permno-month, keeping the latest ``(rdq, datadate)``
       as in ``mergeCRSPCOMP.m:172-175``). MATLAB's ``FQTR`` is
       ``yyyymmdd(datadate)`` (``mergeCRSPCOMP.m:190-192``), *not* Compustat's
       fiscal-quarter field, so the filter requires a non-missing ``datadate``.
    4. ``FillMonths`` (quarterly branch, persist=2) forward-fills interior NaNs
       and extends at most ``QUARTERLY_FILL_HORIZON`` (=2) months past the last
       *finite* value.

    The final ``CAR3(isnan(ret)) = nan`` monthly-return mask is applied by the
    pipeline stage after merging into ``ccm_panel``.

    Implementation note: the loop this replaces scattered each stock's daily
    rows into its own dense calendar-length vector and then read the three
    window days out of it one announcement at a time. Both loops are gone.
    ``(permno, calendar position)`` is packed into a single ascending key, so
    one binary search per announcement finds the announcement day, and its two
    neighbours are the adjacent rows — used only when their key is exactly one
    position away, which is the same "a missing calendar day contributes NaN"
    rule the dense vector encoded. ``FillMonths`` then becomes a forward-fill
    along one stacked month grid.
    """
    from .compustat import QUARTERLY_FILL_HORIZON

    ret_col = _ret_col(daily)
    empty = pd.DataFrame(columns=["permno", "date", "car3"])
    if len(daily) == 0:
        return empty

    # --- Dense daily calendar and abnormal returns (MATLAB dxret) ---
    permno_row = daily["permno"].to_numpy(dtype=np.int64)
    date_row = pd.to_datetime(daily["date"]).to_numpy()
    ret_row = pd.to_numeric(daily[ret_col], errors="coerce").to_numpy(dtype="float64")

    # The panel arrives sorted by (permno, date) from every caller; sorting
    # 100M rows again just to confirm that would cost more than the rest of
    # this function put together.
    ordered = bool(np.all(
        (permno_row[1:] > permno_row[:-1])
        | ((permno_row[1:] == permno_row[:-1]) & (date_row[1:] >= date_row[:-1]))
    ))
    if not ordered:
        order = np.lexsort((date_row, permno_row))
        permno_row, date_row, ret_row = permno_row[order], date_row[order], ret_row[order]

    calendar = np.unique(date_row)
    n_days = len(calendar)

    # Market return per calendar day (dmkt + drf); NaN where factors are
    # missing so it propagates exactly like MATLAB's rptdMkt.
    mkt = np.zeros(n_days, dtype=np.float64)
    if factors is not None and not factors.empty:
        f = factors.copy()
        f["date"] = pd.to_datetime(f["date"])
        f = f.drop_duplicates(subset=["date"]).set_index("date")
        f = f.reindex(pd.DatetimeIndex(calendar))
        mkt = np.full(n_days, np.nan, dtype=np.float64)
        if "mktrf" in f.columns:
            mktrf = pd.to_numeric(f["mktrf"], errors="coerce").astype("float64").to_numpy()
            rf = (
                pd.to_numeric(f["rf"], errors="coerce").astype("float64").to_numpy()
                if "rf" in f.columns
                else np.zeros(n_days, dtype=np.float64)
            )
            mkt = mktrf + rf

    pos_row = np.searchsorted(calendar, date_row)
    abret = 1.0 + ret_row - mkt[pos_row]
    del ret_row, date_row

    # (permno, calendar position) as one ascending key.
    key = permno_row * n_days + pos_row
    del permno_row, pos_row
    if len(key) > 1:
        # Scattering into a dense per-stock vector kept the last row written
        # for a duplicated (permno, day); dropping all but the last keeps that
        # reading. CRSP daily has no duplicates, MATLAB's matrix could not
        # represent them, and dlret placement overwrites in place.
        dup = key[1:] == key[:-1]
        if dup.any():
            unique_row = np.ones(len(key), dtype=bool)
            unique_row[:-1] = ~dup
            key, abret = key[unique_row], abret[unique_row]

    # --- Announcement months: one row per permno-month, latest (rdq, datadate) ---
    keep_cols = [c for c in ["permno", "rdq", "datadate"] if c in fundq.columns]
    q = fundq[keep_cols].copy()
    q["rdq"] = pd.to_datetime(q["rdq"], errors="coerce")
    q = q.dropna(subset=["rdq"])
    sort_cols = ["permno", "rdq"]
    if "datadate" in q.columns:
        # RDQ(isnan(FQTR)) = nan, where FQTR = yyyymmdd(datadate)
        q["datadate"] = pd.to_datetime(q["datadate"], errors="coerce")
        q = q.dropna(subset=["datadate"])
        sort_cols.append("datadate")
    if q.empty:
        LOGGER.info("No valid RDQ dates in fundq; CAR3 will be empty")
        return empty

    q["permno"] = q["permno"].astype(int)
    q["month"] = q["rdq"] + pd.offsets.MonthEnd(0)
    q = q.sort_values(sort_cols)
    q = q.drop_duplicates(subset=["permno", "month"], keep="last")

    # --- Window products on the global calendar ---
    rdq_row = q["rdq"].to_numpy()
    ev_pos = np.searchsorted(calendar, rdq_row)
    # MATLAB: r = find(ddates==RDQ); skip when RDQ is not a trading day or
    # the window would run off the calendar (r < length(ddates)).
    on_calendar = calendar[np.clip(ev_pos, 0, n_days - 1)] == rdq_row
    valid = on_calendar & (ev_pos >= 1) & (ev_pos <= n_days - 2)
    if not valid.any():
        LOGGER.info("Computed CAR3 for 0 announcement events")
        return empty

    ev_permno = q["permno"].to_numpy(dtype=np.int64)[valid]
    ev_month = (
        q["month"].dt.year.to_numpy(dtype=np.int64) * 12
        + q["month"].dt.month.to_numpy(dtype=np.int64)
    )[valid]
    target = ev_permno * n_days + ev_pos[valid]

    n_key = len(key)
    r = np.searchsorted(key, target)
    at = np.minimum(r, n_key - 1)
    # No row on the announcement day itself leaves the product NaN, which is
    # also what a stock with no daily rows at all gets: an all-NaN stock drops
    # out of FillMonths below, exactly as it never entered the old stock loop.
    hit = key[at] == target
    center = np.where(hit, abret[at], np.nan)
    before = np.maximum(r - 1, 0)
    left = np.where(hit & (r > 0) & (key[before] == target - 1), abret[before], np.nan)
    after = np.minimum(r + 1, n_key - 1)
    right = np.where(
        hit & (r + 1 < n_key) & (key[after] == target + 1), abret[after], np.nan
    )
    car3_vals = left * center * right - 1.0
    LOGGER.info(
        "Computed CAR3 for %d announcement events", int(np.isfinite(car3_vals).sum())
    )

    # --- FillMonths: ffill interior NaNs, extend 2 months past last finite ---
    # `q` is sorted by permno then rdq, so events are already grouped by stock
    # and ascending in month; a group starts wherever permno changes.
    grp_start = np.flatnonzero(np.r_[True, ev_permno[1:] != ev_permno[:-1]])
    n_grp = len(grp_start)
    observed = ~np.isnan(car3_vals)
    finite = np.isfinite(car3_vals)
    last_finite = np.maximum.reduceat(np.where(finite, ev_month, -1), grp_start)
    first_obs = np.minimum.reduceat(
        np.where(observed, ev_month, np.iinfo(np.int64).max), grp_start
    )

    grid_end = pd.Timestamp(calendar[-1]) + pd.offsets.MonthEnd(0)
    grid_end_ym = grid_end.year * 12 + grid_end.month
    # A stock with no finite CAR3 anywhere contributes no rows at all.
    kept = np.flatnonzero(last_finite >= 0)
    if len(kept) == 0:
        return empty
    # The ffill-then-dropna the loop did means each stock's panel runs from its
    # first non-NaN announcement to two months past its last finite one.
    start_ym = first_obs[kept]
    cap_ym = np.minimum(last_finite[kept] + QUARTERLY_FILL_HORIZON, grid_end_ym)

    n_months = cap_ym - start_ym + 1
    offsets = np.concatenate([[0], np.cumsum(n_months)])
    n_cells = int(offsets[-1])
    grp_of_cell = np.repeat(np.arange(len(kept), dtype=np.int64), n_months)
    ym_of_cell = start_ym[grp_of_cell] + (
        np.arange(n_cells, dtype=np.int64) - offsets[grp_of_cell]
    )

    grp_of_event = np.repeat(
        np.arange(n_grp, dtype=np.int64), np.diff(np.r_[grp_start, len(ev_month)])
    )
    cell_of_grp = np.full(n_grp, -1, dtype=np.int64)
    cell_of_grp[kept] = np.arange(len(kept), dtype=np.int64)
    g = cell_of_grp[grp_of_event]
    take = observed & (g >= 0)
    g, ym, val = g[take], ev_month[take], car3_vals[take]
    inside = (ym >= start_ym[g]) & (ym <= cap_ym[g])
    cells = offsets[g[inside]] + (ym[inside] - start_ym[g[inside]])

    filled = np.zeros(n_cells, dtype=bool)
    values = np.full(n_cells, np.nan, dtype=np.float64)
    filled[cells] = True
    values[cells] = val[inside]
    # Forward-fill: carry the index of the last filled cell. Every stock's
    # first cell is its first non-NaN announcement month, so the running
    # maximum resets there and cannot leak from one stock into the next.
    values = values[np.maximum.accumulate(np.where(filled, np.arange(n_cells), -1))]

    car3_monthly = pd.DataFrame({
        "permno": ev_permno[grp_start][kept][grp_of_cell],
        "car3": values,
    })
    month_lut, inverse = np.unique(ym_of_cell, return_inverse=True)
    car3_monthly["date"] = pd.DatetimeIndex(
        _month_ends_from_ym_int(pd.Series(month_lut))
    )[inverse]
    LOGGER.info("CAR3 monthly panel: %d rows, %d stocks", n_cells, len(kept))
    return car3_monthly[["permno", "date", "car3"]]


__all__ = [
    "coerce_nullable_dtypes",
    "compute_daily_delisting_adj",
    "adjust_nasdaq_volume",
    "compute_monthly_rvol",
    "compute_realized_volatility",
    "compute_amihud",
    "compute_maxret",
    "compute_idiovol",
    "compute_car3",
    "transform_daily",
    "aggregate_daily_to_monthly",
    "RVOL_WINDOWS_MONTHS",
]
