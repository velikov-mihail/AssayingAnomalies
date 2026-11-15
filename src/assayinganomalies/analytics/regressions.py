"""
Regression utilities (Fama–MacBeth and related helpers).

This module implements a Python port of the MATLAB `runFamaMacBeth.m` workflow:
- (optional) winsorize/trim RHS variables by month
- (optional) fill low-frequency RHS variables forward
- lag RHS variables by `num_lags` (default 1)
- run monthly cross-sectional OLS or WLS
- average coefficients over time and compute t-stats
  - either plain OLS t-stats on the mean
  - or Newey–West HAC t-stats on the mean
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


@dataclass
class RegressionResult:
    beta: pd.DataFrame
    bhat: pd.Series
    t: pd.Series
    rbar2: pd.Series
    mean_r2: float
    metadata: dict[str, Any]

    def print_results(self) -> None:
        labels = list(self.bhat.index)
        print("----------------------------------------------------------------------")
        print("           Results from Fama - MacBeth regressions")
        print("----------------------------------------------------------------------")
        for lab in labels:
            b = self.bhat.loc[lab]
            tt = self.t.loc[lab]
            b_str = f"{b:12.3f}" if pd.notna(b) else f"{'NaN':>12}"
            t_str = f"{tt:12.3f}" if pd.notna(tt) else f"{'NaN':>12}"
            print(f"{lab:<25}{b_str}{t_str}")
        print("----------------------------------------------------------------------")


def _ensure_panel_index(obj: pd.Series | pd.DataFrame, name: str) -> None:
    if not isinstance(obj.index, pd.MultiIndex) or obj.index.names[:2] != ["date", "permno"]:
        raise ValueError(f"{name} must be indexed by MultiIndex (date, permno) with names ['date','permno'].")


def _dedupe_names(names: Sequence[str]) -> list[str]:
    """Make regressor names unique without renaming any name that is free.

    The first use of a name keeps it; later repeats get ``_2``, ``_3``, ...
    skipping any label already requested elsewhere in ``names``, so
    ``["a", "a", "a_2"]`` becomes ``["a", "a_3", "a_2"]``.
    """
    taken = set(names)
    seen: set[str] = set()
    out: list[str] = []
    for nm in names:
        if nm not in seen:
            seen.add(nm)
            out.append(nm)
            continue
        j = 2
        while f"{nm}_{j}" in taken:
            j += 1
        new = f"{nm}_{j}"
        taken.add(new)
        out.append(new)
    return out


def _as_regressor(obj: Any, what: str) -> pd.Series:
    """One regressor: a Series, or a one-column DataFrame squeezed to one."""
    if isinstance(obj, pd.DataFrame):
        if obj.shape[1] != 1:
            raise ValueError(
                f"{what} must be a Series or a one-column DataFrame "
                f"(got {obj.shape[1]} columns)."
            )
        return obj.iloc[:, 0]
    if not isinstance(obj, pd.Series):
        raise TypeError(f"{what} must be a pandas Series (got {type(obj).__name__}).")
    return obj


def _regressor_frame(
    x: pd.DataFrame | pd.Series | Sequence[pd.Series] | Mapping[str, pd.Series],
) -> tuple[pd.DataFrame, list[str]]:
    """Put the regressors in one DataFrame, one column per requested regressor.

    Columns are placed by position, never looked up by key, so two regressors
    that share a name (``[x, x * x]`` keeps ``x.name``) both reach the fit.
    Returns ``(frame, names)`` where ``names`` are the unique column names.
    """
    if isinstance(x, pd.DataFrame):
        if x.columns.has_duplicates:
            dups = sorted({str(c) for c in x.columns[x.columns.duplicated()]})
            raise ValueError(f"x has duplicate column labels: {dups}")
        return x, [str(c) for c in x.columns]
    if isinstance(x, pd.Series):
        items = [x]
        raw = [x.name]
    elif isinstance(x, Mapping):
        items = [_as_regressor(v, f"x[{k!r}]") for k, v in x.items()]
        raw = list(x.keys())
    elif isinstance(x, (list, tuple)):
        items = [_as_regressor(s, f"x[{i}]") for i, s in enumerate(x)]
        raw = [s.name for s in items]
    else:
        raise TypeError(
            "x must be a DataFrame, a Series, a list/tuple of Series, or a mapping "
            f"of name -> Series (got {type(x).__name__})."
        )
    if not items:
        raise ValueError("x must contain at least one regressor.")
    base = [
        f"x{i}" if (nm is None or nm == "") else str(nm)
        for i, nm in enumerate(raw, start=1)
    ]
    names = _dedupe_names(base)
    # `keys=` labels the columns in list order; `join="outer"` is concat's
    # default and matches the old dict-of-Series concat.
    frame = pd.concat(items, axis=1, keys=names)
    return frame, names


def _panel_to_date_stock(
    values: np.ndarray,
    date_keys,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Reshape a long panel into a MATLAB-style dates × stocks matrix.

    Each date becomes one row; stocks observed that date occupy columns
    ``0 .. n_t-1`` (ragged months are NaN-padded to the widest cross-section).
    Stock identity is not aligned across dates — winsorization and the
    cross-sectional regressions only ever look within a row.

    Returns ``(mat, unique_dates, date_codes, within)`` where original row
    ``i`` sits at ``mat[date_codes[i], within[i]]``.

    Layout and scatter are recomputed every call.
    """
    from ..session_cache import pack_layout, pack_values

    layout = pack_layout(date_keys)
    mat = pack_values(values, layout)
    return mat, layout.unique_keys, layout.group_codes, layout.within


def _matlab_prctile_rows_finite(x: np.ndarray, pcts: Sequence[float]) -> np.ndarray:
    """Row-wise MATLAB ``prctile``, dropping non-finite values.

    Matches ``sorts._matlab_prctile`` (plot positions ``(i-0.5)/n``) on each
    row. Non-finite entries are set aside before the sort, so ``±Inf`` does
    not move the tails — the same rule the old per-date loop used.
    """
    p = np.atleast_1d(np.asarray(pcts, dtype=float))
    n_rows = x.shape[0]
    out = np.full((n_rows, p.size), np.nan, dtype=np.float64)
    work = np.where(np.isfinite(x), x, np.nan)
    xs = np.sort(work, axis=1)
    counts = np.isfinite(work).sum(axis=1)
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


def _winsor_or_trim_by_date(
    x: pd.DataFrame, *, pct: float, trim: bool
) -> pd.DataFrame:
    if pct <= 0:
        return x
    if pct >= 50:
        raise ValueError("winsor_trim_pct must be in [0, 50).")
    # MATLAB `winsorize.m` / `trim.m` cut at `prctile(row, [n 100-n])` on a
    # dates × stocks matrix. Packing the long panel into that shape lets the
    # tails be one row-wise percentile + clip instead of a pandas groupby.
    # Always float64: nullable Int64 from DuckDB/CZ can't clip to float bounds.
    # np.stack returns a new array, so clipping never touches the caller's data.
    cols = list(x.columns)
    if not cols:
        return x
    from ..session_cache import pack_column, pack_layout

    layout = pack_layout(x.index)
    mats = [
        pack_column(
            pd.to_numeric(x[c], errors="coerce").to_numpy(dtype="float64"),
            layout,
            name=c,
        )
        for c in cols
    ]
    mat = np.stack(mats, axis=-1)
    if mat.shape[1] == 0:
        values = np.column_stack(
            [pd.to_numeric(x[c], errors="coerce").to_numpy(dtype="float64") for c in cols]
        )
        return pd.DataFrame(values, index=x.index, columns=cols)
    date_codes = layout.group_codes
    within = layout.within
    lo_hi = np.array([pct, 100.0 - pct], dtype=float)
    for j in range(mat.shape[2]):
        col = mat[:, :, j]
        bounds = _matlab_prctile_rows_finite(col, lo_hi)
        lo = bounds[:, 0:1]
        hi = bounds[:, 1:2]
        finite_b = np.isfinite(lo[:, 0]) & np.isfinite(hi[:, 0])
        if not finite_b.any():
            continue
        if trim:
            drop = (col < lo) | (col > hi)
            col = np.where(finite_b[:, None] & drop, np.nan, col)
        else:
            clipped = np.clip(col, lo, hi)
            col = np.where(finite_b[:, None], clipped, col)
        mat[:, :, j] = col
    out_vals = mat[date_codes, within, :]
    return pd.DataFrame(out_vals, index=x.index, columns=cols)


def _maybe_fill_low_frequency(x: pd.DataFrame) -> pd.DataFrame:
    """
    Carry sparse regressors forward for one observation interval, no further.

    MATLAB ``runFamaMacBeth.m`` (``dataFreq > 1``) copies each observed
    cross-section over the rows up to the next observed date. Here a regressor
    whose observed dates are more than 40 days apart on median is carried
    forward within each permno for at most ``freq - 1`` calendar months, where
    ``freq`` is the most common gap in calendar months between its observed
    dates (the smallest on ties). With June-only annual data that is June
    through May, as in MATLAB: a stock missing one June has no value for that
    year, whatever it had the June before.

    Unlike MATLAB, the carry does not run past ``freq - 1`` months after an
    irregular gap in the observed dates or after the last observed date.
    """
    from .sorts import _calendar_ffill, _date_codes_and_months

    out = x.copy()
    for col in out.columns:
        s = pd.to_numeric(out[col], errors="coerce")
        obs = s.notna().groupby(level="date").any()
        idx = obs.index[obs.to_numpy()].sort_values()
        if len(idx) < 3 or pd.Series(idx).diff().median() <= pd.Timedelta(days=40):
            out[col] = s
            continue
        _, _, months = _date_codes_and_months(idx)
        gaps = pd.Series(np.diff(months)).value_counts()
        freq = int(gaps[gaps == gaps.max()].index.min())
        out[col] = _calendar_ffill(s, freq - 1)
    return out


def _calendar_lag_panel(
    obj: pd.Series | pd.DataFrame, lag: int
) -> pd.Series | pd.DataFrame:
    """Lag a (date, permno) panel by ``lag`` calendar months, MATLAB-grid style.

    Cells whose (date - lag months, permno) row is absent from the panel come
    back NaN instead of reaching further back to that stock's last observed
    month. That includes every cell after a whole month missing from the panel.
    Dates must be month-ends and (date, permno) keys unique (``ValueError``).
    """
    from .sorts import _calendar_lag_positions, _date_codes_and_months, _take_lagged

    orig_index = obj.index
    already_sorted = bool(orig_index.is_monotonic_increasing)
    o = obj if already_sorted else obj.sort_index(kind="stable")
    date_codes, _, date_months = _date_codes_and_months(
        o.index.get_level_values("date")
    )
    src = _calendar_lag_positions(
        date_months[date_codes], o.index.get_level_values("permno"), lag=lag
    )
    if isinstance(o, pd.Series):
        out: pd.Series | pd.DataFrame = pd.Series(
            _take_lagged(o.to_numpy(dtype=float), src, np.nan),
            index=o.index,
            name=o.name,
        )
    else:
        out = pd.DataFrame(
            {
                c: _take_lagged(o[c].to_numpy(dtype=float), src, np.nan)
                for c in o.columns
            },
            index=o.index,
        )
    return out if already_sorted else out.reindex(orig_index)


def _ols_beta_rbar(y: np.ndarray, X: np.ndarray) -> tuple[np.ndarray, float]:
    # OLS beta and adjusted R^2
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    yhat = X @ beta
    resid = y - yhat
    n = y.shape[0]
    k = X.shape[1]
    if n <= k + 1:
        return beta, np.nan
    ss_res = float((resid**2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot != 0 else np.nan
    rbar = 1 - (1 - r2) * (n - 1) / (n - k) if pd.notna(r2) else np.nan
    return beta, rbar


def _wls_beta_rbar(y: np.ndarray, X: np.ndarray, w: np.ndarray) -> tuple[np.ndarray, float]:
    # WLS: beta = (X'WX)^-1 X'Wy. Weights assumed non-negative.
    w = w.astype(float)
    wsum = w.sum()
    if wsum <= 0:
        return np.full(X.shape[1], np.nan), np.nan
    w = w / wsum  # MATLAB normalizes weights to sum 1
    WX = X * w[:, None]
    XtWX = X.T @ WX
    XtWy = X.T @ (w * y)
    beta = np.linalg.solve(XtWX, XtWy)
    yhat = X @ beta
    resid = y - yhat
    n = y.shape[0]
    k = X.shape[1]
    if n <= k + 1:
        return beta, np.nan
    # Keep Rbar similar to MATLAB nanwls (unweighted mean in SST)
    ss_res = float((resid**2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot != 0 else np.nan
    rbar = 1 - (1 - r2) * (n - 1) / (n - k) if pd.notna(r2) else np.nan
    return beta, rbar


def _rbar_from_packed(
    y: np.ndarray,
    x: np.ndarray,
    beta: np.ndarray,
    mask: np.ndarray,
    eligible: np.ndarray,
) -> np.ndarray:
    """Adjusted R² on a packed dates × stocks design, matching ``_ols_beta_rbar``."""
    t, _, k = x.shape
    n = mask.sum(axis=1).astype(np.float64)
    yhat = np.einsum("tnk,tk->tn", x, beta)
    resid = np.where(mask, y - yhat, 0.0)
    ss_res = np.einsum("tn,tn->t", resid, resid)
    y_sum = np.where(mask, y, 0.0).sum(axis=1)
    y_mean = np.divide(y_sum, n, out=np.full(t, np.nan), where=n > 0)
    yd = np.where(mask, y - y_mean[:, None], 0.0)
    ss_tot = np.einsum("tn,tn->t", yd, yd)
    r2 = np.full(t, np.nan, dtype=np.float64)
    tot_ok = ss_tot != 0.0
    np.divide(ss_res, ss_tot, out=r2, where=tot_ok)
    r2 = np.where(tot_ok, 1.0 - r2, np.nan)
    dof_ok = eligible & (n > k + 1) & np.isfinite(r2)
    return np.where(
        dof_ok,
        1.0 - (1.0 - r2) * (n - 1.0) / (n - k),
        np.nan,
    )


def _lstsq_full_rank(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Least-squares coefficients of ``b`` on ``a``; all NaN if ``a`` lacks full column rank.

    Columns are divided by their largest absolute value before the SVD solve
    and the coefficients are scaled back. That leaves the least-squares
    solution unchanged but makes the rank decision independent of units:
    without it, ``lstsq``'s default cutoff (``eps * max(n, k)`` times the largest
    singular value) truncated a market-cap column in dollars next to a ratio
    around 1e-4 and silently set its slope to zero.

    A rank-deficient month has no identified coefficients, so it is left NaN
    and drops out of the Fama-MacBeth averages. MATLAB ``nanols``/``nanwls``
    hit a singular matrix there and ``runFamaMacBeth`` keeps finite rows only.
    """
    k = a.shape[1]
    nan = np.full(k, np.nan, dtype=np.float64)
    if a.shape[0] < k:
        return nan
    scale = np.abs(a).max(axis=0)
    if not (scale > 0).all():
        return nan
    c, _, rank, _ = np.linalg.lstsq(a / scale, b, rcond=None)
    if rank < k:
        return nan
    return c / scale


def _batched_ols_beta_rbar(
    y: np.ndarray,
    x: np.ndarray,
    mask: np.ndarray,
    min_obs: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Least squares of each date's cross-section on a packed design.

    Each date with at least ``min_obs`` valid rows is solved by
    :func:`_lstsq_full_rank` (column-scaled SVD least squares) on those rows
    only. Rank-deficient months stay NaN.

    Do not replace this with the normal equations ``(X'X) b = X'y``. Forming
    ``X'X`` squares the condition number, and for nearly collinear regressors
    the stacked solve returned finite but wrong slopes. A
    Python loop over dates costs well under a millisecond per month.
    """
    t, _, k = x.shape
    n_obs = mask.sum(axis=1)
    beta = np.full((t, k), np.nan, dtype=np.float64)
    rbar = np.full(t, np.nan, dtype=np.float64)
    ok = n_obs >= min_obs
    if not ok.any():
        return beta, rbar
    for i in np.flatnonzero(ok):
        m = mask[i]
        beta[i] = _lstsq_full_rank(x[i, m], y[i, m])
    rbar = _rbar_from_packed(y, x, beta, mask, ok)
    return beta, rbar


def _batched_wls_beta_rbar(
    y: np.ndarray,
    x: np.ndarray,
    w: np.ndarray,
    mask: np.ndarray,
    min_obs: int,
) -> tuple[np.ndarray, np.ndarray]:
    """WLS of each date's cross-section: least squares on ``sqrt(w) * [X, y]``.

    Weights are normalized to sum to one per date (MATLAB ``nanwls``); this
    does not change the coefficients. Dates whose valid weights sum to zero
    stay NaN, as do rank-deficient months (on the weighted design). Adjusted
    R² uses unweighted residuals, as ``nanwls`` does. See
    :func:`_batched_ols_beta_rbar` for why this is not a normal-equation solve.
    """
    t, _, k = x.shape
    n_obs = mask.sum(axis=1)
    beta = np.full((t, k), np.nan, dtype=np.float64)
    rbar = np.full(t, np.nan, dtype=np.float64)
    ok = n_obs >= min_obs
    if not ok.any():
        return beta, rbar
    wsum = np.where(mask, w, 0.0).sum(axis=1)
    good_w = ok & (wsum > 0)
    if not good_w.any():
        return beta, rbar
    for i in np.flatnonzero(good_w):
        m = mask[i]
        sw = np.sqrt(w[i, m] / wsum[i])
        beta[i] = _lstsq_full_rank(x[i, m] * sw[:, None], y[i, m] * sw)
    rbar = _rbar_from_packed(y, x, beta, mask, good_w)
    return beta, rbar


def _cross_section_fits(
    y: np.ndarray,
    x: np.ndarray,
    *,
    no_const: bool,
    w: np.ndarray | None,
    min_obs: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Run every date's OLS/WLS on a packed dates × stocks design."""
    t, n_max, n_x = x.shape
    k = n_x if no_const else n_x + 1
    if t == 0 or n_max == 0 or k == 0:
        return (
            np.full((t, k), np.nan, dtype=np.float64),
            np.full(t, np.nan, dtype=np.float64),
        )
    design = np.full((t, n_max, k), np.nan, dtype=np.float64)
    col0 = 0
    if not no_const:
        # A packed cell is occupied if it was scattered into from the long
        # panel (NaN pads stay NaN). Occupied rows get intercept 1, matching
        # ``np.ones(n_rows)`` on the date's ``xs`` slice.
        occupied = ~np.isnan(y)
        design[:, :, 0] = np.where(occupied, 1.0, np.nan)
        col0 = 1
    if n_x:
        design[:, :, col0:] = x
    mask = np.isfinite(y) & np.isfinite(design).all(axis=2)
    if w is not None:
        mask = mask & np.isfinite(w) & (w >= 0)
        return _batched_wls_beta_rbar(y, design, w, mask, min_obs)
    return _batched_ols_beta_rbar(y, design, mask, min_obs)


def _nw_se_of_mean(x: np.ndarray, lags: int) -> float:
    """
    Newey–West HAC standard error of the sample mean of x.
    Bartlett kernel with `lags`.
    """
    x = x.astype(float)
    x = x[np.isfinite(x)]
    T = x.shape[0]
    if T == 0:
        return np.nan
    if lags <= 0:
        # Var(mean) = Var(x)/T
        return float(np.std(x, ddof=1) / np.sqrt(T)) if T > 1 else np.nan

    u = x - x.mean()
    gamma0 = (u @ u) / T
    s = gamma0
    for ell in range(1, min(lags, T - 1) + 1):
        w = 1 - ell / (lags + 1)
        gamma = (u[ell:] @ u[:-ell]) / T
        s += 2 * w * gamma
    var_mean = s / T
    return float(np.sqrt(var_mean)) if var_mean >= 0 else np.nan


def run_fama_macbeth(
    y: pd.Series,
    x: pd.DataFrame | pd.Series | Sequence[pd.Series] | Mapping[str, pd.Series],
    *,
    num_lags: int = 1,
    min_obs: int = 100,
    weight_matrix: pd.Series | None = None,
    newey_west_lags: int = 0,
    print_results: bool = False,
    time_period: (
        int
        | tuple[int, int]
        | date
        | datetime
        | tuple[date | datetime | pd.Timestamp, date | datetime | pd.Timestamp]
        | tuple[pd.Timestamp, pd.Timestamp]
        | None
    ) = None,
    trim_indicator: bool = False,
    winsor_trim_pct: float = 1.0,
    no_const: bool = False,
    labels: Sequence[str] | None = None,
    fill_low_frequency: bool = True,
) -> RegressionResult:
    """
    Fama–MacBeth cross-sectional regressions of y on x (MATLAB-style).

    Parameters mirror MATLAB `runFamaMacBeth.m` closely, but with pandas inputs:
    - y: Series indexed by (date, permno)
    - x: DataFrame indexed by (date, permno) with one column per regressor (unlagged)
    """
    # Accept ergonomic MATLAB-like input forms for x:
    # - DataFrame: regressors in columns (labels must be unique)
    # - Series: single regressor
    # - Sequence[Series]: multiple regressors, e.g. [log(me), R]
    # - Mapping[name -> Series]: explicit naming
    x, regressor_names = _regressor_frame(x)
    n_x = len(regressor_names)

    _ensure_panel_index(y, "y")
    _ensure_panel_index(x, "x")
    # From here on columns are addressed by position only. Internal names
    # "x1".."xK" cannot collide with each other or with the "y"/"w" columns
    # of the stacked frame below (a regressor named "y" used to replace y).
    x = x.set_axis([f"x{j}" for j in range(1, n_x + 1)], axis=1)
    if weight_matrix is not None:
        _ensure_panel_index(weight_matrix, "weight_matrix")

    if num_lags < 0:
        raise ValueError("num_lags must be >= 0")
    if newey_west_lags < 0:
        raise ValueError("newey_west_lags must be >= 0")

    x = x.copy()
    x = x.apply(pd.to_numeric, errors="coerce")
    y = pd.to_numeric(y, errors="coerce")

    # (optional) winsorize/trim RHS by month (like MATLAB loop over regressors)
    x = _winsor_or_trim_by_date(x, pct=winsor_trim_pct, trim=trim_indicator)

    # (optional) fill low-frequency regressors forward (Pythonic approximation)
    if fill_low_frequency:
        x = _maybe_fill_low_frequency(x)

    # lag RHS by num_lags (MATLAB default is 1). MATLAB's `lag(thisX, n, nan)`
    # shifts rows of a rectangular months x stocks grid, so a stock missing from
    # the panel last month contributes nothing; a per-permno shift would instead
    # carry its last *observed* value across the gap.
    if num_lags > 0:
        x = _calendar_lag_panel(x, num_lags)

    wls = False
    w = None
    if weight_matrix is not None:
        w = pd.to_numeric(weight_matrix, errors="coerce")
        w = _calendar_lag_panel(w, 1)
        wls = True

    if time_period is not None:
        date_index = y.index.get_level_values("date")
        def _to_month_end(dt_like: date | datetime | pd.Timestamp) -> pd.Timestamp:
            ts = pd.to_datetime(dt_like)
            return ts + pd.offsets.MonthEnd(0)

        if isinstance(time_period, int):
            start_yyyymm = time_period
            end_yyyymm = None
        elif isinstance(time_period, tuple) and len(time_period) == 2 and all(
            isinstance(v, int) for v in time_period
        ):
            start_yyyymm, end_yyyymm = time_period
        elif isinstance(time_period, (date, datetime, pd.Timestamp)):
            start_yyyymm = end_yyyymm = None
            start = _to_month_end(time_period)
            end = pd.to_datetime(date_index.max())
        else:
            start, end = time_period  # type: ignore[misc]
            start_yyyymm = end_yyyymm = None

        if start_yyyymm is not None:
            start = pd.Timestamp(f"{start_yyyymm // 100:04d}-{start_yyyymm % 100:02d}-01") + pd.offsets.MonthEnd(0)
            if end_yyyymm is None:
                end = pd.to_datetime(date_index.max())
            else:
                end = pd.Timestamp(f"{end_yyyymm // 100:04d}-{end_yyyymm % 100:02d}-01") + pd.offsets.MonthEnd(0)
        else:
            if isinstance(start, (date, datetime, pd.Timestamp)):
                start = _to_month_end(start)
            if isinstance(end, (date, datetime, pd.Timestamp)):
                end = _to_month_end(end)
        mask = (date_index >= start) & (date_index <= end)
        y = y[mask]
        x = x.loc[y.index]
        if w is not None:
            w = w.loc[y.index]

    df = pd.concat({"y": y, **{c: x[c] for c in x.columns}}, axis=1)
    if w is not None:
        df["w"] = w
    df = df.dropna(subset=["y"])

    k = n_x + (0 if no_const else 1)
    col_labels: list[str]
    if labels is not None:
        if len(labels) != k:
            raise ValueError(f"labels must have length {k} (got {len(labels)})")
        col_labels = list(labels)
    else:
        col_labels = []
        if not no_const:
            col_labels.append("Const")
        col_labels.extend([f"var {i}" for i in range(1, n_x + 1)])

    x_cols = list(x.columns)
    if len(x_cols) != n_x:
        raise RuntimeError(
            f"Fama-MacBeth design has {len(x_cols)} regressors; {n_x} were requested."
        )
    pieces = [df["y"].to_numpy(dtype=float)[:, None]]
    if x_cols:
        pieces.append(df[x_cols].to_numpy(dtype=float))
    if wls:
        pieces.append(pd.to_numeric(df["w"], errors="coerce").to_numpy(dtype=float)[:, None])
    stacked = np.concatenate(pieces, axis=1)
    packed, unique_dates, _, _ = _panel_to_date_stock(stacked, df.index)
    dates = pd.Index(unique_dates)
    y_mat = packed[:, :, 0]
    x_mat = packed[:, :, 1 : 1 + n_x] if n_x else packed[:, :, 1:1]
    w_mat = packed[:, :, -1] if wls else None
    beta_arr, rbar_arr = _cross_section_fits(
        y_mat, x_mat, no_const=no_const, w=w_mat, min_obs=min_obs
    )
    if beta_arr.shape[1] != k:
        raise RuntimeError(
            f"Fama-MacBeth fit returned {beta_arr.shape[1]} coefficients; expected {k}."
        )
    beta_ts = pd.DataFrame(beta_arr, index=dates, columns=col_labels, dtype="float64")
    rbar2 = pd.Series(rbar_arr, index=dates, dtype="float64")

    # Average betas and compute t-stats (OLS or NW) on the mean.
    valid_rows = beta_ts.notna().all(axis=1)
    bhat = beta_ts[valid_rows].mean(axis=0)
    tstats = pd.Series(index=beta_ts.columns, dtype="float64")
    for col in beta_ts.columns:
        series = beta_ts.loc[valid_rows, col].to_numpy(dtype=float)
        se = _nw_se_of_mean(series, newey_west_lags)
        mu = float(np.nanmean(series)) if np.isfinite(series).any() else np.nan
        tstats.loc[col] = mu / se if (pd.notna(mu) and pd.notna(se) and se != 0) else np.nan

    out = RegressionResult(
        beta=beta_ts,
        bhat=bhat,
        t=tstats,
        rbar2=rbar2,
        mean_r2=float(rbar2.mean(skipna=True)),
        metadata={
            "num_lags": num_lags,
            "min_obs": min_obs,
            "wls": wls,
            "newey_west_lags": newey_west_lags,
            "trim_indicator": bool(trim_indicator),
            "winsor_trim_pct": float(winsor_trim_pct),
            "no_const": bool(no_const),
            "regressor_names": regressor_names,
            # Months whose cross-section gave a full set of finite betas (the
            # ones averaged in bhat). Kept here because saved protocol results
            # drop the beta matrix.
            "n_months": int(valid_rows.sum()),
        },
    )

    if print_results:
        out.print_results()

    return out


__all__ = ["RegressionResult", "run_fama_macbeth"]

