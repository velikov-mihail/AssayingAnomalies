"""
Split a sample into contiguous subperiods for the report's subsample table.

No MATLAB counterpart (``Tab_SubSample``). The rule: with ``N`` years
of data, use ``min(4, N // 10)``
subsamples when ``N >= 20`` and two otherwise, so each subsample spans at
least about ten years once the sample allows it. The subsamples are blocks of
consecutive months of (nearly) equal length; when the months do not divide
evenly, the leftover months go to the earliest blocks, one each.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..signal_io import month_end_to_yyyymm

__all__ = ["n_subsamples", "subsample_bounds", "subsample_windows"]


def n_subsamples(n_years: int) -> int:
    """Number of subsamples for a sample of ``n_years`` years.

    ``min(4, n_years // 10)`` when ``n_years >= 20``, else 2: 20-29 years give
    two, 30-39 three, 40 or more four.
    """
    n = int(n_years)
    if n >= 20:
        return min(4, n // 10)
    return 2


def subsample_bounds(n_months: int, n_sub: int) -> list[tuple[int, int]]:
    """Half-open positional bounds ``[(start, stop), ...]`` of ``n_sub`` blocks.

    The blocks cover ``range(n_months)`` contiguously with the semantics of
    :func:`numpy.array_split`: their lengths differ by at most one, and the
    longer blocks come first (``subsample_bounds(10, 4) ==
    [(0, 3), (3, 6), (6, 8), (8, 10)]``).

    Raises
    ------
    ValueError
        If ``n_sub < 1`` or ``n_months < n_sub`` (a block would be empty).
    """
    n_months, n_sub = int(n_months), int(n_sub)
    if n_sub < 1:
        raise ValueError(f"n_sub must be at least 1, got {n_sub}")
    if n_months < n_sub:
        raise ValueError(
            f"cannot split {n_months} months into {n_sub} non-empty subsamples"
        )
    base, extra = divmod(n_months, n_sub)
    bounds: list[tuple[int, int]] = []
    start = 0
    for k in range(n_sub):
        stop = start + base + (1 if k < extra else 0)
        bounds.append((start, stop))
        start = stop
    return bounds


def subsample_windows(index: pd.Index, n_sub: int | None = None) -> list[tuple[int, int]]:
    """First and last month (YYYYMM) of each subsample of a monthly ``index``.

    ``index`` holds the sample's months in order (month-end dates).
    ``n_sub`` defaults to ``n_subsamples(len(index) // 12)``. Flooring the
    number of years is immaterial for the rule: ``n_months / 12 >= 20`` holds
    exactly when ``n_months // 12 >= 20``, and
    ``(n_months // 12) // 10 == n_months // 120``, so fractional years never
    change the number of subsamples.
    """
    dates = pd.DatetimeIndex(index)
    if n_sub is None:
        n_sub = n_subsamples(len(dates) // 12)
    yyyymm = np.array([month_end_to_yyyymm(d) for d in dates], dtype=int)
    return [
        (int(yyyymm[start]), int(yyyymm[stop - 1]))
        for start, stop in subsample_bounds(len(dates), n_sub)
    ]
