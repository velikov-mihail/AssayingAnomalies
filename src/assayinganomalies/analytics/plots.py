"""
Plotting helpers ported from the MATLAB toolkit.

- ``ibbots`` : ``Functions/Utilities/ibbots.m`` — cumulative performance of $1
  invested in each strategy, log scale by default.
- ``moving`` : ``Functions/Utilities/moving.m`` — centered m-point moving
  average with edge padding.

The 4-panel strategy figure MATLAB draws by default (``plotStrategyFigs.m``)
is available as :meth:`SortResult.plot_results`.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd

from .sorts import _time_mask

__all__ = ["ibbots", "moving"]


def ibbots(
    rets: pd.Series | pd.DataFrame,
    time_period: Any = None,
    lin_plot_ind: bool = False,
    legend_labels: Sequence[str] | None = None,
    ax: Any = None,
    title: str | None = None,
) -> pd.DataFrame:
    """Port of ``ibbots.m``: cumulative performance of $1, log scale by default.

    Parameters
    ----------
    rets : Series or DataFrame
        Monthly return series (decimal), indexed by month-end date.
    time_period : optional
        MATLAB-style YYYYMM start or (start, end) pair to subset the sample.
    lin_plot_ind : bool
        If True, plot cumulative gains on a linear scale instead of $1 growth
        on a log scale.
    legend_labels : sequence of str, optional
        Legend labels; defaults to the column names.
    ax : matplotlib Axes, optional
        Axes to draw on; a new figure is created if omitted.
    title : str, optional
        Plot title.

    Returns
    -------
    pd.DataFrame
        The cumulative $1 growth paths (including the $1 starting point).
    """
    import matplotlib.pyplot as plt

    rets = rets.to_frame() if isinstance(rets, pd.Series) else rets.copy()
    rets = rets[_time_mask(rets.index, time_period)]
    y = (1 + rets.fillna(0)).cumprod()
    y.loc[y.index.min() - pd.offsets.MonthEnd(1)] = 1.0
    y = y.sort_index()

    ax = ax or plt.subplots()[1]
    if lin_plot_ind:
        ax.plot(y.index, y.to_numpy() - 1, linewidth=2.0)
        ax.set_title(title or "Cumulative gains")
    else:
        ax.semilogy(y.index, y.to_numpy(), linewidth=2.0)
        ax.set_title(title or "Performance of $1 (log scale)")
        ticks = 10.0 ** np.arange(0, 9)
        ax.set_yticks(ticks)
        ax.set_yticklabels([f"${t:,.0f}" for t in ticks])
        ax.set_ylim(0.8 * float(np.nanmin(y.to_numpy())),
                    1.4 * float(np.nanmax(y.to_numpy())))
    ax.legend(legend_labels or list(y.columns), loc="upper left")
    return y


def moving(x: Any, m: int) -> np.ndarray:
    """Port of ``moving.m``: centered m-point moving average with edge padding."""
    s = pd.Series(np.asarray(x, dtype=float))
    return s.rolling(m, center=True, min_periods=m).mean().bfill().ffill().to_numpy()
