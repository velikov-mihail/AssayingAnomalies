"""
Held-leg returns and trading costs, the calculation behind every univariate sort.

Each portfolio is bought at a trade and then left alone until the next trade.
Returns, trading costs and turnover all describe that one portfolio.

Definitions, for one portfolio (a "leg"), month ``t`` and stock ``i``:

- **Trade months** are the months in which any stock has a portfolio
  assignment. ``J(t)`` is the last trade month at or before ``t``.
- **Target weights** ``W*`` at a trade: market cap (``"v"``), 1 (``"e"``) or
  a custom weight, over the portfolio's stocks that have a market cap in the
  trade month, scaled to sum to 1.
- **Holdings** at the end of month ``t``, per $1 of leg after the trade at
  ``J``: ``D[t] = W*[J] * X[t] / X[J]`` for every stock that has a market cap
  at ``t``, where ``X`` is the growth index, the running product of
  ``1 + ret`` (a missing ``ret`` counts as zero). A position grows with the
  stock's total return: a dividend is reinvested in the stock that paid it,
  and that purchase is not charged. With no stock losing its market cap and
  no missing return, a leg's return is the buy-and-hold return of its target
  weights. The value of a stock that loses its market cap becomes cash, which
  earns nothing until the next trade.
- ``held_legs`` takes an optional ``growth`` grid to use in place of ``ret``
  for ``X`` (for example ``retx``, the return without dividends: dividends
  then become cash). Nothing in the toolkit passes it; it is there for the
  comparison in the paper's notebook and for the tests.
- **P&L** of month ``t``: the holdings ``H = D[t-1]`` earn
  ``sum(H) * sum(H * ret[t]) / sum(H)``, the last two sums over the held
  stocks that have a return in month ``t``: a stock without a return earns
  the average of the others.
- **Value** entering month ``t``: ``V[t-1] = 1 +`` the leg's P&L since its
  last trade. **Leg return** ``= P&L[t] / V[t-1]``.

For a long/short pair (``held_long_short``):

- **Gross return** = the long leg's return minus the short leg's, each on its
  own value.
- At a trade each leg is given a size ``s`` and moved from its holdings ``D``
  to ``s * W*``. There are two conventions for ``s``:

  - ``"dollar"`` (the default): each leg goes back to $1, the size it had
    after the previous trade. What it gained is taken out and what it lost is
    put back. The cost is the same whichever leg is called long.
  - ``"capital"``: both legs are set to the strategy's capital
    ``K = 1 + long P&L - short P&L`` since the previous trade. The two legs
    are again equal, and their size grows or shrinks with the strategy. The
    cost then depends on which leg is long.

  The gross return is the same under both (a leg's return does not depend on
  its size); only the cost and the turnover differ.
- **Cost** of a leg at a trade ``= sum(|s * W* - D| * tcost) / V``, with
  ``tcost`` the half-spread of the trade month and ``V`` the leg's value
  entering that month. **Turnover** is the same sum without ``tcost``. The
  strategy's cost and turnover are the sums over its two legs. A stock without
  a market cap in the trade month is not traded, and a stock without a
  ``tcost`` is traded for free.
- **The entry cost** is the cost of the first purchase, ``sum(W* * tcost)``
  per leg, the same under both conventions. It is reported as one number
  (``entry_cost``, and each leg's part) and is not in the cost or turnover
  series: the month of the first trade has no return to charge it to, and a
  strategy's running cost should not depend on the month its sample starts.
  Every later trade is booked in its own month.

The reference for this calculation is ``tcost_schedules.ipynb`` in the paper's
revision repository: row 4 ("Held, legs to K") for ``"capital"`` and row 3
("Held, legs to $1") for ``"dollar"``; the notebook's row 4 charges the first
purchase in the cost series, which is here the separate entry cost. Three
cases the notebook leaves undefined are settled here:

- A return of -100% or less makes a held position worthless from that month
  on. A stock bought at a later trade grows normally from that trade. (A
  growth index that reaches zero cannot be used as a ratio, so growth since
  the trade is tracked separately from the index.)
- A portfolio with no stocks at a trade holds nothing (all cash) until the
  next trade. Its return is missing in those months, and the trade that
  empties it pays to sell what it held.
- Under ``"capital"``, if ``K`` is zero or negative at a trade (the pair
  lost at least everything since the previous trade), the strategy starts
  again with fresh capital: both legs are set to $1, the size they had after
  the previous trade, and the trade is charged as the move from what is held
  to those $1 legs. A warning is logged. The returns after the trade are those
  of the new portfolios, as after any other trade.

The strategy held short (``cost_exchanged``)
--------------------------------------------
Someone who holds the strategy short is long its short leg and short its long
leg: the same two portfolios with the legs exchanged. Its gross return is
minus the strategy's. Under ``"dollar"`` its cost is the strategy's cost, since
each portfolio goes back to $1 whichever leg it is. Under ``"capital"`` it is
not: the exchanged pair has its own capital,
``K' = 1 + short P&L - long P&L``, so a strategy that made money sizes its
legs up and the same strategy held short, which lost, sizes them down.
``cost_exchanged`` and ``turnover_exchanged`` are the cost and turnover of
that exchanged pair (``capital_exchanged`` its ``K'``, with the same restart
at $1 legs when ``K'`` is zero or negative, which is not logged). They are
what ``held_long_short(legs, short=long, long=short)`` returns as ``cost``.
The generalized alpha charges them when the net mean-variance efficient
portfolio holds a strategy short (``analytics/gen_alpha.py``). The entry cost
is the same either way.

One portfolio on its own (``held_portfolio_costs``)
--------------------------------------------------
Every portfolio of a sort also has a cost of its own, as a portfolio held by
itself and not as a leg of a pair:

- ``"dollar"``: the portfolio goes back to $1 at every trade. For the two
  legs of a pair these are the pair's two parts, so they add up to its cost.
- ``"capital"``: the portfolio rolls its own value over: at a trade it moves
  from what it holds to its own value (1 plus its P&L since the previous
  trade) times the new target weights. Nothing is put in or taken out. These
  are not the parts of a pair's cost, whose legs are both set to ``K``.

The cost of a trade is again the half-spreads paid over the portfolio's value
entering the month, and the first purchase is the portfolio's entry cost.

A side made of several portfolios (``held_composite_long_short``)
-----------------------------------------------------------------
A Fama-French factor is long the equal-weighted average of two or three
portfolios and short the average of two or three others. Its published return
averages the portfolios' returns every month, which means that each side
starts every month with the same dollars in each of its portfolios. For the
cost to describe that portfolio:

- Each of the side's portfolios is a held leg as above (bought at a trade,
  left alone until the next).
- **Re-split.** At the end of every month that is not a trade month, the side
  brings its portfolios back to equal shares of its own value: each
  portfolio's positions are scaled by one number. The dollars this moves pay
  that month's half-spreads, and the cost is divided by the side's value
  entering the month, as for a trade. The size of the side does not change.
- The **side's return** is therefore the average of its portfolios' returns,
  and its value compounds: ``V[t] = V[t-1] * (1 + return[t])``.
- **At a trade** the side moves in one step from what it holds (the positions
  as the re-splits have left them) to ``s / m`` times the new target weights
  of each of its ``m`` portfolios, netted stock by stock within the side.
  ``s`` is the size of the convention, as above; under ``"capital"`` the
  strategy's capital is ``K = 1 + (V_long - 1) - (V_short - 1)``.
- A portfolio with no stocks at a trade is left out until the next trade: the
  side is split equally among the others. The cash of a stock that lost its
  market cap is scaled with its portfolio's positions, at no cost.

All arrays are dense months x stocks grids on a complete monthly calendar, so
that row ``t - 1`` is the month before row ``t``. ``held_legs`` and
``held_long_short`` do not loop over months; ``held_composite_long_short``
loops over the trades to compound a side's value.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Sequence

import numpy as np

LOGGER = logging.getLogger("assayinganomalies.analytics.held")


@dataclass(frozen=True)
class HeldLegs:
    """Held portfolios, one column per portfolio id ``1..n_ptfs``.

    Monthly arrays have shape (months, n_ptfs) and are NaN where the portfolio
    has no return: up to and including the first trade month, and after the
    last return month.

    Attributes
    ----------
    ret : leg return, ``pl / value``.
    pl : P&L of the month, per $1 of leg after its last trade.
    value : the leg's value entering the month (``V[t-1]``), same units.
    n_stocks : number of held stocks that have a return in the month.
    mcap : their total market cap at the end of the previous month.
    trade_rows : rows of the trade months, shape (n_trades,).
    trade_pl : each leg's P&L since the previous trade, at each trade
        (zero at the first), shape (n_trades, n_ptfs).
    last_row : the last row that has a return (-1 if none).

    The remaining attributes are the stock-level positions at the trades, one
    entry per (trade, stock) in which something is held before or after the
    trade. ``trade_idx`` indexes ``trade_rows`` and ``stock`` is the column of
    the input grids. ``target`` is the stock's target weight in portfolio
    ``ptf_new`` after the trade (0 if in none), ``pre`` its holding in
    portfolio ``ptf_old`` just before the trade (0 if none), and ``tcost`` its
    half-spread in the trade month (NaN if missing).

    With ``held_legs(..., monthly_holdings=True)`` two more monthly arrays are
    filled (they are ``None`` otherwise), for ``held_composite_long_short``:
    ``held`` is the dollars each portfolio has in stocks at the end of the
    month, per $1 of leg after its last trade (in a trade month: after that
    trade), and ``held_cost`` the same dollars times each stock's half-spread
    of that month. Both are NaN outside the months from the first trade to the
    last month with a return.
    """

    ret: np.ndarray
    pl: np.ndarray
    value: np.ndarray
    n_stocks: np.ndarray
    mcap: np.ndarray
    trade_rows: np.ndarray
    trade_pl: np.ndarray
    last_row: int
    trade_idx: np.ndarray
    stock: np.ndarray
    ptf_new: np.ndarray
    ptf_old: np.ndarray
    target: np.ndarray
    pre: np.ndarray
    tcost: np.ndarray
    held: np.ndarray | None = None
    held_cost: np.ndarray | None = None

    @property
    def n_months(self) -> int:
        return self.ret.shape[0]

    @property
    def n_ptfs(self) -> int:
        return self.ret.shape[1]


@dataclass(frozen=True)
class HeldLongShort:
    """A long/short pair of held legs. All arrays have shape (months,).

    Attributes
    ----------
    gross : long leg's return minus short leg's; NaN where either is missing.
    cost : trading cost booked in the month, both legs (0 in months without a
        trade). The first purchase is not in it (``entry_cost``).
    turnover : traded dollars over leg value, both legs (0 likewise; the
        first purchase is not in it either).
    cost_short, cost_long, turnover_short, turnover_long : the two legs' parts.
    entry_cost : the cost of the first purchase, both legs (a number, per $1
        in each leg); ``entry_cost_short`` and ``entry_cost_long`` its parts.
    cost_exchanged, turnover_exchanged : cost and turnover of the same two
        portfolios with the legs exchanged, which is the strategy held short.
        Equal to ``cost`` and ``turnover`` under ``"dollar"``.
    capital_exchanged : that pair's capital ``K' = 1 + short P&L - long P&L``
        in each trade month, as computed; NaN in other months.
    capital : the strategy's capital ``K`` in each trade month, as computed
        (also where it is zero or negative and the legs were set to $1
        instead, and under ``convention="dollar"``, which does not use it);
        NaN in other months.
    """

    gross: np.ndarray
    cost: np.ndarray
    turnover: np.ndarray
    cost_short: np.ndarray
    cost_long: np.ndarray
    turnover_short: np.ndarray
    turnover_long: np.ndarray
    capital: np.ndarray
    entry_cost: float
    entry_cost_short: float
    entry_cost_long: float
    cost_exchanged: np.ndarray
    turnover_exchanged: np.ndarray
    capital_exchanged: np.ndarray


@dataclass(frozen=True)
class HeldPortfolioCosts:
    """Each portfolio's own trading cost, as a portfolio held by itself.

    Attributes
    ----------
    cost, turnover : (months, n_ptfs); 0 in a month without a trade. The
        first purchase is in neither.
    entry_cost : (n_ptfs,), the cost of each portfolio's first purchase (0
        for a portfolio that has no stock at the first trade).
    """

    cost: np.ndarray
    turnover: np.ndarray
    entry_cost: np.ndarray


def _grid(x, name: str, shape: tuple[int, int] | None = None) -> np.ndarray:
    out = np.asarray(x, dtype=float)
    if out.ndim != 2:
        raise ValueError(f"{name} must be a months x stocks grid; got {out.ndim} dimension(s)")
    if shape is not None and out.shape != shape:
        raise ValueError(f"{name} has shape {out.shape}; expected {shape}, the shape of ret")
    return out


def _last_return_row(trade_rows: np.ndarray, n_months: int) -> int:
    """Last row with a return, by the rule of ``calc_ptf_rets``.

    Holdings formed in month ``J`` first earn in month ``J + 1``. With ``f``
    the most common gap between those first-return months (the smallest on
    ties), returns run through ``f`` months after the last of them, or to the
    end of the grid when there is only one. (So an annual sort earns for 13
    months after its last trade if the data go that far, as ``calc_ptf_rets``
    does.) Returns -1 when no trade is followed by a month.
    """
    first_ret = trade_rows + 1
    first_ret = first_ret[first_ret <= n_months - 1]
    if first_ret.size == 0:
        return -1
    if first_ret.size == 1:
        return n_months - 1
    gaps, counts = np.unique(np.diff(first_ret), return_counts=True)
    freq = int(gaps[np.argmax(counts)])
    # Never before the last trade: a leg is held at least until it is traded.
    return max(min(int(first_ret[-1]) + freq, n_months - 1), int(trade_rows[-1]))


def held_legs(
    ret,
    me,
    tcost,
    ind,
    weights: Literal["v", "e"] | np.ndarray = "v",
    *,
    growth=None,
    n_ptfs: int | None = None,
    monthly_holdings: bool = False,
) -> HeldLegs:
    """Held returns and trade positions of every portfolio of a sort.

    Parameters
    ----------
    ret : months x stocks grid of returns (decimals). It is what a position
        earns and, unless ``growth`` is given, what an untraded position
        grows with.
    me : market cap grid. A stock without one is not bought at a trade and is
        not counted as held in that month.
    tcost : half-spread grid (decimals), used at the trade months.
    ind : portfolio assignment grid: ``1..n_ptfs`` in the months the sort has
        values, 0 or NaN otherwise. A month with any assignment is a trade
        month.
    weights : ``"v"`` (market cap), ``"e"`` (equal) or a months x stocks grid
        of non-negative custom weights, read at the trade months and scaled to
        sum to 1 within each portfolio.
    growth : optional months x stocks grid of the returns an untraded position
        grows with, in place of ``ret`` (for example ``retx``).
    n_ptfs : number of portfolios, when it is more than the highest id in
        ``ind`` (a portfolio that never has a stock still gets its column).
    monthly_holdings : also return each portfolio's month-end dollars in
        stocks and their half-spread-weighted sum (``HeldLegs.held`` and
        ``held_cost``), which ``held_composite_long_short`` needs.

    All grids must have the same shape and sit on a complete monthly calendar
    (a month absent from the data is an all-NaN row).

    Returns
    -------
    HeldLegs
    """
    ret = _grid(ret, "ret")
    shape = ret.shape
    growth = ret if growth is None else _grid(growth, "growth", shape)
    me = _grid(me, "me", shape)
    tcost = _grid(tcost, "tcost", shape)
    ind = _grid(ind, "ind", shape)
    n_months = shape[0]

    assigned = ind > 0  # NaN compares False
    if not assigned.any():
        raise ValueError("ind has no portfolio assignment (no value above 0)")
    if (ind[assigned] != np.round(ind[assigned])).any():
        raise ValueError("ind must hold whole portfolio ids 1..n_ptfs")
    highest = int(ind[assigned].max())
    if n_ptfs is None:
        n_ptfs = highest
    elif n_ptfs < highest:
        raise ValueError(f"n_ptfs={n_ptfs} is below the highest portfolio id in ind ({highest})")
    trade_rows = np.flatnonzero(assigned.any(axis=1))
    n_trades = trade_rows.size

    # Only stocks that are ever assigned can be held.
    cols = np.flatnonzero(assigned.any(axis=0))
    ret, growth, me = ret[:, cols], growth[:, cols], me[:, cols]

    # ---- target weights at the trades: (n_trades, stocks)
    me_tr = me[trade_rows]
    if isinstance(weights, str):
        kind = weights.lower()
        if kind == "v":
            base = me_tr
        elif kind == "e":
            base = np.ones_like(me_tr)
        else:
            raise ValueError(f"weights must be 'v', 'e' or a grid; got {weights!r}")
    else:
        base = _grid(weights, "weights", shape)[np.ix_(trade_rows, cols)]
        if (base < 0).any():
            raise ValueError("custom weights must not be negative")
    ptf = np.where(assigned[np.ix_(trade_rows, cols)], ind[np.ix_(trade_rows, cols)], 0)
    member = (ptf > 0) & np.isfinite(me_tr) & np.isfinite(base) & (base > 0)
    ptf = np.where(member, ptf, 0).astype(np.int16)
    n_keys = n_ptfs + 1
    key = np.arange(n_trades)[:, None] * n_keys + ptf
    total = np.bincount(key[member], weights=base[member], minlength=n_trades * n_keys)
    target = np.zeros(ptf.shape)
    target[member] = base[member] / total[key[member]]
    del key, base, member

    # ---- growth of an untraded position between two months
    # Xp is the growth index with every factor of zero or less (a return of
    # -100%) left out, and `dead` counts those months. A position bought at J is worth
    # Xp[t] / Xp[J] at t if no such month lies in between, and nothing otherwise.
    factor = 1.0 + np.nan_to_num(growth)
    wiped = factor <= 0
    xp = np.cumprod(np.where(wiped, 1.0, factor), axis=0)
    dead = np.cumsum(wiped, axis=0, dtype=np.int32) if wiped.any() else None
    del factor, wiped

    def drifted(k: np.ndarray, rows: np.ndarray) -> np.ndarray:
        """Holdings at the end of ``rows`` of the weights of trades ``k``."""
        j = trade_rows[k]
        out = target[k] * (xp[rows] / xp[j])
        gone = ~np.isfinite(me[rows])
        if dead is not None:
            gone |= dead[rows] != dead[j]
        out[gone] = 0.0
        return out

    # ---- monthly P&L: holdings at the end of row t earn ret[t + 1]
    pl = np.full((n_months, n_ptfs), np.nan)
    n_stocks = np.full((n_months, n_ptfs), np.nan)
    mcap = np.full((n_months, n_ptfs), np.nan)
    last_row = _last_return_row(trade_rows, n_months)
    hold = np.arange(trade_rows[0], max(last_row, trade_rows[0]))
    trade_of = np.searchsorted(trade_rows, np.arange(n_months), side="right") - 1
    held_m = held_cost_m = None
    if monthly_holdings:
        held_m = np.full((n_months, n_ptfs), np.nan)
        held_cost_m = np.full((n_months, n_ptfs), np.nan)
        # The last month with a return is not in `hold` (nothing earns after
        # it), but its month-end holdings are wanted too.
        end = max(last_row, int(trade_rows[0]))
        k_end = trade_of[end]
        at_end = drifted(np.array([k_end]), np.array([end]))[0]
        in_ptf = at_end > 0
        ids = ptf[k_end, in_ptf] - 1
        held_m[end] = np.bincount(ids, weights=at_end[in_ptf], minlength=n_ptfs)
        held_cost_m[end] = np.bincount(
            ids,
            weights=at_end[in_ptf] * np.nan_to_num(tcost[end, cols[in_ptf]]),
            minlength=n_ptfs,
        )
        del at_end, in_ptf, ids
    if hold.size:
        k = trade_of[hold]
        holdings = drifted(k, hold)
        rr, cc = np.nonzero(holdings > 0)
        d = holdings[rr, cc]
        del holdings
        key = rr * n_ptfs + (ptf[k[rr], cc] - 1)
        size = hold.size * n_ptfs
        r = ret[hold[rr] + 1, cc]
        ok = np.isfinite(r)
        held_sum = np.bincount(key, weights=d, minlength=size)
        if monthly_holdings:
            spread = np.nan_to_num(tcost[hold[rr], cols[cc]])
            held_m[hold] = held_sum.reshape(hold.size, n_ptfs)
            held_cost_m[hold] = np.bincount(key, weights=d * spread, minlength=size).reshape(
                hold.size, n_ptfs
            )
            del spread
        key, d, r = key[ok], d[ok], r[ok]
        earned = np.bincount(key, weights=d * r, minlength=size)
        with_ret = np.bincount(key, weights=d, minlength=size)
        count = np.bincount(key, minlength=size)
        cap = np.bincount(key, weights=me[hold[rr[ok]], cc[ok]], minlength=size)
        has = count > 0
        with np.errstate(invalid="ignore", divide="ignore"):
            month_pl = np.where(has, held_sum * earned / with_ret, np.nan)
        pl[hold + 1] = month_pl.reshape(hold.size, n_ptfs)
        n_stocks[hold + 1] = np.where(has, count, np.nan).reshape(hold.size, n_ptfs)
        mcap[hold + 1] = np.where(has, cap, np.nan).reshape(hold.size, n_ptfs)
        del rr, cc, d, r, key, ok

    # ---- value and return: P&L accumulates between trades
    cum = np.cumsum(np.nan_to_num(pl), axis=0)
    value = np.full((n_months, n_ptfs), np.nan)
    if hold.size:
        # Month t + 1 belongs to the trade in force at t; its value entering
        # is 1 plus the P&L of the months after that trade, through t.
        value[hold + 1] = 1.0 + cum[hold] - cum[trade_rows[trade_of[hold]]]
    with np.errstate(invalid="ignore", divide="ignore"):
        leg_ret = pl / value
    trade_pl = np.zeros((n_trades, n_ptfs))
    trade_pl[1:] = cum[trade_rows[1:]] - cum[trade_rows[:-1]]

    # ---- positions before each trade, and the entries that trade or are held
    pre = np.zeros(ptf.shape)
    ptf_old = np.zeros(ptf.shape, dtype=np.int16)
    if n_trades > 1:
        pre[1:] = drifted(np.arange(n_trades - 1), trade_rows[1:])
        ptf_old[1:] = ptf[:-1]
    ptf_old[pre <= 0] = 0
    tt, cc = np.nonzero((target > 0) | (pre > 0))

    return HeldLegs(
        ret=leg_ret,
        pl=pl,
        value=value,
        n_stocks=n_stocks,
        mcap=mcap,
        trade_rows=trade_rows,
        trade_pl=trade_pl,
        last_row=last_row,
        trade_idx=tt,
        stock=cols[cc],
        ptf_new=ptf[tt, cc],
        ptf_old=ptf_old[tt, cc],
        target=target[tt, cc],
        pre=pre[tt, cc],
        tcost=tcost[trade_rows[tt], cols[cc]],
        held=held_m,
        held_cost=held_cost_m,
    )


CONVENTIONS = ("capital", "dollar")


def _trade_costs(legs: HeldLegs, size: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Cost and turnover of every portfolio at every trade.

    ``size`` is (n_trades, n_ptfs): the dollars each portfolio is set to at
    each trade, per $1 after its previous trade. A portfolio moves from what
    it holds (``pre``) to ``size`` times its target weights; a stock that
    changes portfolio is sold by the one and bought by the other. Returns two
    (n_trades, n_ptfs) arrays: the half-spreads paid and the dollars traded,
    each over the portfolio's value entering the trade month ($1 at the first
    trade, whose row is the first purchase).
    """
    n_trades, n_ptfs = legs.trade_rows.size, legs.n_ptfs
    k, new_p, old_p = legs.trade_idx, legs.ptf_new, legs.ptf_old
    half_spread = np.nan_to_num(legs.tcost)
    size_new = size[k, np.maximum(new_p, 1) - 1]
    same = (new_p == old_p) & (new_p > 0)
    buys = (new_p > 0) & ~same
    sells = (old_p > 0) & ~same
    key = np.concatenate([k[same] * n_ptfs + new_p[same] - 1,
                          k[buys] * n_ptfs + new_p[buys] - 1,
                          k[sells] * n_ptfs + old_p[sells] - 1])
    traded = np.concatenate([np.abs(size_new[same] * legs.target[same] - legs.pre[same]),
                             np.abs(size_new[buys] * legs.target[buys]),
                             np.abs(legs.pre[sells])])
    spread = np.concatenate([half_spread[same], half_spread[buys], half_spread[sells]])
    shape = (n_trades, n_ptfs)
    dollars = np.bincount(key, weights=traded, minlength=n_trades * n_ptfs).reshape(shape)
    paid = np.bincount(key, weights=traded * spread, minlength=n_trades * n_ptfs).reshape(shape)
    entering = np.ones(shape)  # the first purchase is of a $1 portfolio
    entering[1:] = legs.value[legs.trade_rows[1:]]
    with np.errstate(invalid="ignore", divide="ignore"):
        return paid / entering, dollars / entering


def _booked(per_trade: np.ndarray, legs: HeldLegs) -> np.ndarray:
    """A per-trade column as a monthly series: every trade after the first in its own month."""
    out = np.zeros(legs.n_months)
    out[legs.trade_rows[1:]] = per_trade[1:]
    return out


def held_portfolio_costs(legs: HeldLegs, *, convention: str = "dollar") -> HeldPortfolioCosts:
    """Trading cost and turnover of every portfolio held on its own.

    ``convention`` is the size a portfolio is given at a trade: $1
    (``"dollar"``, the default) or its own value, 1 plus its P&L since the
    previous trade (``"capital"``: the portfolio rolls its value over). See
    the module docstring. A portfolio whose value is zero or negative at a
    trade (every stock it held lost everything) starts again with $1.
    """
    if convention not in CONVENTIONS:
        raise ValueError(f"convention must be 'capital' or 'dollar'; got {convention!r}")
    n_trades, n_ptfs = legs.trade_rows.size, legs.n_ptfs
    if convention == "dollar":
        size = np.ones((n_trades, n_ptfs))
    else:
        own = 1.0 + legs.trade_pl
        size = np.where(own > 0, own, 1.0)
    cost, turnover = _trade_costs(legs, size)
    monthly_cost = np.zeros((legs.n_months, n_ptfs))
    monthly_turnover = np.zeros((legs.n_months, n_ptfs))
    monthly_cost[legs.trade_rows[1:]] = cost[1:]
    monthly_turnover[legs.trade_rows[1:]] = turnover[1:]
    return HeldPortfolioCosts(cost=monthly_cost, turnover=monthly_turnover, entry_cost=cost[0].copy())


def held_long_short(
    legs: HeldLegs,
    short: int = 1,
    long: int | None = None,
    *,
    convention: str = "dollar",
    label: str | None = None,
) -> HeldLongShort:
    """Gross return, trading cost and turnover of ``long`` minus ``short``.

    Parameters
    ----------
    legs : the output of ``held_legs``.
    short, long : portfolio ids (1-based). ``long`` defaults to the last
        portfolio.
    convention : the size each leg is given at a trade: ``"dollar"`` ($1,
        the default) or ``"capital"`` (the strategy's capital K).
    label : the strategy's name, for the warning logged when its capital is
        zero or negative at a trade (``"capital"`` only).

    Returns
    -------
    HeldLongShort
    """
    n_ptfs = legs.n_ptfs
    long = n_ptfs if long is None else long
    for name, p in (("short", short), ("long", long)):
        if not 1 <= p <= n_ptfs:
            raise ValueError(f"{name}={p} is not a portfolio id in 1..{n_ptfs}")
    if short == long:
        raise ValueError("short and long must be different portfolios")
    if convention not in CONVENTIONS:
        raise ValueError(f"convention must be 'capital' or 'dollar'; got {convention!r}")

    n_months, trade_rows = legs.n_months, legs.trade_rows
    n_trades = trade_rows.size
    gross = legs.ret[:, long - 1] - legs.ret[:, short - 1]

    capital = 1.0 + legs.trade_pl[:, long - 1] - legs.trade_pl[:, short - 1]
    if convention == "capital" and (capital <= 0).any():
        LOGGER.warning(
            "held_long_short%s: the strategy's capital is zero or negative at %d of %d trades "
            "(lowest %.3f); at those trades the strategy restarts with $1 in each leg",
            f" ({label})" if label else "", int((capital <= 0).sum()), n_trades,
            float(capital.min()),
        )
    leg_size = np.ones(n_trades) if convention == "dollar" else np.where(capital > 0, capital, 1.0)
    size = np.ones((n_trades, n_ptfs))
    size[:, short - 1] = size[:, long - 1] = leg_size

    # Every trade is booked in its own month. The first purchase is not in the
    # series: it is the entry cost.
    cost, turnover = _trade_costs(legs, size)
    cost_short, cost_long = _booked(cost[:, short - 1], legs), _booked(cost[:, long - 1], legs)
    turnover_short = _booked(turnover[:, short - 1], legs)
    turnover_long = _booked(turnover[:, long - 1], legs)
    capital_ts = np.full(n_months, np.nan)
    capital_ts[trade_rows] = capital
    entry_short, entry_long = float(cost[0, short - 1]), float(cost[0, long - 1])
    total_cost, total_turnover = cost_short + cost_long, turnover_short + turnover_long

    # The same two portfolios with the legs exchanged (the strategy held short).
    capital_x = 1.0 + legs.trade_pl[:, short - 1] - legs.trade_pl[:, long - 1]
    if convention == "dollar":
        cost_x, turnover_x = total_cost, total_turnover
    else:
        size[:, short - 1] = size[:, long - 1] = np.where(capital_x > 0, capital_x, 1.0)
        cx, tx = _trade_costs(legs, size)
        cost_x = _booked(cx[:, short - 1], legs) + _booked(cx[:, long - 1], legs)
        turnover_x = _booked(tx[:, short - 1], legs) + _booked(tx[:, long - 1], legs)
    capital_x_ts = np.full(n_months, np.nan)
    capital_x_ts[trade_rows] = capital_x
    return HeldLongShort(
        gross=gross,
        cost=total_cost,
        turnover=total_turnover,
        cost_short=cost_short,
        cost_long=cost_long,
        turnover_short=turnover_short,
        turnover_long=turnover_long,
        capital=capital_ts,
        entry_cost=entry_short + entry_long,
        entry_cost_short=entry_short,
        entry_cost_long=entry_long,
        cost_exchanged=cost_x,
        turnover_exchanged=turnover_x,
        capital_exchanged=capital_x_ts,
    )


@dataclass(frozen=True)
class HeldCompositeLongShort(HeldLongShort):
    """A long/short pair of sides, each the equal-share average of several held legs.

    The attributes of :class:`HeldLongShort`, where ``cost`` and ``turnover``
    (and the two sides' parts) include the monthly re-splits (also those of
    the month after the first purchase), plus:

    Attributes
    ----------
    ret_short, ret_long : each side's return (the average of its portfolios'
        returns); NaN where the side has none.
    resplit_cost, resplit_turnover : the part of ``cost`` and ``turnover``
        that comes from the re-splits (both sides; 0 in a trade month).
    """

    ret_short: np.ndarray
    ret_long: np.ndarray
    resplit_cost: np.ndarray
    resplit_turnover: np.ndarray


def held_composite_long_short(
    legs: HeldLegs,
    short: Sequence[int],
    long: Sequence[int],
    *,
    convention: str = "dollar",
    label: str | None = None,
) -> HeldCompositeLongShort:
    """Long minus short where each side is the average of several portfolios.

    Each side holds its portfolios (``short`` and ``long`` are their ids in
    ``legs``) in equal shares: it is brought back to equal shares at the end
    of every month without a trade, at that month's half-spreads, and moved to
    the new targets in one netted step at a trade. See the module docstring.
    With one portfolio per side this is ``held_long_short``.

    Parameters
    ----------
    legs : the output of ``held_legs(..., monthly_holdings=True)``.
    short, long : the portfolio ids (1-based) of each side; no id in both.
    convention : the size each side is given at a trade: ``"dollar"`` ($1,
        the default) or ``"capital"`` (the strategy's capital K).
    label : the strategy's name, for the warning logged when its capital is
        zero or negative at a trade (``"capital"`` only).

    Returns
    -------
    HeldCompositeLongShort
    """
    n_ptfs = legs.n_ptfs
    sides = []
    for name, ids in (("short", short), ("long", long)):
        ids = [int(p) for p in ids]
        if not ids or len(set(ids)) != len(ids):
            raise ValueError(f"{name} must be a non-empty list of distinct portfolio ids")
        for p in ids:
            if not 1 <= p <= n_ptfs:
                raise ValueError(f"{name} has {p}, which is not a portfolio id in 1..{n_ptfs}")
        sides.append(np.array(ids) - 1)
    if set(sides[0]) & set(sides[1]):
        raise ValueError("short and long must not share a portfolio")
    if convention not in CONVENTIONS:
        raise ValueError(f"convention must be 'capital' or 'dollar'; got {convention!r}")
    if legs.held is None or legs.held_cost is None:
        raise ValueError("legs must come from held_legs(..., monthly_holdings=True)")

    n_months, trade_rows = legs.n_months, legs.trade_rows
    n_trades = trade_rows.size
    is_trade = np.zeros(n_months, dtype=bool)
    is_trade[trade_rows] = True
    last = max(legs.last_row, int(trade_rows[0]))

    # Which portfolios hold something after each trade: (n_trades, n_ptfs).
    bought = legs.ptf_new > 0
    funded = (
        np.bincount(
            legs.trade_idx[bought] * n_ptfs + legs.ptf_new[bought] - 1,
            weights=legs.target[bought],
            minlength=n_trades * n_ptfs,
        ).reshape(n_trades, n_ptfs)
        > 0
    )
    # A leg's value at the end of each month, per $1 after its last trade (in
    # a trade month: before that trade).
    leg_end = legs.value + np.nan_to_num(legs.pl)
    half_spread = np.nan_to_num(legs.tcost)

    def one_side(cols: np.ndarray):
        """Return, value and re-split of one side, per $1 of side after its last trade."""
        ret = np.full(n_months, np.nan)
        value_end = np.full(n_months, np.nan)  # at the end of the month, before a trade
        entering = np.full(n_months, np.nan)   # entering the month
        # share[t, j]: dollars of side in portfolio cols[j] per $1 of that leg
        # (after its last trade), during month t + 1, i.e. after month t's
        # re-split or trade.
        share = np.zeros((n_months, cols.size))
        cost, turnover = np.zeros(n_months), np.zeros(n_months)
        n_funded = funded[:, cols].sum(axis=1)
        for k in range(n_trades):
            j = int(trade_rows[k])
            stop = int(trade_rows[k + 1]) if k + 1 < n_trades else last
            m = int(n_funded[k])
            on = funded[k, cols]
            share[j] = 0.0  # whatever the last re-split left is replaced by the trade
            if m:
                share[j, on] = 1.0 / m
            rows = np.arange(j + 1, min(stop, last) + 1)
            if rows.size == 0:
                continue
            entering[rows[0]] = 1.0
            if m == 0:
                # An empty side holds nothing: no return, its value stays at $1.
                value_end[rows] = 1.0
                entering[rows[1:]] = 1.0
                continue
            r = legs.ret[np.ix_(rows, cols[on])]
            has = np.isfinite(r).any(axis=1)
            side_ret = np.nan_to_num(r).sum(axis=1) / m
            ret[rows] = np.where(has, side_ret, np.nan)
            v = np.cumprod(1.0 + side_ret)
            value_end[rows] = v
            entering[rows[1:]] = v[:-1]
            # Equal shares again at the end of each of these months. (The
            # month of the next trade is overwritten by that trade.)
            with np.errstate(invalid="ignore", divide="ignore"):
                new = (v / m)[:, None] / leg_end[np.ix_(rows, cols[on])]
            new[~np.isfinite(new)] = 0.0  # a leg that is worth nothing holds nothing
            if m == 1:
                new[:] = 1.0  # one portfolio is the whole side: nothing to re-split
            share[np.ix_(rows, np.flatnonzero(on))] = new
            split = rows[~is_trade[rows]]
            if split.size:
                moved = np.abs(share[split] - share[split - 1])[:, on]
                dollars = (moved * np.nan_to_num(legs.held[np.ix_(split, cols[on])])).sum(axis=1)
                spread = (moved * np.nan_to_num(legs.held_cost[np.ix_(split, cols[on])])).sum(axis=1)
                cost[split] = spread / entering[split]
                turnover[split] = dollars / entering[split]
        return ret, value_end, entering, share, n_funded, cost, turnover

    out = [one_side(cols) for cols in sides]
    (ret_s, end_s, ent_s, share_s, m_s, split_cost_s, split_to_s) = out[0]
    (ret_l, end_l, ent_l, share_l, m_l, split_cost_l, split_to_l) = out[1]
    gross = ret_l - ret_s

    # The strategy's capital at each trade, per $1 in each side after the
    # previous trade.
    capital = np.ones(n_trades)
    if n_trades > 1:
        later = trade_rows[1:]
        capital[1:] = 1.0 + (np.nan_to_num(end_l[later], nan=1.0) - 1.0) - (
            np.nan_to_num(end_s[later], nan=1.0) - 1.0
        )
    if convention == "dollar":
        size = np.ones(n_trades)
    else:
        if (capital <= 0).any():
            LOGGER.warning(
                "held_composite_long_short%s: the strategy's capital is zero or negative at "
                "%d of %d trades (lowest %.3f); at those trades the strategy restarts with $1 "
                "in each side",
                f" ({label})" if label else "", int((capital <= 0).sum()), n_trades,
                float(capital.min()),
            )
        size = np.where(capital > 0, capital, 1.0)

    # Every trade is booked in its own month. The first purchase is not in the
    # series: it is the entry cost.
    prev_row = np.maximum(trade_rows - 1, 0)  # the month before each trade

    def trades(cols: np.ndarray, share, n_funded, entering_ts, size=size):
        where = np.full(n_ptfs + 1, -1)
        where[cols + 1] = np.arange(cols.size)
        j_new, j_old = where[legs.ptf_new], where[legs.ptf_old]
        k = legs.trade_idx
        with np.errstate(invalid="ignore", divide="ignore"):
            per_ptf = np.where(n_funded > 0, size / n_funded, 0.0)
        new = np.where(j_new >= 0, per_ptf[k] * legs.target, 0.0)
        # What the side holds going into the trade: the leg's holding times the
        # side's share of that leg as last month's re-split (or trade) left it.
        old = np.where(j_old >= 0, share[prev_row[k], np.maximum(j_old, 0)] * legs.pre, 0.0)
        traded = np.abs(new - old)
        dollars = np.bincount(k, weights=traded, minlength=n_trades)
        spread = np.bincount(k, weights=traded * half_spread, minlength=n_trades)
        entering = np.ones(n_trades)  # the first purchase is of a $1 side
        entering[1:] = np.nan_to_num(entering_ts[trade_rows[1:]], nan=1.0)
        cost, turnover = np.zeros(n_months), np.zeros(n_months)
        cost[trade_rows[1:]] = (spread / entering)[1:]
        turnover[trade_rows[1:]] = (dollars / entering)[1:]
        return cost, turnover, float(spread[0])

    trade_cost_s, trade_to_s, entry_short = trades(sides[0], share_s, m_s, ent_s)
    trade_cost_l, trade_to_l, entry_long = trades(sides[1], share_l, m_l, ent_l)
    cost_short, cost_long = trade_cost_s + split_cost_s, trade_cost_l + split_cost_l
    to_short, to_long = trade_to_s + split_to_s, trade_to_l + split_to_l
    capital_ts = np.full(n_months, np.nan)
    capital_ts[trade_rows] = capital

    # The same two sides exchanged (the factor held short). The re-splits are
    # within a side and do not depend on which side is long.
    capital_x = 2.0 - capital
    if convention == "dollar":
        cost_x, turnover_x = cost_short + cost_long, to_short + to_long
    else:
        size_x = np.where(capital_x > 0, capital_x, 1.0)
        xc_s, xt_s, _ = trades(sides[0], share_s, m_s, ent_s, size_x)
        xc_l, xt_l, _ = trades(sides[1], share_l, m_l, ent_l, size_x)
        cost_x = xc_s + xc_l + split_cost_s + split_cost_l
        turnover_x = xt_s + xt_l + split_to_s + split_to_l
    capital_x_ts = np.full(n_months, np.nan)
    capital_x_ts[trade_rows] = capital_x
    return HeldCompositeLongShort(
        gross=gross,
        cost=cost_short + cost_long,
        turnover=to_short + to_long,
        cost_short=cost_short,
        cost_long=cost_long,
        turnover_short=to_short,
        turnover_long=to_long,
        capital=capital_ts,
        entry_cost=entry_short + entry_long,
        entry_cost_short=entry_short,
        entry_cost_long=entry_long,
        cost_exchanged=cost_x,
        turnover_exchanged=turnover_x,
        capital_exchanged=capital_x_ts,
        ret_short=ret_s,
        ret_long=ret_l,
        resplit_cost=split_cost_s + split_cost_l,
        resplit_turnover=split_to_s + split_to_l,
    )


__all__ = [
    "CONVENTIONS",
    "HeldCompositeLongShort",
    "HeldLegs",
    "HeldLongShort",
    "HeldPortfolioCosts",
    "held_composite_long_short",
    "held_legs",
    "held_long_short",
    "held_portfolio_costs",
]
