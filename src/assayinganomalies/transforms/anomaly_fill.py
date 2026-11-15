"""
Anomaly-signal coverage checks and rank-filling.

Python ports of the MATLAB helpers used by the combination-strategy protocol:

- ``fill_var``             : ``fillVar.m`` — cross-sectional rank in
  [-0.5, 0.5], median-filled for stocks with market cap but no signal.
- ``check_fill_anomalies`` : ``checkFillAnomalies.m`` — keep anomalies whose
  market-cap coverage exceeds a threshold and fill the kept signals.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

import numpy as np
import pandas as pd

from ..analytics.sorts import _calendar_ffill, _to_month_end
from ..logging_utils import emit
from ..tiebreak import anomaly_noise_rng

LOGGER = logging.getLogger("assayinganomalies.transforms.anomaly_fill")

__all__ = ["fill_var", "check_fill_anomalies"]


def fill_var(var: pd.Series, mcap: pd.Series) -> pd.Series:
    """Port of ``fillVar.m``: cross-sectional rank in [-0.5, 0.5], median-filled.

    Both inputs are (date, permno)-indexed Series. Annual (quarterly) signals
    are first carried forward 11 (2) calendar months per stock, like MATLAB
    ``FillMonths``; monthly signals are left alone. The limit is in calendar
    months, so months a stock has no row for count toward it and a value
    cannot outlive its window. Stocks with a market cap
    but no signal get the cross-sectional median rank (0.0); stocks without a
    market cap are NaN.
    """
    obs = var.groupby(level="date").count()
    months_with_obs = obs.index[obs > 0]
    if len(months_with_obs) > 1:
        gaps = pd.Series(months_with_obs).diff().dt.days.dropna()
        step = float(gaps.mode().iloc[0]) if not gaps.empty else 30.0
        # MATLAB FillMonths carries an annual value 11 months forward, a quarterly
        # value 2 months forward; monthly data is left alone.
        limit = {12: 11, 6: 5, 3: 2}.get(int(round(step / 30.4)), 0)
        if limit:
            var = _calendar_ffill(var, limit)

    rk = var.groupby(level="date").rank(method="average")
    mx = rk.groupby(level="date").transform("max")
    out = (rk - 1) / (mx - 1) - 0.5
    out = out.mask(out.isna() & mcap.notna(), 0.0)
    return out.where(mcap.notna())


def check_fill_anomalies(
    anoms: Mapping[str, pd.Series] | pd.DataFrame,
    mcap: pd.Series,
    time_period: tuple[Any, Any],
    mcap_thresh: float = 0.40,
    n_roll: int = 120,
    seed: int = 0,
) -> tuple[dict[str, pd.Series], pd.Series, pd.DataFrame]:
    """Port of ``checkFillAnomalies.m``.

    Parameters
    ----------
    anoms : mapping or DataFrame
        Anomaly signals, one (date, permno)-indexed Series per name.
    mcap : pd.Series
        Market capitalization, (date, permno)-indexed.
    time_period : tuple
        (start, end) sample bounds as YYYYMM integers or Timestamps.
    mcap_thresh : float
        Minimum average share of market-cap observations covered by the signal.
    n_roll : int
        Rolling window (months) for the time-varying coverage check.
    seed : int
        Seed for the infinitesimal tie-breaking noise MATLAB adds. Each
        anomaly draws from the stream of its name
        (:func:`assayinganomalies.tiebreak.anomaly_noise_rng`), so a signal's
        noise depends neither on the panel's size nor on the other anomalies
        or its place among them.

    Returns
    -------
    (filled, keep, keep_roll)
        A dict of filled signals for the kept anomalies, a bool Series over
        anomaly names, and a (date x anomaly) bool frame.
    """
    emit(LOGGER, f"\nNow working on checking the anomalies. Run started at "
         f"{pd.Timestamp.now():%Y-%m-%d %H:%M:%S}.\n")
    all_dates = mcap.index.get_level_values("date").unique().sort_values()
    n_finite_me = mcap.groupby(level="date").count().reindex(all_dates).fillna(0)

    names = list(anoms)
    keep = pd.Series(False, index=names)
    keep_roll = pd.DataFrame(False, index=all_dates, columns=names)
    filled: dict[str, pd.Series] = {}

    for i, name in enumerate(names, start=1):
        if i % 10 == 0:
            emit(LOGGER, f"Done with {i}/{len(names)} anomalies @ {pd.Timestamp.now():%H:%M:%S}.")
        var = anoms[name].reindex(mcap.index).astype(float)
        # One independent stream per anomaly, keyed on its name. A
        # single shared cursor would advance by `len(var)` per anomaly, so
        # lengthening the panel -- extra months, or extra stocks in later
        # months -- would hand every anomaly after the first a different slice
        # of the stream and move the ranks of *earlier* months. The noise
        # carries no information, but a rank at month t still must not depend
        # on how much data follows t, nor
        # on which other anomalies are in the list.
        rng = anomaly_noise_rng(seed, name)
        var = var + rng.standard_normal(len(var)) * 1e-12
        var = var.where(mcap.notna())      # kick out stock-months with no market cap

        n_obs = var.groupby(level="date").count().reindex(all_dates).fillna(0)
        has_obs = n_obs > 0
        if not has_obs.any():
            continue
        obs_dates = all_dates[has_obs.to_numpy()]
        s = max(_to_month_end(time_period[0]), obs_dates.min())
        e = min(_to_month_end(time_period[1]), obs_dates.max())
        if len(all_dates[(all_dates > s) & (all_dates <= e)]) <= n_roll:
            continue

        pct = n_obs / n_finite_me.replace(0, np.nan)
        in_sample = has_obs.to_numpy() & (all_dates >= s) & (all_dates <= e)
        if not (pct[in_sample].mean() > mcap_thresh):
            continue

        keep[name] = True
        filled[name] = fill_var(var, mcap)
        roll = (pct.rolling(n_roll, min_periods=n_roll).mean() > mcap_thresh).to_numpy()
        keep_roll[name] = roll & (all_dates >= s) & (all_dates <= e)

    emit(LOGGER, f"\nDone with checking the anomalies at {pd.Timestamp.now():%Y-%m-%d %H:%M:%S}. "
         f"Kept {int(keep.sum())}/{len(names)}.\n")
    return filled, keep, keep_roll
