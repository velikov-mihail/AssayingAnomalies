"""
Portfolio sorting utilities (univariate/bivariate sorts).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import pandas as pd

from ..data_access import load as aa_load
from .held import CONVENTIONS, held_legs, held_long_short, held_portfolio_costs
from .ols import nanols


def _to_month_end(yyyymm: Any) -> pd.Timestamp | None:
    """Convert a MATLAB-style YYYYMM integer to a month-end Timestamp."""
    if yyyymm is None:
        return None
    if isinstance(yyyymm, (pd.Timestamp, np.datetime64)):
        return pd.Timestamp(yyyymm) + pd.offsets.MonthEnd(0)
    yyyymm = int(yyyymm)
    if not (100001 <= yyyymm <= 999912) or not (1 <= yyyymm % 100 <= 12):
        raise ValueError(
            f"timePeriod has to be YYYYMM or [YYYYMM YYYYMM]; got {yyyymm}"
        )
    return (pd.Timestamp(year=yyyymm // 100, month=yyyymm % 100, day=1)
            + pd.offsets.MonthEnd(0))


def _time_mask(index: pd.Index, time_period: Any) -> np.ndarray:
    """Boolean mask over a (date, permno) or date index for a MATLAB timePeriod.

    ``time_period`` may be a YYYYMM integer (sample start), a Timestamp, or a
    1- or 2-element sequence ``(start, end)`` of YYYYMM integers/Timestamps
    (either possibly None). Mirrors MATLAB ``runUnivSort`` timePeriod handling.
    """
    if time_period is None:
        return np.ones(len(index), dtype=bool)
    if np.isscalar(time_period) or isinstance(time_period, (pd.Timestamp, np.datetime64)):
        time_period = (time_period, None)
    if len(time_period) not in (1, 2):
        raise ValueError("timePeriod has to be YYYYMM or [YYYYMM YYYYMM]")
    start = _to_month_end(time_period[0])
    end = _to_month_end(time_period[1]) if len(time_period) == 2 else None
    d = index.get_level_values("date") if isinstance(index, pd.MultiIndex) else index
    mask = np.ones(len(d), dtype=bool)
    if start is not None:
        mask &= (d >= start)
    if end is not None:
        mask &= (d <= end)
    return mask


@dataclass
class SortResult:
    leg_returns: pd.DataFrame
    long_short: pd.Series | None
    metadata: dict[str, Any]
    long_short_net: pd.Series | None = None

    # MATLAB-style outputs (see `runUnivSort.m` / `estFactorRegs.m`).
    # Conventions:
    # - xret/alpha are in % per month (MATLAB multiplies by 100).
    # - sharpe/info are annualized ratios (unitless), using monthly data and sqrt(12).
    xret: pd.Series | None = None
    txret: pd.Series | None = None
    alpha: pd.Series | None = None
    talpha: pd.Series | None = None
    sharpe: pd.Series | None = None
    info: pd.Series | None = None
    resid: pd.DataFrame | None = None

    # Legacy Python outputs (kept for backwards compatibility).
    # - `alphas` are in raw return units (NOT %).
    # - `tstats` are the t-stats of `alphas`.
    alphas: pd.Series | None = None
    tstats: pd.Series | None = None
    factor_loadings: pd.DataFrame | None = None
    factor_loading_tstats: pd.DataFrame | None = None
    r2: pd.Series | None = None
    r2_adj: pd.Series | None = None
    ptf_num_stocks: pd.DataFrame | None = None
    ptf_market_cap: pd.DataFrame | None = None

    # Trading-cost block (populated when a per-stock tcost panel is supplied;
    # mirrors the MATLAB `runUnivSort` Res fields with tcosts).
    tcosts_ts: pd.Series | None = None    # long+short leg costs per month (decimal)
    netpret: pd.Series | None = None      # net long-short returns (decimal)
    to_ts: pd.DataFrame | None = None     # turnover of the two extreme legs
    netxret: float | None = None          # mean net L/S return, %/mo
    tnetxret: float | None = None         # t-stat of netxret
    turnover: float | None = None         # average one-sided monthly turnover (decimal)
    tcosts: float | None = None           # average monthly costs (decimal)
    ptf_costs: pd.DataFrame | None = None  # per-portfolio costs (date x n_ptfs)
    ptf_to: pd.DataFrame | None = None     # per-portfolio turnover (date x n_ptfs)
    # The cost of the first purchase of the two extreme legs (decimal, per $1
    # in each leg). It is not in tcosts_ts, netpret, tcosts or turnover.
    entry_cost: float | None = None
    ptf_entry_costs: pd.Series | None = None  # the same per portfolio (index 1..n_ptfs)
    # convention="capital" only: the cost per month of the strategy held short
    # (the same two portfolios with the legs exchanged), for
    # calc_gen_alpha(..., anom_tcosts_short=). None under "dollar", where it
    # is tcosts_ts.
    tcosts_ts_short: pd.Series | None = None

    @property
    def pret(self) -> pd.DataFrame:
        """Portfolio returns with a 'long_short' column appended (MATLAB Res.pret)."""
        out = self.leg_returns.copy()
        if self.long_short is not None:
            out["long_short"] = self.long_short
        return out

    @property
    def dates(self) -> pd.Index:
        """Month-end dates of the portfolio return series (MATLAB Res.dates)."""
        return self.leg_returns.index

    def table(self) -> pd.DataFrame:
        """MATLAB ``prtSortResults``-style summary table.

        Requires MATLAB-style stats (i.e. the sort was run with a factor model).
        """
        if self.xret is None:
            raise ValueError(
                "MATLAB-style stats unavailable; run the sort with a factor_model."
            )
        out = pd.DataFrame({
            "xret (%/mo)": self.xret,
            "t(xret)": self.txret,
            "alpha (%/mo)": self.alpha,
            "t(alpha)": self.talpha,
            "Sharpe": self.sharpe,
            "Info ratio": self.info,
        }).T
        if self.factor_loadings is not None:
            for fac in self.factor_loadings.columns:
                out.loc[fac] = self.factor_loadings[fac]
                out.loc[f"t({fac})"] = (
                    self.factor_loading_tstats[fac]
                    if self.factor_loading_tstats is not None
                    else np.nan
                )
        if self.ptf_num_stocks is not None:
            out.loc["n stocks"] = self.ptf_num_stocks.mean().reindex(out.columns)
        if self.netxret is not None:
            out.loc["net xret (%/mo)"] = np.nan
            out.loc["net xret (%/mo)", out.columns[-1]] = self.netxret
            out.loc["t(net xret)"] = np.nan
            out.loc["t(net xret)", out.columns[-1]] = self.tnetxret
        return out

    def print_results(self) -> None:
        """Print a summary of the sort results.

        When MATLAB-style stats are available (the sort was run with a factor
        model), prints the ``prtSortResults``-style table of excess returns,
        alphas, loadings, and (if a per-stock tcost panel was supplied) net
        returns and turnover. Otherwise falls back to a plain summary of raw
        portfolio returns.
        """
        if self.xret is not None:
            meta = self.metadata
            weighting = str(meta.get("weighting", "v"))
            w = "Value-weighted" if weighting.lower().startswith("v") else "Equally-weighted"
            hperiod = meta.get("holding_period", 1)
            factor_model = meta.get("factor_model")
            dates = self.leg_returns.index
            print(f"\n{w} sort, {hperiod}-month holding period, "
                  f"factor model = {factor_model}, "
                  f"{dates.min():%Y-%m} to {dates.max():%Y-%m}")
            with pd.option_context("display.float_format", lambda v: f"{v:8.2f}"):
                print(self.table().to_string())
            if self.turnover is not None:
                print(f"\nturnover = {100 * self.turnover:.2f}%/mo, "
                      f"tcosts = {100 * self.tcosts:.3f}%/mo")
            return
        self._print_results_legacy()

    def _print_results_legacy(self) -> None:
        """Print summary of sort results using pandas DataFrames for clean display."""
        meta = self.metadata
        n_bins = meta.get("n_bins", 5)
        weighting = meta.get("weighting", "v")
        holding = meta.get("holding_period", 1)
        breaks = meta.get("breaks", "name")

        w_label = "Value-weighted" if weighting.startswith("v") else "Equally-weighted"
        breaks_label = {"name": "Name", "nyse": "NYSE", "cap": "Cap-weighted"}.get(breaks, breaks)

        print()
        print(f"  {w_label} portfolio sort, {holding}-month holding period")
        print(f"  Breakpoints: {breaks_label}, {n_bins} portfolios")
        print()

        # Build column labels
        cols = [str(i) for i in range(1, n_bins + 1)]
        if self.long_short is not None:
            cols.append("L/S")

        # Compute statistics
        means = self.leg_returns.mean() * 100
        stds = self.leg_returns.std() * 100
        n_obs = self.leg_returns.notna().sum()
        t_means = means / (stds / np.sqrt(n_obs))
        sharpes = means / stds * np.sqrt(12)
        counts = self.ptf_num_stocks.mean() if self.ptf_num_stocks is not None else None

        # Add L/S stats
        if self.long_short is not None:
            ls_mean = self.long_short.mean() * 100
            ls_std = self.long_short.std() * 100
            ls_n = self.long_short.notna().sum()
            ls_t = ls_mean / (ls_std / np.sqrt(ls_n))
            ls_sharpe = (self.long_short.mean() / self.long_short.std()) * np.sqrt(12)
            means["L/S"] = ls_mean
            t_means["L/S"] = ls_t
            sharpes["L/S"] = ls_sharpe
            if counts is not None:
                counts["L/S"] = counts.get(1, 0) + counts.get(n_bins, 0)

        # Build summary DataFrame
        summary = pd.DataFrame(index=cols)
        summary["Mean (%)"] = [means.get(int(c) if c != "L/S" else c, np.nan) for c in cols]
        summary["t-stat"] = [t_means.get(int(c) if c != "L/S" else c, np.nan) for c in cols]
        summary["Sharpe"] = [sharpes.get(int(c) if c != "L/S" else c, np.nan) for c in cols]
        if counts is not None:
            summary["# Stocks"] = [int(round(counts.get(int(c) if c != "L/S" else c, 0))) for c in cols]

        # Format and print
        def _fmt(row_name: str, val: float) -> str:
            if pd.isna(val):
                return "NaN"
            if row_name == "# Stocks":
                return f"{int(val)}"
            return f"{val:.2f}"

        print("Portfolio Returns:")
        summary_t = summary.T
        # Build formatted output manually for control
        header = "           " + "  ".join(f"{c:>8}" for c in cols)
        print(header)
        for row_name in summary_t.index:
            row_vals = "  ".join(f"{_fmt(row_name, v):>8}" for v in summary_t.loc[row_name])
            print(f"{row_name:<11}{row_vals}")
        print()

        # Factor model results
        if self.alphas is not None and self.tstats is not None:
            alpha_vals = []
            alpha_t = []
            for c in cols:
                key = int(c) if c != "L/S" else "long_short"
                alpha_vals.append(self.alphas.get(key, np.nan) * 100)
                alpha_t.append(self.tstats.get(key, np.nan))

            factor_summary = pd.DataFrame(index=cols)
            factor_summary["Alpha (%)"] = alpha_vals
            factor_summary["t(Alpha)"] = alpha_t

            if self.factor_loadings is not None and not self.factor_loadings.empty:
                for factor in self.factor_loadings.columns:
                    loadings = []
                    load_t = []
                    for c in cols:
                        key = int(c) if c != "L/S" else "long_short"
                        if key in self.factor_loadings.index:
                            loadings.append(self.factor_loadings.loc[key, factor])
                            if self.factor_loading_tstats is not None and key in self.factor_loading_tstats.index:
                                load_t.append(self.factor_loading_tstats.loc[key, factor])
                            else:
                                load_t.append(np.nan)
                        else:
                            loadings.append(np.nan)
                            load_t.append(np.nan)
                    factor_summary[factor] = loadings
                    factor_summary[f"t({factor})"] = load_t

            print("Factor Model:")
            factor_t = factor_summary.T
            header = "           " + "  ".join(f"{c:>8}" for c in cols)
            print(header)
            for row_name in factor_t.index:
                row_vals = "  ".join(f"{v:>8.2f}" if pd.notna(v) else f"{'NaN':>8}" for v in factor_t.loc[row_name])
                print(f"{row_name:<11}{row_vals}")
            print()

    def plot_results(self, figsize: tuple[int, int] = (12, 10)) -> Any:
        """
        Plot 4-panel strategy figure (matching MATLAB plotStrategyFigs).

        Panels:
        1. Cumulative return (in logs)
        2. 5-year rolling Sharpe ratio
        3. # of stocks over time
        4. Returns by year (bar chart)

        Parameters
        ----------
        figsize : tuple, default (12, 10)
            Figure size in inches.

        Returns
        -------
        matplotlib.figure.Figure
            The figure object.
        """
        try:
            import matplotlib.pyplot as plt

            from ..plotting import maybe_show
        except ImportError:
            raise ImportError("matplotlib is required for plotting. Install with: pip install matplotlib")

        if self.long_short is None:
            raise ValueError("No long/short portfolio to plot. Set add_long_short=True.")

        r = self.long_short.dropna()
        dates = pd.to_datetime(r.index)

        fig, axes = plt.subplots(2, 2, figsize=figsize)
        fig.suptitle("Strategy Performance", fontsize=14, fontweight="bold")

        # Panel 1: Cumulative return (in logs)
        ax1 = axes[0, 0]
        cum_ret = np.log(np.cumprod(1 + r.values))
        ax1.plot(dates, cum_ret, "-", color="crimson", linewidth=1.5)
        ax1.set_title("Cumulative return (in logs)")
        ax1.set_xlabel("Date")
        ax1.set_ylabel("Log return")
        ax1.grid(True, alpha=0.3)

        # Panel 2: 5-year rolling Sharpe ratio
        ax2 = axes[0, 1]
        window = 60  # 5 years * 12 months
        if len(r) > window:
            rolling_mean = r.rolling(window).mean()
            rolling_std = r.rolling(window).std()
            rolling_sharpe = np.sqrt(12) * rolling_mean / rolling_std
            ax2.plot(dates, rolling_sharpe.values, "-", color="crimson", linewidth=1.5)
        ax2.set_title("5-year rolling Sharpe ratio")
        ax2.set_xlabel("Date")
        ax2.set_ylabel("Sharpe ratio")
        ax2.axhline(0, color="black", linewidth=0.5, linestyle="--")
        ax2.grid(True, alpha=0.3)

        # Panel 3: # of stocks over time
        ax3 = axes[1, 0]
        if self.ptf_num_stocks is not None:
            n_bins = self.metadata.get("n_bins", 5)
            # L/S = Q1 + Q_n stocks
            if 1 in self.ptf_num_stocks.columns and n_bins in self.ptf_num_stocks.columns:
                ls_stocks = self.ptf_num_stocks[1] + self.ptf_num_stocks[n_bins]
                ls_stocks = ls_stocks.dropna()
                stock_dates = pd.to_datetime(ls_stocks.index)
                ax3.plot(stock_dates, ls_stocks.values, "-", color="steelblue", linewidth=1.5)
        ax3.set_title("# of stocks (long + short legs)")
        ax3.set_xlabel("Date")
        ax3.set_ylabel("Number of stocks")
        ax3.grid(True, alpha=0.3)

        # Panel 4: Returns by year (bar chart)
        ax4 = axes[1, 1]
        years = dates.year
        annual_returns = []
        unique_years = sorted(years.unique())
        for yr in unique_years:
            mask = years == yr
            yr_ret = r.values[mask]
            # Compound annual return
            ann_ret = (np.prod(1 + yr_ret) - 1) * 100
            annual_returns.append(ann_ret)

        colors = ["green" if ret >= 0 else "red" for ret in annual_returns]
        ax4.bar(unique_years, annual_returns, color=colors, alpha=0.7, edgecolor="black", linewidth=0.5)
        ax4.set_title("Returns by year (%)")
        ax4.set_xlabel("Year")
        ax4.set_ylabel("Annual return (%)")
        ax4.axhline(0, color="black", linewidth=0.5)
        ax4.grid(True, alpha=0.3, axis="y")

        plt.tight_layout()
        maybe_show(plt)
        return fig


@dataclass
class BivariateSortResult:
    """
    Results for a bivariate portfolio sort.

    - `flat` contains the n1*n2 portfolios (flattened, MATLAB-style numbering).
    - `cell_returns` is the same data reshaped as a (bin1, bin2) grid via MultiIndex columns.
    - `cond_var1_given_var2` are long-short strategies (high var1 minus low var1) within each var2 bin.
    - `cond_var2_given_var1` are long-short strategies (high var2 minus low var2) within each var1 bin.
    """

    flat: SortResult
    cell_returns: pd.DataFrame
    cond_var1_given_var2: SortResult
    cond_var2_given_var1: SortResult
    metadata: dict[str, Any]

    def print_grid(
        self,
        label: str = "",
        name1: str = "var1",
        name2: str = "var2",
    ) -> pd.DataFrame:
        """Compact display of the bivariate sort: the average-return grid plus
        the conditional var2-within-var1 long/short strategies.

        Returns the (n1 x n2) grid of average portfolio returns in %/mo.
        """
        n1 = int(self.metadata["n_bins1"])
        n2 = int(self.metadata["n_bins2"])
        grid = pd.DataFrame(
            100 * self.flat.leg_returns.mean().to_numpy().reshape(n1, n2),
            index=[f"{name1} {i}" for i in range(1, n1 + 1)],
            columns=[f"{name2} {j}" for j in range(1, n2 + 1)],
        )
        print(f"\n=== {label} ===")
        print(f"\nAverage portfolio returns (%/mo), {n1}x{n2} grid:")
        with pd.option_context("display.float_format", lambda v: f"{v:7.3f}"):
            print(grid.to_string())
        cond = self.cond_var2_given_var1
        if cond.xret is not None:
            tbl = pd.DataFrame({
                "xret (%/mo)": cond.xret,
                "t(xret)": cond.txret,
                "alpha (%/mo)": cond.alpha,
                "t(alpha)": cond.talpha,
            })
            tbl.index = [f"{name2} L/S within {name1} {i}" for i in tbl.index]
            print(f"\nConditional {name2} strategies:")
            with pd.option_context("display.float_format", lambda v: f"{v:7.3f}"):
                print(tbl.to_string())
        return grid


def _date_codes_and_months(
    dates: pd.Index | np.ndarray,
) -> tuple[np.ndarray, pd.DatetimeIndex, np.ndarray]:
    """Observed-date grouping codes plus calendar-month ordinals.

    Returns ``(date_codes, uniq_dates, uniq_months)``. Row ``i`` belongs to
    observed date ``uniq_dates[date_codes[i]]``, whose calendar-month ordinal
    (``year * 12 + month - 1``) is ``uniq_months[date_codes[i]]``.

    ``date_codes`` are positions among the dates *present in the panel*: use
    them only to group rows by date. Any "k months earlier" arithmetic must use
    the ordinals, because a whole month absent from the panel makes adjacent
    codes more than one calendar month apart.

    Raises ``ValueError`` unless every date is a month-end timestamp at
    midnight (the panel convention).
    """
    date_codes, uniq = pd.factorize(dates, sort=True)
    if (date_codes < 0).any():
        raise ValueError("panel dates must not contain missing values (NaT)")
    if pd.api.types.is_numeric_dtype(uniq):
        raise ValueError(
            "panel dates must be month-end timestamps; got numeric "
            f"values such as {uniq[0]!r}"
        )
    uniq = pd.DatetimeIndex(uniq)
    bad = ~(uniq.is_month_end & (uniq == uniq.normalize()))
    if bad.any():
        examples = ", ".join(str(d) for d in uniq[bad][:3])
        raise ValueError(
            "panel dates must be month-end dates (e.g. 2000-02-29); "
            f"got {int(bad.sum())} other date(s): {examples}"
        )
    uniq_months = (uniq.year.to_numpy(dtype=np.int64) * 12
                   + uniq.month.to_numpy(dtype=np.int64) - 1)
    return date_codes, uniq, uniq_months


def _calendar_lag_positions(
    month_ord: np.ndarray, permnos: np.ndarray, lag: int = 1
) -> np.ndarray:
    """Row position of each observation's value ``lag`` calendar months earlier.

    ``month_ord`` holds each row's calendar-month ordinal (see
    ``_date_codes_and_months``), not its observed-date code. The lookup is
    exact: it returns -1 where that (month, permno) cell is absent from the
    panel -- whether the stock or the whole month is missing -- which is how
    MATLAB's rectangular grid behaves (the cell exists but holds NaN / 0). It
    never reaches further back to an earlier observation.

    Assumes the panel is sorted by (date, permno); raises ``ValueError`` on
    duplicate (date, permno) keys.
    """
    permno_codes, uniq = pd.factorize(np.asarray(permnos), sort=True)
    stride = len(uniq)
    month_ord = np.asarray(month_ord, dtype=np.int64)
    base = month_ord.min() if month_ord.size else 0
    keys = (month_ord - base) * stride + permno_codes
    steps = np.diff(keys)
    if (steps == 0).any():
        raise ValueError("panel has duplicate (date, permno) keys")
    if (steps < 0).any():
        raise ValueError("panel must be sorted by (date, permno)")
    prev = keys - lag * stride
    pos = np.searchsorted(keys, prev)
    pos_c = np.minimum(pos, max(keys.size - 1, 0))
    ok = (prev >= 0) & (pos < keys.size) & (keys[pos_c] == prev)
    return np.where(ok, pos_c, -1)


def _take_lagged(values: np.ndarray, lag_src: np.ndarray, fill: float) -> np.ndarray:
    out = np.full(values.shape, fill, dtype=float)
    ok = lag_src >= 0
    out[ok] = values[lag_src[ok]]
    return out


def _calendar_ffill_plan(index: pd.MultiIndex) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """What ``_calendar_ffill`` needs from a (date, permno) index, computed once.

    Returns ``(order, month, first)``: the row order sorted by (permno, month),
    the calendar-month ordinal of each sorted row and the sorted position of
    the first row of each sorted row's stock. Raises ``ValueError`` on
    duplicate keys or non-month-end dates.
    """
    date_codes, _, uniq_months = _date_codes_and_months(index.get_level_values("date"))
    month = uniq_months[date_codes]
    permno = np.asarray(index.get_level_values("permno"))
    order = np.lexsort((month, permno))
    m, p = month[order], permno[order]
    same = (p[1:] == p[:-1])
    if (same & (m[1:] == m[:-1])).any():
        raise ValueError("panel has duplicate (date, permno) keys")
    first = np.where(np.r_[True, ~same], np.arange(m.size), 0)
    np.maximum.accumulate(first, out=first)
    return order, m, first


def _calendar_ffill_values(
    values: np.ndarray,
    plan: tuple[np.ndarray, np.ndarray, np.ndarray],
    max_months: int,
) -> np.ndarray:
    order, m, first = plan
    out = np.asarray(values, dtype=float).copy()
    v = out[order]
    last = np.where(~np.isnan(v), np.arange(v.size), -1)
    np.maximum.accumulate(last, out=last)
    src = np.where(last >= first, last, -1)
    ok = (src >= 0) & np.isnan(v) & (m - m[np.maximum(src, 0)] <= max_months)
    out[order] = np.where(ok, v[np.maximum(src, 0)], v)
    return out


def _calendar_ffill(s: pd.Series, max_months: int) -> pd.Series:
    """Carry each stock's last non-NaN value forward at most ``max_months`` months.

    ``s`` is indexed by (date, permno) with month-end dates. A missing cell
    takes the stock's most recent non-NaN value when that value is at most
    ``max_months`` *calendar* months older, so rows absent from the panel count
    toward the limit rather than stretching it (``groupby().ffill(limit=k)``
    counts rows). Observed values are never changed. Raises ``ValueError`` on
    duplicate keys or non-month-end dates.
    """
    out = s.to_numpy(dtype=float).copy()
    if max_months <= 0 or out.size == 0:
        return pd.Series(out, index=s.index, name=s.name)
    out = _calendar_ffill_values(out, _calendar_ffill_plan(s.index), max_months)
    return pd.Series(out, index=s.index, name=s.name)


def fill_months(x: pd.Series | pd.DataFrame, months: int = 11) -> pd.Series | pd.DataFrame:
    """
    Carry each stock's last value forward for at most ``months`` calendar months.

    The Python counterpart of MATLAB's ``FillMonths``. Annual Compustat columns
    are stored in ``ccm_panel`` on one row a year, the June in which the record
    becomes available. ``fill_months`` spreads such a column, or a signal
    computed from such columns, over the following months, so that it has a
    value every month from June through the next May::

        d = aa.load(["gp", "at"])            # values in June only
        signal = d["gp"] / d["at"]           # June only: a sort trades once a year
        monthly = aa.fill_months(signal)     # June to May: a sort trades every month

    Parameters
    ----------
    x : Series or DataFrame
        Indexed by (date, permno) with month-end dates, numeric. A DataFrame
        is filled column by column, each column on its own.
    months : int, default 11
        How many calendar months a value is carried. 11 is the annual case: a
        June value reaches the following May and stops there, so it never
        stands in for a later year that has no record. Use 2 for a quarterly
        value. 0 returns the input unchanged.

    Returns
    -------
    Series or DataFrame
        Same index and columns, as float. A missing cell takes the stock's most
        recent non-missing value if that value is at most ``months`` calendar
        months older. Values that are present are never changed.

    Notes
    -----
    The limit counts calendar months, not rows, so a month in which the stock
    has no row still counts. Only rows that exist are filled; no row is added.
    A stock with no row in the June of a record therefore gets nothing from
    that record. Raises ``ValueError`` on duplicate (date, permno) keys and on
    dates that are not month-ends, ``TypeError`` on a non-numeric column.
    """
    if int(months) != months or months < 0:
        raise ValueError(f"months must be a non-negative whole number, got {months!r}")
    months = int(months)
    if not isinstance(x, (pd.Series, pd.DataFrame)):
        raise TypeError("fill_months takes a Series or DataFrame indexed by (date, permno)")
    if not isinstance(x.index, pd.MultiIndex) or not {"date", "permno"} <= set(x.index.names):
        raise ValueError(
            "fill_months needs a (date, permno) MultiIndex, as aa.load returns; "
            f"got index names {list(x.index.names)}"
        )
    frame = x.to_frame() if isinstance(x, pd.Series) else x
    bad = [
        str(c) for c in frame.columns
        if not (pd.api.types.is_numeric_dtype(frame[c]) or pd.api.types.is_bool_dtype(frame[c]))
    ]
    if bad:
        raise TypeError(f"fill_months fills numeric columns only; not numeric: {', '.join(bad)}")
    plan = _calendar_ffill_plan(frame.index) if months > 0 and len(frame) else None
    filled = {}
    for pos in range(frame.shape[1]):
        values = frame.iloc[:, pos].to_numpy(dtype=float, na_value=np.nan)
        filled[pos] = values.copy() if plan is None else _calendar_ffill_values(values, plan, months)
    out = pd.DataFrame(filled, index=frame.index)
    out.columns = frame.columns
    if isinstance(x, pd.Series):
        return out.iloc[:, 0].rename(x.name)
    return out


def calc_ptf_rets(
    returns: pd.Series,
    ind: pd.Series,
    mcap: pd.Series | None,
    *,
    holding_period: int = 1,
    weighting: str = "v",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    MATLAB-style portfolio returns calculator (mirrors `calcPtfRets.m`).

    - Lags portfolio assignment and market cap by 1 month (formation at t-1, returns at t).
    - Carries the lagged assignment forward through months with no new
      assignments (annual or lower-frequency rebalancing), bounded by the
      detected rebalance frequency (MATLAB `calcPtfRets.m` lines 48-58).
    - Requires finite return AND finite lagged market cap for a stock-month to
      contribute (MATLAB `calcPtfRets.m` lines 79-81 — even for equal-weighted legs).
    - If holding_period>1, holds overlapping portfolios by including membership
      from the prior `holding_period-1` vintages (union, not a rolling mean).
    """
    _ensure_multiindex(returns, "returns")
    _ensure_multiindex(ind, "ind")
    if mcap is not None:
        _ensure_multiindex(mcap, "mcap")

    if holding_period < 1:
        raise ValueError("holding_period must be >= 1")

    weighting = weighting.lower()
    if not (weighting.startswith("v") or weighting.startswith("e")):
        raise ValueError("weighting must be 'v' (value) or 'e' (equal)")

    parts = {
        "ret": returns.astype(float),
        "ind": pd.to_numeric(ind, errors="coerce"),
        "mcap": (mcap.astype(float) if mcap is not None else 1.0),
    }
    try:
        df = pd.concat(parts, axis=1).sort_index(kind="stable")
    except ValueError:
        # pandas refuses to align non-unique MultiIndexes with an opaque message.
        for name, obj in parts.items():
            if isinstance(obj, pd.Series) and not obj.index.is_unique:
                raise ValueError(
                    f"{name} has duplicate (date, permno) keys"
                ) from None
        raise

    n_ptfs = int(df["ind"].max() if df["ind"].notna().any() else 0)
    if n_ptfs <= 0:
        raise ValueError("ind must contain positive portfolio ids (1..K).")

    # Two date encodings: `date_codes` group rows by observed date (output
    # rows); `row_months` are calendar-month ordinals for all lag arithmetic.
    dates = df.index.get_level_values(0)
    date_codes, out_index, date_months = _date_codes_and_months(dates)
    row_months = date_months[date_codes]
    n_dates = len(out_index)

    # Lag market cap and the portfolio index (MATLAB lag(mcap,1,nan) /
    # lag(ind,1,0)). MATLAB lags one row of a rectangular months x stocks grid,
    # so a stock absent from the panel last month contributes nothing. A
    # per-permno `shift(1)` would instead reach back to that stock's previous
    # *observed* month -- resurrecting a stale portfolio assignment across gaps
    # -- so look the previous calendar month up explicitly. When the whole
    # previous month is absent the lag is missing for every stock.
    lag_src = _calendar_lag_positions(row_months, df.index.get_level_values(1))
    lmcap = _take_lagged(df["mcap"].to_numpy(dtype=float), lag_src, np.nan)
    lind_arr = _take_lagged(df["ind"].to_numpy(dtype=float), lag_src, 0.0)
    lind_arr = np.where(np.isfinite(lind_arr), lind_arr, 0.0).astype(np.int64)

    # Carry the lagged index forward through months with no new assignments
    # (MATLAB `calcPtfRets.m` lines 48-58): rebalance months are those where
    # any stock has a positive lagged assignment; the fill runs from the month
    # after the first rebalance up to one detected rebalance frequency past the
    # last one. Sequential row-copying is equivalent to sourcing each empty
    # month from the most recent rebalance month at or before it.
    #
    # All of this runs in calendar months: the frequency is the mode of the
    # elapsed months between rebalance months and the window ends that many
    # calendar months after the last one. On a complete calendar this is the
    # MATLAB row arithmetic. A month whose preceding calendar month is absent
    # from the panel has no lagged assignments because of the gap, not because
    # of a lower rebalancing frequency, so it is not filled.
    n_nonzero = np.bincount(date_codes, weights=(lind_arr > 0).astype(float), minlength=n_dates)
    reb = np.flatnonzero(n_nonzero > 0)  # observed-date codes
    if len(reb) > 0:
        reb_months = date_months[reb]
        gaps = np.diff(reb_months)
        if len(gaps) > 0:
            vals, cnts = np.unique(gaps, return_counts=True)
            reb_freq = int(vals[np.argmax(cnts)])  # mode; smallest on ties, like MATLAB
            end_month = min(int(reb_months[-1]) + reb_freq, int(date_months[-1]))
        else:
            end_month = int(date_months[-1])  # MATLAB: min(NaN, nMonths) -> nMonths
        prev_present = np.isin(date_months - 1, date_months)
        fill_months = np.flatnonzero(
            (date_months > reb_months[0])
            & (date_months <= end_month)
            & (n_nonzero == 0)
            & prev_present
        )
        if fill_months.size:
            order = np.argsort(date_codes, kind="stable")
            bounds = np.searchsorted(date_codes[order], np.arange(n_dates + 1))
            permnos_arr = df.index.get_level_values(1).to_numpy()

            months_by_src: dict[int, list[int]] = {}
            for m in fill_months:
                i_src = np.searchsorted(reb_months, date_months[m], side="right") - 1
                months_by_src.setdefault(int(reb[i_src]), []).append(int(m))

            for src, months in months_by_src.items():
                src_rows = order[bounds[src]:bounds[src + 1]]
                src_ser = pd.Series(lind_arr[src_rows], index=permnos_arr[src_rows])
                src_ser = src_ser[src_ser > 0]
                if src_ser.empty:
                    continue
                rows = np.concatenate([order[bounds[m]:bounds[m + 1]] for m in months])
                lind_arr[rows] = (
                    src_ser.reindex(permnos_arr[rows]).fillna(0).to_numpy(dtype=np.int64)
                )

    # Lagged vintages for overlapping holding periods (lag of lind, per stock,
    # by exact calendar month: a vintage from an absent month holds nothing).
    lagged_linds: list[np.ndarray] = []
    if holding_period > 1:
        lind_float = lind_arr.astype(float)
        permnos_lvl = df.index.get_level_values(1)
        for h in range(1, holding_period):
            src = _calendar_lag_positions(row_months, permnos_lvl, lag=h)
            lagged_linds.append(_take_lagged(lind_float, src, 0.0).astype(np.int64))

    # Finite checks (mirrors MATLAB isfinite).
    ret_arr = df["ret"].to_numpy(dtype=float)
    lmcap_arr = lmcap
    finite_ok = np.isfinite(ret_arr) & np.isfinite(lmcap_arr)

    # Equal-weight vs value-weight.
    w_arr = np.ones(len(df), dtype=float) if weighting.startswith("e") else lmcap_arr

    ptf_ret = pd.DataFrame(np.nan, index=out_index, columns=range(1, n_ptfs + 1), dtype="float64")
    ptf_n = pd.DataFrame(np.nan, index=out_index, columns=range(1, n_ptfs + 1), dtype="float64")
    ptf_m = pd.DataFrame(np.nan, index=out_index, columns=range(1, n_ptfs + 1), dtype="float64")

    for i in range(1, n_ptfs + 1):
        held = lind_arr == i
        for shifted in lagged_linds:
            held |= shifted == i
        ok = held & finite_ok
        if not ok.any():
            continue

        w = np.where(ok, w_arr, 0.0)
        wsum = np.bincount(date_codes, weights=w, minlength=n_dates)
        rwsum = np.bincount(date_codes, weights=np.where(ok, ret_arr, 0.0) * w, minlength=n_dates)
        nsum = np.bincount(date_codes, weights=ok.astype(float), minlength=n_dates)
        msum = np.bincount(date_codes, weights=np.where(ok, lmcap_arr, 0.0), minlength=n_dates)

        has_stocks = nsum > 0
        with np.errstate(invalid="ignore", divide="ignore"):
            ret_col = np.where(wsum != 0, rwsum / np.where(wsum != 0, wsum, 1.0), np.nan)
        ptf_ret[i] = np.where(has_stocks, ret_col, np.nan)
        ptf_n[i] = np.where(has_stocks, nsum, np.nan)
        ptf_m[i] = np.where(has_stocks, msum, np.nan)

    return ptf_ret, ptf_n, ptf_m


def average_firm_size(ptf_market_cap: Any, ptf_num_stocks: Any) -> np.ndarray:
    """Average firm size of each portfolio, in the units of market capitalization.

    The time-series mean, over the months in which a portfolio has stocks, of
    its total market capitalization divided by its number of stocks. With
    ``me`` in millions of dollars (``ccm_panel``) the result is in $10^6,
    which is what the report's "me ($10^6)" and "Average market
    capitalization ($10^6)" rows print. One value per column of
    ``ptf_num_stocks``; extra columns of ``ptf_market_cap`` are ignored.
    """
    n = np.asarray(ptf_num_stocks, dtype=float)
    m = np.asarray(ptf_market_cap, dtype=float)
    if n.ndim != 2 or m.ndim != 2 or n.shape[0] != m.shape[0]:
        raise ValueError(
            "ptf_market_cap and ptf_num_stocks must be months x portfolios grids "
            f"over the same months; got shapes {m.shape} and {n.shape}"
        )
    k = min(n.shape[1], m.shape[1])
    n, m = n[:, :k], m[:, :k]
    with np.errstate(invalid="ignore", divide="ignore"):
        per_firm = np.where(n > 0, m / n, np.nan)
    out = np.full(k, np.nan)
    has = np.isfinite(per_firm).any(axis=0)
    if has.any():
        out[has] = np.nanmean(per_firm[:, has], axis=0)
    return out


def est_factor_regs(
    pret: pd.DataFrame,
    *,
    factor_model: int | pd.DataFrame,
    add_long_short: bool = False,
    robust_se: bool = False,
    input_is_excess: bool = False,
    factors: pd.DataFrame | None = None,
) -> tuple[pd.Series, pd.Series, pd.DataFrame, pd.DataFrame, pd.Series]:
    """
    MATLAB-style factor regressions helper (mirrors `estFactorRegs.m`).

    If add_long_short=True, also runs a long-short regression using last-first columns.
    With an integer ``factor_model``, an explicit ``factors`` frame supplies the
    model's columns and risk-free rate; without it they are loaded from the
    database.
    """
    if pret.empty:
        raise ValueError("pret is empty")

    long_short: pd.Series | None = None
    if add_long_short:
        cols = [c for c in pret.columns if pd.notna(c)]
        if len(cols) >= 2:
            lo = min(cols)
            hi = max(cols)
            long_short = pret[hi] - pret[lo]
        else:
            add_long_short = False

    factor_df = _resolve_factor_model(pret.index, factor_model, factors=factors)
    if long_short is None:
        # Reuse the same engine; we'll drop the placeholder result if needed.
        long_short = pd.Series(index=pret.index, dtype="float64")

    alphas, tstats, loadings, loading_tstats, r2 = _run_factor_regs(
        pret, long_short, factor_df, robust=robust_se, input_is_excess=input_is_excess
    )

    if not add_long_short:
        alphas = alphas.drop(index=["long_short"], errors="ignore")
        tstats = tstats.drop(index=["long_short"], errors="ignore")
        loadings = loadings.drop(index=["long_short"], errors="ignore")
        loading_tstats = loading_tstats.drop(index=["long_short"], errors="ignore")
        r2 = r2.drop(index=["long_short"], errors="ignore")

    return alphas, tstats, loadings, loading_tstats, r2


def _matlab_prctile(x: np.ndarray, pcts: Sequence[float]) -> np.ndarray:
    """MATLAB ``prctile``: plot positions ``(i-0.5)/n``, linear interp, clamped ends.

    Differs from ``numpy.percentile`` / ``Series.quantile`` (which use the
    ``(i-1)/(n-1)`` rule); the gap moves quintile breakpoints enough to shuffle
    a handful of stocks between bins every month.
    """
    x = np.sort(np.asarray(x, dtype=float)[np.isfinite(x)])
    p = np.atleast_1d(np.asarray(pcts, dtype=float))
    if x.size == 0:
        return np.full(p.shape, np.nan)
    if x.size == 1:
        return np.full(p.shape, x[0])
    pos = (np.arange(1, x.size + 1) - 0.5) * 100.0 / x.size
    return np.interp(p, pos, x)


def _percentile_cuts(n_bins: int | Sequence[float]) -> list[float]:
    if isinstance(n_bins, int):
        return [i * 100 / n_bins for i in range(1, n_bins)]
    return list(n_bins)


def _matlab_prctile_rows(x: np.ndarray, pcts: Sequence[float]) -> np.ndarray:
    """Row-wise MATLAB ``prctile``, dropping non-finite values.

    Matches ``_matlab_prctile`` on each row. Non-finite entries are set aside
    before the sort, so ``±Inf`` does not move the tails.
    """
    p = np.atleast_1d(np.asarray(pcts, dtype=float))
    n_rows = x.shape[0]
    out = np.full((n_rows, p.size), np.nan, dtype=np.float64)
    if x.size == 0 or p.size == 0:
        return out
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


def _pack_by_group(
    values: np.ndarray,
    group_keys,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Reshape a long panel into a groups × slots matrix.

    Each distinct key becomes one row; observations with that key occupy
    columns ``0 .. n_g-1`` (ragged groups NaN-padded). Original row ``i``
    sits at ``mat[group_codes[i], within[i]]``.

    Layout and scatter are recomputed every call (see
    :mod:`assayinganomalies.session_cache`).
    """
    from ..session_cache import pack_layout, pack_values

    values = np.asarray(values, dtype=np.float64)
    if values.ndim == 1:
        values = values[:, None]
    layout = pack_layout(group_keys)
    mat = pack_values(values, layout)
    return (
        mat,
        layout.unique_keys,
        layout.group_codes,
        layout.within,
    )


def _nyse_values(nyse_flag: pd.Series, index: pd.Index) -> np.ndarray:
    """Align a NYSE flag to ``index`` and return float 0/1/NaN (not bool).

    DuckDB may yield float flags with NULLs; nullable ``boolean`` cannot
    ``fillna(0)``. Callers treat non-zero finite as NYSE, matching the
    previous ``fillna(0).astype(bool)`` rule.
    """
    if hasattr(nyse_flag, "index") and nyse_flag.index is index:
        nyse_mask = nyse_flag
    else:
        nyse_mask = nyse_flag.reindex(index) if hasattr(nyse_flag, "reindex") else nyse_flag
    if str(getattr(nyse_mask, "dtype", "")) == "boolean":
        return nyse_mask.fillna(False).astype(float).to_numpy(dtype=float)
    return pd.to_numeric(nyse_mask, errors="coerce").to_numpy(dtype=float)


def _nyse_ok(nyse_mat: np.ndarray) -> np.ndarray:
    return np.isfinite(nyse_mat) & (nyse_mat != 0)


def _cap_breakpoint_rows(
    sig_mat: np.ndarray,
    mcap_mat: np.ndarray,
    pct: Sequence[float],
) -> np.ndarray:
    """Equal-mass cap breakpoints for every row of a packed cross-section.

    Membership is ``~isnan(sig)`` (``dropna``): ``±Inf`` stocks keep their
    mass. NaN mcap is filled with 0, matching ``mcap.reindex(s.index).fillna(0)``.
    """
    t, n_max = sig_mat.shape
    p = np.atleast_1d(np.asarray(pct, dtype=float))
    out = np.full((t, p.size), np.nan, dtype=np.float64)
    if t == 0 or n_max == 0 or p.size == 0:
        return out
    present = ~np.isnan(sig_mat)
    mass = np.where(present, np.where(np.isnan(mcap_mat), 0.0, mcap_mat), 0.0)
    total = mass.sum(axis=1)
    n_present = present.sum(axis=1).astype(np.int64)
    empty = (n_present == 0) | (total == 0)
    order = np.argsort(np.where(present, sig_mat, np.nan), axis=1, kind="mergesort")
    sorted_sig = np.take_along_axis(sig_mat, order, axis=1)
    sorted_m = np.take_along_axis(mass, order, axis=1)
    cumw = np.cumsum(sorted_m, axis=1)
    targets = total[:, None] * (p[None, :] / 100.0)
    pos = (cumw[:, :, None] <= targets[:, None, :]).sum(axis=1)
    last = np.maximum(n_present - 1, 0)
    pos = np.minimum(pos, last[:, None])
    cuts = sorted_sig[np.arange(t)[:, None], pos]
    return np.where(empty[:, None], np.nan, cuts)


def _breakpoint_rows(
    sig_mat: np.ndarray,
    n_bins: int | Sequence[float],
    breaks: str,
    nyse_mat: np.ndarray | None,
    mcap_mat: np.ndarray | None,
) -> np.ndarray:
    """Breakpoints for every packed row. NaN row = no assignments that group."""
    pct = _percentile_cuts(n_bins)
    breaks = breaks.lower()
    if breaks == "cap":
        if mcap_mat is None:
            raise ValueError("mcap required for breaks='cap'")
        return _cap_breakpoint_rows(sig_mat, mcap_mat, pct)
    if breaks == "nyse":
        if nyse_mat is None:
            raise ValueError("nyse_flag required for breaks='NYSE'")
        work = np.where(_nyse_ok(nyse_mat), sig_mat, np.nan)
        return _matlab_prctile_rows(work, pct)
    return _matlab_prctile_rows(sig_mat, pct)


def _assign_bins_rows(
    sig_mat: np.ndarray,
    cuts: np.ndarray,
    n_bins: int,
) -> np.ndarray:
    """Assign 1..n_bins from row-wise cuts. NaN signal / invalid cuts stay NaN.

    Tie handling matches MATLAB ``assignToPtf.m``: ``x < bp1`` is bin 1,
    ``x >= bpj`` pushes the observation to the higher bin, ``x >= last`` is
    ``n_bins``. ``±Inf`` is assigned (it is not NaN); a month with no finite
    cuts — including ``n_bins == 1``, which has an empty percentile grid —
    assigns nothing, matching the previous empty-``breakpoints`` path.
    """
    t, n_max = sig_mat.shape
    n_cuts = int(cuts.shape[1]) if cuts.ndim == 2 else 0
    out = np.full((t, n_max), np.nan, dtype=np.float64)
    if n_cuts == 0 or t == 0 or n_max == 0:
        return out
    valid = ~np.isnan(cuts).any(axis=1)
    present = ~np.isnan(sig_mat)
    cuts_s = np.sort(cuts, axis=1)
    ge = sig_mat[:, :, None] >= cuts_s[:, None, :]
    bins = 1.0 + ge.sum(axis=2)
    bins = np.where(sig_mat >= cuts_s[:, [-1]], float(n_bins), bins)
    return np.where(valid[:, None] & present, bins, np.nan)


def _get_breakpoints(
    sig: pd.Series,
    n_bins: int | Sequence[float],
    breaks: str,
    nyse_flag: pd.Series | None,
    mcap: pd.Series | None,
) -> pd.Series:
    """
    Compute breakpoints for one cross-section.

    breaks:
      - "name": percentiles on all stocks (equal # of stocks per bin)
      - "NYSE": percentiles on NYSE stocks only (equal # of NYSE stocks per bin)
      - "cap": cumulative market-cap breakpoints (equal total cap per bin)

    If n_bins is int: use percentile grid; if sequence: treat as explicit percentiles.

    Percentiles follow MATLAB ``prctile`` (``makeUnivSortInd.m``), not the
    pandas/numpy default rule.
    """
    pct = _percentile_cuts(n_bins)
    x = pd.to_numeric(sig, errors="coerce").to_numpy(dtype=float).reshape(1, -1)
    nyse_mat = None
    if nyse_flag is not None:
        nyse_mat = _nyse_values(nyse_flag, sig.index).reshape(1, -1)
    mcap_mat = None
    if mcap is not None:
        mcap_mat = (
            pd.to_numeric(mcap.reindex(sig.index), errors="coerce")
            .to_numpy(dtype=float)
            .reshape(1, -1)
        )
    cuts = _breakpoint_rows(x, n_bins, breaks, nyse_mat, mcap_mat)[0]
    if cuts.size == 0 or np.isnan(cuts).all():
        return pd.Series(dtype=float)
    if breaks.lower() == "cap":
        return pd.Series(cuts)
    return pd.Series(cuts, index=[p / 100 for p in pct])


def _assign_bins(
    sig: pd.Series,
    breakpoints: pd.Series,
    n_bins: int,
) -> pd.Series:
    """
    Assign each element into 1..n_bins given breakpoints.

    Tie handling matches MATLAB `assignToPtf.m`:
    - first bin: x < bp1
    - subsequent bins: x >= bpj pushes the observation to the higher bin
    """
    if breakpoints.empty:
        return pd.Series(pd.NA, index=sig.index, dtype="Int64")
    x = pd.to_numeric(sig, errors="coerce").to_numpy(dtype=float).reshape(1, -1)
    cuts = np.asarray(sorted(breakpoints.tolist()), dtype=float).reshape(1, -1)
    bins = _assign_bins_rows(x, cuts, n_bins)[0]
    return pd.Series(bins, index=sig.index, dtype="Int64")


def _align_bin_inputs(
    signal: pd.Series,
    nyse_flag: pd.Series | None,
    mcap: pd.Series | None,
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
    sig_vals = pd.to_numeric(signal, errors="coerce").to_numpy(dtype=float)
    nyse_vals = None
    if nyse_flag is not None and isinstance(nyse_flag.index, pd.MultiIndex):
        nyse_vals = _nyse_values(nyse_flag, signal.index)
    mcap_vals = None
    if mcap is not None and isinstance(mcap.index, pd.MultiIndex):
        mcap_vals = pd.to_numeric(mcap.reindex(signal.index), errors="coerce").to_numpy(
            dtype=float
        )
    return sig_vals, nyse_vals, mcap_vals


def _stack_bin_cols(
    sig_vals: np.ndarray,
    nyse_vals: np.ndarray | None,
    mcap_vals: np.ndarray | None,
) -> np.ndarray:
    cols = [sig_vals]
    if nyse_vals is not None:
        cols.append(nyse_vals)
    if mcap_vals is not None:
        cols.append(mcap_vals)
    return np.column_stack(cols) if len(cols) > 1 else sig_vals.reshape(-1, 1)


def _unpack_bin_mats(
    mat: np.ndarray,
    nyse_vals: np.ndarray | None,
    mcap_vals: np.ndarray | None,
) -> tuple[np.ndarray, np.ndarray | None, np.ndarray | None]:
    sig_mat = mat[:, :, 0]
    col = 1
    nyse_mat = None
    if nyse_vals is not None:
        nyse_mat = mat[:, :, col]
        col += 1
    mcap_mat = None
    if mcap_vals is not None:
        mcap_mat = mat[:, :, col]
    return sig_mat, nyse_mat, mcap_mat


def _bin_by_cross_section(
    signal: pd.Series,
    n_bins: int | Sequence[float],
    breaks: str,
    nyse_flag: pd.Series | None,
    mcap: pd.Series | None,
) -> pd.Series:
    """
    For each date, compute breakpoints and assign portfolios (1..n_bins).

    breaks: "name" | "NYSE" | "cap"

    Packs the long panel into a dates × slots matrix (ragged months
    NaN-padded) so breakpoints and assignment run as array operations
    rather than a Python loop over months.
    """
    if not isinstance(signal.index, pd.MultiIndex):
        raise ValueError("signal must be indexed by MultiIndex (date, permno).")

    n_bins_count = n_bins if isinstance(n_bins, int) else len(n_bins) + 1
    if len(signal) == 0:
        return pd.Series(pd.NA, index=signal.index, dtype="Int64")

    sig_vals, nyse_vals, mcap_vals = _align_bin_inputs(signal, nyse_flag, mcap)
    from ..session_cache import pack_column, pack_layout

    layout = pack_layout(signal.index)
    sig_mat = pack_column(sig_vals, layout, name=signal.name)
    nyse_mat = (
        pack_column(nyse_vals, layout, name=getattr(nyse_flag, "name", "nyse_flag"))
        if nyse_vals is not None
        else None
    )
    mcap_mat = (
        pack_column(mcap_vals, layout, name=getattr(mcap, "name", "mcap"))
        if mcap_vals is not None
        else None
    )
    date_codes = layout.group_codes
    within = layout.within
    cuts = _breakpoint_rows(sig_mat, n_bins, breaks, nyse_mat, mcap_mat)
    bins_mat = _assign_bins_rows(sig_mat, cuts, n_bins_count)
    return pd.Series(bins_mat[date_codes, within], index=signal.index, dtype="Int64")


def check_convention(convention: str) -> str:
    """``"capital"`` or ``"dollar"``, lower-cased; anything else raises.

    The convention is the size each leg of a long/short strategy is given at
    a trade: the strategy's capital K (``"capital"``) or $1 (``"dollar"``).
    """
    if not isinstance(convention, str) or convention.lower() not in CONVENTIONS:
        raise ValueError(
            f"convention must be 'capital' or 'dollar'; got {convention!r}"
        )
    return convention.lower()


@dataclass(frozen=True)
class HeldSort:
    """Held-leg portfolios of one sort, on the observed dates of the returns.

    ``leg_returns``, ``num_stocks`` and ``market_cap`` are dates x portfolios
    (columns ``1..n_ptfs``), as ``calc_ptf_rets`` returns them. ``costs`` is
    None unless half-spreads were given; its columns are ``cost``,
    ``turnover`` (both legs), ``cost_short``, ``cost_long``,
    ``turnover_short``, ``turnover_long`` (0 in a month without a trade),
    ``capital`` (the strategy's capital K in the trade months, NaN otherwise)
    and ``cost_exchanged`` (the cost of the same pair with its legs exchanged,
    which is the strategy held short; equal to ``cost`` under ``"dollar"``).
    The first purchase is not in ``costs``: ``entry_cost`` is its cost for the
    two legs together. ``ptf_costs`` and ``ptf_turnover`` (dates x
    portfolios) and ``entry_costs`` (per portfolio) are each portfolio's own
    cost, turnover and entry cost as a portfolio held by itself
    (``held_portfolio_costs``): under ``"dollar"`` the two legs' columns are
    the parts of the pair's cost; under ``"capital"`` each portfolio rolls its
    own value over, and they are not. All are None without half-spreads.
    ``restarts`` is the number of trades at which K was zero or negative and
    the strategy restarted with $1 in each leg (``convention="capital"``; 0
    under ``"dollar"``, which does not use K).
    """

    leg_returns: pd.DataFrame
    num_stocks: pd.DataFrame
    market_cap: pd.DataFrame
    costs: pd.DataFrame | None = None
    restarts: int = 0
    entry_cost: float | None = None
    entry_costs: pd.Series | None = None
    ptf_costs: pd.DataFrame | None = None
    ptf_turnover: pd.DataFrame | None = None


def calc_held_ptfs(
    returns: pd.Series,
    ind: pd.Series,
    mcap: pd.Series,
    tcosts: pd.Series | None = None,
    *,
    weighting: str = "v",
    n_ptfs: int | None = None,
    short: int = 1,
    long: int | None = None,
    convention: str = "dollar",
    label: str | None = None,
) -> HeldSort:
    """
    Held-leg portfolio returns and trading costs.

    Each portfolio is bought in a month in which ``ind`` assigns stocks and
    left alone until the next such month (see ``analytics/held.py`` for the
    calculation). ``convention`` is the size the two legs are given at a
    trade: the strategy's capital (``"capital"``) or $1 (``"dollar"``). The
    inputs are (date, permno) Series; ``ind``, ``mcap`` and ``tcosts`` are read
    on the index of ``returns``. ``tcosts`` holds decimal half-spreads; with
    it, the costs and turnover of ``long`` (default: the last portfolio) minus
    ``short`` are returned as well. ``label`` names the strategy in the
    warning logged when its capital is zero or negative at a trade.
    """
    _ensure_multiindex(returns, "returns")
    weighting = weighting.lower()
    if not (weighting.startswith("v") or weighting.startswith("e")):
        raise ValueError("weighting must be 'v' (value) or 'e' (equal)")
    convention = check_convention(convention)
    index = returns.index

    def values(obj: pd.Series, name: str) -> np.ndarray:
        _ensure_multiindex(obj, name)
        if obj.index is not index and not obj.index.equals(index):
            obj = obj.reindex(index)
        return pd.to_numeric(obj, errors="coerce").to_numpy(dtype=float, na_value=np.nan)

    ind_vals = np.nan_to_num(values(ind, "ind"))
    assigned = ind_vals > 0
    if not assigned.any():
        raise ValueError("ind must contain positive portfolio ids (1..K).")

    # The dense grid the core works on: a complete monthly calendar (a month
    # absent from the panel is an empty row) by the stocks that are ever
    # assigned. Rows and columns are found from the labels, never by position.
    date_codes, out_index, date_months = _date_codes_and_months(index.get_level_values(0))
    obs_rows = date_months - date_months[0]
    stock_codes, stocks = pd.factorize(index.get_level_values(1))
    ever = np.bincount(stock_codes[assigned], minlength=len(stocks)) > 0
    keep = ever[stock_codes]
    rows = obs_rows[date_codes[keep]]
    cols = (np.cumsum(ever) - 1)[stock_codes[keep]]
    shape = (int(obs_rows[-1]) + 1, int(ever.sum()))
    cell = np.full(shape, -1, dtype=np.int64)
    cell[rows, cols] = np.arange(rows.size)
    if (cell[rows, cols] != np.arange(rows.size)).any():
        raise ValueError("returns has duplicate (date, permno) keys")
    del cell

    def grid(vals: np.ndarray, fill: float = np.nan) -> np.ndarray:
        out = np.full(shape, fill)
        out[rows, cols] = vals[keep]
        return out

    with_costs = tcosts is not None
    legs = held_legs(
        grid(returns.to_numpy(dtype=float, na_value=np.nan)),
        grid(values(mcap, "mcap")),
        grid(values(tcosts, "tcosts")) if with_costs else np.zeros(shape),
        grid(ind_vals, 0.0),
        "v" if weighting.startswith("v") else "e",
        n_ptfs=n_ptfs,
    )
    ptf_ids = range(1, legs.n_ptfs + 1)

    def frame(arr: np.ndarray) -> pd.DataFrame:
        return pd.DataFrame(arr[obs_rows], index=out_index, columns=ptf_ids)

    costs = None
    restarts = 0
    entry_cost = entry_costs = ptf_costs = ptf_turnover = None
    if with_costs:
        own = held_portfolio_costs(legs, convention=convention)
        entry_costs = pd.Series(own.entry_cost, index=list(ptf_ids), dtype=float)
        ptf_costs, ptf_turnover = frame(own.cost), frame(own.turnover)
    if with_costs and legs.n_ptfs >= 2:
        ls = held_long_short(legs, short=short, long=long, convention=convention, label=label)
        entry_cost = ls.entry_cost
        costs = pd.DataFrame(
            {
                "cost": ls.cost,
                "turnover": ls.turnover,
                "cost_short": ls.cost_short,
                "cost_long": ls.cost_long,
                "turnover_short": ls.turnover_short,
                "turnover_long": ls.turnover_long,
                "capital": ls.capital,
                "cost_exchanged": ls.cost_exchanged,
            }
        ).iloc[obs_rows].set_axis(out_index)
        if convention == "capital":
            restarts = int((ls.capital <= 0).sum())  # NaN compares False
    return HeldSort(
        leg_returns=frame(legs.ret),
        num_stocks=frame(legs.n_stocks),
        market_cap=frame(legs.mcap),
        costs=costs,
        restarts=restarts,
        entry_cost=entry_cost,
        entry_costs=entry_costs,
        ptf_costs=ptf_costs,
        ptf_turnover=ptf_turnover,
    )


def run_univariate_sort(
    returns: pd.Series,
    signal: pd.Series,
    mcap: pd.Series,
    *,
    n_bins: int | Sequence[float] = 5,
    breaks: str = "name",
    nyse_flag: pd.Series | None = None,
    portfolio_mass: pd.Series | None = None,
    weighting: str = "v",
    holding_period: int = 1,
    time_period: tuple[int, int] | None = None,
    add_long_short: bool = True,
    factor_model: int | pd.DataFrame | None = None,
    factors: pd.DataFrame | None = None,
    tcosts: float | pd.Series | None = None,
    robust_se: bool = False,
    print_results: bool = False,
    plot_results: bool = False,
    convention: str = "dollar",
) -> SortResult:
    """
    Univariate sort (MATLAB runUnivSort) on held portfolios.

    Each portfolio is bought in a month in which the signal has values and is
    left alone until the next such month: positions grow with the stocks'
    returns, the long-short return is the long leg's return minus the short
    leg's, each on its own value, and trading costs are those of the trades
    that move the two legs from what they hold to the new targets
    (``analytics/held.py``). **The data decide when the portfolios trade:** a
    signal with values every month is sorted and traded every month, which
    gives the returns of monthly rebalanced portfolios; a signal with values
    each June is sorted and traded each June and held for the year.

    ``convention`` sets the size of the two legs after a trade: each back at
    $1 (``"dollar"``, the default) or both at the strategy's capital
    (``"capital"``). It changes the trading costs and the turnover, not the
    gross returns. Under ``"dollar"`` the cost is the same whichever leg is
    long; under ``"capital"`` it is not.

    Parameters
    ----------
    returns : pd.Series
        Stock returns, MultiIndex (date, permno). Month t returns.
    signal : pd.Series
        Sorting variable, MultiIndex (date, permno). Pass contemporaneous values
        (e.g., df["me"] for size sort). Portfolios are formed on the month-t
        signal and returns accrue from month t+1 (`calc_ptf_rets` lags the
        assignment by one month, mirroring MATLAB `makeUnivSortInd` +
        `calcPtfRets`).
    mcap : pd.Series
        Market capitalization, MultiIndex (date, permno).
        Used for value-weighting (weighting='v') and cap-weighted breaks (breaks='cap').
        `calc_ptf_rets` lags it by 1 month internally (prior-month weights).
    n_bins : int or Sequence[float]
        Number of portfolios (e.g., 5 for quintiles) or explicit percentile cutoffs.
    breaks : str
        Breakpoint method:
          - "name": equal number of stocks per bin (default)
          - "NYSE": equal number of NYSE stocks per bin (requires nyse_flag)
          - "cap": equal total market cap per bin
    nyse_flag : pd.Series, optional
        Boolean indicator for NYSE stocks, required if breaks="NYSE".
    portfolio_mass : pd.Series, optional
        Portfolio-mass Series used to compute equal-mass breakpoint assignment when
        breaks="cap". If omitted, defaults to `mcap`.
    weighting : str
        Portfolio weighting: "v" (value-weight by mcap, default) or "e" (equal-weight).
    holding_period : int
        Holding period in months (1 = no overlap, >1 = each leg holds the
        union of the last ``holding_period`` monthly formations). With a
        value above 1 the portfolios are not held legs: every month each leg
        earns the return of fresh target weights over that union
        (``calc_ptf_rets``). Gross returns only: a per-stock ``tcosts`` panel
        with ``holding_period > 1`` raises ``ValueError``.
    time_period : tuple[int, int], optional
        (start, end) dates to subset the sample.
    add_long_short : bool
        Whether to compute long-short (top - bottom) portfolio.
    factor_model : int or pd.DataFrame, optional
        Factor model: 1 (CAPM), 3 (FF3), 4 (FF4), 5 (FF5), 6 (FF6),
        or a custom DataFrame of factors. If int, the model's columns come
        from ``factors`` when supplied, otherwise from the database.
    factors : pd.DataFrame, optional
        Explicit factor store (date index; ``mkt``/``mktrf``, ``smb``,
        ``hml``, ``mom``/``umd``, ``smb2``, ``rmw``, ``cma``, ``rf`` as
        needed). An integer ``factor_model`` selects its columns and the
        risk-free rate from this frame by name and never opens a database.
        Ignored when ``factor_model`` is a DataFrame or None.
    tcosts : float or pd.Series, optional
        Trading costs. A scalar or date-indexed Series is subtracted from the
        long-short return as is. A (date, permno)-indexed Series holds
        stock-level decimal effective half-spreads and is priced on the legs'
        trades. The first purchase is reported separately (``entry_cost``)
        and is not in the cost series. Not available with
        ``holding_period > 1``.
    robust_se : bool, default False
        If True, use White heteroskedasticity-robust standard errors for
        factor regressions. If False (default), use classical OLS standard
        errors (matching MATLAB).
    print_results : bool, default False
        If True, print MATLAB-style summary table after computing results.
    plot_results : bool, default False
        If True, display 4-panel strategy figure (cumulative returns in logs,
        5-year rolling Sharpe, # stocks over time, annual returns bar chart).
    convention : str, default "dollar"
        ``"capital"`` or ``"dollar"`` (see above).

    Returns
    -------
    SortResult
        Contains leg_returns, long_short, alphas, tstats, etc. With a
        per-stock ``tcosts`` panel, ``tcosts_ts`` is the cost of the two
        extreme legs in each month (0 in a month without a trade) and
        ``netpret = long_short - tcosts_ts``.
        ``ptf_costs`` and ``ptf_to`` are each portfolio's own cost and
        turnover as a portfolio held by itself (0 in a month without a trade):
        under ``"dollar"`` every portfolio goes back to $1 at a trade, so the
        two extreme columns add up to ``tcosts_ts``; under ``"capital"`` each
        portfolio rolls its own value over, and they do not (the pair's legs
        are both set to the strategy's capital). ``to_ts`` is the turnover
        of the two extreme legs as legs of the pair.
        ``tcosts`` and ``turnover`` average over the months in which the
        long-short portfolio has a return, so that the mean gross return less
        ``tcosts`` is the mean net return; ``entry_cost`` is the cost of the
        first purchase of the two extreme legs (a decimal, per $1 in each
        leg; ``ptf_entry_costs`` has it for every portfolio), which is in
        none of the series or averages above; ``tcosts_ts_short`` is, under
        ``"capital"`` only, the cost of the strategy held short (the same two
        portfolios with the legs exchanged; None under ``"dollar"``, where
        that is ``tcosts_ts``), which ``calc_gen_alpha`` takes as
        ``anom_tcosts_short``; and
        ``metadata["capital_restarts"]`` counts the trades at which the
        strategy's capital was zero or negative (``"capital"`` only).
    """
    # MATLAB-style input validation (mirrors `runUnivSort.m` input parsing).
    if not isinstance(weighting, str) or weighting not in ("V", "v", "E", "e"):
        raise ValueError(
            f"weighting must be one of 'V', 'v', 'E', 'e'; got {weighting!r}"
        )
    if (
        factor_model is not None
        and isinstance(factor_model, (int, np.integer))
        and int(factor_model) not in (1, 3, 4, 5, 6)
    ):
        raise ValueError("Factor model must be 1, 3, 4, 5, 6, or a user-defined matrix.")
    weighting = weighting.lower()
    convention = check_convention(convention)
    if (
        isinstance(holding_period, bool)
        or not isinstance(holding_period, (int, np.integer))
        or holding_period < 1
    ):
        raise ValueError(f"holding_period must be a positive integer; got {holding_period!r}")

    _ensure_multiindex(returns, "returns")
    _ensure_multiindex(signal, "signal")
    _ensure_multiindex(mcap, "mcap")
    if portfolio_mass is not None:
        _ensure_multiindex(portfolio_mass, "portfolio_mass")
    if nyse_flag is not None:
        _ensure_multiindex(nyse_flag, "nyse_flag")

    # MATLAB semantics (`makeUnivSortInd` + `runUnivSort`/`calcPtfRets`):
    # the portfolio indicator is computed on *contemporaneous* signals over all
    # stocks with a finite signal (subject only to the breakpoint filter);
    # `calc_ptf_rets` then applies the single one-month lag (formation at t,
    # returns at t+1) and requires finite return and finite lagged market cap.
    mass = portfolio_mass if portfolio_mass is not None else mcap

    df = pd.concat({"ret": returns, "signal": signal, "mcap": mcap}, axis=1)

    # Optional date filtering (accepts YYYYMM integers, Timestamps, a scalar
    # sample start, or a (start, end) pair; raises ValueError on malformed
    # values like 1963). Mirrors MATLAB `runUnivSort`, which subsets rows
    # *before* `calcPtfRets` lags, so the first month of the window has no
    # positions.
    if time_period is not None:
        df = df[_time_mask(df.index, time_period)]

    n_bins_count = n_bins if isinstance(n_bins, int) else len(n_bins) + 1

    bins = _bin_by_cross_section(
        df["signal"],
        n_bins,
        breaks=breaks,
        nyse_flag=nyse_flag,
        mcap=mass,
    )
    ind = bins.reindex(df.index).fillna(0)

    if int(pd.to_numeric(ind, errors="coerce").max() or 0) <= 0:
        raise ValueError("No data available after filtering/NaN removal.")

    # Trading costs. A per-stock tcost panel (Series indexed by (date, permno))
    # is priced on the legs' trades; a scalar or date-indexed Series is simply
    # subtracted from the long-short return (legacy behavior).
    per_stock_tcosts = (
        tcosts is not None
        and isinstance(tcosts, (pd.Series, pd.DataFrame))
        and isinstance(tcosts.index, pd.MultiIndex)
    )

    if per_stock_tcosts and holding_period > 1:
        raise ValueError(
            f"Trading costs are not available with holding_period={holding_period}: "
            "per-stock costs are those of held legs, which are bought at a trade and "
            "left alone until the next one, and overlapping holdings are not held "
            "legs. Use holding_period=1 with the cost panel, or drop tcosts to get "
            "the gross returns of the overlapping portfolios."
        )

    held: HeldSort | None = None
    if holding_period == 1:
        tc_panel = None
        if per_stock_tcosts and add_long_short and n_bins_count >= 2:
            tc_panel = tcosts.iloc[:, 0] if isinstance(tcosts, pd.DataFrame) else tcosts
            tc_panel = tc_panel.reindex(df.index).astype(float)
        held = calc_held_ptfs(
            df["ret"], ind, df["mcap"], tc_panel,
            weighting=weighting, n_ptfs=n_bins_count, convention=convention,
            label=None if signal.name is None else str(signal.name),
        )
        leg_ts, ptf_counts, ptf_mcap = held.leg_returns, held.num_stocks, held.market_cap
    else:
        # Overlapping holdings: fresh target weights over the union of the
        # last `holding_period` formations, every month. Gross returns only.
        leg_ts, ptf_counts, ptf_mcap = calc_ptf_rets(
            df["ret"], ind, df["mcap"], holding_period=holding_period, weighting=weighting
        )
    leg_ts = leg_ts.reindex(columns=range(1, n_bins_count + 1))
    ptf_counts = ptf_counts.reindex(columns=range(1, n_bins_count + 1))
    ptf_mcap = ptf_mcap.reindex(columns=range(1, n_bins_count + 1))

    long_short = None
    if add_long_short and leg_ts.shape[1] >= 2:
        long_short = leg_ts[n_bins_count] - leg_ts[1]

    long_short_net = None
    if long_short is not None and tcosts is not None and not per_stock_tcosts:
        if np.isscalar(tcosts):
            long_short_net = long_short - float(tcosts)
        else:
            tcosts_aligned = pd.Series(tcosts).reindex(long_short.index)
            long_short_net = long_short - tcosts_aligned

    pret_all = leg_ts.copy()
    if long_short is not None:
        pret_all["long_short"] = long_short

    alphas = tstats = factor_loadings = factor_loading_tstats = r2 = None
    xret = txret = alpha = talpha = sharpe = info = resid = r2_adj = None
    if factor_model is not None:
        factor_df = _resolve_factor_model(pret_all.index, factor_model, factors=factors)
        ls_for_regs = (
            long_short
            if long_short is not None
            else pd.Series(index=pret_all.index, dtype="float64")
        )
        alphas, tstats, factor_loadings, factor_loading_tstats, r2 = _run_factor_regs(
            leg_ts, ls_for_regs, factor_df, robust=robust_se
        )
        if long_short is None:
            # Drop the placeholder long-short row.
            alphas = alphas.drop(index=["long_short"], errors="ignore")
            tstats = tstats.drop(index=["long_short"], errors="ignore")
            factor_loadings = factor_loadings.drop(index=["long_short"], errors="ignore")
            factor_loading_tstats = factor_loading_tstats.drop(
                index=["long_short"], errors="ignore"
            )
            r2 = r2.drop(index=["long_short"], errors="ignore")
        stats = _matlab_style_sort_outputs(
            pret_all,
            factors=factor_df,
            robust_se=robust_se,
            input_is_excess=False,
        )
        xret = stats["xret"]
        txret = stats["txret"]
        alpha = stats["alpha"]
        talpha = stats["talpha"]
        sharpe = stats["sharpe"]
        info = stats["info"]
        resid = stats["resid"]
        r2_adj = stats["r2_adj"]

    # Per-stock trading-cost block: the held legs' trades.
    tcosts_ts = netpret = to_ts = ptf_costs = ptf_to = None
    netxret = tnetxret = turnover = tcosts_avg = None
    entry_cost = ptf_entry_costs = tcosts_ts_short = None
    if held is not None and held.costs is not None:
        if convention == "capital":
            tcosts_ts_short = held.costs["cost_exchanged"].rename(None)
        entry_cost = held.entry_cost
        ptf_entry_costs = held.entry_costs.reindex(leg_ts.columns)
        c = held.costs
        first, last = 1, n_bins_count
        # Zeros in months without a trade (and outside the strategy's life),
        # so that netpret == long_short - tcosts_ts wherever there is a return.
        tcosts_ts = c["cost"].rename(None)
        netpret = long_short - tcosts_ts
        nr = nanols(100 * netpret, np.ones(len(netpret)))
        ptf_costs = held.ptf_costs.reindex(columns=leg_ts.columns)
        ptf_to = held.ptf_turnover.reindex(columns=leg_ts.columns)
        to_ts = pd.DataFrame({first: c["turnover_short"], last: c["turnover_long"]})
        netxret = float(nr.beta[0])
        tnetxret = float(nr.tstat[0])
        # Averages over the months the long-short portfolio has a return.
        live = long_short.notna().to_numpy()
        if live.any():
            turnover = float(c["turnover"].to_numpy()[live].mean() / 4)
            tcosts_avg = float(tcosts_ts.to_numpy()[live].mean())
        else:
            turnover = tcosts_avg = float("nan")
        long_short_net = netpret

    if factor_model is None:
        factor_model_label = None
    elif np.isscalar(factor_model):
        factor_model_label = factor_model
    else:
        factor_model_label = "user-defined"

    meta = {
        "n_bins": n_bins_count,
        "breaks": breaks.lower(),
        "weighting": weighting,
        "holding_period": holding_period,
        "add_long_short": add_long_short,
        "factor_model": factor_model_label,
        "tcosts": tcosts,
        "convention": convention,
    }
    if held is not None and held.costs is not None:
        meta["capital_restarts"] = held.restarts
    result = SortResult(
        leg_returns=leg_ts,
        long_short=long_short,
        metadata=meta,
        long_short_net=long_short_net,
        xret=xret,
        txret=txret,
        alpha=alpha,
        talpha=talpha,
        sharpe=sharpe,
        info=info,
        resid=resid,
        alphas=alphas,
        tstats=tstats,
        factor_loadings=factor_loadings,
        factor_loading_tstats=factor_loading_tstats,
        r2=r2,
        r2_adj=r2_adj,
        ptf_num_stocks=ptf_counts,
        ptf_market_cap=ptf_mcap,
        tcosts_ts=tcosts_ts,
        netpret=netpret,
        to_ts=to_ts,
        netxret=netxret,
        tnetxret=tnetxret,
        turnover=turnover,
        tcosts=tcosts_avg,
        ptf_costs=ptf_costs,
        ptf_to=ptf_to,
        entry_cost=entry_cost,
        ptf_entry_costs=ptf_entry_costs,
        tcosts_ts_short=tcosts_ts_short,
    )

    if print_results:
        result.print_results()

    if plot_results and result.long_short is not None:
        result.plot_results()

    return result


def _ensure_multiindex(series: pd.Series, name: str) -> None:
    if not isinstance(series.index, pd.MultiIndex):
        raise ValueError(f"{name} must be indexed by MultiIndex (date, permno)")


def load_factors(db_path: str | Path | None = None) -> pd.DataFrame:
    """
    Load Fama-French factors from the database.
    
    Returns a DataFrame indexed by end-of-month date with columns:
    mkt, smb, hml, rf, mom, smb2, rmw, cma (where available).
    smb2 is the five-factor SMB, used by factor models 5 and 6.
    
    This function can be used by univariate_sort, bivariate_sort, or standalone.

    Results are cached per ``(database, sample_start, sample_end)`` for the
    rest of the process; callers receive a copy so in-place edits cannot
    poison a later sort.
    """
    from ..session_cache import db_sample_key, get_cached_factors, put_cached_factors

    key = db_sample_key(db_path)
    cached = get_cached_factors(key)
    if cached is not None:
        return cached

    from ..config import load_config
    
    if db_path is None:
        cfg = load_config()
        db_path = cfg.database_path

    # Load from the canonical time-series store.
    cols = {"date": "date", "mktrf": "mktrf", "smb": "smb", "hml": "hml", "rf": "rf", "umd": "umd", "smb2": "smb2", "rmw": "rmw", "cma": "cma"}
    try:
        factors = aa_load(
            cols,
            path=db_path,
            panel=False,
            table="ts_data",
            common_shares_only=False,
        )
    except Exception:
        # Older databases predate smb2; retry without it (models 5/6 will
        # raise a helpful error in _resolve_factor_model).
        cols.pop("smb2")
        factors = aa_load(
            cols,
            path=db_path,
            panel=False,
            table="ts_data",
            common_shares_only=False,
        )

    # Normalize to end-of-month date index
    factors.index = pd.to_datetime(factors.index) + pd.offsets.MonthEnd(0)
    
    # Rename to standard names
    rename_map = {"mktrf": "mkt", "umd": "mom"}
    factors = factors.rename(columns={k: v for k, v in rename_map.items() if k in factors.columns})
    
    return put_cached_factors(key, factors)


# Factor model code -> required columns.
# Models 5 and 6 use the five-factor SMB (smb2), like MATLAB `estFactorRegs`
# (`ff.mat` keeps both; the FF5/FF6 regressions load smb2). It is renamed to
# "smb" in the resolved DataFrame so loadings keep the conventional label.
FACTOR_MODEL_COLS = {
    1: ["mkt"],
    3: ["mkt", "smb", "hml"],
    4: ["mkt", "smb", "hml", "mom"],
    5: ["mkt", "smb2", "hml", "rmw", "cma"],
    6: ["mkt", "smb2", "hml", "rmw", "cma", "mom"],
}


# WRDS column names that a raw factor frame may carry -> canonical names.
_FACTOR_ALIASES = {"mktrf": "mkt", "umd": "mom"}


def _canonical_factor_names(factors: pd.DataFrame) -> pd.DataFrame:
    """Rename WRDS aliases (``mktrf``, ``umd``) unless the canonical column exists.

    Renaming only when the canonical name is absent means a frame carrying both
    spellings never ends up with two ``mkt`` columns.
    """
    rename = {
        k: v for k, v in _FACTOR_ALIASES.items()
        if k in factors.columns and v not in factors.columns
    }
    return factors.rename(columns=rename)


def _select_model_factors(
    factors: pd.DataFrame,
    factor_model: int,
    *,
    explicit: bool,
) -> pd.DataFrame:
    """Pick model ``factor_model``'s columns (plus ``rf``) from a factor store by name.

    ``smb2`` is renamed to ``smb`` in the output so loadings keep the
    conventional label, but a store without ``smb2`` is never served ``smb``
    in its place (nor the reverse).
    """
    factors = _canonical_factor_names(factors)
    cols = FACTOR_MODEL_COLS[factor_model]
    missing = [c for c in cols if c not in factors.columns]
    if missing:
        hint = (
            "Add them to the explicit factors frame; smb and smb2 are not "
            "substituted for each other."
            if explicit
            else "You may need to re-run the factor fetch stage to get rmw/cma."
        )
        raise ValueError(f"Missing factor columns for model {factor_model}: {missing}. {hint}")

    df = factors[cols].copy()
    if "smb2" in df.columns:
        df = df.rename(columns={"smb2": "smb"})
    if "rf" in factors.columns:
        df["rf"] = factors["rf"]
    return df


def _resolve_factor_model(
    index: pd.Index,
    factor_model: int | pd.DataFrame,
    db_path: str | Path | None = None,
    *,
    factors: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Resolve factor_model to a DataFrame of factors aligned to the given index.

    If factor_model is a DataFrame, use it directly.
    If factor_model is an int (1/3/4/5/6), select that model's columns from
    ``factors`` when it is supplied, and only otherwise load them from the
    database (``load_factors(db_path)``, the interactive default). Once an
    explicit ``factors`` frame is passed, no database is opened.
    """
    if isinstance(factor_model, pd.DataFrame):
        # User provided custom factors; rename if needed and align
        return _canonical_factor_names(factor_model.copy()).reindex(index)

    if factor_model not in FACTOR_MODEL_COLS:
        raise ValueError("factor_model must be one of 1, 3, 4, 5, 6 or a DataFrame.")

    if factors is not None:
        df = _select_model_factors(factors, int(factor_model), explicit=True)
    else:
        df = _select_model_factors(load_factors(db_path), int(factor_model), explicit=False)
    return df.reindex(index)


def _run_factor_regs(
    leg_ts: pd.DataFrame,
    long_short: pd.Series,
    factors: pd.DataFrame,
    robust: bool = False,
    input_is_excess: bool = False,
) -> tuple[pd.Series, pd.Series, pd.DataFrame, pd.DataFrame, pd.Series]:
    """Run OLS of portfolio excess returns on factors.

    Parameters
    ----------
    robust : bool, default False
        If True, use White heteroskedasticity-robust standard errors.
        If False (default), use classical OLS standard errors.

    Returns
    -------
    alphas, tstats, loadings, loading_tstats, r2
    """
    if factors.empty:
        raise ValueError("Factors DataFrame is empty.")

    def excess(ret: pd.Series, *, already_excess: bool) -> pd.Series:
        if already_excess:
            return ret
        if "rf" in factors.columns:
            return ret - factors["rf"]
        return ret

    aligned_factors = factors.drop(columns=["rf"], errors="ignore")
    alphas = {}
    tstats = {}
    loadings = []
    loading_tstats = []
    r2 = {}

    all_series = leg_ts.copy()
    all_series["long_short"] = long_short

    for col, series in all_series.items():
        # Long-short is self-financing; rf cancels, so it is already excess.
        already_excess = input_is_excess or (col == "long_short")
        y = excess(series, already_excess=already_excess).dropna()
        X = aligned_factors.reindex(y.index).dropna()
        common_idx = y.index.intersection(X.index)
        y = y.reindex(common_idx)
        X = X.reindex(common_idx)
        if X.empty or y.empty:
            alphas[col] = np.nan
            tstats[col] = np.nan
            r2[col] = np.nan
            loadings.append(pd.Series(dtype=float, name=col))
            loading_tstats.append(pd.Series(dtype=float, name=col))
            continue
        const = np.ones(len(y))
        X_mat = np.column_stack([const, X.to_numpy()])
        beta, tstat_vec, r2_val = _ols(y.to_numpy(), X_mat, robust=robust)
        alphas[col] = beta[0]
        tstats[col] = tstat_vec[0]
        r2[col] = r2_val
        loading = pd.Series(beta[1:], index=aligned_factors.columns, name=col)
        loading_t = pd.Series(tstat_vec[1:], index=aligned_factors.columns, name=col)
        loadings.append(loading)
        loading_tstats.append(loading_t)

    loadings_df = (
        pd.concat(loadings, axis=1).T if loadings else pd.DataFrame(columns=aligned_factors.columns)
    )
    loading_tstats_df = (
        pd.concat(loading_tstats, axis=1).T if loading_tstats else pd.DataFrame(columns=aligned_factors.columns)
    )
    return (
        pd.Series(alphas),
        pd.Series(tstats),
        loadings_df,
        loading_tstats_df,
        pd.Series(r2),
    )


def _ols(
    y: np.ndarray, X: np.ndarray, robust: bool = False
) -> tuple[np.ndarray, np.ndarray, float]:
    """OLS regression with classical or White robust standard errors.

    Parameters
    ----------
    y : array
        Dependent variable (n,).
    X : array
        Regressors including constant (n, k).
    robust : bool, default False
        If True, use White heteroskedasticity-robust standard errors.
        If False (default), use classical OLS standard errors (matching MATLAB).

    Returns
    -------
    beta : array
        Coefficient estimates (k,).
    tstats : array
        t-statistics (k,).
    r2 : float
        R-squared.
    """
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n, k = X.shape
    if n <= k:
        return beta, np.full_like(beta, np.nan), np.nan

    XtX_inv = np.linalg.inv(X.T @ X)

    if robust:
        # White heteroskedasticity-robust: (X'X)^-1 * X' diag(e^2) X * (X'X)^-1
        meat = np.zeros((k, k))
        for i in range(n):
            xi = X[i : i + 1].T
            meat += resid[i] ** 2 * (xi @ xi.T)
        cov = XtX_inv @ meat @ XtX_inv
        se = np.sqrt(np.diag(cov))
    else:
        # Classical OLS: Var(beta) = sigma^2 * (X'X)^-1
        sigma2 = (resid @ resid) / (n - k)
        se = np.sqrt(sigma2 * np.diag(XtX_inv))

    tstats = beta / se

    # R-squared
    y_mean = y.mean()
    ss_tot = ((y - y_mean) ** 2).sum()
    ss_res = (resid**2).sum()
    r2 = 1 - ss_res / ss_tot if ss_tot != 0 else np.nan

    return beta, tstats, r2


def _matlab_style_sort_outputs(
    pret: pd.DataFrame,
    *,
    factors: pd.DataFrame,
    robust_se: bool,
    input_is_excess: bool,
) -> dict[str, Any]:
    """
    Compute MATLAB `estFactorRegs.m`-style outputs for a matrix of portfolio returns.

    Returns a dict with:
    - xret/txret: mean excess returns (%/mo) and t-stats (constant-only regression)
    - alpha/talpha: alphas (%/mo) and t-stats (factor regression)
    - sharpe: annualized Sharpe ratio (sqrt(12) * mean(excess) / std(excess))
    - info: annualized information ratio (sqrt(12) * alpha / (100 * sqrt(sige)))
    - resid: residual time series (aligned to pret.index)
    - r2_adj: adjusted R^2

    Notes
    -----
    - If `factors` includes `rf`, excess returns are computed as (pret - rf) unless
      `input_is_excess=True`. A column named "long_short" is treated as excess
      regardless (rf cancels for self-financing strategies), matching MATLAB.
    """
    if pret.empty:
        return {
            "xret": pd.Series(dtype="float64"),
            "txret": pd.Series(dtype="float64"),
            "alpha": pd.Series(dtype="float64"),
            "talpha": pd.Series(dtype="float64"),
            "sharpe": pd.Series(dtype="float64"),
            "info": pd.Series(dtype="float64"),
            "resid": pd.DataFrame(index=pret.index),
            "r2_adj": pd.Series(dtype="float64"),
        }

    rf = factors["rf"] if "rf" in factors.columns else None
    X = factors.drop(columns=["rf"], errors="ignore")

    xret: dict[Any, float] = {}
    txret: dict[Any, float] = {}
    alpha: dict[Any, float] = {}
    talpha: dict[Any, float] = {}
    sharpe: dict[Any, float] = {}
    info: dict[Any, float] = {}
    r2_adj: dict[Any, float] = {}
    resid_cols: list[pd.Series] = []

    for col in pret.columns:
        y_raw = pd.to_numeric(pret[col], errors="coerce").astype(float)

        # MATLAB: ptfXRets = pret - rf (unless input is already excess). For the long-short
        # portfolio, rf cancels; it is already excess.
        already_excess = bool(input_is_excess) or (str(col) == "long_short")
        y_ex = y_raw.copy()
        if (not already_excess) and (rf is not None):
            y_ex = y_ex - rf.reindex(y_ex.index)

        mu, tmu = _matlab_mean_tstat(y_ex)
        xret[col] = mu * 100.0
        txret[col] = tmu

        yv = y_ex.dropna()
        if yv.empty:
            sharpe[col] = np.nan
        else:
            sd = float(yv.std(ddof=1))
            sharpe[col] = (np.sqrt(12.0) * float(yv.mean()) / sd) if sd != 0 else np.nan

        # Factor regression: excess returns on factors (with const).
        y = y_ex.dropna()
        Xc = X.reindex(y.index).dropna()
        idx = y.index.intersection(Xc.index)
        y = y.reindex(idx)
        Xc = Xc.reindex(idx)

        if y.empty or Xc.empty:
            alpha[col] = np.nan
            talpha[col] = np.nan
            info[col] = np.nan
            r2_adj[col] = np.nan
            resid_cols.append(pd.Series(index=pret.index, dtype="float64", name=col))
            continue

        n = int(len(y))
        k = int(Xc.shape[1] + 1)  # +1 for constant
        const = np.ones(n)
        X_mat = np.column_stack([const, Xc.to_numpy()])
        b, tvec, r2 = _ols(y.to_numpy(), X_mat, robust=robust_se)

        resid = y.to_numpy() - (X_mat @ b)
        dof = n - k
        sige = float((resid @ resid) / dof) if dof > 0 else np.nan

        # Alpha in %/mo (MATLAB multiplies by 100).
        alpha[col] = float(b[0]) * 100.0
        talpha[col] = float(tvec[0])

        # Annualized information ratio: sqrt(12) * alpha / (100 * sqrt(sige))
        if np.isfinite(sige) and sige > 0:
            info[col] = (np.sqrt(12.0) * alpha[col]) / (100.0 * np.sqrt(sige))
        else:
            info[col] = np.nan

        # Adjusted R^2 (MATLAB stores rbar).
        if np.isfinite(r2) and n > k and k > 1:
            r2_adj[col] = float(1.0 - (1.0 - r2) * (n - 1) / (n - k))
        else:
            r2_adj[col] = np.nan

        resid_s = pd.Series(resid, index=y.index, name=col)
        resid_cols.append(resid_s.reindex(pret.index))

    return {
        "xret": pd.Series(xret),
        "txret": pd.Series(txret),
        "alpha": pd.Series(alpha),
        "talpha": pd.Series(talpha),
        "sharpe": pd.Series(sharpe),
        "info": pd.Series(info),
        "resid": pd.concat(resid_cols, axis=1) if resid_cols else pd.DataFrame(index=pret.index),
        "r2_adj": pd.Series(r2_adj),
    }


def _n_bins_count(n_bins: int | Sequence[float]) -> int:
    return n_bins if isinstance(n_bins, int) else (len(n_bins) + 1)


def _conditional_bin_by_cross_section(
    signal2: pd.Series,
    bins1: pd.Series,
    *,
    n_bins2: int | Sequence[float],
    breaks: str,
    nyse_flag: pd.Series | None,
    mcap: pd.Series | None,
) -> pd.Series:
    """
    Conditional bivariate sort: for each date, bin signal2 *within* each bins1 group.

    Mirrors MATLAB `makeBivSortInd(..., sortType='conditional')` behavior.

    Groups are ``(date, bin1)`` rather than date: the same packed-matrix
    breakpoint / assign path as ``_bin_by_cross_section``, one row per
    within-bin cross-section.
    """
    if not isinstance(signal2.index, pd.MultiIndex) or not isinstance(bins1.index, pd.MultiIndex):
        raise ValueError("signal2 and bins1 must be MultiIndex (date, permno)")

    n2 = _n_bins_count(n_bins2)
    n = len(signal2)
    if n == 0:
        return pd.Series(pd.NA, index=signal2.index, dtype="Int64")

    b1_vals = pd.to_numeric(bins1.reindex(signal2.index), errors="coerce").to_numpy(
        dtype=float
    )
    valid = np.isfinite(b1_vals)
    out_vals = np.full(n, np.nan, dtype=np.float64)
    if not valid.any():
        return pd.Series(out_vals, index=signal2.index, dtype="Int64")

    date_codes, _ = pd.factorize(
        np.asarray(signal2.index.get_level_values(0)), sort=True
    )
    b1_int = np.where(valid, b1_vals, 0.0).astype(np.int64)
    stride = int(np.nanmax(b1_vals)) + 1
    group_keys = date_codes.astype(np.int64) * stride + b1_int

    idx = np.flatnonzero(valid)
    sig_vals, nyse_vals, mcap_vals = _align_bin_inputs(signal2, nyse_flag, mcap)
    stacked = _stack_bin_cols(
        sig_vals[idx],
        None if nyse_vals is None else nyse_vals[idx],
        None if mcap_vals is None else mcap_vals[idx],
    )
    mat, _, g_codes, within = _pack_by_group(stacked, group_keys[idx])
    sig_mat, nyse_mat, mcap_mat = _unpack_bin_mats(
        mat,
        None if nyse_vals is None else nyse_vals[idx],
        None if mcap_vals is None else mcap_vals[idx],
    )
    cuts = _breakpoint_rows(sig_mat, n_bins2, breaks, nyse_mat, mcap_mat)
    bins_mat = _assign_bins_rows(sig_mat, cuts, n2)
    out_vals[idx] = bins_mat[g_codes, within]
    return pd.Series(out_vals, index=signal2.index, dtype="Int64")


def run_bivariate_sort(
    returns: pd.Series,
    signal1: pd.Series,
    signal2: pd.Series,
    mcap: pd.Series,
    *,
    n_bins1: int | Sequence[float] = 5,
    n_bins2: int | Sequence[float] = 5,
    sort_type: str = "unconditional",
    breaks: str = "name",
    nyse_flag: pd.Series | None = None,
    portfolio_mass: pd.Series | None = None,
    weighting: str = "v",
    holding_period: int = 1,
    time_period: tuple[int, int] | None = None,
    factor_model: int | pd.DataFrame | None = None,
    factors: pd.DataFrame | None = None,
    tcosts: float | pd.Series | None = None,
    robust_se: bool = False,
    print_results: bool = False,
    plot_results: bool = False,
) -> BivariateSortResult:
    """
    Bivariate sort mirroring MATLAB `makeBivSortInd` + `runBivSort` (Pythonic API).

    Notes:
    - Portfolio assignment uses *contemporaneous* signals (month t), binned over
      all stocks with a finite signal — stocks with missing month-t returns are
      kept in the breakpoint cross-section, and the NYSE flag comes from the
      same month as the signals (MATLAB `makeBivSortInd`).
    - Portfolio returns use lagged membership/weights (month t+1) via
      `calc_ptf_rets`, which requires finite return and finite lagged market
      cap (even for equal-weighted legs) and implements holding_period > 1 as
      MATLAB's overlapping-membership union.
    - `sort_type='unconditional'` bins signal1 and signal2 independently each month.
    - `sort_type='conditional'` bins signal2 within signal1 bins each month.
    - An integer `factor_model` takes its columns and `rf` from `factors` when
      that frame is supplied (no database access), as in `run_univariate_sort`.
    """
    _ensure_multiindex(returns, "returns")
    _ensure_multiindex(signal1, "signal1")
    _ensure_multiindex(signal2, "signal2")
    _ensure_multiindex(mcap, "mcap")
    if nyse_flag is not None:
        _ensure_multiindex(nyse_flag, "nyse_flag")
    if portfolio_mass is not None:
        _ensure_multiindex(portfolio_mass, "portfolio_mass")

    sort_type = sort_type.lower()
    if sort_type not in ("unconditional", "conditional"):
        raise ValueError("sort_type must be 'unconditional' or 'conditional'")

    n1 = _n_bins_count(n_bins1)
    n2 = _n_bins_count(n_bins2)

    mass = portfolio_mass if portfolio_mass is not None else mcap

    df = pd.concat({"ret": returns, "s1": signal1, "s2": signal2, "mcap": mcap}, axis=1)

    # optional date filtering (supports YYYYMM integers or datetime); mirrors
    # MATLAB `runUnivSort`, which subsets rows *before* `calcPtfRets` lags.
    if time_period:
        start, end = time_period if len(time_period) == 2 else (time_period[0], time_period[0])
        dates = df.index.get_level_values(0)
        # Convert YYYYMM integers to month-end timestamps
        if start is not None and isinstance(start, int):
            start = pd.Timestamp(year=start // 100, month=start % 100, day=1) + pd.offsets.MonthEnd(0)
        if end is not None and isinstance(end, int):
            end = pd.Timestamp(year=end // 100, month=end % 100, day=1) + pd.offsets.MonthEnd(0)
        mask = pd.Series(True, index=df.index)
        if start is not None:
            mask &= dates >= start
        if end is not None:
            mask &= dates <= end
        df = df[mask]

    if df.empty:
        raise ValueError("No data available after filtering/NaN removal.")

    bins1 = _bin_by_cross_section(df["s1"], n_bins1, breaks=breaks, nyse_flag=nyse_flag, mcap=mass)
    if sort_type == "unconditional":
        bins2 = _bin_by_cross_section(df["s2"], n_bins2, breaks=breaks, nyse_flag=nyse_flag, mcap=mass)
    else:
        bins2 = _conditional_bin_by_cross_section(
            df["s2"],
            bins1,
            n_bins2=n_bins2,
            breaks=breaks,
            nyse_flag=nyse_flag,
            mcap=mass,
        )

    # Combine into MATLAB-style portfolio ids 1..n1*n2 (row-major: var1 first,
    # var2 second); a stock must be assigned on *both* dimensions (MATLAB
    # `makeBivSortInd` leaves ind = 0 otherwise).
    ind = (bins1.astype("Int64") - 1) * n2 + bins2.astype("Int64")
    ind = ind.reindex(df.index).fillna(0)

    if int(pd.to_numeric(ind, errors="coerce").max() or 0) <= 0:
        raise ValueError("No data available after filtering/NaN removal.")

    pret_flat, n_flat, m_flat = calc_ptf_rets(
        df["ret"], ind, df["mcap"], holding_period=holding_period, weighting=weighting
    )
    pret_flat = pret_flat.reindex(columns=range(1, n1 * n2 + 1))
    n_flat = n_flat.reindex(columns=range(1, n1 * n2 + 1))
    m_flat = m_flat.reindex(columns=range(1, n1 * n2 + 1))

    # Main (flattened) result, like MATLAB's Res from runUnivSort(..., addLongShort=0)
    alphas = tstats = loadings = loading_tstats = r2 = None
    xret = txret = alpha = talpha = sharpe = info = resid = r2_adj = None
    if factor_model is not None:
        # Portfolio legs are not excess returns: subtract rf if available.
        factor_df = _resolve_factor_model(pret_flat.index, factor_model, factors=factors)
        dummy_ls = pd.Series(index=pret_flat.index, dtype="float64")
        alphas, tstats, loadings, loading_tstats, r2 = _run_factor_regs(
            pret_flat, dummy_ls, factor_df, robust=robust_se
        )
        # Drop dummy long_short row
        alphas = alphas.drop(index=["long_short"], errors="ignore")
        tstats = tstats.drop(index=["long_short"], errors="ignore")
        loadings = loadings.drop(index=["long_short"], errors="ignore")
        loading_tstats = loading_tstats.drop(index=["long_short"], errors="ignore")
        r2 = r2.drop(index=["long_short"], errors="ignore")

        stats = _matlab_style_sort_outputs(
            pret_flat,
            factors=factor_df,
            robust_se=robust_se,
            input_is_excess=False,
        )
        xret = stats["xret"]
        txret = stats["txret"]
        alpha = stats["alpha"]
        talpha = stats["talpha"]
        sharpe = stats["sharpe"]
        info = stats["info"]
        resid = stats["resid"]
        r2_adj = stats["r2_adj"]

    flat = SortResult(
        leg_returns=pret_flat,
        long_short=None,
        metadata={
            "n_bins": n1 * n2,
            "n_bins1": n1,
            "n_bins2": n2,
            "sort_type": sort_type,
            "breaks": breaks.lower(),
            "weighting": weighting.lower(),
            "holding_period": holding_period,
            "factor_model": None if factor_model is None else str(factor_model),
        },
        xret=xret,
        txret=txret,
        alpha=alpha,
        talpha=talpha,
        sharpe=sharpe,
        info=info,
        resid=resid,
        alphas=alphas,
        tstats=tstats,
        factor_loadings=loadings,
        factor_loading_tstats=loading_tstats,
        r2=r2,
        r2_adj=r2_adj,
        ptf_num_stocks=n_flat,
        ptf_market_cap=m_flat,
    )

    # Reshape to (bin1, bin2) grid columns for convenience
    cols = pd.MultiIndex.from_tuples(
        [((k - 1) // n2 + 1, (k - 1) % n2 + 1) for k in pret_flat.columns],
        names=["bin1", "bin2"],
    )
    cell_returns = pret_flat.copy()
    cell_returns.columns = cols

    # Conditional long/short strategies computed from the grid (like MATLAB runBivSort.m)
    # var1 | var2: (high var1 - low var1) for each var2 bin
    cond1 = pd.DataFrame(index=pret_flat.index, columns=range(1, n2 + 1), dtype="float64")
    cond1_n = pd.DataFrame(index=pret_flat.index, columns=cond1.columns, dtype="float64")
    cond1_m = pd.DataFrame(index=pret_flat.index, columns=cond1.columns, dtype="float64")
    for j in range(1, n2 + 1):
        long_id = (n1 - 1) * n2 + j
        short_id = j
        cond1[j] = pret_flat[long_id] - pret_flat[short_id]
        cond1_n[j] = n_flat[long_id] + n_flat[short_id]
        cond1_m[j] = m_flat[long_id] + m_flat[short_id]

    # var2 | var1: (high var2 - low var2) for each var1 bin
    cond2 = pd.DataFrame(index=pret_flat.index, columns=range(1, n1 + 1), dtype="float64")
    cond2_n = pd.DataFrame(index=pret_flat.index, columns=cond2.columns, dtype="float64")
    cond2_m = pd.DataFrame(index=pret_flat.index, columns=cond2.columns, dtype="float64")
    for i in range(1, n1 + 1):
        long_id = (i - 1) * n2 + n2
        short_id = (i - 1) * n2 + 1
        cond2[i] = pret_flat[long_id] - pret_flat[short_id]
        cond2_n[i] = n_flat[long_id] + n_flat[short_id]
        cond2_m[i] = m_flat[long_id] + m_flat[short_id]

    c1_alphas = c1_tstats = c1_load = c1_load_t = c1_r2 = None
    c2_alphas = c2_tstats = c2_load = c2_load_t = c2_r2 = None
    c1_xret = c1_txret = c1_alpha = c1_talpha = c1_sharpe = c1_info = c1_resid = c1_r2_adj = None
    c2_xret = c2_txret = c2_alpha = c2_talpha = c2_sharpe = c2_info = c2_resid = c2_r2_adj = None
    if factor_model is not None:
        factor_df = _resolve_factor_model(cond1.index, factor_model, factors=factors)
        dummy_ls = pd.Series(index=cond1.index, dtype="float64")
        c1_alphas, c1_tstats, c1_load, c1_load_t, c1_r2 = _run_factor_regs(
            cond1, dummy_ls, factor_df, robust=robust_se, input_is_excess=True
        )
        c2_alphas, c2_tstats, c2_load, c2_load_t, c2_r2 = _run_factor_regs(
            cond2, dummy_ls, factor_df, robust=robust_se, input_is_excess=True
        )
        # Drop dummy long_short row
        c1_alphas = c1_alphas.drop(index=["long_short"], errors="ignore")
        c1_tstats = c1_tstats.drop(index=["long_short"], errors="ignore")
        c1_load = c1_load.drop(index=["long_short"], errors="ignore")
        c1_load_t = c1_load_t.drop(index=["long_short"], errors="ignore")
        c1_r2 = c1_r2.drop(index=["long_short"], errors="ignore")
        c2_alphas = c2_alphas.drop(index=["long_short"], errors="ignore")
        c2_tstats = c2_tstats.drop(index=["long_short"], errors="ignore")
        c2_load = c2_load.drop(index=["long_short"], errors="ignore")
        c2_load_t = c2_load_t.drop(index=["long_short"], errors="ignore")
        c2_r2 = c2_r2.drop(index=["long_short"], errors="ignore")

        c1_stats = _matlab_style_sort_outputs(
            cond1,
            factors=factor_df,
            robust_se=robust_se,
            input_is_excess=True,
        )
        c2_stats = _matlab_style_sort_outputs(
            cond2,
            factors=factor_df,
            robust_se=robust_se,
            input_is_excess=True,
        )
        c1_xret = c1_stats["xret"]
        c1_txret = c1_stats["txret"]
        c1_alpha = c1_stats["alpha"]
        c1_talpha = c1_stats["talpha"]
        c1_sharpe = c1_stats["sharpe"]
        c1_info = c1_stats["info"]
        c1_resid = c1_stats["resid"]
        c1_r2_adj = c1_stats["r2_adj"]

        c2_xret = c2_stats["xret"]
        c2_txret = c2_stats["txret"]
        c2_alpha = c2_stats["alpha"]
        c2_talpha = c2_stats["talpha"]
        c2_sharpe = c2_stats["sharpe"]
        c2_info = c2_stats["info"]
        c2_resid = c2_stats["resid"]
        c2_r2_adj = c2_stats["r2_adj"]

    cond_var1_given_var2 = SortResult(
        leg_returns=cond1,
        long_short=None,
        metadata={
            "n_bins": n2,
            "direction": "var1_given_var2",
            "breaks": breaks.lower(),
            "weighting": weighting.lower(),
            "holding_period": holding_period,
            "factor_model": None if factor_model is None else str(factor_model),
        },
        xret=c1_xret,
        txret=c1_txret,
        alpha=c1_alpha,
        talpha=c1_talpha,
        sharpe=c1_sharpe,
        info=c1_info,
        resid=c1_resid,
        alphas=c1_alphas,
        tstats=c1_tstats,
        factor_loadings=c1_load,
        factor_loading_tstats=c1_load_t,
        r2=c1_r2,
        r2_adj=c1_r2_adj,
        ptf_num_stocks=cond1_n,
        ptf_market_cap=cond1_m,
    )

    cond_var2_given_var1 = SortResult(
        leg_returns=cond2,
        long_short=None,
        metadata={
            "n_bins": n1,
            "direction": "var2_given_var1",
            "breaks": breaks.lower(),
            "weighting": weighting.lower(),
            "holding_period": holding_period,
            "factor_model": None if factor_model is None else str(factor_model),
        },
        xret=c2_xret,
        txret=c2_txret,
        alpha=c2_alpha,
        talpha=c2_talpha,
        sharpe=c2_sharpe,
        info=c2_info,
        resid=c2_resid,
        alphas=c2_alphas,
        tstats=c2_tstats,
        factor_loadings=c2_load,
        factor_loading_tstats=c2_load_t,
        r2=c2_r2,
        r2_adj=c2_r2_adj,
        ptf_num_stocks=cond2_n,
        ptf_market_cap=cond2_m,
    )

    out = BivariateSortResult(
        flat=flat,
        cell_returns=cell_returns,
        cond_var1_given_var2=cond_var1_given_var2,
        cond_var2_given_var1=cond_var2_given_var1,
        metadata={
            "n_bins1": n1,
            "n_bins2": n2,
            "sort_type": sort_type,
            "breaks": breaks.lower(),
            "weighting": weighting.lower(),
            "holding_period": holding_period,
            "factor_model": None if factor_model is None else str(factor_model),
            "tcosts": tcosts,
        },
    )

    if print_results:
        _print_bivariate_results_matlab_like(
            out,
            n1=n1,
            n2=n2,
            factor_model=factor_model,
            factors=factors,
            robust_se=robust_se,
        )

    if plot_results:
        _plot_bivariate_results_matlab_like(
            out,
            n1=n1,
            n2=n2,
            factor_model=factor_model,
        )

    return out


def _matlab_mean_tstat(x: pd.Series) -> tuple[float, float]:
    x = pd.to_numeric(x, errors="coerce").dropna()
    if x.empty:
        return np.nan, np.nan
    mu = float(x.mean())
    sd = float(x.std(ddof=1))
    n = int(x.shape[0])
    if sd == 0 or n <= 1:
        return mu, np.nan
    t = mu / (sd / np.sqrt(n))
    return mu, float(t)


def _factor_details(
    pret: pd.DataFrame,
    factors: pd.DataFrame,
    *,
    input_is_excess: bool,
    robust_se: bool,
) -> dict[str, Any]:
    """
    Build MATLAB-like quantities for prtSortResults + GRS:
    - xret/txret: mean excess returns and t-stats
    - alpha/talpha, loadings/t(loadings), residuals
    """
    aligned = factors.copy()
    rf = aligned["rf"] if "rf" in aligned.columns else None
    X = aligned.drop(columns=["rf"], errors="ignore")
    labels = list(X.columns)

    xret = {}
    txret = {}
    alpha = {}
    talpha = {}
    betas = {}
    tbetas = {}
    resid_cols = []

    for col in pret.columns:
        y_raw = pd.to_numeric(pret[col], errors="coerce")
        y = y_raw.copy()
        if (not input_is_excess) and rf is not None:
            y = y - rf.reindex(y.index)

        mu, tmu = _matlab_mean_tstat(y)
        xret[col] = mu
        txret[col] = tmu

        y = y.dropna()
        Xc = X.reindex(y.index).dropna()
        idx = y.index.intersection(Xc.index)
        y = y.reindex(idx)
        Xc = Xc.reindex(idx)
        if y.empty or Xc.empty:
            alpha[col] = np.nan
            talpha[col] = np.nan
            betas[col] = pd.Series({k: np.nan for k in labels})
            tbetas[col] = pd.Series({k: np.nan for k in labels})
            resid_cols.append(pd.Series(index=pret.index, dtype="float64", name=col))
            continue

        const = np.ones(len(y))
        X_mat = np.column_stack([const, Xc.to_numpy()])
        b, tvec, _r2 = _ols(y.to_numpy(), X_mat, robust=robust_se)
        alpha[col] = float(b[0])
        talpha[col] = float(tvec[0])
        betas[col] = pd.Series(b[1:], index=labels)
        tbetas[col] = pd.Series(tvec[1:], index=labels)
        resid = y.to_numpy() - (X_mat @ b)
        resid_s = pd.Series(resid, index=y.index, name=col)
        resid_cols.append(resid_s.reindex(pret.index))

    return {
        "xret": pd.Series(xret),
        "txret": pd.Series(txret),
        "alpha": pd.Series(alpha),
        "talpha": pd.Series(talpha),
        "betas": pd.DataFrame(betas).T if betas else pd.DataFrame(columns=labels),
        "tbetas": pd.DataFrame(tbetas).T if tbetas else pd.DataFrame(columns=labels),
        "resid": pd.concat(resid_cols, axis=1) if resid_cols else pd.DataFrame(index=pret.index),
        "labels": labels,
        "n_factors": len(labels),
    }


def _grs_test_like_matlab(details: dict[str, Any], factors: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Replicates `GRStest_p.m` outputs: pvals, Fstats, dfs (2x1, 2x1, 2x2).
    Uses SciPy if available for the F distribution survival function.
    """
    try:
        from scipy.stats import f as f_dist  # type: ignore
    except Exception:  # pragma: no cover
        f_dist = None

    resid = details["resid"].copy()
    alpha = details["alpha"].copy()
    xret = details["xret"].copy()

    # Align finite rows across resid and factor matrix
    X = factors.drop(columns=["rf"], errors="ignore")
    common = pd.concat([resid, X], axis=1).dropna()
    if common.empty:
        pvals = np.array([np.nan, np.nan])
        fstats = np.array([np.nan, np.nan])
        dfs = np.array([[np.nan, np.nan], [np.nan, np.nan]])
        return pvals, fstats, dfs

    resid_a = resid.loc[common.index]
    X_a = X.loc[common.index]
    alpha_a = alpha.reindex(resid_a.columns).astype(float).to_numpy()
    xret_a = xret.reindex(resid_a.columns).astype(float).to_numpy()

    n_ptfs = resid_a.shape[1]
    t = resid_a.shape[0]
    k = X_a.shape[1]

    # Full GRS
    df1_full = n_ptfs
    df2_full = t - n_ptfs - k
    Sigma_e = np.cov(resid_a.to_numpy(), rowvar=False)
    Sigma_f = np.atleast_2d(np.cov(X_a.to_numpy(), rowvar=False))  # ensure 2D when K=1
    Ef = X_a.mean(axis=0).to_numpy()
    try:
        numer = float(alpha_a.T @ np.linalg.inv(Sigma_e) @ alpha_a)
        denom = float(1.0 + Ef.T @ np.linalg.inv(Sigma_f) @ Ef) if k > 0 else 1.0
        F_full = (df2_full / df1_full) * (numer / denom)
    except Exception:  # pragma: no cover
        F_full = np.nan

    # Reduced GRS
    df1_red = n_ptfs
    df2_red = t - n_ptfs
    try:
        Sigma_r = np.cov((X_a.to_numpy() @ details["betas"].reindex(resid_a.columns).to_numpy().T + alpha_a + resid_a.to_numpy()), rowvar=False)
        numer2 = float(xret_a.T @ np.linalg.inv(Sigma_r) @ xret_a)
        F_red = (df2_red / df1_red) * numer2
    except Exception:  # pragma: no cover
        F_red = np.nan

    if f_dist is not None and np.isfinite(F_full) and df2_full > 0:
        p_full = float(f_dist.sf(F_full, df1_full, df2_full))
    else:
        p_full = np.nan
    if f_dist is not None and np.isfinite(F_red) and df2_red > 0:
        p_red = float(f_dist.sf(F_red, df1_red, df2_red))
    else:
        p_red = np.nan

    return (
        np.array([p_full, p_red]),
        np.array([F_full, F_red]),
        np.array([[df1_full, df2_full], [df1_red, df2_red]], dtype=float),
    )


def _print_prt_sort_results_like_matlab(
    *,
    title: str,
    weighting: str,
    holding_period: int,
    factor_model: int | pd.DataFrame | None,
    details: dict[str, Any],
    ls_label: bool = False,
) -> None:
    www = "Equally-weighted" if weighting.lower().startswith("e") else "Value-weighted"
    n_factors = int(details["n_factors"])
    if factor_model is None:
        mdl = "No factor model"
    elif isinstance(factor_model, int):
        mdl = "CAPM" if factor_model == 1 else f"Fama and French {n_factors}-factor model"
    else:
        mdl = f"User-defined {n_factors}-factor model"

    labels = details["labels"]
    cols = ["xret", "alpha", *labels]
    hdr = " " * 14 + "  ".join(f"{c:>8}" for c in cols)

    print("     ---------------------------------------------------------------------------- ")
    print(f"              {www} portfolio sort, {holding_period}-month holding period")
    print("              Excess returns, alphas, and loadings on:")
    print(f"              {mdl}")
    print(f"              {title}")
    print("     ---------------------------------------------------------------------------- ")
    print(hdr)

    xret = details["xret"] * 100
    txret = details["txret"]
    alpha = details["alpha"] * 100
    talpha = details["talpha"]
    betas = details["betas"]
    tbetas = details["tbetas"]

    for i, ptf in enumerate(xret.index, start=1):
        row_label = "L/S" if (ls_label and i == len(xret.index)) else str(ptf)
        vals = [xret.loc[ptf], alpha.loc[ptf]] + [betas.loc[ptf, c] for c in labels]
        tvals = [txret.loc[ptf], talpha.loc[ptf]] + [tbetas.loc[ptf, c] for c in labels]
        line1 = f"{row_label:>12}  " + "  ".join(f"{v:8.3f}" if pd.notna(v) else f"{'NaN':>8}" for v in vals)
        line2 = " " * 14 + "  ".join(f"[{t:5.2f}]" if pd.notna(t) else f"{'[ NaN]':>8}" for t in tvals)
        print(line1)
        print(line2)

    print("     ---------------------------------------------------------------------------- ")


def _print_bivariate_results_matlab_like(
    out: BivariateSortResult,
    *,
    n1: int,
    n2: int,
    factor_model: int | pd.DataFrame | None,
    factors: pd.DataFrame | None = None,
    robust_se: bool,
) -> None:
    factors = _resolve_factor_model(out.flat.leg_returns.index, factor_model, factors=factors) if factor_model is not None else pd.DataFrame(index=out.flat.leg_returns.index)

    # Full bivariate portfolios (flattened)
    if factor_model is not None:
        details_flat = _factor_details(out.flat.leg_returns, factors, input_is_excess=False, robust_se=robust_se)
        pvals, fstats, dfs = _grs_test_like_matlab(details_flat, factors)
        print("      GRS test results:  p-value     F-stat  df1  df2")
        print(f"      full test -        {pvals[0]} {fstats[0]}   {int(dfs[0,0])}   {int(dfs[0,1])}")
        print(f"      partial test -     {pvals[1]} {fstats[1]}   {int(dfs[1,0])}   {int(dfs[1,1])}")

        # Conditional strategies printed like MATLAB prtSortResults
        details_c1 = _factor_details(out.cond_var1_given_var2.leg_returns, factors, input_is_excess=True, robust_se=robust_se)
        details_c2 = _factor_details(out.cond_var2_given_var1.leg_returns, factors, input_is_excess=True, robust_se=robust_se)
        _print_prt_sort_results_like_matlab(
            title="Conditional strategies: High minus low var1, conditioned on var2",
            weighting=out.metadata["weighting"],
            holding_period=int(out.metadata["holding_period"]),
            factor_model=factor_model,
            details=details_c1,
        )
        _print_prt_sort_results_like_matlab(
            title="Conditional strategies: High minus low var2, conditioned on var1",
            weighting=out.metadata["weighting"],
            holding_period=int(out.metadata["holding_period"]),
            factor_model=factor_model,
            details=details_c2,
        )

        # Portfolio matrices
        xret_mat = (details_flat["xret"] * 100).to_numpy().reshape(n1, n2)
    else:
        # If no factor model, treat returns as "excess" for display purposes
        xret_mat = (out.flat.leg_returns.mean() * 100).to_numpy().reshape(n1, n2)

    print("Portfolio Average Excess Returns (%/month)")
    print("     ")
    print(pd.DataFrame(xret_mat).to_string(index=False, header=False))

    # Avg # firms and avg firm size
    n_mat = out.flat.ptf_num_stocks.mean().to_numpy().reshape(n1, n2) if out.flat.ptf_num_stocks is not None else np.full((n1, n2), np.nan)
    print("Portfolio Average Number of Firms")
    print("     ")
    n_tbl = pd.DataFrame(n_mat).astype(float).round(0)
    print(n_tbl.to_string(index=False, header=False))

    if out.flat.ptf_market_cap is not None and out.flat.ptf_num_stocks is not None:
        size_mat = (out.flat.ptf_market_cap / out.flat.ptf_num_stocks).mean().to_numpy().reshape(n1, n2) / 1e6
    else:
        size_mat = np.full((n1, n2), np.nan)
    print("Portfolio Average Firm Size ($10^6)")
    print("     ")
    size_tbl = pd.DataFrame(size_mat).astype(float).round(0)
    print(size_tbl.to_string(index=False, header=False))


def _plot_bivariate_results_matlab_like(
    out: BivariateSortResult,
    *,
    n1: int,
    n2: int,
    factor_model: int | pd.DataFrame | None,
) -> Any:
    """
    MATLAB doesn't meaningfully plot bivariate sorts by default; this provides the closest useful analog:
    - heatmap of average returns for the (bin1, bin2) grid
    - time series of conditional long-short strategies (one line per conditioning bin)
    """
    try:
        import matplotlib.pyplot as plt

        from ..plotting import maybe_show
    except ImportError:  # pragma: no cover
        raise ImportError("matplotlib is required for plot_results. Install with: pip install matplotlib")

    # Heatmap of mean returns (%/month)
    avg = (out.cell_returns.mean() * 100).unstack(level="bin2").astype(float)
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    ax0 = axes[0]
    im = ax0.imshow(avg.to_numpy(dtype=float), aspect="auto", origin="lower")
    ax0.set_title("Bivariate sort: mean returns (%/mo)")
    ax0.set_xlabel("bin2")
    ax0.set_ylabel("bin1")
    ax0.set_xticks(range(n2))
    ax0.set_yticks(range(n1))
    fig.colorbar(im, ax=ax0, fraction=0.046, pad=0.04)

    # Conditional L/S time series
    ax1 = axes[1]
    for j in out.cond_var1_given_var2.leg_returns.columns:
        y = pd.to_numeric(out.cond_var1_given_var2.leg_returns[j], errors="coerce").astype(float)
        ax1.plot(out.cond_var1_given_var2.leg_returns.index, y, label=str(j), linewidth=1)
    ax1.set_title("High-low var1 | var2 bins")
    ax1.set_xlabel("Date")
    ax1.set_ylabel("Return")
    ax1.legend(title="var2 bin", fontsize=8)

    ax2 = axes[2]
    for i in out.cond_var2_given_var1.leg_returns.columns:
        y = pd.to_numeric(out.cond_var2_given_var1.leg_returns[i], errors="coerce").astype(float)
        ax2.plot(out.cond_var2_given_var1.leg_returns.index, y, label=str(i), linewidth=1)
    ax2.set_title("High-low var2 | var1 bins")
    ax2.set_xlabel("Date")
    ax2.set_ylabel("Return")
    ax2.legend(title="var1 bin", fontsize=8)

    plt.tight_layout()
    maybe_show(plt)
    return fig

