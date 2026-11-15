"""
Utilities for fetching CRSP daily data from WRDS.

MATLAB equivalent: getCRSPDailyData.m
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import shutil
import time
from typing import Any, Callable, Sequence

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..config import AssayConfig
from .crsp_source import SIZ_DAILY_SQL, CRSPSource, crsp_source_for
from .wrds_client import WRDSClient

LOGGER = logging.getLogger("assayinganomalies.ingest.crsp_daily")

# The tape-specific query now lives in ``crsp_source``; this name is kept so
# existing callers still resolve, and always means the legacy SIZ tape.
CRSP_DAILY_SQL = SIZ_DAILY_SQL

DAILY_INT_COLUMNS: tuple[str, ...] = ("permno",)
DAILY_FLOAT_COLUMNS: tuple[str, ...] = (
    "ret", "retx", "prc", "bid", "ask", "bidlo", "askhi",
    "vol", "shrout", "cfacpr", "cfacshr",
)
# Column order of the daily SQL, which is the staged file's column order.
# Both tapes alias onto it, so the staged
# daily file has the same schema whichever source produced it.
DAILY_COLUMNS: tuple[str, ...] = ("permno", "date") + DAILY_FLOAT_COLUMNS

# The staged extract's schema is pinned rather than inferred per chunk: an
# early year whose quotes are entirely missing would otherwise arrive as a
# different arrow type than the years around it and the parts would not
# concatenate. ``date`` is text because that is what the single-shot pull
# staged and what `pipeline._read_daily_staging` parses.
DAILY_SCHEMA = pa.schema(
    [("permno", pa.int64()), ("date", pa.string())]
    + [(name, pa.float64()) for name in DAILY_FLOAT_COLUMNS]
)

# Sorting the merged file makes the staged extract independent of the order
# the chunks happened to arrive in (year-major, unlike the permno-major order
# a single pull returned). Every consumer sorts on these keys anyway.
DAILY_SORT_KEYS: tuple[str, ...] = ("permno", "date")

DEFAULT_YEARS_PER_CHUNK = 1
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_WAIT_S = 30.0
# Budget for the ordered merge. Left to itself DuckDB would sort the whole
# 108M-row file in memory (measured: 28 GB peak), which would put back the
# peak the chunked fetch just removed; with a budget it spills to
# ``temp_directory`` instead.
DEFAULT_MERGE_MEMORY_LIMIT = "4GB"
MANIFEST_NAME = "manifest.json"
# 2: the manifest stamps the CRSP source, so a resumed chunked pull can
# never mix parts fetched from the SIZ tape with parts fetched from CIZ.
MANIFEST_VERSION = 2
_MERGE_BATCH_ROWS = 262_144
# pyarrow's own default. DuckDB writes 122,880-row groups unless told
# otherwise, which costs ~40% on the merged file's size.
_MERGE_ROW_GROUP_ROWS = 1_048_576


def generate_placeholder_daily(config: AssayConfig) -> pd.DataFrame:
    """
    Create a deterministic mini daily sample for CI/tests.

    Produces 2 permnos × 22 trading days (roughly one month of daily data).
    """
    rng = np.random.default_rng(44)
    dates = pd.bdate_range(
        f"{config.sample_start}-01-03",
        periods=22,
        freq="B",
    )
    rows = []
    for permno, base_prc in [(10001, 50.0), (10002, 12.0)]:
        prc = base_prc
        for dt in dates:
            ret = rng.normal(0.0005, 0.02)
            prc = prc * (1 + ret)
            rows.append({
                "permno": permno,
                "date": pd.Timestamp(dt),
                "ret": round(ret, 6),
                "retx": round(ret, 6),
                "prc": round(prc, 2),
                "bid": round(prc * 0.999, 2),
                "ask": round(prc * 1.001, 2),
                "bidlo": round(prc * 0.995, 2),
                "askhi": round(prc * 1.005, 2),
                "vol": int(rng.integers(50000, 500000)),
                "shrout": 3000.0 if permno == 10001 else 1500.0,
                "cfacpr": 1.0,
                "cfacshr": 1.0,
            })
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class DailyChunk:
    """One year range of crsp.dsf, fetched and staged on its own."""

    index: int
    first_year: int
    last_year: int

    @property
    def start_date(self) -> str:
        return f"{self.first_year}-01-01"

    @property
    def end_date(self) -> str:
        return f"{self.last_year}-12-31"

    @property
    def label(self) -> str:
        if self.first_year == self.last_year:
            return str(self.first_year)
        return f"{self.first_year}-{self.last_year}"

    @property
    def part_name(self) -> str:
        return f"part_{self.index:03d}_{self.label}.parquet"


def plan_daily_chunks(
    sample_start: int,
    sample_end: int,
    years_per_chunk: int = DEFAULT_YEARS_PER_CHUNK,
) -> list[DailyChunk]:
    """
    Split the sample window into consecutive year ranges.

    The last chunk is truncated at ``sample_end`` rather than overshooting it,
    so the union of the chunks is exactly the window the single-shot query
    covered.
    """
    if years_per_chunk < 1:
        raise ValueError(f"years_per_chunk must be >= 1, got {years_per_chunk}")
    if sample_end < sample_start:
        raise ValueError(
            f"sample_end ({sample_end}) is before sample_start ({sample_start})"
        )
    return [
        DailyChunk(index, year, min(year + years_per_chunk - 1, sample_end))
        for index, year in enumerate(range(sample_start, sample_end + 1, years_per_chunk))
    ]


def daily_parts_dir(destination: Path) -> Path:
    """Directory holding the per-chunk parquet parts for ``destination``."""
    destination = Path(destination)
    return destination.parent / f"{destination.stem}_parts"


def _manifest_payload(
    chunks: Sequence[DailyChunk], sql_template: str, source_name: str
) -> dict[str, Any]:
    return {
        "version": MANIFEST_VERSION,
        "source": source_name,
        "sql_template": sql_template.strip(),
        "columns": list(DAILY_COLUMNS),
        "chunks": [
            {
                "index": chunk.index,
                "start_date": chunk.start_date,
                "end_date": chunk.end_date,
                "part": chunk.part_name,
            }
            for chunk in chunks
        ],
    }


def _prepare_parts_dir(parts_dir: Path, payload: dict[str, Any], *, resume: bool) -> None:
    """
    Make ``parts_dir`` ready for this fetch plan.

    Parts are only reused when the manifest they were written under matches
    the plan about to run, so a changed sample window, chunk size or query
    can never contribute rows to the merged file. A finished fetch stamps
    ``completed_at`` into its manifest, which fails that comparison too: parts
    kept from a run that already merged are old data, not a resume.
    """
    manifest_path = parts_dir / MANIFEST_NAME
    if parts_dir.exists():
        stale = True
        if resume:
            try:
                stale = json.loads(manifest_path.read_text(encoding="utf-8")) != payload
            except (OSError, ValueError):
                stale = True
            if stale:
                LOGGER.warning(
                    "Discarding CRSP daily parts in %s: written for a different fetch plan",
                    parts_dir,
                )
        if stale:
            shutil.rmtree(parts_dir)
    parts_dir.mkdir(parents=True, exist_ok=True)
    for leftover in parts_dir.glob("*.tmp"):
        leftover.unlink()
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _finish_parts_dir(parts_dir: Path, payload: dict[str, Any], *, keep_parts: bool) -> None:
    """Stamp the manifest complete, then drop the parts unless asked to keep them."""
    manifest_path = parts_dir / MANIFEST_NAME
    if manifest_path.exists():
        completed = dict(payload, completed_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        manifest_path.write_text(json.dumps(completed, indent=2), encoding="utf-8")
    if keep_parts:
        return
    try:
        shutil.rmtree(parts_dir)
    except OSError as exc:
        LOGGER.warning(
            "Could not remove CRSP daily parts in %s (%s); they will not be reused",
            parts_dir, exc,
        )


def _iso_date_strings(series: pd.Series) -> pd.Series:
    """Return ``dsf.date`` as ISO text, whatever the driver handed back."""
    if len(series) == 0:
        return series.astype(object)
    if pd.api.types.infer_dtype(series, skipna=True) == "string":
        return series
    return pd.to_datetime(series).dt.strftime("%Y-%m-%d")


def _chunk_to_arrow(df: pd.DataFrame) -> pa.Table:
    """Coerce one fetched chunk onto ``DAILY_SCHEMA``."""
    by_lower = {str(name).lower(): name for name in df.columns}
    missing = [name for name in DAILY_COLUMNS if name not in by_lower]
    if missing:
        raise KeyError(f"CRSP daily extract is missing columns: {missing}")

    columns: dict[str, pd.Series] = {}
    for name in DAILY_COLUMNS:
        series = df[by_lower[name]]
        if name == "date":
            series = _iso_date_strings(series)
        elif name in DAILY_INT_COLUMNS and series.dtype != "int64":
            series = series.astype("int64")
        elif name in DAILY_FLOAT_COLUMNS and series.dtype != "float64":
            series = series.astype("float64")
        columns[name] = series
    frame = pd.DataFrame(columns, copy=False)
    return pa.Table.from_pandas(frame, schema=DAILY_SCHEMA, preserve_index=False)


def _write_part(table: pa.Table, part_path: Path) -> None:
    """Write a part through a temp name so a killed process leaves no half part."""
    tmp = part_path.with_name(part_path.name + ".tmp")
    pq.write_table(table, tmp)
    os.replace(tmp, part_path)


class _WRDSSession:
    """
    One WRDS connection, reopened after a failed chunk.

    A dropped connection is the common way an hour-long pull dies, and the
    dead handle cannot serve the retry, so a failure closes the session and
    the next attempt opens a fresh one. With a :class:`WRDSClient` the
    connection is the client's shared one, so ``reset`` asks the client to
    reconnect rather than leaving the dead handle cached there.
    """

    def __init__(
        self,
        connect: Callable[[], Any],
        reset: Callable[[], Any] | None = None,
    ):
        self._connect = connect
        self._reset = reset
        self._cm: Any | None = None
        self._conn: Any | None = None

    def connection(self) -> Any:
        if self._conn is None:
            cm = self._connect()
            self._conn = cm.__enter__()
            self._cm = cm
        return self._conn

    def close(self) -> None:
        cm, self._cm, self._conn = self._cm, None, None
        if cm is not None:
            with suppress(Exception):
                cm.__exit__(None, None, None)

    def reset(self) -> None:
        """
        Drop the handle after a failure; the next :meth:`connection` gets a
        fresh one. ``reset`` (the client's ``reconnect``) logs in again; if
        that fails, the next attempt raises and is retried in turn.
        """
        self.close()
        if self._reset is not None:
            with suppress(Exception):
                self._reset()


def _run_chunk_query(
    session: _WRDSSession,
    sql: str,
    chunk: DailyChunk,
    *,
    max_attempts: int,
    retry_wait: float,
) -> pd.DataFrame:
    for attempt in range(1, max_attempts + 1):
        try:
            return session.connection().raw_sql(sql)
        except Exception as exc:  # noqa: BLE001 - any driver error is retryable
            session.reset()
            if attempt >= max_attempts:
                LOGGER.error(
                    "CRSP daily chunk %s failed after %d attempt(s): %s",
                    chunk.label, attempt, exc,
                )
                raise
            wait = retry_wait * attempt
            LOGGER.warning(
                "CRSP daily chunk %s failed (attempt %d/%d): %s; retrying in %.0fs",
                chunk.label, attempt, max_attempts, exc, wait,
            )
            if wait > 0:
                time.sleep(wait)
    raise AssertionError("unreachable")  # pragma: no cover


def _fetch_chunks(
    chunks: Sequence[DailyChunk],
    parts_dir: Path,
    session: _WRDSSession,
    sql_template: str,
    *,
    resume: bool,
    max_attempts: int,
    retry_wait: float,
) -> tuple[int, int]:
    """Stage every chunk as its own parquet part. Returns (rows, chunks fetched)."""
    total_rows = 0
    fetched = 0
    for chunk in chunks:
        part = parts_dir / chunk.part_name
        if resume and part.exists():
            try:
                # Opened by hand so a rejected part is not still held open by
                # pyarrow when we try to delete it (Windows).
                with part.open("rb") as handle:
                    rows = pq.ParquetFile(handle).metadata.num_rows
            except Exception as exc:  # noqa: BLE001 - unreadable part is just a missing one
                LOGGER.warning(
                    "Staged CRSP daily chunk %s is unreadable (%s); refetching it",
                    chunk.label, exc,
                )
                part.unlink()
            else:
                total_rows += rows
                LOGGER.info(
                    "CRSP daily chunk %s already staged (rows=%d); skipping",
                    chunk.label, rows,
                )
                continue

        sql = sql_template.format(start_date=chunk.start_date, end_date=chunk.end_date)
        LOGGER.debug("CRSP DSF SQL (chunk %s): %s", chunk.label, sql.strip())
        t0 = time.perf_counter()
        df = _run_chunk_query(
            session, sql, chunk, max_attempts=max_attempts, retry_wait=retry_wait
        )
        table = _chunk_to_arrow(df)
        del df
        _write_part(table, part)
        total_rows += table.num_rows
        fetched += 1
        LOGGER.info(
            "Fetched CRSP daily chunk %s: rows=%d in %.2fs -> %s",
            chunk.label, table.num_rows, time.perf_counter() - t0, part.name,
        )
        del table
    return total_rows, fetched


def _sql_literal(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _merge_parts(parts: Sequence[Path], destination: Path) -> None:
    """Concatenate the parts in chunk order, one row group at a time."""
    tmp = destination.with_name(destination.name + ".tmp")
    with pq.ParquetFile(parts[0]) as first:
        schema = first.schema_arrow
    writer = pq.ParquetWriter(tmp, schema)
    try:
        for part in parts:
            # Closed per part: an open handle would block the parts directory
            # from being removed on Windows.
            with pq.ParquetFile(part) as reader:
                for batch in reader.iter_batches(batch_size=_MERGE_BATCH_ROWS):
                    writer.write_batch(batch)
    finally:
        writer.close()
    os.replace(tmp, destination)


def _merge_parts_sorted(
    parts: Sequence[Path],
    destination: Path,
    *,
    order_by: Sequence[str],
    temp_dir: Path,
    memory_limit: str | None = DEFAULT_MERGE_MEMORY_LIMIT,
) -> None:
    """Concatenate the parts into one file ordered by ``order_by``, spilling to disk."""
    import duckdb

    tmp = destination.with_name(destination.name + ".tmp")
    files = ", ".join(_sql_literal(str(part)) for part in parts)
    con = duckdb.connect()
    try:
        con.execute(f"SET temp_directory = {_sql_literal(str(temp_dir))}")
        if memory_limit:
            con.execute(f"SET memory_limit = {_sql_literal(memory_limit)}")
        con.execute(
            f"COPY (SELECT {', '.join(DAILY_COLUMNS)} "
            f"FROM read_parquet([{files}]) "
            f"ORDER BY {', '.join(order_by)}) "
            f"TO {_sql_literal(str(tmp))} "
            f"(FORMAT PARQUET, ROW_GROUP_SIZE {_MERGE_ROW_GROUP_ROWS})"
        )
    finally:
        con.close()
    os.replace(tmp, destination)


def fetch_crsp_daily(
    config: AssayConfig,
    destination: Path,
    *,
    wrds_client: WRDSClient | None = None,
    source: CRSPSource | None = None,
    connect: Callable[[], Any] | None = None,
    years_per_chunk: int = DEFAULT_YEARS_PER_CHUNK,
    resume: bool = True,
    keep_parts: bool = False,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_wait: float = DEFAULT_RETRY_WAIT_S,
    sort_output: bool = True,
    merge_memory_limit: str | None = DEFAULT_MERGE_MEMORY_LIMIT,
) -> Path:
    """
    Download CRSP daily stock file (crsp.dsf) from WRDS into a Parquet file.

    This is a large dataset (~100x monthly): the 1925-2024 window is ~108M
    rows and the pull takes the best part of an hour. It is fetched one year
    range at a time, each range written to its own parquet part under
    ``<destination stem>_parts/`` before the parts are merged into
    ``destination``. Only one chunk is ever in memory, and a pull that dies
    part way through keeps the parts it finished — rerunning resumes from the
    first missing chunk instead of restarting the hour.

    Parameters
    ----------
    config : AssayConfig
        Configuration with sample window and WRDS credentials.
    destination : Path
        Output parquet file path.
    wrds_client : WRDSClient, optional
        Existing WRDS client to reuse.
    source : CRSPSource, optional
        Which CRSP tape to pull from. Defaults to ``config.crsp_format``. The
        source's name is stamped into the parts manifest, so parts staged from
        one tape are discarded rather than resumed against another.
    connect : callable, optional
        Zero-argument callable returning a context manager that yields
        something with ``raw_sql``. Defaults to the WRDS client's ``connect``;
        tests substitute a fake connection here.
    years_per_chunk : int, default 1
        Width of each chunk. Wider chunks mean fewer round trips and coarser
        resume granularity.
    resume : bool, default True
        Reuse parts staged by an earlier interrupted run. Parts written under
        a different sample window, chunk size or query are always discarded.
    keep_parts : bool, default False
        Leave the per-chunk parts on disk after a successful merge.
    max_attempts : int, default 3
        Attempts per chunk before giving up; the connection is reopened
        between attempts and the wait grows with the attempt number.
    sort_output : bool, default True
        Sort the merged file by ``(permno, date)``. Chunks arrive year-major,
        which is not the order a single pull returned; sorting keeps the
        staged file's order a property of the data rather than of the fetch.
    merge_memory_limit : str or None, default "4GB"
        Memory budget for the ordered merge, which spills the rest to the
        parts directory. ``None`` lets DuckDB use its own default (80% of
        RAM), which sorts the whole file in memory.

    Returns
    -------
    Path
        Path to the written parquet file.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    source = source or crsp_source_for(config)
    sql_template = source.daily_sql()

    chunks = plan_daily_chunks(config.sample_start, config.sample_end, years_per_chunk)
    parts_dir = daily_parts_dir(destination)
    manifest = _manifest_payload(chunks, sql_template, source.name)
    _prepare_parts_dir(parts_dir, manifest, resume=resume)

    reset = None
    if connect is None:
        client = wrds_client or WRDSClient(config.wrds_username)
        connect = client.connect
        reset = client.reconnect

    LOGGER.info(
        "Fetching CRSP daily (%s tape) from WRDS: sample=%s..%s in %d chunk(s) of <=%d year(s) -> %s",
        source.name,
        config.sample_start,
        config.sample_end,
        len(chunks),
        years_per_chunk,
        destination,
    )
    t0 = time.perf_counter()
    session = _WRDSSession(connect, reset)
    try:
        total_rows, fetched = _fetch_chunks(
            chunks,
            parts_dir,
            session,
            sql_template,
            resume=resume,
            max_attempts=max_attempts,
            retry_wait=retry_wait,
        )
    except Exception:
        staged = sum(1 for chunk in chunks if (parts_dir / chunk.part_name).exists())
        LOGGER.error(
            "CRSP daily fetch stopped with %d/%d chunk(s) staged in %s; "
            "rerunning the fetch resumes from the first missing chunk.",
            staged, len(chunks), parts_dir,
        )
        raise
    finally:
        session.close()

    LOGGER.info(
        "Fetched CRSP daily: rows=%d cols=%d chunks=%d (%d resumed) in %.2fs",
        total_rows, len(DAILY_COLUMNS), len(chunks), len(chunks) - fetched,
        time.perf_counter() - t0,
    )

    parts = [parts_dir / chunk.part_name for chunk in chunks]
    t1 = time.perf_counter()
    if sort_output:
        _merge_parts_sorted(
            parts,
            destination,
            order_by=DAILY_SORT_KEYS,
            temp_dir=parts_dir,
            memory_limit=merge_memory_limit,
        )
    else:
        _merge_parts(parts, destination)
    LOGGER.info(
        "Merged %d CRSP daily part(s) -> %s in %.2fs (sorted=%s)",
        len(parts), destination, time.perf_counter() - t1, sort_output,
    )

    _finish_parts_dir(parts_dir, manifest, keep_parts=keep_parts)

    try:
        LOGGER.info(
            "Wrote CRSP daily parquet: %s bytes=%d",
            destination, destination.stat().st_size,
        )
    except Exception:
        LOGGER.info("Wrote CRSP daily parquet: %s", destination)
    return destination


__all__ = [
    "CRSP_DAILY_SQL",
    "DAILY_COLUMNS",
    "DAILY_SCHEMA",
    "DailyChunk",
    "daily_parts_dir",
    "generate_placeholder_daily",
    "fetch_crsp_daily",
    "plan_daily_chunks",
]
