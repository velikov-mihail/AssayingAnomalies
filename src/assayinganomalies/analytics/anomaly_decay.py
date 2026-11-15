"""
Anomaly-decay analysis (McLean and Pontiff, 2016; Chen and Velikov, 2022).

Python port of the anomaly-decay loop in ``use_library.m`` section 11: run
each documented Chen-Zimmerman signal through its own rebalancing frequency,
screens, sample window and weighting, then line the long/short strategies up
on their publication dates.

All sorts are expressed on :func:`run_univariate_sort`:

- quantile strategies keep only the extreme legs via percentile ``n_bins``
  (e.g. deciles -> ``[10, 90]``: the long/short return is the top bin minus
  the bottom bin and the inert middle bin does not affect either leg);
- categorical strategies (discrete signals, zero-vs-positive splits) map the
  legs onto a synthetic {1, 2} signal sorted with a breakpoint filter pinned
  to the long leg, which places the breakpoint at exactly 2.0;
- the ``me > me_nyse20`` screen drops stocks in the bottom quintile of a
  NYSE-break size sort (MATLAB ``makeUnivSortInd(me, 5, NYSE) == 1``).
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd

from .sorts import (
    SortResult,
    _bin_by_cross_section,
    _to_month_end,
    run_univariate_sort,
)

__all__ = ["run_anomaly_decay", "plot_anomaly_decay"]


def _two_leg_sort(
    returns: pd.Series,
    leg: pd.Series,
    mcap: pd.Series,
    *,
    weighting: str,
    time_period: Any,
) -> SortResult:
    """Sort on a synthetic {1, 2} leg signal (1 = short, 2 = long, NaN = out).

    Uses ``breaks='nyse'`` with the flag pinned to the long leg so the single
    breakpoint is exactly 2.0: bin 1 collects the 1s, bin 2 the 2s.
    """
    return run_univariate_sort(
        returns=returns,
        signal=leg,
        mcap=mcap,
        n_bins=2,
        breaks="nyse",
        nyse_flag=(leg == 2),
        weighting=weighting,
        time_period=time_period,
        factor_model=4,
    )


def run_anomaly_decay(
    anoms_panel: pd.DataFrame,
    summary: pd.DataFrame,
    *,
    returns: pd.Series,
    mcap: pd.Series,
    prc: pd.Series | None = None,
    exchcd: pd.Series | None = None,
    nyse_flag: pd.Series | None = None,
    verbose: bool = True,
) -> dict[str, SortResult]:
    """Port of the MATLAB anomaly-decay loop over the Chen-Zimmerman signals.

    Parameters
    ----------
    anoms_panel : pd.DataFrame
        (date, permno)-indexed panel with one column per anomaly signal.
    summary : pd.DataFrame
        Chen-Zimmerman signal documentation (``aa.get_cz_signal_info()``);
        matched on lowercase ``acronym``.
    returns, mcap : pd.Series
        Stock returns and market cap, (date, permno)-indexed.
    prc, exchcd, nyse_flag : pd.Series, optional
        Price, exchange code and NYSE indicator panels used by the
        documentation screens; screens whose inputs are missing are skipped.
    verbose : bool
        Print anomalies whose sorts raise instead of failing the loop.

    Returns
    -------
    dict[str, SortResult]
        One sort result per anomaly that could be run.
    """
    print(f"Start at {pd.Timestamp.now():%Y-%m-%d %H:%M:%S}.")
    t0 = time.time()

    mths = anoms_panel.index.get_level_values("date").month
    june = mths == 6
    june_dec = np.isin(mths, [6, 12])
    quarter_end = np.isin(mths, [3, 6, 9, 12])
    all_dates = anoms_panel.index.get_level_values("date").unique().sort_values()
    n_months = len(all_dates)

    ind_me5 = None  # lazily computed NYSE-break size quintile assignment
    results: dict[str, SortResult] = {}

    for label in anoms_panel.columns:
        rows = summary[summary["acronym"] == label.lower()]
        if rows.empty:
            continue
        r = rows.iloc[0]
        var = anoms_panel[label].astype(float)

        # Rebalancing period
        period = r["PortfolioPeriod"]
        if period in (12, 36):
            var = var.where(june)
        elif period == 6:
            var = var.where(june_dec)
        elif period == 3:
            var = var.where(quarter_end)

        # Screens
        filt = "" if pd.isna(r["Filter"]) else str(r["Filter"]).replace(" ", "")
        if filt:
            if "abs(prc)>1" in filt and prc is not None:
                var = var.where(prc.abs() > 1)
            if "abs(prc)>5" in filt and prc is not None:
                var = var.where(prc.abs() > 5)
            if "exchcd%in%c(1,2)" in filt and exchcd is not None:
                var = var.where((exchcd <= 2).fillna(False))
            if "exchcd==1" in filt and exchcd is not None:
                var = var.where((exchcd <= 1).fillna(False))
            if "me>me_nyse20" in filt and nyse_flag is not None:
                if ind_me5 is None:
                    ind_me5 = (
                        _bin_by_cross_section(
                            mcap, 5, breaks="nyse", nyse_flag=nyse_flag, mcap=None
                        )
                        .reindex(mcap.index)
                        .fillna(0)
                        .astype("Int64")
                    )
                var = var.where(ind_me5 != 1)

        # Sample
        if pd.isna(r["SampleStartYear"]):
            continue
        start_month = r["StartMonth"]
        sample_start = int(100 * r["SampleStartYear"]
                           + (6 if pd.isna(start_month) else start_month))
        obs = var.groupby(level="date").count()
        obs = obs[obs > 0]
        if obs.empty:
            continue
        last_pos = all_dates.get_loc(obs.index.max())
        hold = 0 if pd.isna(period) else int(period)
        sample_end = all_dates[min(last_pos + hold, n_months - 1)]
        dts = (sample_start, int(f"{sample_end:%Y%m}"))

        # Portfolio construction
        weighting = "v" if r["StockWeight"] == "VW" else "e"
        leg = None
        if label.lower() == "changeinrecommendation":
            lo = var.groupby(level="date").transform(lambda s: s.quantile(0.20))
            hi = var.groupby(level="date").transform(lambda s: s.quantile(0.80))
            leg = pd.Series(np.nan, index=var.index, dtype="float64")
            leg = leg.mask(var <= lo, 1.0).mask(var >= hi, 2.0)
        elif label.lower() in ("numearnincrease", "rdcap"):
            leg = pd.Series(np.nan, index=var.index, dtype="float64")
            leg = leg.mask(var == 0, 1.0).mask(var > 0, 2.0)
        elif r["Cat_Form"] == "discrete":
            lo, hi = var.min(), var.max()
            leg = pd.Series(np.nan, index=var.index, dtype="float64")
            leg = leg.mask(var == lo, 1.0).mask(var == hi, 2.0)

        try:
            if leg is not None:
                if leg.notna().sum() == 0:
                    continue
                results[label] = _two_leg_sort(
                    returns, leg, mcap, weighting=weighting, time_period=dts
                )
            else:
                if var.notna().sum() == 0:
                    continue
                ls_q = r["LSQuantile"]
                nptfs = 5 if pd.isna(ls_q) else int(round(1 / ls_q))
                use_nyse = r["QuantileFilter"] == "NYSE" and nyse_flag is not None
                if nptfs == 2:
                    pct = [1 * 100 / nptfs]
                else:
                    pct = [1 * 100 / nptfs, (nptfs - 1) * 100 / nptfs]
                results[label] = run_univariate_sort(
                    returns=returns,
                    signal=var,
                    mcap=mcap,
                    n_bins=pct,
                    breaks="nyse" if use_nyse else "name",
                    nyse_flag=nyse_flag if use_nyse else None,
                    weighting=weighting,
                    time_period=dts,
                    factor_model=4,
                )
        except Exception as exc:
            if verbose:
                print(f"  {label}: {type(exc).__name__}: {exc}")

    print(f"Done running sorts at {pd.Timestamp.now():%Y-%m-%d %H:%M:%S} "
          f"({time.time() - t0:.0f}s, {len(results)} anomalies).")
    return results


def plot_anomaly_decay(
    results: dict[str, SortResult],
    summary: pd.DataFrame,
    all_dates: pd.Index,
) -> np.ndarray:
    """Line the strategies up on publication date and plot the average decay."""
    import matplotlib.pyplot as plt

    from ..plotting import maybe_show
    from .plots import moving

    n_months = len(all_dates)
    relative = np.full((2 * n_months + 1, len(results)), np.nan)

    for k, (label, res) in enumerate(results.items()):
        rows = summary[summary["acronym"] == label.lower()]
        if rows.empty or pd.isna(rows.iloc[0]["Year"]):
            continue
        pub = _to_month_end(int(100 * rows.iloc[0]["Year"] + 12))
        ls = res.pret["long_short"]
        if pub < ls.index.min() or pub > ls.index.max():
            continue
        e = int(ls.index.searchsorted(pub, side="right"))
        relative[n_months - e:n_months, k] = ls.to_numpy()[:e]
        relative[n_months:n_months + len(ls) - e, k] = ls.to_numpy()[e:]

    avg = np.nanmean(relative, axis=1)
    x = np.arange(-n_months, n_months + 1) / 12
    fig, ax = plt.subplots()
    ax.plot(x, 100 * avg, color=(0.8, 0.8, 0.8), lw=1.0, label="Average")
    ax.plot(x, 100 * moving(avg, 60), lw=1.8, label="5-year moving average")
    ax.set_ylim(-0.5, 1.0)
    ax.set_xlim(-30, 20)
    ax.set_xlabel("Years relative to publication")
    ax.set_title("Average returns across anomalies")
    ax.legend()
    maybe_show(plt)
    return relative
