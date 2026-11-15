"""Process-level caches for interactive day-to-day analytics.

A typical ``use_library`` session calls ``aa.load`` / ``load_factors`` /
``run_univariate_sort`` many times against the same DuckDB file and the same
sample window. Opening a new connection, re-reading ``ts_data``, recomputing
NYSE breakpoints, and re-pivoting the same column into a dates × slots matrix
are all pure overhead: the numbers do not change.

Only two things are cached: DuckDB connections (keyed by resolved path) and
the ``ts_data`` factor frame (keyed by ``(database, sample_start,
sample_end)``). Writers go through
:class:`~assayinganomalies.db.manager.DuckDBManager`, which drops the cached
connection and factor frames for that path before opening its own. Factor
frames are copied on the way in and out, so a caller's in-place edits cannot
reach a later caller. Tests (and pipeline rebuilds) call
:func:`clear_session_cache` so Windows can delete temp database files.

Pack layouts, packed values, NYSE breakpoint cuts and wide pivots are
recomputed on every call. They used to be memoized on a fingerprint of the
MultiIndex codes (which ignores the level values, so a 2020 panel could reuse
a 2000 panel's dates) and on a 256-point sample of a mutable array (which
misses in-place edits).
The helpers and :func:`cache_info` keep their signatures so callers work
unchanged. Any replacement cache needs its own correctness case and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Hashable, Mapping

import duckdb
import numpy as np
import pandas as pd

# (resolved db path, sample_start, sample_end)
SampleKey = tuple[str, int, int]


_connections: dict[str, duckdb.DuckDBPyConnection] = {}
_factors: dict[SampleKey, pd.DataFrame] = {}
_sample_key: SampleKey | None = None


@dataclass(slots=True)
class PackLayout:
    """Dates × slots addressing for a long (date, permno) panel.

    Original row ``i`` sits at ``mat[group_codes[i], within[i]]``. Ragged
    months are NaN-padded to ``n_max``. ``unique_keys`` is the sorted set of
    group labels (month-ends, or ``(date, bin1)`` for a conditional sort).
    """

    unique_keys: np.ndarray | pd.Index | pd.arrays.DatetimeArray | Any
    group_codes: np.ndarray
    within: np.ndarray
    n_max: int
    n_groups: int


def _resolve_db_path(path: str | Path) -> str:
    return str(Path(path).expanduser().resolve())


def db_sample_key(
    db_path: str | Path | None = None,
    sample: tuple[int, int] | None = None,
) -> SampleKey:
    """``(resolved_db, sample_start, sample_end)`` for factor / NYSE caches.

    ``sample`` defaults to the configured window. The resolved key is kept
    until :func:`clear_session_cache` so a sort does not re-open config.
    """
    global _sample_key
    if db_path is None and sample is None and _sample_key is not None:
        return _sample_key

    from .config import SampleEndUnresolvedError, load_config

    cfg = load_config()
    path = _resolve_db_path(db_path if db_path is not None else cfg.database_path)
    if sample is None:
        start = int(cfg.sample_start)
        # "latest" keys on the year the database's last build resolved it to;
        # a database that records none keys on the sentinel, which is stable.
        try:
            end = cfg.resolved_sample_end(path)
        except SampleEndUnresolvedError:
            end = cfg.sample_end
    else:
        start, end = int(sample[0]), int(sample[1])
    key = (path, start, end)
    if db_path is None and sample is None:
        _sample_key = key
    return key


def get_connection(path: str | Path) -> duckdb.DuckDBPyConnection:
    """Return a kept-alive DuckDB connection for ``path`` (read-heavy ``aa.load``)."""
    key = _resolve_db_path(path)
    con = _connections.get(key)
    if con is None:
        con = duckdb.connect(key)
        _connections[key] = con
    return con


def cached_connection(path: str | Path) -> duckdb.DuckDBPyConnection | None:
    """The kept-alive connection for ``path`` if one is open, else ``None``.

    Does not open one. A reader that would otherwise open the same file
    read-only must use this instead: DuckDB refuses a second connection to a
    file with a different configuration in the same process.
    """
    return _connections.get(_resolve_db_path(path))


def close_cached_connection(path: str | Path | None = None) -> None:
    """Close the cached connection for ``path``, or all of them if ``path`` is None.

    Also drops factor / NYSE entries whose key starts with that database, so a
    rebuild cannot serve pre-rebuild numbers.
    """
    global _sample_key
    if path is None:
        clear_session_cache()
        return
    key = _resolve_db_path(path)
    con = _connections.pop(key, None)
    if con is not None:
        con.close()
    for fk in [k for k in _factors if k[0] == key]:
        _factors.pop(fk, None)
    if _sample_key is not None and _sample_key[0] == key:
        _sample_key = None


def query_df(path: str | Path, sql: str) -> pd.DataFrame:
    return get_connection(path).execute(sql).df()


def get_cached_factors(key: SampleKey) -> pd.DataFrame | None:
    cached = _factors.get(key)
    if cached is None:
        return None
    return cached.copy()


def put_cached_factors(key: SampleKey, frame: pd.DataFrame) -> pd.DataFrame:
    _factors[key] = frame
    return frame.copy()


def nyse_breakpoint_cuts(
    key: Hashable,
    factory: Callable[[], np.ndarray],
    *,
    layout: PackLayout | None = None,
) -> np.ndarray:
    """Compute NYSE breakpoint rows. ``key`` and ``layout`` are ignored.

    Kept for callers of the old memoized API; ``factory`` runs every call.
    """
    return factory()


def _layout_keys(group_keys: Any):
    if isinstance(group_keys, pd.MultiIndex):
        return np.asarray(group_keys.get_level_values(0))
    if isinstance(group_keys, pd.Index):
        return np.asarray(group_keys)
    return np.asarray(group_keys)


def pack_layout(group_keys: Any) -> PackLayout:
    """Build the dates × slots layout for ``group_keys``.

    ``group_keys`` may be a ``MultiIndex`` (date is level 0), a date ``Index``,
    or an array of group labels. Computed fresh on every call.
    """
    return _compute_pack_layout(_layout_keys(group_keys))


def _compute_pack_layout(keys: np.ndarray) -> PackLayout:
    n = int(keys.shape[0])
    group_codes, unique_keys = pd.factorize(keys, sort=True)
    t = int(unique_keys.shape[0])
    group_codes = group_codes.astype(np.int64, copy=False)
    if n == 0 or t == 0:
        return PackLayout(
            unique_keys=unique_keys,
            group_codes=group_codes,
            within=np.empty(0, dtype=np.int64),
            n_max=0,
            n_groups=t,
        )
    counts = np.bincount(group_codes, minlength=t)
    n_max = int(counts.max())
    order = np.argsort(group_codes, kind="mergesort")
    starts = np.empty(t, dtype=np.int64)
    starts[0] = 0
    if t > 1:
        starts[1:] = np.cumsum(counts[:-1])
    within = np.empty(n, dtype=np.int64)
    within[order] = np.arange(n, dtype=np.int64) - np.repeat(starts, counts)
    return PackLayout(
        unique_keys=unique_keys,
        group_codes=group_codes,
        within=within,
        n_max=n_max,
        n_groups=t,
    )


def pack_values(
    values: np.ndarray,
    layout: PackLayout,
    *,
    name: Hashable | None = None,
) -> np.ndarray:
    """Scatter ``values`` into a new ``(n_groups, n_max, k)`` matrix.

    ``name`` is accepted for compatibility and ignored. The result never
    shares memory with ``values``, so callers may modify it.
    """
    values = np.asarray(values, dtype=np.float64)
    if values.ndim == 1:
        values = values[:, None]
    n, k = values.shape
    mat = np.full((layout.n_groups, layout.n_max, k), np.nan, dtype=np.float64)
    if n and layout.n_max:
        mat[layout.group_codes, layout.within, :] = values
    return mat


def pack_column(
    values: np.ndarray,
    layout: PackLayout,
    *,
    name: Hashable | None = None,
) -> np.ndarray:
    """Like :func:`pack_values` but returns a 2-D ``(n_groups, n_max)`` slice."""
    mat = pack_values(values, layout, name=name)
    return mat[:, :, 0]


def wide_matrix(series: pd.Series) -> pd.DataFrame:
    """Date × permno pivot of a ``(date, permno)`` series, computed fresh.

    The packed dates × slots matrix used by sorts / FM is the usual wide form
    in this package (ragged months, no permno alignment). This is the true
    ``unstack`` pivot for callers that want permno columns.
    """
    if not isinstance(series.index, pd.MultiIndex):
        raise ValueError("wide_matrix requires a MultiIndex (date, permno) series")
    names = list(series.index.names)
    if "date" in names and "permno" in names:
        date_level: Hashable = "date"
        permno_level: Hashable = "permno"
    else:
        date_level = 0
        permno_level = 1
    wide = pd.to_numeric(series, errors="coerce").unstack(level=permno_level)
    if wide.index.name != date_level and "date" in names:
        wide.index.name = "date"
    return wide


def cache_info() -> Mapping[str, int]:
    """Entry counts per cache. Layout / packed / NYSE / wide are always 0."""
    return {
        "connections": len(_connections),
        "factors": len(_factors),
        "nyse_breakpoints": 0,
        "layouts": 0,
        "packed": 0,
        "wide": 0,
    }


def clear_session_cache() -> None:
    """Drop every session cache and close kept-alive DuckDB connections."""
    global _sample_key
    for con in _connections.values():
        try:
            con.close()
        except Exception:
            pass
    _connections.clear()
    _factors.clear()
    _sample_key = None


__all__ = [
    "PackLayout",
    "SampleKey",
    "cache_info",
    "cached_connection",
    "clear_session_cache",
    "close_cached_connection",
    "db_sample_key",
    "get_cached_factors",
    "get_connection",
    "nyse_breakpoint_cuts",
    "pack_column",
    "pack_layout",
    "pack_values",
    "put_cached_factors",
    "query_df",
    "wide_matrix",
]
