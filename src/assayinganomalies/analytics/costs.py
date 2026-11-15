"""
Portfolio-level trading cost calculation.

MATLAB equivalent: calcTcosts.m

Computes trading costs, turnover, and weight changes for factor strategies
by tracking portfolio weight evolution between rebalancing dates.

References:
  Detzel, Novy-Marx, Velikov, 2023, JF
  Novy-Marx, Velikov, 2026, Working paper
"""

from __future__ import annotations

import logging
from typing import Literal

import numpy as np
import pandas as pd

LOGGER = logging.getLogger("assayinganomalies.analytics.costs")


def calc_tcosts(
    tcosts: pd.DataFrame,
    ind: pd.DataFrame,
    me: pd.DataFrame,
    weighting: Literal["v", "e"] | pd.DataFrame = "v",
    ptf_rets: pd.DataFrame | None = None,
    compute_dw: bool = True,
    holding_period: int = 1,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Calculate trading costs, turnover, and weight changes for a factor strategy.

    Parameters
    ----------
    tcosts : pd.DataFrame
        Stock-level trading costs as decimal effective **half-spreads**
        (0.005 = 50 bp between the quote midpoint and the trade price), indexed by
        (date, permno) or wide (date × permno); e.g. the panel ``tcost``
        column. A trade of |dw| in a stock costs |dw| × tcost, so the
        two-sided turnover of a full replacement pays one half-spread on the
        sale and one on the purchase. Do not pass full spreads: costs would
        double.
    ind : pd.DataFrame
        Portfolio assignment: 1 = short leg, 2 = long leg, etc.
        Same dates and permnos as tcosts.
    me : pd.DataFrame
        Market equity. Same dates and permnos as tcosts.
    weighting : 'v', 'e', or pd.DataFrame
        'v' = value-weighted (default), 'e' = equal-weighted,
        or a custom weight matrix with the same dates and permnos.
    ptf_rets : pd.DataFrame, optional
        Portfolio returns, which switch the strategy from a constant to a
        compounding base (see Notes): the same dates as tcosts, with
        portfolio ids 1..n_ptfs as columns (extra columns are ignored).
        No caller in ``src/`` passes it, so the constant base is what
        every stored result uses.
    compute_dw : bool
        When False, skip the net weight-change matrix and return zeros for it.
        Only the first and last portfolios feed ``dw``, so callers that ignore
        it (e.g. the FF factor costs on a full CRSP grid) avoid a dense
        date × permno buffer per portfolio.
    holding_period : int, default 1
        Months each formation is held, as in ``calc_ptf_rets``. Portfolio k
        at the end of month t holds the union of the stocks assigned to k in
        months t - holding_period + 1 .. t (exact calendar months), which is
        the membership that earns the gross return in month t + 1. Values
        above 1 require assignments in every calendar month from the first
        to the last formation month and a ``'v'`` or ``'e'`` weighting;
        otherwise ``ValueError`` is raised rather than pricing holdings that
        differ from the gross-return portfolio.

    Every input is read by its labels, never by position: each may be long,
    (date, permno)-indexed or wide, in any row or column order. All must cover
    the same month-end dates and the same permnos; duplicate keys, differing
    label sets and ambiguous value columns raise ``ValueError``. Lags run in
    calendar months: a month absent from the inputs is an empty grid row, so
    the month after it has no prior weights and books no trades.

    Returns
    -------
    ptf_tc : pd.DataFrame
        Trading costs per portfolio per date (date × n_ptfs), decimal per
        month: sum over stocks of |dw| × half-spread.
    ptf_to : pd.DataFrame
        Turnover per portfolio per date (date × n_ptfs).
    dw : pd.DataFrame
        Net weight changes (long - short), observed dates × sorted permnos.

    Notes
    -----
    **Constant-base convention.** With ``ptf_rets=None`` the strategy runs on
    a constant $1 base, as in MATLAB ``calcTcosts`` ("Assumes a constant base
    of $1 for the factor trading strategy"). Target weights sum to 1 each
    month, while pre-trade weights sum to the portfolio's gross ex-dividend
    return, both denominated in the prior month's $1. Reported turnover
    therefore includes the notional rebalance: a portfolio that needs no
    trading at all still books ``|1 - R_p|`` of turnover, which is the
    appreciation withdrawn to restore the $1 base. Under this convention that
    is a real trade paying a real half-spread, not an artifact. Passing
    ``ptf_rets`` scales target weights by ``(1 + r)`` instead, compounding the
    base and leaving only the dividend component.

    **``me`` is a proxy for the ex-dividend return.** Weight drift uses the
    growth in market capitalization, ``me(t) / me(t - reb_freq)``, as a
    shortcut for the gross ex-dividend return on a fixed holding. The two
    differ whenever shares outstanding change: issuance, buybacks, splits and
    other share-count changes move ``me`` without moving the value of a
    position already held, and this function receives only ``me``, so it
    cannot tell the two apart. Under ``'e'`` weighting that injects turnover
    in the month of the share-count change even when nothing needs trading;
    under ``'v'`` some rebalancing is genuinely owed, because the target
    weight moves with the firm's size. Feeding a price-based ex-dividend
    return instead would remove the approximation.
    """
    # Read every labelled input by its (date, permno) labels onto one shared
    # grid: sorted permnos and a complete month-end calendar, so row lags are
    # calendar-month lags. Positional conversion let a reordered input price a
    # different stock.
    if (
        isinstance(holding_period, bool)
        or not isinstance(holding_period, (int, np.integer))
        or holding_period < 1
    ):
        raise ValueError(f"holding_period must be a positive integer; got {holding_period!r}")
    holding_period = int(holding_period)
    if holding_period > 1 and not isinstance(weighting, str):
        raise ValueError(
            f"calc_tcosts: a custom weighting matrix cannot be combined with "
            f"holding_period={holding_period}: its weights are per formation month "
            "and do not define weights for the overlapping formations held at "
            "once. Use weighting='v' or 'e', or holding_period=1."
        )

    frames = {"tcosts": _to_wide(tcosts, "tcosts"), "ind": _to_wide(ind, "ind"),
              "me": _to_wide(me, "me")}
    if not isinstance(weighting, str):
        frames["weighting"] = _to_wide(weighting, "weighting")
    obs_dates, grid_dates, permnos = _shared_axis(frames)
    obs_rows = grid_dates.get_indexer(obs_dates)

    def _grid(name: str) -> np.ndarray:
        frame = frames[name]
        if not (frame.index.equals(grid_dates) and frame.columns.equals(permnos)):
            frame = frame.reindex(index=grid_dates, columns=permnos)
        # C order: row sums over a Fortran-ordered reindex result can differ
        # in the last bit from the historical (C-ordered) conversion.
        return np.ascontiguousarray(frame.to_numpy(dtype=float))

    tc_mat = _grid("tcosts")
    ind_mat = _grid("ind")
    me_mat = _grid("me")

    # Build weight matrix
    if isinstance(weighting, str):
        if weighting.lower() == "v":
            w = me_mat.copy()
        elif weighting.lower() == "e":
            w = np.where(np.isnan(me_mat), np.nan, 1.0)
        else:
            raise ValueError(f"weighting must be 'v', 'e', or a DataFrame; got '{weighting}'")
    else:
        w = _grid("weighting")

    n_months, n_stocks = tc_mat.shape
    n_ptfs = int(np.nanmax(ind_mat))

    ptf_tc = np.full((n_months, n_ptfs), np.nan)
    ptf_to = np.full((n_months, n_ptfs), np.nan)
    dw_first: np.ndarray | None = None
    dw_last: np.ndarray | None = None

    # Identify rebalancing months (rows with any assignment > 0)
    reb_mask = np.nansum(ind_mat > 0, axis=1) > 0
    reb_months = np.where(reb_mask)[0]

    pret_mat = None
    if ptf_rets is not None:
        pret_mat = _align_ptf_rets(ptf_rets, obs_dates, grid_dates, n_ptfs)

    def _frames(tc_arr, to_arr, dw_arr):
        cols = range(1, n_ptfs + 1)
        return (
            pd.DataFrame(tc_arr[obs_rows], index=obs_dates, columns=cols),
            pd.DataFrame(to_arr[obs_rows], index=obs_dates, columns=cols),
            pd.DataFrame(dw_arr[obs_rows], index=obs_dates, columns=permnos),
        )

    if len(reb_months) < 2:
        LOGGER.warning("Fewer than 2 rebalancing months; cannot compute trading costs")
        return _frames(ptf_tc, ptf_to, np.zeros((n_months, n_stocks)))

    # Overlapping formations are priced only where the gross-return portfolio
    # is exactly their union: monthly formations with none missing. With a
    # lower rebalancing frequency (or a month without assignments) calc_ptf_rets
    # first carries the last formation forward, which this arithmetic, lagging
    # target weights by the rebalancing frequency, does not reproduce.
    if holding_period > 1:
        gaps = np.diff(reb_months)
        if (gaps != 1).any():
            first_gap = int(np.flatnonzero(gaps != 1)[0])
            raise ValueError(
                f"calc_tcosts: holding_period={holding_period} needs portfolio "
                "assignments in every calendar month from the first to the last "
                f"formation month; ind has rebalancing gaps of "
                f"{sorted({int(g) for g in gaps[gaps != 1]})} months (first after "
                f"{grid_dates[reb_months[first_gap]].date()}). Trading costs for "
                "overlapping holdings of lower-frequency or gapped strategies are "
                "not supported; use holding_period=1 for costs."
            )

    # Rebalancing frequency = mode of gaps between rebalancing months
    reb_gaps = np.diff(reb_months)
    reb_freq = int(pd.Series(reb_gaps).mode().iloc[0])

    # Shortcut to the gross ex-dividend return: the increase in market
    # capitalization, me(t) / me(t - reb_freq). Not the same thing whenever
    # shares outstanding change (issuance, buybacks, splits) -- see Notes.
    me_lag = np.full_like(me_mat, np.nan)
    if reb_freq < n_months:
        me_lag[reb_freq:] = me_mat[:-reb_freq]
    gretxd = me_mat / me_lag

    for i in range(n_ptfs):
        ptf_id = i + 1  # 1-indexed portfolio

        # Weights for stocks in this portfolio
        this_w = np.where(_held_membership(ind_mat, ptf_id, holding_period), w, 0.0)
        this_w = np.where(np.isnan(this_w), 0.0, this_w)

        # Normalize to sum to 1 each month
        row_sums = np.nansum(this_w, axis=1, keepdims=True)
        row_sums[row_sums == 0] = np.nan
        w_out = this_w / row_sums

        # Lag the out-weights by rebalancing frequency
        lag_w_out = np.zeros_like(w_out)
        if reb_freq < n_months:
            lag_w_out[reb_freq:] = w_out[:-reb_freq]

        # Optional: scale out-weights by (1 + portfolio return)
        if pret_mat is not None:
            w_out = w_out * (1 + pret_mat[:, i][:, np.newaxis])

        # Weights on the way in: last month's weight × price change
        w_in = lag_w_out * gretxd

        # Weight changes
        dw_i = w_out - w_in
        if compute_dw:
            if i == 0:
                dw_first = dw_i.copy()
            if i == n_ptfs - 1:
                dw_last = dw_i.copy()

        # Turnover and trading costs
        ptf_to[:, i] = np.nansum(np.abs(dw_i), axis=1)
        ptf_tc[:, i] = np.nansum(np.abs(dw_i) * tc_mat, axis=1)

    # Net dW = dW(long) - dW(short)
    if compute_dw and dw_first is not None and dw_last is not None:
        dw_net = np.where(np.isnan(dw_last - dw_first), 0.0, dw_last - dw_first)
    else:
        dw_net = np.zeros((n_months, n_stocks))

    ptf_tc_df, ptf_to_df, dw_df = _frames(ptf_tc, ptf_to, dw_net)

    # DEBUG, not INFO: this is a per-call shape dump and calc_tcosts runs once
    # per portfolio sort (157 anomalies, then 5 variants x 5 factor models, ...),
    # so at INFO it buries the actual progress lines. Only n_ptfs ever varies.
    LOGGER.debug(
        "calcTcosts: %d months, %d stocks, %d portfolios, reb_freq=%d",
        n_months, n_stocks, n_ptfs, reb_freq,
    )
    return ptf_tc_df, ptf_to_df, dw_df


def _held_membership(ind_mat: np.ndarray, ptf_id: int, holding_period: int) -> np.ndarray:
    """
    Boolean (months × stocks) membership of portfolio ``ptf_id``.

    Row t is held by the formations of months t - holding_period + 1 .. t.
    ``ind_mat`` is on a complete month-end calendar, so a row lag is a
    calendar-month lag and an absent month (an empty row) contributes no
    stocks, as in ``calc_ptf_rets``'s exact calendar lookup. With
    ``holding_period=1`` this is ``ind_mat == ptf_id``.
    """
    held = ind_mat == ptf_id
    for h in range(1, holding_period):
        held[h:] |= ind_mat[:-h] == ptf_id
    return held


def _to_wide(obj: pd.DataFrame | pd.Series, name: str) -> pd.DataFrame:
    """
    One input as a labelled wide (date × permno) DataFrame.

    Accepts a Series or single-value-column DataFrame on a (date, permno)
    MultiIndex, a long DataFrame with ``date``, ``permno`` and one value
    column, or an already-wide DataFrame (date index, permno columns). Raises
    ``ValueError`` on duplicate keys or labels and on ambiguous value columns.
    """
    if isinstance(obj, pd.Series):
        if not isinstance(obj.index, pd.MultiIndex):
            raise ValueError(f"{name} must be indexed by (date, permno) when given as a Series")
        obj = obj.to_frame()

    if not isinstance(obj, pd.DataFrame):
        raise TypeError(f"{name} must be a pandas DataFrame or Series; got {type(obj).__name__}")

    long = None
    if isinstance(obj.index, pd.MultiIndex):
        if obj.index.nlevels != 2:
            raise ValueError(f"{name} index must have exactly two levels (date, permno)")
        long = obj.rename_axis(["date", "permno"])
    elif "date" in obj.columns and "permno" in obj.columns:
        long = obj.set_index(["date", "permno"])

    if long is not None:
        if long.shape[1] != 1:
            raise ValueError(
                f"{name} must have exactly one value column; got {list(long.columns)}"
            )
        try:
            return long.iloc[:, 0].unstack("permno")
        except ValueError:
            # unstack refuses duplicate keys; checking uniqueness up front
            # would cost a second pass over a CRSP-sized index.
            if not long.index.is_unique:
                raise ValueError(f"{name} has duplicate (date, permno) keys") from None
            raise

    if not obj.index.is_unique:
        raise ValueError(f"{name} has duplicate dates")
    if not obj.columns.is_unique:
        raise ValueError(f"{name} has duplicate permno columns")
    return obj


def _shared_axis(
    frames: dict[str, pd.DataFrame],
) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex, pd.Index]:
    """
    The (date, permno) axis every input is read on.

    All inputs must span the same dates and the same permnos, in any order.
    Otherwise raise ``ValueError`` naming the input, rather than filling the
    difference with missing values. Returns ``(obs_dates, grid_dates,
    permnos)``: the sorted observed dates; the complete month-end calendar
    from the first to the last of them (an absent month becomes an
    all-missing grid row, as in MATLAB's rectangular grid, so row lags are
    calendar-month lags); and the sorted permnos.
    """
    from .sorts import _date_codes_and_months

    ref_name, ref = next(iter(frames.items()))
    ref_dates, ref_permnos = set(ref.index), set(ref.columns)
    for name, frame in frames.items():
        for axis, labels, ref_labels in (
            ("dates", frame.index, ref_dates),
            ("permnos", frame.columns, ref_permnos),
        ):
            if set(labels) != ref_labels:
                own = set(labels)
                extra = [x for x in own if x not in ref_labels][:3]
                missing = [x for x in ref_labels if x not in own][:3]
                raise ValueError(
                    f"calc_tcosts: {name} covers different {axis} than {ref_name} "
                    f"(e.g. only in {name}: {extra}; only in {ref_name}: {missing}); "
                    "align the inputs on the same (date, permno) labels first"
                )

    _, obs_dates, _ = _date_codes_and_months(ref.index)
    if len(obs_dates):
        grid_dates = pd.date_range(obs_dates[0], obs_dates[-1], freq="ME")
    else:
        grid_dates = obs_dates
    permnos = pd.Index(sorted(ref_permnos), name=ref.columns.name)
    return obs_dates.rename(ref.index.name), grid_dates.rename(ref.index.name), permnos


def _align_ptf_rets(
    ptf_rets: pd.DataFrame,
    obs_dates: pd.DatetimeIndex,
    grid_dates: pd.DatetimeIndex,
    n_ptfs: int,
) -> np.ndarray:
    """Portfolio returns (grid months × n_ptfs), read by date and by portfolio
    id 1..n_ptfs. Other columns (e.g. a long-short column) are ignored."""
    if not isinstance(ptf_rets, pd.DataFrame):
        raise TypeError(
            "ptf_rets must be a DataFrame indexed by date with portfolio ids "
            f"1..n_ptfs as columns; got {type(ptf_rets).__name__}"
        )
    if not ptf_rets.index.is_unique or not ptf_rets.columns.is_unique:
        raise ValueError("ptf_rets has duplicate dates or portfolio columns")
    if set(ptf_rets.index) != set(obs_dates):
        raise ValueError(
            "calc_tcosts: ptf_rets covers different dates than tcosts; "
            "align the inputs on the same dates first"
        )
    missing = [k for k in range(1, n_ptfs + 1) if k not in ptf_rets.columns]
    if missing:
        raise ValueError(
            f"ptf_rets is missing portfolio column(s) {missing}; columns must be "
            "the portfolio ids 1..n_ptfs (as returned by calc_ptf_rets)"
        )
    cols = list(range(1, n_ptfs + 1))
    return ptf_rets[cols].reindex(grid_dates).to_numpy(dtype=float)


def make_ff_tcosts(
    panel: pd.DataFrame,
    tcost_series: pd.Series,
    annual: pd.DataFrame | None = None,
    *,
    convention: str = "dollar",
) -> pd.DataFrame:
    """
    Fama-French factor trading costs (Detzel, Novy-Marx, Velikov 2023) on held legs.

    Delegates to ``transforms.tcosts.make_ff_tcosts``; see there. Each
    factor's long and short side is bought when its 2x3 sort exists (each
    June; every month for UMD) and held until the next trade. ``convention``
    (``"capital"`` or ``"dollar"``) is the size of the two sides after a
    trade, as in ``run_univariate_sort``. ``mkt_tc`` is zero by construction.
    """
    from assayinganomalies.transforms.tcosts import make_ff_tcosts as _impl

    return _impl(panel, tcost_series, annual, convention=convention)


__all__ = ["calc_tcosts", "make_ff_tcosts"]
