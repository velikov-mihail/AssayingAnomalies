"""
Orchestrates the DuckDB setup pipeline.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import logging.handlers
import os
from pathlib import Path
import time
from typing import Callable, List

import numpy as np
import pandas as pd
import requests

from .config import (
    DEMO_SAMPLE_END,
    LATEST_SAMPLE_END,
    LEGACY_CRSP_FORMAT,
    MEMORY_BUDGET_ENV,
    SAMPLE_END_RESOLVED_KEY,
    AssayConfig,
    SampleEndUnresolvedError,
    crsp_daily_rows,
    load_config,
    required_setup_ram_gb,
    machine_memory_gb,
    read_metadata_value,
    resolve_memory_budget_gb,
)
from .db.cache import FieldCatalog, save_field_catalog
from .db.manager import DuckDBManager
from .db.migrations import migrate_ts_data_monthly_dates_to_month_end
from .db.writer import write_table
from .ingest import crsp as crsp_ingest
from .ingest import crsp_daily as crsp_daily_ingest
from .ingest import compustat as compustat_ingest
from .ingest import cz_anomalies as cz_ingest
from .ingest import cz_release
from .ingest import ff_factors
from .ingest import gibbs as gibbs_input
from .ingest.crsp_source import CRSPSource, crsp_source_for, name_window_columns
from .ingest.sample_end import SampleEndResolution, resolve_latest_sample_end
from .ingest.wrds_client import WRDSClient, pgpass_save_path
from . import run_manifest
from .compustat_extras import EXTRA_FILES, persisted_extra_vars
from .provenance import (
    AmbiguousInputError,
    CREDENTIAL_HELP,
    DEMO_KEY,
    DemoDatabaseError,
    DownloadFailedError,
    MissingCredentialsError,
    MissingInputError,
    database_is_demo,
    mark_database_demo,
    missing_credentials_error,
    provenance_payload,
)
from .transforms import betas as betas_mod
from .transforms import compustat, crsp_daily, crsp_monthly, nmv_anomalies, tcosts

LOGGER = logging.getLogger("assayinganomalies.pipeline")
CRSP_RAW_FILE = "crsp_monthly_raw.parquet"
CRSP_DAILY_RAW_FILE = "crsp_daily_raw.parquet"
CRSP_DAILY_FACTORS_FILE = "ff_daily_factors.parquet"
# Full-universe monthly aggregates from the daily panel (incl. idiovol for
# every permno-month with daily data, not just ccm_panel rows) — MATLAB's
# dense matrices need this wider universe for tcosts NN-fill ranks.
CRSP_DAILY_MONTHLY_AGG_FILE = "crsp_daily_monthly_agg.parquet"
COMPUSTAT_ANNUAL_FILE = "compustat_funda_raw.parquet"
COMPUSTAT_QUARTERLY_FILE = "compustat_fundq_raw.parquet"
# Auxiliary staging filenames for the legacy SIZ tape. The live mapping is
# ``ctx.source.aux_raw_files`` -- this module-level copy is kept so external
# tooling that imports it still resolves, and always means SIZ.
CRSP_AUX_RAW = crsp_source_for("siz").aux_raw_files

# Columns of the raw daily staging file each consumer stage actually reads.
# `PipelineContext.daily_raw` prunes to these, so a stage that only ever looks
# at three of the thirteen columns stops copying, sorting and concatenating
# 108M rows of the other ten.
#
# compute-tcosts: Corwin-Schultz (prc, askhi, bidlo, cfacpr), Abdi-Ranaldo
# (prc, askhi, bidlo) and Kyle-Obizhaeva (ret, prc, vol).
DAILY_TCOST_COLUMNS: tuple[str, ...] = (
    "permno", "date", "ret", "prc", "vol", "bidlo", "askhi", "cfacpr",
)
# compute-betas: every estimator reduces the panel to (permno, date, ret).
DAILY_BETA_COLUMNS: tuple[str, ...] = ("permno", "date", "ret")

# Stages that read the daily staging parquet. The runners drop the shared
# panel once the last one in the plan has finished, so the ~10 GB frame does
# not sit resident through the rest of a build.
DAILY_PARQUET_STAGES: frozenset[str] = frozenset(
    {"transform-crsp-daily", "compute-tcosts", "compute-betas"}
)


@dataclass
class PipelineContext:
    config: AssayConfig
    db_path: Path
    staging_dir: Path
    full_refresh: bool
    # Build from deterministic synthetic stand-ins instead of WRDS and the CZ
    # zoo. Off by default: a production build that cannot reach its real
    # inputs raises rather than quietly substituting them. See `provenance`.
    demo: bool = False
    logger: logging.Logger = field(default_factory=lambda: LOGGER)
    # Which CRSP tape this build reads. Resolved from ``config.crsp_format``
    # when not passed; every stage goes through it rather than naming a WRDS
    # table or a raw CRSP column itself.
    source: CRSPSource | None = None
    stage_history: list[dict[str, str]] = field(default_factory=list)
    # ``sample_end`` as configured (a year or "latest"), and how the build
    # resolved it. `_preflight_sample_end` fills the resolution and replaces
    # ``config`` with a copy holding the year, so stages only see ints.
    sample_end_requested: int | str | None = None
    sample_end_resolution: SampleEndResolution | None = None
    _wrds_client: WRDSClient | None = None
    _daily_raw: pd.DataFrame | None = None
    _daily_raw_is_full: bool = False

    def __post_init__(self) -> None:
        if self.source is None:
            self.source = crsp_source_for(self.config)
        if self.sample_end_requested is None:
            self.sample_end_requested = self.config.sample_end
        self.db_path = self.db_path.expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.staging_dir.mkdir(parents=True, exist_ok=True)

    def daily_raw(self, columns: Sequence[str] | None = None) -> pd.DataFrame | None:
        """
        The raw CRSP daily panel, read from staging at most once per run.

        Three stages regress or aggregate the same ~108M-row staging file, and
        each used to re-read it and re-parse its 108M date strings. This keeps
        one normalized copy on the context instead.

        Normalization is limited to what all three consumers did identically
        anyway: lowercase column names, ``date`` parsed to datetime64 and
        ``permno`` cast to int. Nullable float columns are deliberately left
        alone — ``compute-tcosts`` runs its estimators on the ``Float64``
        columns as they come off the parquet and only coerces later, inside
        ``make_trading_costs``, while ``compute-betas`` coerces up front.
        Coercing here would silently move one of them.

        ``columns=None`` returns the full frame *by reference*; the caller must
        treat it as read-only. Naming columns returns a caller-owned copy of
        just those that exist in the file, which is what lets a caller mutate
        it (insert delisting rows, coerce dtypes) without disturbing the cache.
        Columns absent from the file are dropped rather than raising, so a
        placeholder extract behaves exactly as it did when each stage read the
        file itself.
        """
        path = self.staging_dir / CRSP_DAILY_RAW_FILE
        if not path.exists():
            return None

        want = None if columns is None else [c.lower() for c in columns]
        cached = set(self._daily_raw.columns) if self._daily_raw is not None else set()
        if want is None:
            need_read = self._daily_raw is None or not self._daily_raw_is_full
        else:
            need_read = self._daily_raw is None or not set(want) <= cached

        if need_read:
            read_cols = None if want is None else sorted(cached | set(want))
            t0 = time.perf_counter()
            self._daily_raw = _read_daily_staging(path, read_cols)
            self._daily_raw_is_full = want is None
            self.logger.info(
                "Read daily staging parquet %s: %d rows x %d cols in %.2fs",
                path.name,
                len(self._daily_raw),
                self._daily_raw.shape[1],
                time.perf_counter() - t0,
            )

        assert self._daily_raw is not None
        if want is None:
            return self._daily_raw
        present = [c for c in want if c in self._daily_raw.columns]
        return self._daily_raw[present].copy()

    def release_daily_raw(self) -> None:
        """Drop the shared daily panel once no remaining stage needs it."""
        if self._daily_raw is None:
            return
        self.logger.info("Releasing shared daily panel (%d rows)", len(self._daily_raw))
        self._daily_raw = None
        self._daily_raw_is_full = False

    def record_stage(
        self, name: str, status: str, message: str = "", hint: str = ""
    ) -> None:
        entry = {
            "name": name,
            "status": status,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if hint:
            entry["hint"] = hint
        self.stage_history.append(entry)

    def resolved_sample_end_record(self) -> SampleEndResolution | None:
        """The sample-end resolution, or an explicit one for an int config."""
        if self.sample_end_resolution is not None:
            return self.sample_end_resolution
        if self.config.sample_end_is_latest:
            return None
        return SampleEndResolution(
            requested=self.sample_end_requested,
            resolved=int(self.config.sample_end),
            source="explicit",
        )

    def persist_metadata(self) -> None:
        payload = {
            "refresh_completed_at": datetime.now(timezone.utc).isoformat(),
            "sample_start": self.config.sample_start,
            # The resolved year (never "latest"), so readers of this key keep
            # getting an int; what was requested is sample_end_requested.
            "sample_end": self.config.sample_end,
            "dom_com_eq": int(self.config.dom_com_eq),
            "crsp_format": self.source.name,
            "stage_history": self.stage_history,
        }
        resolution = self.resolved_sample_end_record()
        if resolution is not None:
            payload.update(resolution.as_metadata())
        # A demo run always stamps; a production run never clears a stamp it
        # did not earn. `setup_database` clears it on a full refresh, which is
        # the only run that rebuilds every table from scratch.
        if self.demo:
            payload[DEMO_KEY] = True
        with DuckDBManager(self.db_path) as manager:
            manager.execute(
                "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)"
            )
            for key, value in payload.items():
                serialized = value if isinstance(value, str) else json.dumps(value)
                manager.execute(
                    "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
                    key,
                    serialized,
                )

    def require_wrds_client(self, purpose: str) -> WRDSClient | None:
        """
        The WRDS client this stage needs, or None only in demo mode.

        Production is the strict path: no credentials means no data, and a
        stage that returns anyway would write a synthetic table into a
        database nothing marks as synthetic.
        So it raises instead, naming the stage and the remedies.

        ``demo=True`` is the opt-in that gets None back and falls through to
        this module's deterministic placeholder for ``purpose``.
        """
        client = self.get_wrds_client(prompt=True)
        if client is not None:
            return client
        if not self.demo:
            raise missing_credentials_error(purpose)
        self.logger.warning(
            "DEMO MODE: %s has no WRDS credentials; writing synthetic "
            "placeholder data. This database is stamped %s=true and is not "
            "research output.",
            purpose,
            DEMO_KEY,
        )
        return None

    def get_wrds_client(self, *, prompt: bool = True) -> WRDSClient | None:
        """
        Return a WRDS client with credentials available, or None if unavailable.

        - Uses env vars (WRDS_USERNAME/WRDS_PASSWORD) automatically.
        - Falls back to interactive prompting when allowed.
        - Returns None when credentials are missing. Stages go through
          :meth:`require_wrds_client`, which turns that into an error unless
          the run opted into demo mode.
        """
        if self._wrds_client is None:
            self._wrds_client = WRDSClient(self.config.wrds_username)
        if self._wrds_client.ensure_credentials(prompt=prompt):
            # If the user entered a username interactively, keep it on the config object for this run
            # so pipeline logging and downstream helpers can see it. We do not auto-persist to disk.
            self.config.wrds_username = self._wrds_client._get_username()  # type: ignore[attr-defined]
            return self._wrds_client
        return None

    def close_wrds(self) -> None:
        """Close the run's shared WRDS connection, if one was opened."""
        if self._wrds_client is not None:
            self._wrds_client.close()


# Stage status for a stage that raised NonFatalStageError.
NONFATAL_STATUS = "failed-nonfatal"


class NonFatalStageError(Exception):
    """
    A stage failed, but the database is usable without its output.

    :meth:`PipelineStage.run` records the stage as ``failed-nonfatal`` and the
    build goes on; ``setup_database`` lists such stages, with ``hint`` (what
    the user can do about it), once every stage has run.
    """

    def __init__(self, message: str, *, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


@dataclass
class PipelineStage:
    name: str
    func: Callable[[PipelineContext], None]

    def run(self, ctx: PipelineContext) -> None:
        t0 = time.perf_counter()
        ctx.logger.info("Starting stage %s", self.name)
        try:
            self.func(ctx)
        except NonFatalStageError as exc:
            # The build goes on; `setup_database` lists these at the end.
            ctx.record_stage(self.name, NONFATAL_STATUS, str(exc), exc.hint)
            ctx.logger.warning(
                "Stage %s did not complete after %.2fs; the build continues "
                "without it.\n%s%s",
                self.name,
                time.perf_counter() - t0,
                exc,
                f"\n{exc.hint}" if exc.hint else "",
            )
            ctx.logger.debug("Stage %s traceback", self.name, exc_info=True)
        except Exception as exc:  # pragma: no cover - defensive logging
            ctx.record_stage(self.name, "failed", str(exc))
            ctx.logger.exception("Stage %s failed after %.2fs", self.name, time.perf_counter() - t0)
            raise
        else:
            ctx.record_stage(self.name, "succeeded")
            ctx.logger.info("Completed stage %s in %.2fs", self.name, time.perf_counter() - t0)


def _fmt_bytes(n: int | float | None) -> str:
    if n is None or not pd.notna(n):
        return "n/a"
    n = float(n)
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while n >= 1024 and i < len(units) - 1:
        n /= 1024
        i += 1
    if i == 0:
        return f"{int(n)} {units[i]}"
    return f"{n:.2f} {units[i]}"


def _read_daily_staging(
    path: Path, columns: Sequence[str] | None = None
) -> pd.DataFrame:
    """
    Read the raw daily staging parquet, optionally only some of its columns.

    ``columns`` are matched case-insensitively against the file's own names so
    a caller can ask for the lowercase names the transforms use regardless of
    how the extract was written, and names the file does not have are ignored.
    """
    read_cols: list[str] | None = None
    if columns is not None:
        import pyarrow.parquet as pq

        by_lower = {name.lower(): name for name in pq.ParquetFile(path).schema.names}
        read_cols = [by_lower[c] for c in dict.fromkeys(columns) if c in by_lower]

    df = pd.read_parquet(path, columns=read_cols)
    df.columns = df.columns.str.lower()
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"])
    if "permno" in df.columns:
        df["permno"] = df["permno"].astype(int)
    return df


# Moved to ``ingest.crsp_source`` alongside the tape that defines the name
# windows; re-exported here for callers that still import it from pipeline.
_name_window_columns = name_window_columns


def _df_brief(df: pd.DataFrame, *, name: str) -> str:
    cols = list(df.columns)
    head_cols = cols[:8]
    more = "" if len(cols) <= 8 else f", ... (+{len(cols) - 8} more)"
    return f"{name}: shape={df.shape}, cols={head_cols}{more}"


def _configure_setup_logging(*, db_path: Path, verbose: bool = False) -> None:
    """
    Ensure the setup pipeline emits useful logs without requiring the caller to configure logging.

    We configure *only* the `assayinganomalies` logger family to avoid surprising global changes.
    """
    root = logging.getLogger("assayinganomalies")
    if root.handlers:
        return

    level = logging.DEBUG if verbose else logging.INFO
    root.setLevel(level)

    # Console output should be easy to read (no " | INFO | ... | " noise),
    # but we keep the detailed format in the file log for debugging.
    console_fmt = logging.Formatter(
        fmt="%(asctime)s %(message)s",
        datefmt="%H:%M:%S",
    )
    file_fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sh = logging.StreamHandler()
    sh.setLevel(level)
    sh.setFormatter(console_fmt)
    # Avoid duplicating the explicit `[i/9] ...` progress prints (and other
    # records logged with extra={"printed": True}) in the console. Keep them in
    # the file log for debugging/auditability.
    sh.addFilter(
        lambda record: not str(record.getMessage()).startswith("[")
        and not getattr(record, "printed", False)
    )
    root.addHandler(sh)

    try:
        log_dir = db_path.parent / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            log_dir / "setup_database.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        fh.setLevel(level)
        fh.setFormatter(file_fmt)
        root.addHandler(fh)
    except Exception:  # pragma: no cover - logging should never break setup
        pass


def _stage_initialize_database(ctx: PipelineContext) -> None:
    ctx.logger.debug("Ensuring DuckDB at %s (full_refresh=%s)", ctx.db_path, ctx.full_refresh)
    with DuckDBManager(ctx.db_path) as manager:
        kept_cz_release = None
        if ctx.full_refresh:
            kept_cz_release = _cz_release_to_keep(manager.connection)
            manager.execute("DROP TABLE IF EXISTS metadata")
        manager.execute(
            "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)"
        )
        if kept_cz_release is not None:
            # The row describes cz_anomalies, which stays until the C-Z stage
            # replaces it and rewrites the key; an interrupted full refresh
            # must not leave the zoo without its release.
            manager.execute(
                "INSERT INTO metadata (key, value) VALUES (?, ?)",
                CZ_RELEASE_KEY,
                kept_cz_release,
            )
            ctx.logger.info("Full refresh: kept the C-Z release record of the existing zoo")
        elif ctx.full_refresh:
            ctx.logger.info("Full refresh: no C-Z release record to keep")

    # Run lightweight idempotent migrations on existing DBs (safe no-ops on fresh DBs).
    # Keep this outside the manager context above so each migration can manage its own checks.
    migrate_ts_data_monthly_dates_to_month_end(ctx.db_path)
    try:
        sz = ctx.db_path.stat().st_size if ctx.db_path.exists() else 0
        ctx.logger.info("DuckDB ready: %s (%s)", ctx.db_path, _fmt_bytes(sz))
    except Exception:
        ctx.logger.info("DuckDB ready: %s", ctx.db_path)


def _cz_release_to_keep(con) -> str | None:
    """The stored ``cz_release`` value if ``cz_anomalies`` still exists, else ``None``."""
    tables = {
        str(r[0])
        for r in con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name IN ('metadata', 'cz_anomalies')"
        ).fetchall()
    }
    if tables != {"metadata", "cz_anomalies"}:
        return None
    row = con.execute(
        "SELECT value FROM metadata WHERE key = ?", [CZ_RELEASE_KEY]
    ).fetchone()
    return row[0] if row and row[0] else None


def _stage_generate_field_catalog(ctx: PipelineContext) -> None:
    fields = {
        "ret": "ret",
        "me": "me",
        "date": "date",
        "dates": "date",
        "permno": "permno",
        "NYSE": "nyse_flag",
    }
    save_field_catalog(ctx.db_path, FieldCatalog(fields=fields))
    ctx.logger.info("Field catalog updated (%d aliases).", len(fields))


def _stage_fetch_crsp_monthly(ctx: PipelineContext) -> None:
    dest = ctx.staging_dir / CRSP_RAW_FILE
    t0 = time.perf_counter()
    client = ctx.require_wrds_client("Fetching the CRSP monthly stock file")
    # Demo runs only: a deterministic synthetic stand-in for crsp.msf.
    if client is None:
        df = ctx.source.placeholder_monthly(ctx.config)
        df.to_parquet(dest, index=False)
        ctx.logger.info(
            "Staged CRSP monthly placeholder -> %s (%s) in %.2fs; %s",
            dest,
            _fmt_bytes(dest.stat().st_size if dest.exists() else 0),
            time.perf_counter() - t0,
            _df_brief(df, name="crsp_msf_raw"),
        )
        return
    crsp_ingest.fetch_crsp_monthly(
        ctx.config, dest, wrds_client=client, source=ctx.source
    )
    ctx.logger.info(
        "Staged CRSP monthly WRDS extract -> %s (%s) in %.2fs",
        dest,
        _fmt_bytes(dest.stat().st_size if dest.exists() else 0),
        time.perf_counter() - t0,
    )


def _stage_load_crsp_msf(ctx: PipelineContext) -> None:
    path = ctx.staging_dir / CRSP_RAW_FILE
    t0 = time.perf_counter()
    raw = pd.read_parquet(path)
    write_table(ctx.db_path, "crsp_msf", raw, mode="replace")
    ctx.logger.info(
        "Loaded table crsp_msf from %s in %.2fs; %s",
        path,
        time.perf_counter() - t0,
        _df_brief(raw, name="crsp_msf"),
    )


def _stage_fetch_crsp_aux(ctx: PipelineContext) -> None:
    client = ctx.require_wrds_client("Fetching the CRSP auxiliary tables")
    # DuckDB cannot register a DataFrame with 0 columns, so a demo run still
    # needs a minimal schema per table; rows remain empty.
    schemas = ctx.source.placeholder_aux_schemas()
    for table, fname in ctx.source.aux_raw_files.items():
        dest = ctx.staging_dir / fname
        t0 = time.perf_counter()
        # Demo runs only: an empty table with the right columns.
        if client is None:
            cols = schemas.get(table, {"placeholder": "int64"})
            placeholder = pd.DataFrame({c: pd.Series(dtype=dt) for c, dt in cols.items()})
            placeholder.to_parquet(dest, index=False)
            ctx.logger.info(
                "Staged CRSP aux placeholder %s -> %s (%s) in %.2fs; %s",
                table,
                dest,
                _fmt_bytes(dest.stat().st_size if dest.exists() else 0),
                time.perf_counter() - t0,
                _df_brief(placeholder, name=table),
            )
            continue
        crsp_ingest.fetch_crsp_aux_table(
            table, dest, wrds_client=client, source=ctx.source
        )
        ctx.logger.info(
            "Staged CRSP aux WRDS extract %s -> %s (%s) in %.2fs",
            table,
            dest,
            _fmt_bytes(dest.stat().st_size if dest.exists() else 0),
            time.perf_counter() - t0,
        )


def _stage_transform_crsp_monthly(ctx: PipelineContext) -> None:
    path = ctx.staging_dir / CRSP_RAW_FILE
    t0 = time.perf_counter()
    raw = pd.read_parquet(path)
    aux = {
        name: pd.read_parquet(ctx.staging_dir / fname)
        for name, fname in ctx.source.aux_raw_files.items()
    }
    ctx.logger.info(
        "Transform inputs (%s tape): %s; aux=%s",
        ctx.source.name,
        _df_brief(raw, name="crsp_msf_raw"),
        {k: tuple(v.shape) for k, v in aux.items()},
    )
    # Map the tape's raw columns onto the canonical ones the transform reads.
    # A no-op under SIZ, whose column names are the canonical names.
    raw = ctx.source.normalize_monthly(raw, aux=aux)
    panel = crsp_monthly.transform_monthly(raw, ctx.config, aux=aux, source=ctx.source)
    write_table(ctx.db_path, "ccm_panel", panel, mode="replace")
    ctx.logger.info(
        "Built table ccm_panel in %.2fs; %s",
        time.perf_counter() - t0,
        _df_brief(panel, name="ccm_panel"),
    )


def _stage_load_crsp_aux(ctx: PipelineContext) -> None:
    for table, fname in ctx.source.aux_raw_files.items():
        path = ctx.staging_dir / fname
        t0 = time.perf_counter()
        df = pd.read_parquet(path)
        write_table(ctx.db_path, table, df, mode="replace")
        ctx.logger.info(
            "Loaded table %s from %s in %.2fs; %s",
            table,
            path,
            time.perf_counter() - t0,
            _df_brief(df, name=table),
        )


def _stage_fetch_crsp_daily(ctx: PipelineContext) -> None:
    """Fetch CRSP daily stock file (crsp.dsf) from WRDS."""
    dest = ctx.staging_dir / CRSP_DAILY_RAW_FILE
    t0 = time.perf_counter()
    client = ctx.require_wrds_client("Fetching the CRSP daily stock file")
    if client is None:
        df = ctx.source.placeholder_daily(ctx.config)
        df.to_parquet(dest, index=False)
        ctx.logger.info(
            "Staged CRSP daily placeholder -> %s (%s) in %.2fs; %s",
            dest,
            _fmt_bytes(dest.stat().st_size if dest.exists() else 0),
            time.perf_counter() - t0,
            _df_brief(df, name="crsp_dsf_raw"),
        )
        return
    crsp_daily_ingest.fetch_crsp_daily(
        ctx.config, dest, wrds_client=client, source=ctx.source
    )
    ctx.logger.info(
        "Staged CRSP daily WRDS extract -> %s (%s) in %.2fs",
        dest,
        _fmt_bytes(dest.stat().st_size if dest.exists() else 0),
        time.perf_counter() - t0,
    )


def _stage_load_crsp_dsf(ctx: PipelineContext) -> None:
    """Load raw CRSP daily data into DuckDB."""
    path = ctx.staging_dir / CRSP_DAILY_RAW_FILE
    if not path.exists():
        ctx.logger.warning("CRSP daily file %s not found; skipping", path)
        return
    t0 = time.perf_counter()
    raw = pd.read_parquet(path)
    write_table(ctx.db_path, "crsp_dsf", raw, mode="replace")
    ctx.logger.info(
        "Loaded table crsp_dsf from %s in %.2fs; %s",
        path,
        time.perf_counter() - t0,
        _df_brief(raw, name="crsp_dsf"),
    )


def _stage_fetch_ff_daily(ctx: PipelineContext) -> None:
    """Fetch Fama-French daily factors from WRDS."""
    dest = ctx.staging_dir / CRSP_DAILY_FACTORS_FILE
    t0 = time.perf_counter()
    client = ctx.require_wrds_client("Fetching the Fama-French daily factors")
    if client is None:
        # Demo runs only: 2 trading days of synthetic daily factors.
        df = pd.DataFrame({
            "date": pd.to_datetime([
                f"{ctx.config.sample_start}-01-03",
                f"{ctx.config.sample_start}-01-04",
            ]),
            "mktrf": [0.005, -0.003],
            "smb": [0.001, -0.001],
            "hml": [0.002, 0.0],
            "rf": [0.0001, 0.0001],
            "umd": [0.001, 0.002],
        })
    else:
        df = ff_factors.fetch_ff_daily(ctx.config, wrds_client=client)
    df.to_parquet(dest, index=False)
    ctx.logger.info(
        "Staged FF daily factors -> %s (%s) in %.2fs; %s",
        dest,
        _fmt_bytes(dest.stat().st_size if dest.exists() else 0),
        time.perf_counter() - t0,
        _df_brief(df, name="ff_daily"),
    )


def _stage_transform_crsp_daily(ctx: PipelineContext) -> None:
    """Compute CRSP daily derived variables and aggregate to monthly."""
    t0 = time.perf_counter()
    # Read-only: `transform_daily` copies before it normalizes, which is what
    # keeps the shared panel intact for compute-tcosts and compute-betas.
    raw = ctx.daily_raw()
    if raw is None:
        ctx.logger.warning("CRSP daily raw not found; skipping daily transforms")
        return

    # Load delisting events from aux tables (already staged). Only a tape
    # whose daily returns exclude the delisting payoff needs them.
    delist = None
    if ctx.source.apply_delisting_overlay:
        delist_path = ctx.staging_dir / ctx.source.aux_raw_files.get("msedelist", "")
        if delist_path.exists():
            delist = pd.read_parquet(delist_path)
    else:
        ctx.logger.info(
            "Daily delisting overlay off (%s tape): ret_adj == ret",
            ctx.source.name,
        )

    # Load daily factors if available
    factors_path = ctx.staging_dir / CRSP_DAILY_FACTORS_FILE
    factors = None
    if factors_path.exists():
        factors = pd.read_parquet(factors_path)

    ctx.logger.info(
        "Transform daily inputs: raw=%s, delist=%s, factors=%s",
        raw.shape,
        delist.shape if delist is not None else None,
        factors.shape if factors is not None else None,
    )

    # Run daily transforms
    daily_panel = crsp_daily.transform_daily(raw, ctx.config, delist=delist, factors=factors)

    # Write full daily panel to DuckDB
    write_table(ctx.db_path, "crsp_daily_panel", daily_panel, mode="replace")
    ctx.logger.info(
        "Built table crsp_daily_panel in %.2fs; %s",
        time.perf_counter() - t0,
        _df_brief(daily_panel, name="crsp_daily_panel"),
    )

    # Aggregate daily vars to monthly and merge into ccm_panel.
    # Need monthly exchcd for Gao-Ritter NASDAQ volume adjustment and
    # monthly prc for the Amihud price filter (MATLAB prc.mat).
    exchcd_df = None
    monthly_prc_df = None
    with DuckDBManager(ctx.db_path) as manager:
        tables = manager.query_df(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'ccm_panel'"
        )
        if not tables.empty:
            cols = manager.query_df(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'ccm_panel'"
            )["column_name"].tolist()
            # One scan for both columns rather than one scan each.
            wanted = [c for c in ("exchcd", "prc") if c in cols]
            if wanted:
                monthly = manager.query_df(
                    f"SELECT permno, date, {', '.join(wanted)} FROM ccm_panel"
                )
                monthly["date"] = pd.to_datetime(monthly["date"])
                if "exchcd" in wanted:
                    exchcd_df = monthly[["permno", "date", "exchcd"]].copy()
                if "prc" in wanted:
                    monthly_prc_df = monthly[["permno", "date", "prc"]].copy()
                del monthly

    # MATLAB's monthly aggregates (RVOL/amihud/IVOL/dretmax) are computed
    # from the dense dret matrix: raw returns with dlret placed as separate
    # rows (makeCRSPDailyDerivedVariables.m:62-109) — NOT ret_adj, which
    # folds dlret into the last trading day. Drop ret_adj so _ret_col picks
    # ret, then insert the placement rows.
    agg_input = daily_panel.drop(columns=["ret_adj"], errors="ignore")
    agg_input = _place_dlret_rows(ctx, agg_input, factors, what="monthly aggregates")

    monthly_agg = crsp_daily.aggregate_daily_to_monthly(
        agg_input, factors=factors, exchcd=exchcd_df, monthly_prc=monthly_prc_df,
    )

    # Persist the full monthly universe (ccm_panel merge below is a left join
    # that drops permno-months without panel rows; tcosts NN-fill needs all).
    agg_dest = ctx.staging_dir / CRSP_DAILY_MONTHLY_AGG_FILE
    monthly_agg.to_parquet(agg_dest, index=False)
    ctx.logger.info(
        "Wrote full-universe monthly aggregates to %s (%d rows)",
        agg_dest, len(monthly_agg),
    )

    with DuckDBManager(ctx.db_path) as manager:
        tables = manager.query_df(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'ccm_panel'"
        )
        if tables.empty:
            ctx.logger.warning("ccm_panel not found; skipping daily-to-monthly merge")
            # Still write the daily factors to ts_data
            if factors is not None and not factors.empty:
                write_table(ctx.db_path, "ts_data_daily", factors, mode="replace")
            return
        ccm_panel = manager.query_df("SELECT * FROM ccm_panel")

    ccm_panel["date"] = pd.to_datetime(ccm_panel["date"])
    monthly_agg["date"] = pd.to_datetime(monthly_agg["date"])

    # Drop stale daily-derived columns so rebuilds replace them
    daily_cols = [c for c in monthly_agg.columns if c not in ("permno", "date")]
    stale = [c for c in daily_cols if c in ccm_panel.columns]
    if stale:
        ctx.logger.info("Dropping stale daily-derived columns before merge: %s", stale)
        ccm_panel = ccm_panel.drop(columns=stale)

    merged = ccm_panel.merge(
        monthly_agg[["permno", "date"] + daily_cols],
        on=["permno", "date"],
        how="left",
        suffixes=("", "_daily"),
    )
    write_table(ctx.db_path, "ccm_panel", merged, mode="replace")
    ctx.logger.info(
        "Merged daily aggregates into ccm_panel: added columns %s",
        daily_cols,
    )

    # Write daily factors to ts_data_daily
    if factors is not None and not factors.empty:
        write_table(ctx.db_path, "ts_data_daily", factors, mode="replace")
        ctx.logger.info("Loaded table ts_data_daily: %d rows", len(factors))


COMPUSTAT_FETCH_STAGES = ("fetch-compustat-annual", "fetch-compustat-quarterly")


def _compustat_variables_file(ctx: PipelineContext) -> Path | None:
    """The variable-list CSV ``compustat_variables`` names; None for 'All'."""
    return compustat_ingest.resolve_variables_file(
        ctx.config.compustat_variables,
        lambda name: _find_input_file(ctx, name, "Compustat variable list"),
    )


def _compustat_variables(ctx: PipelineContext, freq: str) -> list[str] | str:
    """
    The ``freq`` ('annual' or 'quarterly') variables the fetch passes to WRDS.

    Read from the CSV ``AssayConfig.compustat_variables`` names (the packaged
    ``compustat_variables.csv`` by default, which reproduces ``ANNUAL_VARS`` /
    ``QUARTERLY_VARS``), or ``'All'`` for every column, as in MATLAB's
    ``getCOMPUSTATQuery.m``.
    """
    path = _compustat_variables_file(ctx)
    if path is None:
        ctx.logger.info("Compustat %s variables: All (select *)", freq)
        return compustat_ingest.ALL_VARIABLES
    run_manifest.note_input(path, "compustat_variables")
    names = compustat_ingest.read_variables_file(path)[freq]
    ctx.logger.info("Compustat %s variables: %d from %s", freq, len(names), path)
    # Columns `aa add-compustat-vars` added to this database are fetched too,
    # so the transform carries them again.
    extras = [n for n in persisted_extra_vars(ctx.db_path)[freq] if n not in names]
    if extras:
        ctx.logger.info(
            "Compustat %s variables: plus %d added with add-compustat-vars: %s",
            freq, len(extras), extras,
        )
        names = [*names, *extras]
    return names


def _preflight_compustat_variables(ctx: PipelineContext, planned: Sequence[str]) -> None:
    """
    Read the Compustat variable list before the first stage runs.

    The Compustat fetch comes after the CRSP downloads, so a mistyped path or a
    CSV without the Annual/Quarterly columns fails now instead. Demo runs skip
    this: they never fetch Compustat.
    """
    if ctx.demo or not any(s in planned for s in COMPUSTAT_FETCH_STAGES):
        return
    path = _compustat_variables_file(ctx)
    if path is not None:
        compustat_ingest.read_variables_file(path)


def _stage_fetch_compustat_annual(ctx: PipelineContext) -> None:
    """Fetch COMPUSTAT annual fundamentals (funda) from WRDS."""
    dest = ctx.staging_dir / COMPUSTAT_ANNUAL_FILE
    t0 = time.perf_counter()
    client = ctx.require_wrds_client("Fetching COMPUSTAT annual fundamentals")

    if client is None:
        # Demo runs only: a deterministic synthetic stand-in for funda.
        df = compustat_ingest.generate_placeholder_annual(ctx.config)
        df.to_parquet(dest, index=False)
        ctx.logger.info(
            "Staged COMPUSTAT annual placeholder -> %s (%s) in %.2fs; %s",
            dest,
            _fmt_bytes(dest.stat().st_size if dest.exists() else 0),
            time.perf_counter() - t0,
            _df_brief(df, name="compustat_funda"),
        )
        return

    compustat_ingest.fetch_compustat_annual(
        ctx.config, dest, wrds_client=client,
        variables=_compustat_variables(ctx, "annual"),
    )
    ctx.logger.info(
        "Staged COMPUSTAT annual WRDS extract -> %s (%s) in %.2fs",
        dest,
        _fmt_bytes(dest.stat().st_size if dest.exists() else 0),
        time.perf_counter() - t0,
    )


def _stage_fetch_compustat_quarterly(ctx: PipelineContext) -> None:
    """Fetch COMPUSTAT quarterly fundamentals (fundq) from WRDS."""
    dest = ctx.staging_dir / COMPUSTAT_QUARTERLY_FILE
    t0 = time.perf_counter()
    client = ctx.require_wrds_client("Fetching COMPUSTAT quarterly fundamentals")

    if client is None:
        # Demo runs only: a deterministic synthetic stand-in for fundq.
        df = compustat_ingest.generate_placeholder_quarterly(ctx.config)
        df.to_parquet(dest, index=False)
        ctx.logger.info(
            "Staged COMPUSTAT quarterly placeholder -> %s (%s) in %.2fs; %s",
            dest,
            _fmt_bytes(dest.stat().st_size if dest.exists() else 0),
            time.perf_counter() - t0,
            _df_brief(df, name="compustat_fundq"),
        )
        return

    compustat_ingest.fetch_compustat_quarterly(
        ctx.config, dest, wrds_client=client,
        variables=_compustat_variables(ctx, "quarterly"),
    )
    ctx.logger.info(
        "Staged COMPUSTAT quarterly WRDS extract -> %s (%s) in %.2fs",
        dest,
        _fmt_bytes(dest.stat().st_size if dest.exists() else 0),
        time.perf_counter() - t0,
    )


def _stage_load_compustat(ctx: PipelineContext) -> None:
    """Load raw COMPUSTAT data into DuckDB tables."""
    for name, fname in [("compustat_funda", COMPUSTAT_ANNUAL_FILE), ("compustat_fundq", COMPUSTAT_QUARTERLY_FILE)]:
        path = ctx.staging_dir / fname
        if not path.exists():
            ctx.logger.warning("COMPUSTAT file %s not found; skipping", path)
            continue
        t0 = time.perf_counter()
        df = pd.read_parquet(path)
        write_table(ctx.db_path, name, df, mode="replace")
        ctx.logger.info(
            "Loaded table %s from %s in %.2fs; %s",
            name,
            path,
            time.perf_counter() - t0,
            _df_brief(df, name=name),
        )


def _read_ccm_link(ctx: PipelineContext, mgr: DuckDBManager) -> pd.DataFrame | None:
    """The cleaned CCM link, for the stages that link Compustat after the transform.

    Reads ``ccm_link`` (written by ``transform-compustat``). A database built
    before that table existed falls back to the raw ``ccmxpf_lnkhist`` table
    (cleaned here, with a warning), then to the staging parquet. None when
    there is no link anywhere.
    """
    tables = set(mgr.query_df(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name IN ('ccm_link', 'ccmxpf_lnkhist')"
    )["table_name"])
    if "ccm_link" in tables:
        return mgr.query_df("SELECT * FROM ccm_link")
    if "ccmxpf_lnkhist" in tables:
        ctx.logger.warning(
            "ccm_link not found; cleaning the raw ccmxpf_lnkhist table instead. "
            "Rebuild transform-compustat to write ccm_link."
        )
        return compustat.clean_ccm_link(
            mgr.query_df("SELECT * FROM ccmxpf_lnkhist"), ctx.config
        )
    link_path = ctx.staging_dir / ctx.source.aux_raw_files["ccmxpf_lnkhist"]
    if link_path.exists():
        ctx.logger.warning(
            "ccm_link not found; cleaning the staged link extract %s instead. "
            "Rebuild transform-compustat to write ccm_link.",
            link_path,
        )
        return compustat.clean_ccm_link(pd.read_parquet(link_path), ctx.config)
    return None


def _with_extra_columns(
    ctx: PipelineContext,
    frame: pd.DataFrame,
    names: Sequence[str],
    file: str,
    keys: Sequence[str],
) -> pd.DataFrame:
    """
    ``frame`` with every column of ``names`` it lacks, taken from staging ``file``.

    ``names`` are the recorded ``add-compustat-vars`` columns. A build whose
    main extract predates them (``--start-from`` a later stage, a scoped
    rebuild) takes them from the command's own extract, matched on ``keys``.
    A column found in neither is added empty, with a warning, so the panel
    never keeps a stale copy of it.
    """
    lower = {str(c).lower() for c in frame.columns}
    missing = [n for n in names if n not in lower]
    if not missing:
        return frame
    frame = frame.copy()
    frame.columns = [str(c).lower() for c in frame.columns]
    path = ctx.staging_dir / file
    found: list[str] = []
    if path.exists():
        extra = pd.read_parquet(path)
        extra.columns = [str(c).lower() for c in extra.columns]
        found = [n for n in missing if n in extra.columns]
        join = [k for k in keys if k in extra.columns and k in frame.columns]
        if found and join:
            extra = extra[[*join, *found]].copy()
            for k in join:
                if k in ("datadate", "rdq"):
                    extra[k] = pd.to_datetime(extra[k])
                    frame[k] = pd.to_datetime(frame[k])
                elif k == "gvkey":
                    extra[k] = extra[k].astype(str)
                    frame[k] = frame[k].astype(str)
            extra = extra.drop_duplicates(subset=join, keep="last")
            frame = frame.merge(extra, on=join, how="left", validate="many_to_one")
            run_manifest.note_input(path, "compustat extra")
            ctx.logger.info("Took %s from %s", found, path.name)
        else:
            found = []
    for name in missing:
        if name not in found:
            ctx.logger.warning(
                "Compustat column %r (added with add-compustat-vars) is in neither the "
                "build's extract nor %s; it is left empty. Run "
                "`aa add-compustat-vars` for it again, or rebuild from the fetch stages.",
                name, file,
            )
            frame[name] = float("nan")
    return frame


def _stage_transform_compustat(ctx: PipelineContext) -> None:
    """
    Merge COMPUSTAT with CRSP (via CCM link) and compute derived variables.

    This stage:
    1. Cleans the CCM link (ccmxpf_lnkhist) and writes it as ``ccm_link``
    2. Links COMPUSTAT gvkey to CRSP permno through it
    3. Aligns annual data to monthly calendar (FYE -> June of following year)
    4. Computes book equity, book-to-market, and other derived variables
    5. Merges derived variables into ccm_panel

    ``ccm_link`` is written even when the Compustat extract or ccm_panel is
    missing, so the link is in the database whenever its extract is staged.
    """
    t0 = time.perf_counter()

    link_path = ctx.staging_dir / ctx.source.aux_raw_files["ccmxpf_lnkhist"]
    if not link_path.exists():
        ctx.logger.warning("CCM link table not found; skipping COMPUSTAT transform")
        return

    link = compustat.clean_ccm_link(pd.read_parquet(link_path), ctx.config)
    write_table(ctx.db_path, "ccm_link", link, mode="replace")
    ctx.logger.info("Built table ccm_link; %s", _df_brief(link, name="ccm_link"))

    # Load required data
    funda_path = ctx.staging_dir / COMPUSTAT_ANNUAL_FILE
    if not funda_path.exists():
        ctx.logger.warning("COMPUSTAT annual not found; skipping transform")
        return

    funda = pd.read_parquet(funda_path)
    extras = persisted_extra_vars(ctx.db_path)
    if extras["annual"] or extras["quarterly"]:
        ctx.logger.info("Compustat columns added with add-compustat-vars: %s", extras)
    funda = _with_extra_columns(
        ctx, funda, extras["annual"], EXTRA_FILES["annual"], ("gvkey", "datadate"),
    )

    # Load ccm_panel to merge derived variables
    with DuckDBManager(ctx.db_path) as manager:
        tables = manager.query_df(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'ccm_panel'"
        )
        if tables.empty:
            ctx.logger.warning("ccm_panel not found; skipping COMPUSTAT merge")
            return
        ccm_panel = manager.query_df("SELECT * FROM ccm_panel")

    # Load quarterly data if available
    fundq_path = ctx.staging_dir / COMPUSTAT_QUARTERLY_FILE
    fundq = None
    if fundq_path.exists():
        fundq = pd.read_parquet(fundq_path)
        ctx.logger.info("Loaded COMPUSTAT quarterly: %s", fundq.shape)
        fundq = _with_extra_columns(
            ctx, fundq, extras["quarterly"], EXTRA_FILES["quarterly"],
            ("gvkey", "datadate", "rdq"),
        )

    ctx.logger.info(
        "Transform inputs: funda=%s, link=%s, ccm_panel=%s, fundq=%s",
        funda.shape, link.shape, ccm_panel.shape,
        fundq.shape if fundq is not None else None,
    )

    # Perform the merge and compute derived variables
    merged = compustat.merge_compustat_crsp(
        funda, link, ccm_panel, ctx.config,
        fundq=fundq,
        extra_annual=extras["annual"],
        extra_quarterly=extras["quarterly"],
    )

    # Update ccm_panel with the merged data
    write_table(ctx.db_path, "ccm_panel", merged, mode="replace")
    if merged is not ccm_panel:
        _record_annual_layout(ctx.db_path)
    ctx.logger.info(
        "Updated ccm_panel with COMPUSTAT variables in %.2fs; %s",
        time.perf_counter() - t0,
        _df_brief(merged, name="ccm_panel"),
    )


def _record_annual_layout(db_path: Path) -> None:
    """Record in ``metadata`` that ``ccm_panel`` holds annual columns in June only.

    Written by the stage that writes those columns. ``aa.load`` and
    ``aa add-compustat-vars`` refuse a database without the record
    (:func:`data_access.require_june_annual_layout`): its annual columns are
    filled June to May.
    """
    with DuckDBManager(db_path) as manager:
        manager.execute(
            "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)"
        )
        manager.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            compustat.ANNUAL_LAYOUT_KEY,
            json.dumps(compustat.ANNUAL_LAYOUT_JUNE),
        )


def has_june_annual_layout(db_path: str | Path) -> bool:
    """Whether ``db_path`` records June-only annual columns (:func:`_record_annual_layout`).

    Read on a connection of its own, opened like the build's, so it works
    while ``aa.load`` holds its kept-alive connection in the same process
    (a read-only connection would be refused there and look like no record).
    """
    with DuckDBManager(Path(db_path)) as manager:
        has_table = manager.query_df(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'metadata'"
        )
        if has_table.empty:
            return False
        rows = manager.query_df(
            f"SELECT value FROM metadata WHERE key = '{compustat.ANNUAL_LAYOUT_KEY}'"
        )
    if rows.empty:
        return False
    return rows["value"].iloc[0] == json.dumps(compustat.ANNUAL_LAYOUT_JUNE)


# Folders a whole-folder search for an input file does not enter: the
# protocol's output tree, and (below) every folder whose name starts with a
# dot, which covers a project's own ``.venv`` and ``.git``.
_INPUT_SEARCH_SKIP_DIRS = frozenset({"Scratch"})


def _walk_for_input(root: Path, pattern: str, skip: Sequence[Path] = ()) -> list[Path]:
    """Every file under ``root`` whose name matches ``pattern``, sorted.

    Folders named in :data:`_INPUT_SEARCH_SKIP_DIRS`, folders whose name starts
    with a dot, and the folders in ``skip`` (already searched) are not entered.
    """
    import fnmatch

    if not root.is_dir():
        return []
    skipped = {p.resolve() for p in skip}
    hits: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = [
            d for d in dirnames
            if not d.startswith(".")
            and d not in _INPUT_SEARCH_SKIP_DIRS
            and (here / d).resolve() not in skipped
        ]
        hits.extend(here / name for name in filenames if fnmatch.fnmatch(name, pattern))
    return sorted(hits)


def _project_dir_of(ctx: PipelineContext) -> Path | None:
    """The project folder, when the database is at ``<project>/Data/``; else None."""
    data_dir = ctx.db_path.parent
    return data_dir.parent if data_dir.name == "Data" else None


def _find_input_file(ctx: PipelineContext, pattern: str, label: str) -> Path | None:
    """
    Search for a hand-placed input file (``hf_monthly.csv``, a Compustat variable list).

    In this order, stopping at the first folder that has a match:

    1. the staging directory, then the database directory (``Data/``), each
       with its subfolders. The first match in sorted order is used, as
       before: these are the documented places;
    2. the rest of the project folder (the parent of ``Data/``), with its
       subfolders, so that a file left anywhere in the project is found from
       whatever folder the build is started in;
    3. the folder the build is started from, with its subfolders.

    Steps 2 and 3 do not enter ``Scratch/`` or a folder whose name starts
    with a dot, and they raise :class:`AmbiguousInputError` when more than one
    file matches: which copy a build reads must not depend on the order in
    which the file system lists them.
    """
    import glob

    for d in (ctx.staging_dir, ctx.db_path.parent):
        matches = sorted(glob.glob(str(d / "**" / pattern), recursive=True))
        if matches:
            ctx.logger.info("Found %s file: %s", label, matches[0])
            return Path(matches[0])

    searched = [ctx.staging_dir, ctx.db_path.parent]
    project = _project_dir_of(ctx)
    roots = ([(project, "the project folder")] if project is not None else []) + [
        (Path.cwd(), "the current folder")
    ]
    for root, where in roots:
        if any(root.resolve() == s.resolve() for s in searched):
            continue
        matches = _walk_for_input(root, pattern, skip=searched)
        if len(matches) > 1:
            listing = "\n".join(f"  {m}" for m in matches)
            raise AmbiguousInputError(
                f"More than one {label} file named {pattern} under {where} "
                f"({root}):\n{listing}\n"
                f"Keep one, or put the one to use in {ctx.staging_dir}, "
                "which is searched first."
            )
        if matches:
            ctx.logger.info("Found %s file: %s (in %s)", label, matches[0], where)
            return matches[0]
        searched.append(root)
    ctx.logger.info("No %s file found (searched pattern: %s)", label, pattern)
    return None


HF_SPREADS_FILE = "hf_monthly.csv"


def _hf_missing_message(ctx: PipelineContext) -> str:
    """Why a ``tcosts_type='full'`` build stopped, and what to do about it."""
    return (
        f"tcosts_type='full' needs the high-frequency spreads file {HF_SPREADS_FILE}, "
        "which is not shipped: you build it on WRDS Cloud with "
        "github.com/chenandrewy/hf-spreads-all (needs ISSM, Daily TAQ, Monthly TAQ "
        f"and WRDS TAQ IID access). Put it in {ctx.staging_dir} or anywhere else "
        "in the project folder, or switch to the "
        "default, which needs only the Gibbs file: aa set-params --tcosts-type lf_combo\n"
        f"Then resume with: {gibbs_input.RESUME_COMMAND}\n"
        f"See {gibbs_input.DOCS_PAGE} for the steps."
    )


def _resolve_tcost_inputs(ctx: PipelineContext) -> tuple[Path | None, Path | None]:
    """
    The Gibbs file and (under ``tcosts_type='full'``) the HF spreads file.

    A production build raises :class:`MissingInputError` when either is
    missing, as MATLAB's ``makeTradingCosts.m`` does for the Gibbs file. A demo
    build never downloads and only warns about a missing Gibbs file; the
    trading costs are then built without the Gibbs measure.
    """
    tcosts_type = getattr(ctx.config, "tcosts_type", "lf_combo")
    try:
        found = gibbs_input.resolve_gibbs_file(
            ctx.config,
            ctx.staging_dir,
            ctx.db_path.parent,
            download=not ctx.demo,
        )
    except MissingInputError:
        if not ctx.demo:
            raise
        ctx.logger.warning(
            "No Gibbs file found (demo run, so not downloading); "
            "trading costs are built without the Gibbs measure"
        )
        gibbs_path = None
    else:
        gibbs_path = found.path
        ctx.logger.info("Found Gibbs file: %s (%s)", gibbs_path, found.origin)

    hf_path = None
    if tcosts_type == "full":
        hf_path = _find_input_file(ctx, HF_SPREADS_FILE, "HF spreads")
        if hf_path is None:
            raise MissingInputError(_hf_missing_message(ctx))
    return gibbs_path, hf_path


TCOSTS_STAGE = "compute-tcosts"


def _preflight_tcost_inputs(ctx: PipelineContext, planned: Sequence[str]) -> None:
    """
    Check the trading-cost inputs before the first stage runs.

    ``compute-tcosts`` runs hours into a fresh build. When it is planned, find
    the Gibbs file now (downloading it into staging if a wheel install has no
    copy) and, under ``tcosts_type='full'``, the HF spreads file, so a missing
    input fails before anything is fetched. Demo runs skip this: there a
    missing Gibbs file is a warning.
    """
    if ctx.demo or TCOSTS_STAGE not in planned:
        return
    _resolve_tcost_inputs(ctx)


def _stage_compute_tcosts(ctx: PipelineContext) -> None:
    """
    Compute transaction cost estimates using make_trading_costs orchestrator.

    Supports three modes via config (default: lf_combo):
    - 'gibbs': Gibbs only
    - 'lf_combo': Gibbs + Corwin-Schultz + Abdi-Ranaldi + Kyle-Obizhaeva
    - 'full': lf_combo + high-frequency TAQ/ISSM spreads

    Every mode needs the Gibbs file and 'full' also needs hf_monthly.csv; see
    :func:`_resolve_tcost_inputs`. They are resolved first, so a missing input
    fails before the daily data is loaded.
    """
    t0 = time.perf_counter()

    tcosts_type = getattr(ctx.config, "tcosts_type", "lf_combo")
    gibbs_path, hf_path = _resolve_tcost_inputs(ctx)

    raw = ctx.daily_raw(DAILY_TCOST_COLUMNS)
    if raw is None:
        ctx.logger.warning("CRSP daily raw not found; skipping tcosts")
        return
    if raw.empty:
        ctx.logger.warning("CRSP daily raw is empty; skipping tcosts")
        return

    # MATLAB's dret matrix carries the dsedelist dlret as an extra daily
    # return row (prc/vol stay NaN there). VoV's return std and its
    # >=11-nonzero-return-days gate see that row, so place it here too.
    factors_path = ctx.staging_dir / CRSP_DAILY_FACTORS_FILE
    factors = pd.read_parquet(factors_path) if factors_path.exists() else None
    raw = _place_dlret_rows(ctx, raw, factors, what="tcosts daily input")

    # Load ccm_panel for ME and idiovol
    with DuckDBManager(ctx.db_path) as mgr:
        tables = mgr.query_df(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'ccm_panel'"
        )
        if tables.empty:
            ctx.logger.warning("ccm_panel not found; skipping tcosts")
            return
        # Get ME, IffVOL3 (preferred) / idiovol, and exchcd for exclusions
        col_check = mgr.query_df(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'ccm_panel' AND column_name IN "
            "('me', 'idiovol', 'idiovol_ff_3m', 'exchcd')"
        )
        available_cols = set(col_check["column_name"].tolist())
        select_cols = ["permno", "date"]
        if "me" in available_cols:
            select_cols.append("me")
        if "idiovol_ff_3m" in available_cols:
            select_cols.append("idiovol_ff_3m")
        elif "idiovol" in available_cols:
            select_cols.append("idiovol")
        if "exchcd" in available_cols:
            select_cols.append("exchcd")
        ccm_panel = mgr.query_df(f"SELECT {', '.join(select_cols)} FROM ccm_panel")

    ccm_panel["date"] = pd.to_datetime(ccm_panel["date"])

    me_df = ccm_panel[["permno", "date", "me"]].copy() if "me" in ccm_panel.columns else pd.DataFrame(columns=["permno", "date", "me"])

    # Prefer the full-universe monthly aggregates for ivol: MATLAB's dense
    # IffVOL3 matrix includes permno-months absent from ccm_panel, and those
    # rows shift the tiedrank used by the NN fill.
    ivol_df = None
    agg_path = ctx.staging_dir / CRSP_DAILY_MONTHLY_AGG_FILE
    if agg_path.exists():
        try:
            import pyarrow.parquet as pq

            # Only the two ivol columns are wanted out of the 14-column,
            # 5.4M-row aggregate file.
            agg_cols = set(pq.ParquetFile(agg_path).schema.names)
            ivol_cols = [c for c in ("idiovol_ff_3m", "idiovol") if c in agg_cols]
            if ivol_cols:
                ivol_df = pd.read_parquet(
                    agg_path, columns=["permno", "date", *ivol_cols]
                )
                ivol_df["date"] = pd.to_datetime(ivol_df["date"])
                ctx.logger.info(
                    "Using full-universe ivol from %s (%d rows)", agg_path, len(ivol_df)
                )
        except Exception:  # pragma: no cover - fall back to ccm_panel below
            ctx.logger.warning("Failed reading %s; falling back to ccm_panel ivol", agg_path)
            ivol_df = None
    if ivol_df is None:
        ivol_cols = [c for c in ("idiovol_ff_3m", "idiovol") if c in ccm_panel.columns]
        ivol_df = ccm_panel[["permno", "date"] + ivol_cols].copy() if ivol_cols else None
    exchcd_df = ccm_panel[["permno", "date", "exchcd"]].copy() if "exchcd" in ccm_panel.columns else None

    # MATLAB's fill matrices span the monthly domestic-common universe
    # (permno_v); restrict ranks/donors/targets to the same set.
    universe_permnos = None
    with DuckDBManager(ctx.db_path) as mgr:
        cols = mgr.query_df(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'ccm_panel' AND column_name = 'shrcd'"
        )
        if not cols.empty and ctx.config.dom_com_eq:
            univ_df = mgr.query_df(
                "SELECT DISTINCT permno FROM ccm_panel WHERE shrcd IN (10, 11)"
            )
            if not univ_df.empty:
                universe_permnos = univ_df["permno"].to_numpy()

    if gibbs_path is not None:
        run_manifest.note_input(gibbs_path, "Gibbs c-estimates")
    if hf_path is not None:
        run_manifest.note_input(hf_path, "HF effective spreads")

    # The grid Gibbs estimates are expanded onto is a property of the tape:
    # under SIZ, MATLAB restricts the monthly stock file to valid name windows
    # and (with domComEqFlag) shrcd 10/11 (makeCRSPMonthlyData.m:60-95).
    link_keys = ctx.source.link_grid(
        ctx.staging_dir, CRSP_RAW_FILE, ctx.config, ctx.logger
    )
    if link_keys is None:
        ctx.logger.warning(
            "No CRSP link grid available (%s tape); "
            "Gibbs expansion falls back to ME panel keys",
            ctx.source.name,
        )

    ctx.logger.info(
        "Computing transaction costs: type=%s, daily=%d rows, gibbs=%s, hf=%s",
        tcosts_type, len(raw), gibbs_path, hf_path,
    )

    filled = tcosts.make_trading_costs(
        daily=raw,
        me=me_df,
        ivol=ivol_df,
        exchcd=exchcd_df,
        tcosts_type=tcosts_type,
        gibbs_path=gibbs_path,
        hf_path=hf_path,
        universe_permnos=universe_permnos,
        link_keys=link_keys,
        demo=ctx.demo,
    )

    if filled.empty:
        ctx.logger.warning("No valid tcost estimates produced; skipping")
        return

    # Write tcosts table
    write_table(ctx.db_path, "tcosts", filled, mode="replace")
    ctx.logger.info(
        "Built table tcosts in %.2fs: %d rows, %.1f%% non-NaN",
        time.perf_counter() - t0,
        len(filled),
        filled["tcost"].notna().mean() * 100,
    )

    # Merge tcost into ccm_panel
    with DuckDBManager(ctx.db_path) as mgr:
        panel = mgr.query_df("SELECT * FROM ccm_panel")
    panel["date"] = pd.to_datetime(panel["date"])
    filled["date"] = pd.to_datetime(filled["date"])

    # Drop existing tcost / tcost_gibbs columns if present (from prior runs)
    drop_cols = [c for c in ("tcost", "tcost_gibbs") if c in panel.columns]
    if drop_cols:
        panel = panel.drop(columns=drop_cols)

    merge_cols = ["permno", "date", "tcost"]
    if "tcost_gibbs" in filled.columns:
        merge_cols.append("tcost_gibbs")
    merged = panel.merge(filled[merge_cols], on=["permno", "date"], how="left")
    write_table(ctx.db_path, "ccm_panel", merged, mode="replace")
    ctx.logger.info(
        "Merged tcost%s into ccm_panel",
        " + tcost_gibbs" if "tcost_gibbs" in merge_cols else "",
    )


def _stage_compute_ff_tcosts(ctx: PipelineContext) -> None:
    """
    Compute FF factor trading costs and merge into ts_data.

    The 2x3 portfolios are those of MATLAB makeFFTcosts.m; the costs are
    those of held legs, with each side brought back to equal shares of its
    2x3 portfolios every month (``transforms.tcosts.ff_tcosts_from_matrices``).
    Depends on stock-level tcosts, ccm_panel (ret, me, momentum, NYSE flag)
    and the *unfilled* June accounting matrices rebuilt from compustat_funda
    + ``ccm_link``. Writes mkt_tc / smb_tc / hml_tc / rmw_tc / cma_tc / umd_tc
    (``convention="dollar"``, the default; mkt_tc is zeros by construction) and
    smb_tc_capital .. umd_tc_capital (``convention="capital"``) and
    smb_tc_capital_short .. (``"capital"``, the factor held short) onto ts_data,
    and records the calculation in ``metadata`` (:func:`_record_ff_tcosts`).
    """
    t0 = time.perf_counter()
    with DuckDBManager(ctx.db_path) as mgr:
        tables = mgr.query_df(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name IN "
            "('ccm_panel', 'ts_data', 'tcosts', 'compustat_funda')"
        )
        available = set(tables["table_name"].tolist()) if not tables.empty else set()
        if "ts_data" not in available:
            ctx.logger.warning("ts_data not found; skipping compute-ff-tcosts")
            return
        if "ccm_panel" not in available:
            ctx.logger.warning("ccm_panel not found; skipping compute-ff-tcosts")
            return

        col_check = mgr.query_df(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'ccm_panel' AND column_name IN "
            "('ret', 'me', 'tcost', 'nyse_flag', 'R12_2')"
        )
        available_cols = set(col_check["column_name"].tolist())
        select_cols = ["permno", "date"]
        for c in ("ret", "me", "tcost", "nyse_flag", "R12_2"):
            if c in available_cols:
                select_cols.append(c)
        quoted = ", ".join(f'"{c}"' for c in select_cols)
        panel_df = mgr.query_df(f"SELECT {quoted} FROM ccm_panel")
        ts_df = mgr.query_df("SELECT * FROM ts_data")

        tcost_s = None
        if "tcosts" in available:
            tc_tbl = mgr.query_df("SELECT permno, date, tcost FROM tcosts")
            if not tc_tbl.empty:
                tc_tbl["date"] = pd.to_datetime(tc_tbl["date"])
                tcost_s = tc_tbl.set_index(["date", "permno"])["tcost"]
        elif "tcost" in panel_df.columns:
            tmp = panel_df[["date", "permno", "tcost"]].copy()
            tmp["date"] = pd.to_datetime(tmp["date"])
            tcost_s = tmp.set_index(["date", "permno"])["tcost"]

        annual = None
        link = _read_ccm_link(ctx, mgr)
        if "compustat_funda" in available and link is not None:
            funda = mgr.query_df("SELECT * FROM compustat_funda")
            if not funda.empty and not link.empty:
                annual = compustat.build_june_annual_panel(funda, link, ctx.config)
        if annual is None:
            ctx.logger.warning(
                "compustat_funda / ccm_link unavailable; non-market FF "
                "factor trading costs will be zero"
            )

    if panel_df.empty:
        ctx.logger.warning("ccm_panel empty; skipping compute-ff-tcosts")
        return

    panel_df["date"] = pd.to_datetime(panel_df["date"])
    panel = panel_df.set_index(["date", "permno"]).sort_index()
    if tcost_s is None:
        tcost_s = pd.Series(0.0, index=panel.index, name="tcost")

    ff_tc = tcosts.make_ff_tcosts_table(panel, tcost_s, annual=annual)
    restarts = {k: int(v) for k, v in ff_tc.attrs.get("capital_restarts", {}).items() if v}
    entry = {k: float(v) for k, v in ff_tc.attrs.get("entry_cost", {}).items()}
    _log_held_factor_returns(ctx, ff_tc, ts_df)
    ff_tc.attrs = {}  # frames in attrs do not survive a merge
    ff_tc = ff_tc.reset_index()
    date_col = ff_tc.columns[0]
    ff_tc = ff_tc.rename(columns={date_col: "date"})
    ff_tc["date"] = pd.to_datetime(ff_tc["date"])

    ts_df["date"] = pd.to_datetime(ts_df["date"])
    tc_cols = list(tcosts.FF_TC_STORED_COLS)
    drop_existing = [c for c in tc_cols if c in ts_df.columns]
    if drop_existing:
        ts_df = ts_df.drop(columns=drop_existing)

    merged = ts_df.merge(ff_tc[["date", *tc_cols]], on="date", how="left")
    for c in tc_cols:
        if c in merged.columns:
            merged[c] = merged[c].fillna(0.0)

    write_table(ctx.db_path, "ts_data", merged, mode="replace")
    _record_ff_tcosts(ctx.db_path, restarts, entry)
    if entry:
        ctx.logger.info(
            "FF factor entry costs (the first purchase, %% of a side; not in the cost "
            "series): %s",
            ", ".join(f"{k.upper()} {100 * v:.3f}" for k, v in entry.items()),
        )
    for name, count in restarts.items():
        ctx.logger.warning(
            "FF factor trading costs: the capital of %s was zero or negative at %d "
            "trade(s); at those trades the factor restarts with $1 in each side "
            "(%s_tc_capital only; %s_tc, the dollar convention, has no capital)",
            name.upper(), count, name, name,
        )
    ctx.logger.info(
        "Merged FF tcosts (%s) into ts_data in %.2fs",
        ", ".join(tc_cols),
        time.perf_counter() - t0,
    )


def _log_held_factor_returns(ctx: PipelineContext, ff_tc: pd.DataFrame, ts_df: pd.DataFrame) -> None:
    """Log each factor's held long-minus-short return beside the factor in ``ts_data``.

    The costs are those of the toolkit's own 2x3 portfolios, the returns in
    ``ts_data`` are the published ones. One line per factor says how close the
    two portfolios are (same months; % a month), and how much of the cost
    comes from the monthly re-splits.
    """
    held = ff_tc.attrs.get("held_returns")
    resplit = ff_tc.attrs.get("resplit_costs")
    if held is None:
        return
    published = ts_df.assign(date=pd.to_datetime(ts_df["date"])).set_index("date")
    for name in held.columns:
        line = ""
        if name in published.columns:
            both = pd.concat([held[name], published[name]], axis=1, keys=["held", "pub"]).dropna()
            if len(both) > 1:
                varies = both["held"].std() > 0 and both["pub"].std() > 0
                corr = both["held"].corr(both["pub"]) if varies else float("nan")
                line = (
                    f"held sides {100 * both['held'].mean():.4f}, ts_data {100 * both['pub'].mean():.4f} "
                    f"% a month over {len(both)} months, correlation {corr:.4f}; "
                )
        ctx.logger.info(
            "FF factor %s: %scost %.4f %% a month, of which monthly re-splits %.4f",
            name.upper(), line,
            100 * float(ff_tc[f"{name}_tc"].mean()),  # the default convention, "dollar"
            100 * float(resplit[name].mean()) if resplit is not None else float("nan"),
        )


def _record_ff_tcosts(
    db_path: Path, restarts: dict[str, int], entry_cost: dict[str, float] | None = None
) -> None:
    """Record in ``metadata`` that the factor costs in ``ts_data`` are held-leg costs.

    Written by ``compute-ff-tcosts`` after it writes the columns. The value
    is ``{"calculation": "held", "version": 2, "capital_restarts": {factor:
    count}, "entry_cost": {factor: cost}}``. The counts are the trades at
    which a factor's capital was zero or negative (``convention="capital"``),
    factors without one left out; ``entry_cost`` is the cost of each factor's
    first purchase (a decimal, both sides), which is not in the stored
    series. A protocol run refuses factor costs from a database without the
    record or with another version
    (``analytics.protocol.require_held_factor_costs``): they were computed by
    an older version of the toolkit.
    """
    with DuckDBManager(db_path) as manager:
        manager.execute(
            "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)"
        )
        manager.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            tcosts.FF_TC_RECORD_KEY,
            json.dumps({
                "calculation": tcosts.FF_TC_HELD,
                "version": tcosts.FF_TC_RECORD_VERSION,
                "capital_restarts": restarts,
                "entry_cost": entry_cost or {},
            }),
        )


def _load_daily_delist(ctx: PipelineContext) -> pd.DataFrame | None:
    """
    Delisting events for MATLAB-style dlret placement in the daily panel.

    Which table those come from — and whether the placement happens at all —
    is the CRSP source's call: SIZ prefers the daily delist file
    (crsp.dsedelist, what MATLAB's daily pipeline reads) and falls back to the
    monthly one for older staging dirs, while CIZ returns ``None`` because its
    daily file already carries the payoff as its own row.
    """

    def load(key: str) -> pd.DataFrame | None:
        fname = ctx.source.aux_raw_files.get(key)
        if not fname:
            return None
        path = ctx.staging_dir / fname
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        return df if not df.empty else None

    return ctx.source.daily_delist_events(load)


def _daily_dlret_events(ctx: PipelineContext, *, what: str) -> pd.DataFrame | None:
    """
    Delisting events for dlret placement, or ``None`` when the tape needs none.

    The MATLAB daily pipeline builds a dense ``dret`` matrix in which each
    delisting return is placed as its own extra row, because SIZ ``dsf.ret``
    stops at the last trading day and excludes the payoff. CIZ already writes
    that row itself, on ``stkdelists.deldlydt``, so placing
    one again would double-count the delisting return in every measure derived
    from the daily panel — RVOL, IVOL, dretmax, VoV, the betas and CAR3. Hence
    the gate, and hence INFO rather than WARNING: under CIZ "no dlret placement"
    is the design, not a missing input.
    """
    if not ctx.source.apply_delisting_overlay:
        ctx.logger.info(
            "%s: no MATLAB dlret placement — the %s tape carries the delisting "
            "payoff as its own daily row",
            what, ctx.source.name,
        )
        return None
    return _load_daily_delist(ctx)


def _place_dlret_rows(
    ctx: PipelineContext,
    daily: pd.DataFrame,
    factors: pd.DataFrame | None,
    *,
    what: str,
) -> pd.DataFrame:
    """``daily`` widened with MATLAB's synthetic dlret rows, where applicable."""
    delist = _daily_dlret_events(ctx, what=what)
    if delist is None or factors is None or factors.empty:
        if ctx.source.apply_delisting_overlay:
            ctx.logger.warning(
                "No daily delist events or factors; %s uses raw ret without "
                "MATLAB dlret placement", what,
            )
        return daily
    return betas_mod._insert_matlab_dlret_rows(daily, delist, factors)


def _stage_compute_betas(ctx: PipelineContext) -> None:
    """
    Compute 6 beta variants (FP, OLS, Dimson, Welch, Vasicek, Standard).

    Requires crsp_daily_panel (or crsp_dsf) and daily FF factors.
    Writes betas table and merges into ccm_panel.
    """
    t0 = time.perf_counter()

    raw = ctx.daily_raw(DAILY_BETA_COLUMNS)
    if raw is None:
        ctx.logger.warning("CRSP daily raw not found; skipping betas")
        return
    if raw.empty:
        ctx.logger.warning("CRSP daily raw is empty; skipping betas")
        return

    # Load daily factors
    factors_path = ctx.staging_dir / CRSP_DAILY_FACTORS_FILE
    if not factors_path.exists():
        ctx.logger.warning("Daily FF factors not found; skipping betas")
        return
    factors = pd.read_parquet(factors_path)
    if factors.empty:
        ctx.logger.warning("Daily FF factors empty; skipping betas")
        return

    # Get month-end dates from ccm_panel
    with DuckDBManager(ctx.db_path) as mgr:
        tables = mgr.query_df(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'ccm_panel'"
        )
        if tables.empty:
            ctx.logger.warning("ccm_panel not found; skipping betas")
            return
        month_ends_df = mgr.query_df("SELECT DISTINCT date FROM ccm_panel ORDER BY date")

    month_ends = pd.to_datetime(month_ends_df["date"]).values

    ctx.logger.info(
        "Computing betas: %d daily rows, %d factor days, %d months",
        len(raw), len(factors), len(month_ends),
    )

    # Column names, `date` and `permno` are already normalized by
    # `daily_raw`; the estimators additionally need numpy float dtypes.
    crsp_daily.coerce_nullable_dtypes(raw)

    # Delisting events for MATLAB-style dlret placement in the daily panel.
    # MATLAB's daily pipeline uses the *daily* delist file (dsedelist), whose
    # dlret is measured from the last daily price — the monthly dlret also
    # compounds the partial-month return and diverges near delistings.
    # ``compute_betas`` does the placement itself, after its universe filter,
    # so this site hands it the events rather than the widened panel.
    delist = _daily_dlret_events(ctx, what="beta estimation")

    # Main universe (domestic common) so Vasicek cross-section matches MATLAB
    with DuckDBManager(ctx.db_path) as mgr:
        cols = mgr.query_df(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'ccm_panel'"
        )
        colset = set(cols["column_name"].tolist()) if not cols.empty else set()
        if "shrcd" in colset and ctx.config.dom_com_eq:
            univ_df = mgr.query_df(
                "SELECT DISTINCT permno FROM ccm_panel WHERE shrcd IN (10, 11)"
            )
        else:
            univ_df = mgr.query_df("SELECT DISTINCT permno FROM ccm_panel")
    universe_permnos = univ_df["permno"].to_numpy() if not univ_df.empty else None

    betas_df = betas_mod.compute_betas(
        raw,
        factors,
        month_ends,
        sample_start=ctx.config.sample_start,
        delist=delist,
        universe_permnos=universe_permnos,
    )

    if betas_df.empty:
        ctx.logger.warning("No betas computed; skipping")
        return

    betas_df = betas_mod.aggregate_betas_to_monthly(betas_df)

    # Write standalone betas table
    write_table(ctx.db_path, "betas", betas_df, mode="replace")
    ctx.logger.info(
        "Built table betas in %.2fs: %d rows",
        time.perf_counter() - t0, len(betas_df),
    )

    # Merge into ccm_panel
    with DuckDBManager(ctx.db_path) as mgr:
        panel = mgr.query_df("SELECT * FROM ccm_panel")

    panel["date"] = pd.to_datetime(panel["date"])
    betas_df["date"] = pd.to_datetime(betas_df["date"])

    beta_cols = [c for c in betas_df.columns if c not in ("permno", "date")]
    # Drop existing beta columns if present (from prior runs)
    panel = panel.drop(columns=[c for c in beta_cols if c in panel.columns], errors="ignore")

    merged = panel.merge(
        betas_df[["permno", "date"] + beta_cols],
        on=["permno", "date"],
        how="left",
    )
    write_table(ctx.db_path, "ccm_panel", merged, mode="replace")
    ctx.logger.info("Merged %s into ccm_panel", beta_cols)


def _stage_compute_car3(ctx: PipelineContext) -> None:
    """
    Compute CAR3 (3-day cumulative abnormal return around earnings announcements).

    Requires both crsp_daily_panel and compustat_fundq to be available.
    Links fundq to CRSP permnos, then computes 3-day abnormal returns
    around each RDQ date and merges into ccm_panel.
    """
    t0 = time.perf_counter()

    with DuckDBManager(ctx.db_path) as mgr:
        # Check required tables exist
        tables = mgr.query_df(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name IN ('crsp_daily_panel', 'compustat_fundq', 'ccm_panel')"
        )
        available = set(tables["table_name"].tolist()) if not tables.empty else set()
        missing = {"crsp_daily_panel", "compustat_fundq", "ccm_panel"} - available
        if missing:
            ctx.logger.info("Skipping CAR3: missing tables %s", missing)
            return

        # Raw daily returns (MATLAB dret_x_dl); the MATLAB-style dlret
        # placement below turns this into the dret matrix CAR3 uses.
        daily = mgr.query_df("SELECT permno, date, ret FROM crsp_daily_panel")
        # CAR3 reads three of `compustat_fundq`'s 38 columns: `gvkey` and
        # `datadate` to resolve the CCM link, `rdq` for the announcement day.
        # Reading the rest only widened the 2.5M-row link merge. Absent
        # columns are left out rather than selected, so a thin extract still
        # reaches the "no linked fundq with RDQ" skip below.
        fundq_cols = mgr.query_df(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'compustat_fundq' AND column_name IN "
            "('gvkey', 'datadate', 'rdq')"
        )["column_name"].tolist()
        fundq = mgr.query_df(
            f"SELECT {', '.join(fundq_cols)} FROM compustat_fundq"
            if fundq_cols
            else "SELECT * FROM compustat_fundq LIMIT 0"
        )
        ccm_panel = mgr.query_df("SELECT * FROM ccm_panel")
        link = _read_ccm_link(ctx, mgr)

    # Load daily factors
    factors = None
    with DuckDBManager(ctx.db_path) as mgr:
        ts_check = mgr.query_df(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'ts_data_daily'"
        )
        if not ts_check.empty:
            factors = mgr.query_df("SELECT * FROM ts_data_daily")

    # Link fundq gvkey → permno
    if link is None:
        ctx.logger.warning("CCM link table not found; skipping CAR3")
        return
    fundq_linked = compustat.merge_on_link(fundq, link)

    if fundq_linked.empty or "rdq" not in fundq_linked.columns:
        ctx.logger.info("No linked fundq with RDQ; skipping CAR3")
        return

    # MATLAB dret: place dlret at the trading day after the last finite
    # return (makeCRSPDailyDerivedVariables.m:81-109), same as compute-betas.
    daily["date"] = pd.to_datetime(daily["date"])
    daily = _place_dlret_rows(ctx, daily, factors, what="CAR3 daily input")

    # Compute CAR3
    car3_monthly = crsp_daily.compute_car3(daily, fundq_linked, factors=factors)

    if car3_monthly.empty:
        ctx.logger.info("No CAR3 values computed; skipping merge")
        return

    # Merge into ccm_panel
    ccm_panel["date"] = pd.to_datetime(ccm_panel["date"])
    car3_monthly["date"] = pd.to_datetime(car3_monthly["date"])

    # Drop existing car3 column if present (from a previous run)
    if "car3" in ccm_panel.columns:
        ccm_panel = ccm_panel.drop(columns=["car3"])

    merged = ccm_panel.merge(
        car3_monthly[["permno", "date", "car3"]],
        on=["permno", "date"],
        how="left",
    )
    # MATLAB makeCRSPDailyDerivedVariables.m:374-376: CAR3(isnan(ret)) = nan
    if "ret" in merged.columns:
        merged.loc[merged["ret"].isna(), "car3"] = np.nan
    write_table(ctx.db_path, "ccm_panel", merged, mode="replace")
    ctx.logger.info(
        "Merged CAR3 into ccm_panel in %.2fs: %d non-null values",
        time.perf_counter() - t0, merged["car3"].notna().sum(),
    )


def _require_june_annual_layout(ctx: PipelineContext, stage: str, panel: pd.DataFrame) -> None:
    """Stop ``stage`` when ``ccm_panel`` has annual columns filled June to May.

    The stage carries June-only annual values forward itself. On a panel built
    before annual columns were stored in June only it would give other numbers
    than a rebuilt database, so it stops and names the stage to start from.
    A panel with no annual value at all (no Compustat data, as in a demo
    build) passes: there is nothing to misread.
    """
    if has_june_annual_layout(ctx.db_path):
        return
    present = [c for c in compustat.ANNUAL_VALUE_COLS if c in panel.columns]
    if not any(panel[c].notna().any() for c in present):
        return
    raise RuntimeError(
        f"{stage}: ccm_panel was built by an older version of the toolkit, with "
        "annual Compustat columns filled June to May. Rebuild it first: "
        "aa setup-database --start-from transform-compustat"
    )


def _stage_compute_nmv_anomalies(ctx: PipelineContext) -> None:
    """
    Compute the 23 Novy-Marx & Velikov (2016) anomaly signals.

    Reads ccm_panel and optionally raw compustat_funda, computes all signals,
    and writes to the nmv_anomalies table.
    """
    t0 = time.perf_counter()

    with DuckDBManager(ctx.db_path) as mgr:
        tables = mgr.query_df(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'ccm_panel'"
        )
        if tables.empty:
            ctx.logger.warning("ccm_panel not found; skipping NMV anomalies")
            return
        panel = mgr.query_df("SELECT * FROM ccm_panel")

        # FF factors (mktrf, rf) for the distress signal's EXRET component
        ts_tables = mgr.query_df(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'ts_data'"
        )
        factors = None
        if not ts_tables.empty:
            cols = mgr.query_df(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'ts_data'"
            )["column_name"].tolist()
            if {"mktrf", "rf"}.issubset(cols):
                factors = mgr.query_df("SELECT date, mktrf, rf FROM ts_data")

    panel["date"] = pd.to_datetime(panel["date"])
    _require_june_annual_layout(ctx, "compute-nmv-anomalies", panel)

    ctx.logger.info(
        "Computing NMV anomalies: panel=%d rows, factors=%s",
        len(panel), factors.shape if factors is not None else None,
    )

    result = nmv_anomalies.compute_nmv_anomalies(panel, factors=factors)

    if result.empty:
        ctx.logger.warning("No NMV anomalies produced; skipping")
        return

    write_table(ctx.db_path, "nmv_anomalies", result, mode="replace")
    ctx.logger.info(
        "Built table nmv_anomalies in %.2fs: %d rows, %d signals",
        time.perf_counter() - t0, len(result),
        len([c for c in result.columns if c not in ("date", "permno")]),
    )


def _stage_validate_bm_hml(ctx: PipelineContext) -> None:
    """
    Sanity-check: replicate the Fama-French HML factor via a 2x3 bivariate
    sort on size (ME) and book-to-market (BM) with NYSE breakpoints, then
    correlate with the published HML.  A correlation of ~0.95+ confirms the
    COMPUSTAT merge and BM computation are correct.
    """
    import numpy as np

    with DuckDBManager(ctx.db_path) as mgr:
        # Check required tables and columns exist
        tables = mgr.query_df(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name IN ('ccm_panel', 'ts_data')"
        )
        available = set(tables["table_name"].tolist())
        if "ccm_panel" not in available or "ts_data" not in available:
            ctx.logger.info("validate-bm-hml: skipping (missing ccm_panel or ts_data)")
            return

        # Check that required columns exist in ccm_panel
        col_df = mgr.query_df(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'ccm_panel' "
            "AND column_name IN ('bm', 'fin_firm')"
        )
        available_cols = set(col_df["column_name"].tolist())
        if "bm" not in available_cols:
            ctx.logger.info("validate-bm-hml: skipping (ccm_panel has no bm column)")
            return

        # Every row is read: ``bm`` is on the June rows only and is carried
        # through the following May below, before any row is dropped.
        panel = mgr.query_df(
            "SELECT date, permno, ret, bm, me, nyse_flag FROM ccm_panel"
        )
        hml_df = mgr.query_df("SELECT date, hml FROM ts_data WHERE hml IS NOT NULL")

    _require_june_annual_layout(ctx, "validate-bm-hml", panel)
    panel["date"] = pd.to_datetime(panel["date"])
    panel = panel.set_index(["date", "permno"]).sort_index()
    from .analytics.sorts import fill_months  # noqa: E402

    panel["bm"] = fill_months(panel["bm"], compustat.ANNUAL_VALIDITY_MONTHS - 1)
    # FF (1993) factor construction: include all common shares with
    # positive book equity. Financial firms are NOT excluded from the
    # published FF factors (that exclusion is specific to FF 1992).
    panel = panel[(panel["bm"] > 0) & panel["me"].notna() & panel["ret"].notna()]

    if len(panel) < 100 or hml_df.empty:
        ctx.logger.info(
            "validate-bm-hml: skipping (panel=%d rows, hml=%d rows)",
            len(panel), len(hml_df),
        )
        return

    # Replicate FF HML: 2x3 conditional sort on ME (2 groups) x BM (3 groups)
    # with NYSE breakpoints, value-weighted.
    from .analytics.sorts import run_bivariate_sort  # noqa: E402

    nyse = panel["nyse_flag"] if "nyse_flag" in panel.columns else None

    try:
        biv = run_bivariate_sort(
            panel["ret"],
            panel["me"],       # signal1 = size
            panel["bm"],       # signal2 = BM
            panel["me"],
            n_bins1=2,
            n_bins2=[30, 70],  # FF: NYSE 30th/70th BM percentiles (not equal thirds)
            sort_type="unconditional",  # FF: BM breakpoints from all NYSE, not within size
            breaks="nyse" if nyse is not None else "name",
            nyse_flag=nyse,
            weighting="v",
        )
    except Exception as exc:
        ctx.logger.warning("validate-bm-hml: bivariate sort failed (%s); skipping", exc)
        return

    # Flat portfolios: (size=1,bm=1)=1, (1,2)=2, (1,3)=3, (2,1)=4, (2,2)=5, (2,3)=6
    # HML = (SmallHigh + BigHigh)/2 - (SmallLow + BigLow)/2
    pret = biv.flat.leg_returns
    required_cols = {1, 3, 4, 6}
    if not required_cols.issubset(set(pret.columns)):
        ctx.logger.info("validate-bm-hml: missing portfolio columns; skipping")
        return

    bm_ls = (pret[3] + pret[6]) / 2.0 - (pret[1] + pret[4]) / 2.0

    # Align with published HML
    bm_ls.index = pd.to_datetime(bm_ls.index)
    hml_df["date"] = pd.to_datetime(hml_df["date"])
    hml_ts = hml_df.set_index("date")["hml"].sort_index()
    hml_ts.index = pd.to_datetime(hml_ts.index)

    common = bm_ls.dropna().index.intersection(hml_ts.dropna().index)
    if len(common) < 12:
        ctx.logger.info(
            "validate-bm-hml: only %d overlapping months; skipping", len(common)
        )
        return

    bm_common = bm_ls.reindex(common).astype(float)
    hml_common = hml_ts.reindex(common).astype(float)

    corr = float(bm_common.corr(hml_common))
    hml_var = float(hml_common.var())
    beta = float(bm_common.cov(hml_common) / hml_var) if hml_var > 0 else np.nan
    mean_ls = float(bm_common.mean()) * 100
    mean_hml = float(hml_common.mean()) * 100

    ctx.logger.info(
        "validate-bm-hml: corr=%.3f  beta=%.3f  mean_LS=%.3f%%  mean_HML=%.3f%%  N=%d months",
        corr, beta, mean_ls, mean_hml, len(common),
    )

    # Write validation summary table
    summary = pd.DataFrame({"bm_ls": bm_common, "hml": hml_common})
    summary.index.name = "date"
    write_table(ctx.db_path, "validation_bm_hml", summary.reset_index(), mode="replace")


def _stage_finalize(ctx: PipelineContext) -> None:
    ctx.logger.info("Pipeline finished.")


def _stage_fetch_ff_factors(ctx: PipelineContext) -> None:
    t0 = time.perf_counter()
    client = ctx.require_wrds_client("Fetching the Fama-French monthly factors")
    if client is None:
        # Demo runs only: a minimal synthetic monthly factor series.
        df = pd.DataFrame(
            {
                "date": pd.to_datetime([f"{ctx.config.sample_start}-01-31", f"{ctx.config.sample_start}-02-28"]),
                "mktrf": [0.01, 0.02],
                "smb": [0.0, 0.0],
                "hml": [0.0, 0.0],
                "rf": [0.001, 0.001],
                "umd": [0.0, 0.0],
                "smb2": [pd.NA, pd.NA],
                "rmw": [pd.NA, pd.NA],
                "cma": [pd.NA, pd.NA],
            }
        )
    else:
        df = ff_factors.fetch_ff_monthly(ctx.config, wrds_client=client)
    write_table(ctx.db_path, "ts_data", df, mode="replace")
    ctx.logger.info(
        "Loaded table ts_data (FF monthly factors) in %.2fs; %s",
        time.perf_counter() - t0,
        _df_brief(df, name="ts_data"),
    )


def _cz_stage_error(what: str, exc: Exception, db_path: Path, doc: str) -> NonFatalStageError:
    """
    The :class:`NonFatalStageError` for a failed CZ ``what``.

    A download failure keeps :func:`cz_manual_hint`. Anything else happened
    while reading a file already on disk (a pinned path, a file placed in
    staging, the release cache, the zip extraction), so it is worded as a read
    failure and does not send the user off to download the file again.
    ``doc`` is ``"signals"`` or ``"SignalDoc"``.
    """
    retry = "aa setup-database --start-from fetch-cz-anomalies"
    if isinstance(exc, (cz_release.DownloadError, requests.RequestException)):
        # cz_anomalies' errors carry the hint for their release's branch.
        hint = getattr(exc, "hint", None) or cz_ingest.cz_manual_hint(db_path, doc)
        # cz_anomalies' own download errors already say "Could not download
        # the CZ <release> ..." and carry the hint; keep each said once.
        detail = str(exc).replace(hint, "").strip()
        if not detail.startswith("Could not download"):
            detail = f"Could not download {what}: {detail}"
        return NonFatalStageError(detail, hint=hint)
    return NonFatalStageError(
        f"Could not read the local C-Z file for {what}: {type(exc).__name__}: {exc}",
        hint=(
            "The file is already on disk, so this is not a download problem. "
            "Check that it is complete and readable (and, for a zip, that "
            "staging has room for the ~8 GB extracted CSV), then rerun only "
            f"this stage: `{retry}`."
        ),
    )


def _drop_cz_tables(db_path: Path) -> None:
    """Remove ``cz_anomalies``, ``cz_signal_info`` and the release they came from."""
    with DuckDBManager(db_path) as manager:
        manager.execute("DROP TABLE IF EXISTS cz_anomalies")
        manager.execute("DROP TABLE IF EXISTS cz_signal_info")
        manager.execute(
            "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)"
        )
        manager.execute("DELETE FROM metadata WHERE key = ?", CZ_RELEASE_KEY)


def _persist_cz_release(db_path: Path) -> None:
    """
    Store which C-Z release the tables just written came from, in ``metadata``.

    The value is what the run manifest records (:func:`run_manifest.noted_cz_releases`),
    kept in the database because the manifest beside it is rewritten by every
    build and a protocol run reads only the database. A file whose release is
    not known (pinned or hand-placed) is stored as such.
    """
    record = run_manifest.noted_cz_releases()
    for what in ("signals", "signal_doc"):
        record.setdefault(what, {"release": run_manifest.UNKNOWN})
    with DuckDBManager(db_path) as manager:
        manager.execute(
            "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)"
        )
        manager.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            CZ_RELEASE_KEY,
            json.dumps(record, sort_keys=True),
        )


def _stage_fetch_cz_anomalies(ctx: PipelineContext) -> None:
    """
    Download Chen-Zimmerman anomaly characteristics and load into cz_anomalies table.

    Requires ccm_panel to be populated first (for permno filtering and CRSP-derived signals).
    Streams the full zoo via DuckDB (does not pre-trim to protocol n≈157).

    Outside demo mode a failure raises :class:`NonFatalStageError`: the build
    finishes without ``cz_anomalies`` (everything else in the database is
    usable) and ``setup_database`` reports how to fetch it later.
    """
    t0 = time.perf_counter()

    # Check if ccm_panel exists
    with DuckDBManager(ctx.db_path) as manager:
        tables = manager.query_df(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'ccm_panel'"
        )
        if tables.empty:
            ctx.logger.warning("ccm_panel not found; skipping CZ anomalies stage")
            return

    # One release choice for both files: with no release configured, the
    # newest on Hugging Face is looked up once, and a download of either file
    # comes from the same commit.
    release = cz_ingest.CZReleaseChoice(ctx.config)

    # DuckDB-native full-zoo load. A failure here used to fall through to a
    # ten-column placeholder and a WARNING nothing downstream ever read, so a
    # network blip produced a database that looked like the real zoo. Only a
    # demo run may substitute; production leaves the table out and reports it.
    try:
        stats = cz_ingest.write_cz_anomalies_table(ctx.config, ctx.db_path, release=release)
        ctx.logger.info(
            "Loaded table cz_anomalies in %.2fs; rows=%s cols=%s dates=%s..%s source=%s",
            time.perf_counter() - t0,
            stats.get("rows"),
            stats.get("columns"),
            stats.get("date_min"),
            stats.get("date_max"),
            stats.get("source"),
        )
    except Exception as exc:
        if not ctx.demo:
            # No half-written table, and no cz_signal_info without a zoo.
            _drop_cz_tables(ctx.db_path)
            raise _cz_stage_error(
                "the Chen-Zimmerman anomaly zoo", exc, ctx.db_path, "signals"
            ) from exc
        ctx.logger.warning(
            "DEMO MODE: could not fetch CZ anomalies (%s); writing synthetic "
            "placeholder data. This database is stamped %s=true and is not "
            "research output.",
            exc,
            DEMO_KEY,
        )
        df = cz_ingest.generate_placeholder_cz_anomalies(ctx.config, ctx.db_path)
        write_table(ctx.db_path, "cz_anomalies", df, mode="replace")
        ctx.logger.info(
            "Loaded table cz_anomalies (demo placeholder) in %.2fs; %s",
            time.perf_counter() - t0,
            _df_brief(df, name="cz_anomalies"),
        )

    # Also fetch signal documentation/metadata. Same rule: the protocol reads
    # this table for anomaly names and holding periods, so a silently
    # truncated version is a scientific defect, not a cosmetic one.
    try:
        info_df = cz_ingest.fetch_cz_signal_info(
            ctx.config, ctx.db_path, demo=ctx.demo, release=release
        )
        write_table(ctx.db_path, "cz_signal_info", info_df, mode="replace")
        ctx.logger.info("Loaded table cz_signal_info: %d signals", len(info_df))
        _persist_cz_release(ctx.db_path)
    except Exception as exc:
        if not ctx.demo:
            # Nor a zoo without its documentation: the rerun loads both.
            _drop_cz_tables(ctx.db_path)
            raise _cz_stage_error(
                "the Chen-Zimmerman signal documentation", exc, ctx.db_path, "SignalDoc"
            ) from exc
        ctx.logger.warning("DEMO MODE: could not fetch CZ signal info (%s)", exc)


STAGES: List[PipelineStage] = [
    PipelineStage("initialize-database", _stage_initialize_database),
    PipelineStage("generate-field-catalog", _stage_generate_field_catalog),
    PipelineStage("fetch-crsp-monthly", _stage_fetch_crsp_monthly),
    PipelineStage("fetch-crsp-aux", _stage_fetch_crsp_aux),
    PipelineStage("fetch-ff-daily", _stage_fetch_ff_daily),
    PipelineStage("fetch-ff-factors", _stage_fetch_ff_factors),
    PipelineStage("fetch-compustat-annual", _stage_fetch_compustat_annual),
    PipelineStage("fetch-compustat-quarterly", _stage_fetch_compustat_quarterly),
    PipelineStage("fetch-crsp-daily", _stage_fetch_crsp_daily),
    PipelineStage("load-crsp-msf", _stage_load_crsp_msf),
    PipelineStage("transform-crsp-monthly", _stage_transform_crsp_monthly),
    PipelineStage("load-crsp-aux", _stage_load_crsp_aux),
    PipelineStage("load-crsp-dsf", _stage_load_crsp_dsf),
    PipelineStage("transform-crsp-daily", _stage_transform_crsp_daily),
    PipelineStage("load-compustat", _stage_load_compustat),
    PipelineStage("transform-compustat", _stage_transform_compustat),
    PipelineStage("validate-bm-hml", _stage_validate_bm_hml),
    PipelineStage("compute-tcosts", _stage_compute_tcosts),
    PipelineStage("compute-ff-tcosts", _stage_compute_ff_tcosts),
    PipelineStage("compute-betas", _stage_compute_betas),
    PipelineStage("compute-car3", _stage_compute_car3),
    PipelineStage("compute-nmv-anomalies", _stage_compute_nmv_anomalies),
    PipelineStage("fetch-cz-anomalies", _stage_fetch_cz_anomalies),
    PipelineStage("finalize", _stage_finalize),
]


def _last_daily_parquet_stage(planned: Sequence[str]) -> str | None:
    """Name of the last stage in ``planned`` that reads the daily staging file."""
    daily = [name for name in planned if name in DAILY_PARQUET_STAGES]
    return daily[-1] if daily else None


# Stages that pull from WRDS. `fetch-cz-anomalies` is deliberately absent: it
# downloads from the Chen-Zimmerman release, not from WRDS, so a run with no
# WRDS account can still fail there for an unrelated reason.
WRDS_FETCH_STAGES: frozenset[str] = frozenset(
    {
        "fetch-crsp-monthly",
        "fetch-crsp-aux",
        "fetch-crsp-daily",
        "fetch-ff-daily",
        "fetch-compustat-annual",
        "fetch-compustat-quarterly",
        "fetch-ff-factors",
    }
)


# Stages that hold the CRSP daily panel in memory; the build's peak RAM is in
# one of them (transform-crsp-daily, in practice).
MEMORY_HEAVY_STAGES: frozenset[str] = frozenset(
    {"load-crsp-dsf", "transform-crsp-daily", "compute-tcosts", "compute-betas"}
)


class InsufficientMemoryError(RuntimeError):
    """Raised before stage 1 when the machine has less RAM than the sample needs."""


def _machine_ram_gb(ctx: PipelineContext) -> tuple[float | None, str]:
    """``(GiB, where it came from)``: an explicit budget, else the machine's memory.

    The machine's memory is physical RAM, or a container's memory limit when
    that is smaller (a Kubernetes pod sees the node's RAM through psutil).
    """
    env = os.getenv(MEMORY_BUDGET_ENV)
    budget = None
    if env is not None and env.strip() != "":
        budget, source = resolve_memory_budget_gb(), MEMORY_BUDGET_ENV
    elif ctx.config.memory_budget_gb is not None:
        budget, source = resolve_memory_budget_gb(ctx.config.memory_budget_gb), "memory_budget_gb"
    if budget is not None:
        return budget, source
    return machine_memory_gb()


def _preflight_memory(
    ctx: PipelineContext, planned: Sequence[str], *, skip: bool = False
) -> None:
    """
    Refuse to start a build this machine cannot hold.

    Running out of memory happens an hour or more into a build, in
    ``transform-crsp-daily``, so check before stage 1 instead. The requirement
    is :func:`~assayinganomalies.config.required_setup_ram_gb` for the
    configured sample; the machine's RAM is ``AA_MEMORY_GB`` or
    ``memory_budget_gb`` when set, else physical RAM or a container's memory
    limit, whichever is smaller. Only runs that include a
    stage holding the daily panel are checked, and demo runs are not.
    ``skip=True`` (``--skip-memory-check``) logs the shortfall and goes on.
    """
    if ctx.demo or not any(name in MEMORY_HEAVY_STAGES for name in planned):
        return
    start, end = int(ctx.config.sample_start), int(ctx.config.sample_end)
    need = required_setup_ram_gb(start, end)
    have, source = _machine_ram_gb(ctx)
    if have is None:
        ctx.logger.info(
            "Memory check skipped: could not read this machine's RAM "
            "(sample %s..%s needs about %d GB)", start, end, need,
        )
        return
    ctx.logger.info(
        "Memory check: sample %s..%s needs about %d GB; %s is %.1f GB",
        start, end, need, source, have,
    )
    if have >= need:
        return
    fits = next(
        (y for y in range(start, end + 1) if required_setup_ram_gb(y, end) <= have),
        None,
    )
    msg = (
        f"This build needs about {need} GB of RAM and this machine has "
        f"{have:.1f} GB ({source}). Sample {start}..{end} holds about "
        f"{crsp_daily_rows(start, end) / 1e6:.0f}M CRSP daily rows, and "
        "transform-crsp-daily keeps several copies of them in memory."
    )
    if fits is not None:
        msg += (
            f" The earliest sample start that fits is {fits} "
            f"(aa set-params --sample-start {fits})."
        )
    msg += (
        " Use a machine with more RAM, shorten the sample, or rerun with "
        "--skip-memory-check (skip_memory_check=True) to try anyway."
    )
    if skip:
        ctx.logger.warning("%s Continuing: the memory check is skipped.", msg)
        return
    raise InsufficientMemoryError(msg)


def _preflight_credentials(ctx: PipelineContext, planned: Sequence[str]) -> None:
    """
    Log in to WRDS before the first stage runs, once for the whole run.

    Without this the first WRDS query would come only at the first fetch
    stage: a run without credentials would fail after a database file, a
    field catalog and several minutes of log, and the Duo push would arrive
    whenever that stage happened to start. Here the credentials are resolved
    (prompting at most once), the shared session is opened, so the one Duo
    approval happens now, and a bad password or an unapproved push stops the
    run before anything has been fetched. Every fetch stage then borrows that
    session. A password typed at the prompt can be saved to the password file
    so the next run does not ask.
    """
    if ctx.demo:
        return
    needed = [name for name in planned if name in WRDS_FETCH_STAGES]
    if not needed:
        return
    client = ctx.get_wrds_client(prompt=True)
    if client is None:
        raise missing_credentials_error(
            f"This run includes {len(needed)} WRDS fetch stage(s) ({', '.join(needed)}) "
            "and preflight found no usable credentials. Nothing has been fetched"
        )
    username = client._get_username()
    password = client._get_password()
    ctx.logger.info(
        "WRDS credentials: user %s, password from %s",
        username,
        client.credential_source or "unknown",
    )
    msg = "Connecting to WRDS. Approve the Duo push on your phone now..."
    ctx.logger.info(msg, extra={"printed": True})
    print(msg, flush=True)
    try:
        client.open_session()
    except Exception as exc:
        detail = str(exc)
        if password:
            detail = detail.replace(password, "***")
        raise MissingCredentialsError(
            f"Could not log in to WRDS as {username!r}: {detail}\n"
            "Check the username and password, and approve the Duo push when it "
            "arrives. Nothing has been fetched.\n"
            f"{CREDENTIAL_HELP}"
        ) from exc
    msg = f"Connected to WRDS as {username}."
    ctx.logger.info(msg, extra={"printed": True})
    print(msg, flush=True)
    _offer_to_save_pgpass(ctx, client)


def _offer_to_save_pgpass(ctx: PipelineContext, client: WRDSClient) -> None:
    """After a login with a typed password, offer once to save it."""
    if client.credential_source != "prompt" or not client._can_prompt():
        return
    target = pgpass_save_path()
    try:
        answer = input(
            f"Save these credentials to {target} so future runs don't ask? [y/N] "
        )
    except EOFError:
        return
    if answer.strip().lower() not in ("y", "yes"):
        return
    try:
        path = client.save_pgpass()
    except Exception as exc:  # noqa: BLE001 - saving is a convenience
        ctx.logger.warning("Could not save WRDS credentials to %s: %s", target, exc)
        return
    msg = f"Saved WRDS credentials to {path}."
    ctx.logger.info(msg, extra={"printed": True})
    print(msg, flush=True)


def _clamp_sample_end_for_tape(ctx: PipelineContext) -> None:
    """
    Clamp an explicit ``sample_end`` past a frozen tape's last year, offline.

    SIZ ends in 2024 (``SIZ_FROZEN_END_YEAR``): a later year would fetch
    nothing past it while the build still believed it held that year, so the
    year is lowered to the tape's, with a warning. "latest" is left alone
    (`_preflight_sample_end` caps it); a live tape is never clamped.
    """
    frozen = ctx.source.frozen_end_year
    if ctx.config.sample_end_is_latest or frozen is None:
        return
    year = int(ctx.config.sample_end)
    if year <= frozen:
        return
    ctx.logger.warning(
        "sample_end is %d, but the %s CRSP tape ends in %d; building through %d. "
        "Switch to the CIZ tape (aa set-params --crsp-format ciz) for later years, "
        "or set --sample-end %d to silence this warning.",
        year,
        ctx.source.name.upper(),
        frozen,
        frozen,
        frozen,
    )
    ctx.sample_end_resolution = SampleEndResolution(
        requested=ctx.sample_end_requested, resolved=frozen, source="clamped-siz"
    )
    ctx.config = ctx.config.with_sample_end(frozen)


def _persisted_sample_end(db_path: Path) -> SampleEndResolution | None:
    """
    The sample end the database's last build resolved, or ``None``.

    Read from ``metadata.sample_end_resolved`` with the tape dates beside it,
    so a run that reuses the year carries them into its own metadata. ``None``
    when the database is missing or records no resolved year (built before
    ``sample_end`` could be "latest").
    """
    year = read_metadata_value(db_path, SAMPLE_END_RESOLVED_KEY)
    if year is None:
        return None
    try:
        year = int(year)
    except (TypeError, ValueError):
        return None

    def text(key: str) -> str | None:
        value = read_metadata_value(db_path, key)
        return None if value is None else str(value)

    return SampleEndResolution(
        requested=LATEST_SAMPLE_END,
        resolved=year,
        source="metadata",
        crsp_max_date=text("crsp_tape_max_date"),
        crsp_last_december=text("crsp_tape_last_december"),
        compustat_max_date=text("compustat_max_datadate"),
        compustat_last_december=text("compustat_last_december"),
    )


def _preflight_sample_end(ctx: PipelineContext, planned: Sequence[str]) -> None:
    """
    Settle ``sample_end`` as a year before the first stage runs.

    An explicit year is used as it is (`_clamp_sample_end_for_tape` has
    already lowered one past a frozen tape). "latest" resolves to:

    - ``DEMO_SAMPLE_END`` in a demo build, which has no tape to ask;
    - the last complete year on the tapes, asked on the shared WRDS session
      `_preflight_credentials` opened, when the run fetches from WRDS;
    - otherwise (``--start-from`` past the fetches, a rebuild without
      refetch) the year the database's last build recorded, so the stages
      read the extracts they were fetched with; with none recorded,
      :class:`SampleEndUnresolvedError`.

    ``ctx.config`` is then replaced by a copy holding the year.
    """
    if ctx.sample_end_resolution is not None:
        return
    if not ctx.config.sample_end_is_latest:
        ctx.sample_end_resolution = ctx.resolved_sample_end_record()
        return
    if ctx.demo:
        resolution = SampleEndResolution(
            requested=LATEST_SAMPLE_END, resolved=DEMO_SAMPLE_END, source="demo"
        )
    elif any(name in WRDS_FETCH_STAGES for name in planned):
        client = ctx.get_wrds_client(prompt=True)
        if client is None:  # pragma: no cover - _preflight_credentials raised already
            raise missing_credentials_error("Resolving sample_end = 'latest'")
        with client.connect() as conn:
            resolution = resolve_latest_sample_end(conn, ctx.source)
    else:
        resolution = _persisted_sample_end(ctx.db_path)
        if resolution is None:
            raise SampleEndUnresolvedError(
                f"sample_end is {LATEST_SAMPLE_END!r} and this run fetches nothing from "
                f"WRDS, so it would reuse the year the last build of {ctx.db_path} "
                "resolved it to, but the database records none "
                "(metadata.sample_end_resolved). Run setup-database from the first "
                "stage (it looks the year up on WRDS), or pin the year the staged "
                "extracts were fetched with: aa set-params --sample-end <year>."
            )
    ctx.sample_end_resolution = resolution
    ctx.config = ctx.config.with_sample_end(resolution.resolved)


def _log_sample_end(ctx: PipelineContext) -> None:
    """Log the year the build runs through and where it came from."""
    res = ctx.sample_end_resolution
    if res is None:
        return
    detail = {
        "explicit": "set in the config",
        "demo": f"{LATEST_SAMPLE_END!r} in a demo build",
        "clamped-siz": f"{res.requested} clamped to the end of the SIZ tape",
        "metadata": f"{LATEST_SAMPLE_END!r}, as resolved by the database's last build",
        "wrds": f"{LATEST_SAMPLE_END!r}, the last complete year on WRDS",
    }[res.source]
    if res.crsp_last_december:
        detail += (
            f"; CRSP {ctx.source.monthly_table} through {res.crsp_max_date} "
            f"(last December {res.crsp_last_december}), Compustat through "
            f"{res.compustat_max_date} (last December {res.compustat_last_december})"
        )
    msg = f"Sample: {ctx.config.sample_start}..{ctx.config.sample_end} (sample_end {detail})."
    ctx.logger.info(msg, extra={"printed": True})
    print(msg, flush=True)


CZ_STAGE = "fetch-cz-anomalies"
# ``metadata`` key holding the release ``cz_anomalies`` and ``cz_signal_info`` came from.
CZ_RELEASE_KEY = "cz_release"


def _preflight_cz(ctx: PipelineContext, planned: Sequence[str]) -> None:
    """
    Check the Chen-Zimmerman settings before the first stage runs, offline.

    A bad ``cz_release_version`` is a config error, so it raises here rather
    than hours into the build. Nothing is downloaded or looked up:
    ``fetch-cz-anomalies`` finds the newest release (when none is configured)
    and downloads the files itself, and a failure there does not stop the
    build. For the signal panel and the SignalDoc, log the local file the
    stage will read, or that it will download one; a pin naming a missing
    file raises. Demo runs skip this.
    """
    if ctx.demo or CZ_STAGE not in planned:
        return
    label = cz_ingest.cz_release_label(ctx.config)  # ValueError on a bad label
    if label is None:
        release = "the newest release on Hugging Face (looked up when the stage runs)"
        source = cz_release.branch_url()
    else:
        release = f"release {label}"
        source = cz_release.branch_url(cz_release.CZ_RELEASES[label])
    for what, find, pin in (
        ("signals", cz_ingest.find_local_cz_signals, "--cz-signals-path"),
        ("SignalDoc", cz_ingest.find_local_signal_doc, "--cz-signal-doc-path"),
    ):
        found = find(ctx.config, ctx.db_path)  # FileNotFoundError on a missing pin
        if found is not None:
            ctx.logger.info(
                "Found CZ %s file: %s (%s)",
                what,
                found.path,
                found.release or f"release unknown, {found.origin}",
            )
        else:
            ctx.logger.info(
                "No local CZ %s file; %s will read %s from the release cache in "
                "staging, or download it from Hugging Face (needs huggingface.co "
                "and *.hf.co). To skip the download, save the file from %s in "
                "inputs/ or pin it with `aa set-params %s <file>`",
                what,
                CZ_STAGE,
                release,
                source,
                pin,
            )


class CRSPFormatMismatchError(RuntimeError):
    """
    Raised when an existing database was built from a different CRSP tape.

    The two tapes disagree about returns, share codes and delisting semantics,
    so half-refreshing a SIZ database with CIZ stages (or the reverse) would
    leave a panel whose columns come from two different tapes. Rebuilding from
    scratch is the only safe way to switch.
    """


def _read_metadata(db_path: str | Path, keys: Sequence[str]) -> dict[str, str] | None:
    """
    ``{key: value}`` for those of ``keys`` present in the ``metadata`` table.

    ``None`` when there is nothing to read: the file is absent, unreadable, or
    has no ``metadata`` table. Reads through the session cache's kept-alive
    connection when one is open for the file (a protocol run holds one after
    loading the zoo); opening the file read-only beside it is refused by
    DuckDB, and that refusal used to be swallowed, so the report said the
    database recorded no C-Z release. A connection that cannot be
    opened is now logged at WARNING.
    """
    path = Path(db_path)
    if not path.exists():
        return None
    import duckdb

    from . import session_cache

    con = session_cache.cached_connection(path)
    owned = con is None
    if owned:
        try:
            con = duckdb.connect(str(path), read_only=True)
        except duckdb.Error as exc:
            LOGGER.warning("Could not read the metadata table of %s: %s", path, exc)
            return None
    try:
        tables = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = 'metadata'"
        ).fetchall()
        if not tables:
            return None
        placeholders = ", ".join("?" for _ in keys)
        rows = con.execute(
            f"SELECT key, value FROM metadata WHERE key IN ({placeholders})",
            list(keys),
        ).fetchall()
    except duckdb.Error as exc:
        LOGGER.warning("Could not read the metadata table of %s: %s", path, exc)
        return None
    finally:
        if owned:
            con.close()
    return {str(k): v for k, v in rows}


def persisted_cz_release(
    db_path: str | Path | None = None,
) -> dict[str, dict[str, str]] | None:
    """
    Which C-Z release the database's zoo came from, as the C-Z stage stored it.

    ``{"signals": {"release": "2026.10", "branch": ..., "commit": ...},
    "signal_doc": {...}}``; ``release`` is ``"unknown"`` (or ``"unknown (...)"``)
    for a pinned or hand-placed file. ``None`` when the database does not say:
    it is missing, or its zoo was built before the release was recorded.
    ``db_path=None`` means the configured database, as for the zoo loader.
    """
    if db_path is None:
        # Same resolution as the zoo loader (``data_access._db_path``).
        try:
            from .config import load_config

            db_path = load_config().database_path
        except Exception:  # no usable config: nothing to read
            return None
    rows = _read_metadata(db_path, [CZ_RELEASE_KEY])
    value = (rows or {}).get(CZ_RELEASE_KEY)
    if not value:
        return None
    try:
        record = json.loads(value)
    except ValueError:
        return None
    return record if isinstance(record, dict) else None


def _persisted_crsp_format(db_path: Path) -> str | None:
    """
    The CRSP tape an existing database was built from, or ``None``.

    ``None`` means "no build to conflict with": the file is absent, or no build
    has finished against it. Every build creates ``metadata`` in its first
    stage and the C-Z stage writes ``cz_release`` into it mid-build, but only
    :meth:`PipelineContext.persist_metadata`, at the end, writes
    ``refresh_completed_at`` (always has, since before the CIZ tape was supported). So a table
    without that key is an interrupted first build, not an old one. A finished
    build that has ``refresh_completed_at`` but no ``crsp_format`` predates
    CIZ support and can only have come from the legacy tape.
    """
    rows = _read_metadata(db_path, ["crsp_format", "refresh_completed_at"])
    if rows is None:
        return None
    if rows.get("crsp_format"):
        return str(rows["crsp_format"]).strip().strip('"').lower()
    if "refresh_completed_at" not in rows:
        return None
    return LEGACY_CRSP_FORMAT


def setup_database(
    config: AssayConfig | None = None,
    *,
    full_refresh: bool = False,
    verbose: bool = False,
    start_from: str | None = None,
    demo: bool = False,
    skip_memory_check: bool = False,
) -> Path:
    """
    Build the library database.

    ``demo=True`` builds from deterministic synthetic stand-ins wherever a real
    input is unavailable, and stamps the result so downstream code can refuse
    it. The default is production: a missing credential or a failed download
    raises (:class:`~assayinganomalies.provenance.MissingCredentialsError`,
    :class:`~assayinganomalies.provenance.DownloadFailedError`) rather than
    substituting synthetic data into a database nothing marks as synthetic.

    The Chen-Zimmerman stage is the exception: its failure raises
    :class:`NonFatalStageError` inside the stage, which is recorded as
    ``failed-nonfatal``. The build then finishes without ``cz_anomalies``,
    prints a summary of what did not complete and how to fetch it, and returns
    normally.

    Before stage 1 the build checks that the machine has the RAM the sample
    needs and raises :class:`InsufficientMemoryError` if not;
    ``skip_memory_check=True`` turns that into a warning.
    """
    cfg = config or load_config()
    db_path = Path(cfg.database_path)
    staging_dir = db_path.parent / "staging"

    from .session_cache import close_cached_connection

    close_cached_connection(db_path)

    _configure_setup_logging(db_path=db_path, verbose=verbose)
    ctx = PipelineContext(cfg, db_path, staging_dir, full_refresh, demo=demo)

    built_format = _persisted_crsp_format(db_path)
    if built_format is not None and built_format != ctx.source.name and not full_refresh:
        raise CRSPFormatMismatchError(
            f"{db_path} was built from the {built_format!r} CRSP tape but "
            f"crsp_format is now {ctx.source.name!r}. The tapes differ in "
            f"returns, share codes and delisting semantics, so they cannot be "
            f"mixed in one database. Rerun with --full-refresh to rebuild from "
            f"scratch, or set crsp_format back to {built_format!r}."
        )

    ctx.logger.info(
        "Setup starting: sample=%s..%s dom_com_eq=%s crsp_format=%s "
        "wrds_username=%s staging_dir=%s demo=%s",
        cfg.sample_start,
        cfg.sample_end,
        cfg.dom_com_eq,
        ctx.source.name,
        bool(cfg.wrds_username),
        staging_dir,
        demo,
    )
    if demo:
        ctx.logger.warning(
            "DEMO MODE: this build may substitute synthetic data for any input "
            "it cannot obtain. The database will be stamped %s=true and "
            "production protocol runs will refuse it.",
            DEMO_KEY,
        )

    # Determine which stages to run
    stage_names = [s.name for s in STAGES]
    if start_from:
        if start_from not in stage_names:
            available = ", ".join(stage_names)
            raise ValueError(
                f"Unknown stage '{start_from}'. Available stages: {available}"
            )
        skip_to = stage_names.index(start_from)
    else:
        skip_to = 0

    total = len(STAGES)
    planned = [s.name for s in STAGES[skip_to:]]
    try:
        # An explicit year is known now, so the memory check still runs
        # before the Duo push; "latest" needs the login to learn the year.
        _clamp_sample_end_for_tape(ctx)
        if not ctx.config.sample_end_is_latest:
            _preflight_memory(ctx, planned, skip=skip_memory_check)
        _preflight_credentials(ctx, planned)
        _preflight_sample_end(ctx, planned)
        if ctx.sample_end_requested == LATEST_SAMPLE_END:
            _preflight_memory(ctx, planned, skip=skip_memory_check)
        _preflight_cz(ctx, planned)
        _preflight_tcost_inputs(ctx, planned)
        _preflight_compustat_variables(ctx, planned)
        _log_sample_end(ctx)
        last_daily_stage = _last_daily_parquet_stage(planned)
        # For the run manifest: `persist_metadata` replaces the stored stage
        # history with this run's, so read the earlier pull dates first.
        started_at = run_manifest.utc_now()
        prior_history = _load_stage_history(db_path)
        with run_manifest.recording_inputs() as noted_inputs:
            for idx, stage in enumerate(STAGES, start=1):
                if idx - 1 < skip_to:
                    msg = f"[{idx}/{total}] Skipping {stage.name}"
                    ctx.logger.info(msg)
                    print(msg, flush=True)
                    continue
                msg = f"[{idx}/{total}] Running {stage.name}"
                ctx.logger.info(msg)
                print(msg, flush=True)
                stage.run(ctx)
                if stage.name == last_daily_stage:
                    ctx.release_daily_raw()
                if ctx.stage_history and ctx.stage_history[-1]["status"] == NONFATAL_STATUS:
                    done_msg = f"[{idx}/{total}] Did not complete {stage.name}; continuing"
                else:
                    done_msg = f"[{idx}/{total}] Done {stage.name}"
                ctx.logger.info(done_msg)
                print(done_msg, flush=True)

        ctx.persist_metadata()
        # Stamp the provenance last, so it reflects a build that actually finished.
        # A demo build always stamps. A production build clears an inherited stamp
        # only on a full refresh from the first stage, which is the one run that
        # rebuilds every table; anything narrower may leave synthetic rows behind,
        # and an over-eager clear would hand back a demo database labelled real.
        if demo:
            mark_database_demo(ctx.db_path, True)
        elif full_refresh and start_from is None:
            mark_database_demo(ctx.db_path, False)
        elif database_is_demo(ctx.db_path):
            ctx.logger.warning(
                "%s is still stamped %s=true from an earlier demo build. This run "
                "replaced only part of it. Rerun with --full-refresh to clear the "
                "stamp.",
                ctx.db_path,
                DEMO_KEY,
            )
        _write_database_manifest(
            ctx,
            noted_inputs,
            started_at=started_at,
            prior_history=prior_history,
            start_from=start_from,
        )
        _report_nonfatal_stages(ctx)
        return ctx.db_path
    finally:
        ctx.close_wrds()


def _report_nonfatal_stages(ctx: PipelineContext) -> None:
    """Log and print the stages that raised :class:`NonFatalStageError`."""
    failed = [e for e in ctx.stage_history if e.get("status") == NONFATAL_STATUS]
    if not failed:
        return
    names = ", ".join(e["name"] for e in failed)
    lines = [f"Build finished; {len(failed)} stage(s) did not complete: {names}."]
    for entry in failed:
        lines.append(f"- {entry['name']}: {entry.get('message', '')}")
        if entry.get("hint"):
            lines.append(f"  {entry['hint']}")
    lines.append("Everything else in the database is usable.")
    summary = "\n".join(lines)
    ctx.logger.warning(summary, extra={"printed": True})
    print(summary, flush=True)


def _write_database_manifest(
    ctx: PipelineContext,
    noted_inputs: list[dict[str, str]],
    *,
    started_at: str,
    prior_history: list[dict[str, str]],
    start_from: str | None = None,
    rebuild_id: str | None = None,
    command: str | None = None,
) -> Path | None:
    """Write ``<db>.manifest.json`` beside the database; never raises.

    Called after the demo stamp is settled, so the manifest's ``demo_data``
    is what the database itself now says. See :mod:`.run_manifest`.
    """
    try:
        t0 = time.perf_counter()
        manifest = run_manifest.database_manifest(
            config=ctx.config,
            db_path=ctx.db_path,
            staging_dir=ctx.staging_dir,
            crsp_format=ctx.source.name,
            demo=database_is_demo(ctx.db_path),
            stage_history=ctx.stage_history,
            prior_history=prior_history,
            noted_inputs=noted_inputs,
            started_at=started_at,
            full_refresh=ctx.full_refresh,
            start_from=start_from,
            rebuild_id=rebuild_id,
            sample_end=ctx.resolved_sample_end_record(),
            compustat_extra_vars=persisted_extra_vars(ctx.db_path),
            command=command,
        )
        path = run_manifest.write_manifest(
            run_manifest.build_manifest_path(ctx.db_path), manifest
        )
    except Exception:  # noqa: BLE001 - the receipt must not sink the build
        ctx.logger.exception("Could not write the database run manifest")
        return None
    ctx.logger.info(
        "Wrote run manifest %s (scientific_id=%s, %d inputs hashed in %.1fs)",
        path,
        manifest["scientific_id"][:12],
        len(manifest["scientific"]["inputs"]),
        time.perf_counter() - t0,
    )
    return path


# ---------------------------------------------------------------------------
# Scoped rebuild
# ---------------------------------------------------------------------------


class RebuildError(Exception):
    """Base class for all rebuild failures."""


class RebuildRefetchBlockedError(RebuildError):
    """Raised when a plan includes fetch-* stages but allow_refetch is False."""


class RebuildAbortedError(RebuildError):
    """Raised when the resolved plan exceeds the safety limit without
    confirm_large=True."""


class RebuildUpstreamMissingError(RebuildError):
    """Raised when an upstream stage required by the plan has never run
    (no metadata.stage_history record of success)."""


class RebuildInterruptedError(RebuildError):
    """Raised when a prior rebuild left the rebuild_state journal in a
    dirty state (running/pending without a terminal status)."""


@dataclass
class StageResult:
    stage: str
    status: str  # done | failed | skipped | pending
    started_at: str | None = None
    finished_at: str | None = None
    message: str = ""


@dataclass
class RebuildReport:
    requested_stages: list[str] | None
    requested_columns: list[str] | None
    requested_tables: list[str] | None
    resolved_plan: list[str]
    executed: list[StageResult]
    dry_run: bool
    started_at: str
    finished_at: str | None
    db_path: Path
    rebuild_id: str | None = None
    log_path: Path | None = None
    demo: bool = False


REBUILD_PLAN_SOFT_LIMIT = 8


def _expand_plan(
    *,
    stages: list[str] | None,
    columns: list[str] | None,
    tables: list[str] | None,
) -> list[str]:
    """Resolve a rebuild request to an ordered stage list.

    Exactly one of ``stages``, ``columns``, ``tables`` must be provided.
    Each selected root stage expands through the downstream cascade
    rule (every later stage in the same table writer chain must
    re-run), and the final list is sorted by pipeline execution order
    with duplicates removed.
    """
    from . import stage_registry

    provided = [x is not None for x in (stages, columns, tables)]
    if sum(provided) != 1:
        raise ValueError(
            "rebuild: exactly one of stages|columns|tables must be provided"
        )

    if stages is not None:
        roots = list(dict.fromkeys(stages))  # dedupe, keep order
        live = {s.name for s in STAGES}
        unknown = [s for s in roots if s not in live]
        if unknown:
            raise ValueError(f"unknown stage(s) in rebuild request: {unknown}")
    elif columns is not None:
        roots = stage_registry.stages_for_columns(list(columns))
    else:
        assert tables is not None
        roots = stage_registry.stages_for_tables(list(tables))

    # Expand cascade
    needed: set[str] = set()
    for r in roots:
        for s in stage_registry.downstream_of(r):
            needed.add(s)

    # Preserve execution order
    order = [s.name for s in STAGES]
    return [s for s in order if s in needed]


def _check_refetch_policy(plan: list[str], allow_refetch: bool) -> None:
    from . import stage_registry

    offenders = [s for s in plan if s in stage_registry.FETCH_STAGES]
    if offenders and not allow_refetch:
        raise RebuildRefetchBlockedError(
            f"plan includes fetch-* stages but allow_refetch=False: {offenders}"
        )


def _check_plan_size(plan: list[str], confirm_large: bool) -> None:
    if len(plan) > REBUILD_PLAN_SOFT_LIMIT and not confirm_large:
        raise RebuildAbortedError(
            f"plan has {len(plan)} stages (limit {REBUILD_PLAN_SOFT_LIMIT}); "
            "re-run with confirm_large=True if intentional"
        )


def _check_upstream_satisfied(
    plan: list[str],
    stage_history: list[dict[str, str]],
) -> None:
    """Every stage that the plan reads from (and that is NOT itself in
    the plan) must have a prior ``succeeded`` entry in stage_history."""
    from . import stage_registry

    succeeded = {
        entry["name"]
        for entry in stage_history
        if entry.get("status") == "succeeded"
    }
    plan_set = set(plan)
    missing: list[str] = []
    for stage in plan:
        for upstream in stage_registry.STAGE_READS.get(stage, set()):
            if upstream in plan_set:
                continue
            if upstream not in succeeded:
                missing.append(f"{stage} -> {upstream}")
    if missing:
        raise RebuildUpstreamMissingError(
            "upstream stages never ran successfully: " + ", ".join(missing)
        )


def _load_stage_history(db_path: Path) -> list[dict[str, str]]:
    if not db_path.exists():
        return []
    try:
        with DuckDBManager(db_path) as mgr:
            rows = mgr.query_df(
                "SELECT value FROM metadata WHERE key = 'stage_history'"
            )
    except Exception:  # pragma: no cover - missing metadata table is normal on first rebuild
        return []
    if rows.empty:
        return []
    raw = rows.iloc[0, 0]
    try:
        loaded = json.loads(raw)
        return loaded if isinstance(loaded, list) else []
    except (TypeError, ValueError):
        return []


def rebuild(
    *,
    stages: list[str] | None = None,
    columns: list[str] | None = None,
    tables: list[str] | None = None,
    dry_run: bool = False,
    allow_refetch: bool = False,
    confirm_large: bool = False,
    config: AssayConfig | None = None,
    verbose: bool = False,
    demo: bool = False,
) -> RebuildReport:
    """Scoped rebuild of selected pipeline stages.

    Exactly one of ``stages``, ``columns``, ``tables`` must be given.
    Downstream stages in the same table writer chain are automatically
    added to the plan (cascade), so callers don't have to think about
    what else writes the same table.

    Guardrails:

    * ``allow_refetch=False`` (default) — any ``fetch-*`` stage in the
      resolved plan raises ``RebuildRefetchBlockedError``. The
      self-healing fixer must never set this True.
    * ``confirm_large=False`` (default) — plans longer than
      ``REBUILD_PLAN_SOFT_LIMIT`` raise ``RebuildAbortedError``.
    * Upstream check — every non-plan stage the plan depends on must have
      a prior ``succeeded`` record in ``metadata.stage_history`` (from a
      previous ``setup_database`` or ``rebuild`` run) or be in the plan
      itself. Raises ``RebuildUpstreamMissingError`` otherwise.

    ``dry_run=True`` returns a populated ``RebuildReport`` without
    touching the DB — useful for the fixer Agent to preview scope before
    the orchestrator confirms.

    ``demo=False`` (default) is the production path: a fetch stage with no
    credentials, or a failed download, raises instead of writing synthetic
    stand-in data. ``demo=True`` allows the stand-ins and stamps the database
    so downstream code can refuse it. A rebuild never clears an existing
    stamp — it replaces part of a database, so it cannot vouch for the rest.
    """
    cfg = config or load_config()
    db_path = Path(cfg.database_path).expanduser()

    plan = _expand_plan(stages=stages, columns=columns, tables=tables)
    _check_refetch_policy(plan, allow_refetch)
    _check_plan_size(plan, confirm_large)

    # The upstream check is a safety rail against partial rebuilds on a
    # live DB. When the DB file doesn't exist there is no history to
    # check against, and the execution path below will fail anyway;
    # skipping keeps dry_run plan previews cheap for the fixer Agent.
    if db_path.exists():
        history = _load_stage_history(db_path)
        _check_upstream_satisfied(plan, history)

    started = datetime.now(timezone.utc).isoformat()
    report = RebuildReport(
        requested_stages=list(stages) if stages else None,
        requested_columns=list(columns) if columns else None,
        requested_tables=list(tables) if tables else None,
        resolved_plan=plan,
        executed=[StageResult(stage=s, status="pending") for s in plan],
        dry_run=dry_run,
        started_at=started,
        finished_at=None,
        db_path=db_path,
        demo=bool(demo) or database_is_demo(db_path),
    )

    if dry_run:
        report.finished_at = datetime.now(timezone.utc).isoformat()
        return report

    return _execute_rebuild(report, cfg, verbose=verbose, demo=bool(demo))


def _rebuild_log_dir(db_path: Path) -> Path:
    return db_path.parent / "logs" / "rebuilds"


def _init_rebuild_state(db_path: Path) -> None:
    """Ensure the rebuild_state journal table exists. The journal is a
    per-row record of ``(rebuild_id, stage, status, plan_json, ts)``
    used to detect interrupted rebuilds on the next entry."""
    with DuckDBManager(db_path) as mgr:
        mgr.execute(
            """
            CREATE TABLE IF NOT EXISTS rebuild_state (
                rebuild_id TEXT,
                stage TEXT,
                status TEXT,
                plan_json TEXT,
                ts TEXT
            )
            """
        )


def _write_rebuild_state(
    db_path: Path,
    rebuild_id: str,
    stage: str,
    status: str,
    plan: list[str],
) -> None:
    with DuckDBManager(db_path) as mgr:
        mgr.execute(
            "INSERT INTO rebuild_state (rebuild_id, stage, status, plan_json, ts) VALUES (?, ?, ?, ?, ?)",
            rebuild_id,
            stage,
            status,
            json.dumps(plan),
            datetime.now(timezone.utc).isoformat(),
        )


def _check_rebuild_state_clean(db_path: Path, plan: list[str]) -> None:
    """Refuse to start a new rebuild when the journal shows any stage in
    ``pending`` or ``running`` without a matching terminal row. If the
    interrupted plan matches the new plan, we let the caller resume by
    re-running (overwriting state rows). Otherwise raise.
    """
    with DuckDBManager(db_path) as mgr:
        rows = mgr.query_df(
            """
            SELECT rebuild_id, stage, status, plan_json
            FROM rebuild_state
            ORDER BY ts
            """
        )
    if rows.empty:
        return

    # Group terminal vs non-terminal per (rebuild_id, stage)
    terminal = {"done", "failed", "skipped"}
    latest: dict[tuple[str, str], tuple[str, str]] = {}
    for _, r in rows.iterrows():
        latest[(r["rebuild_id"], r["stage"])] = (r["status"], r["plan_json"])

    dirty = [
        (rid, stage, plan_json)
        for (rid, stage), (status, plan_json) in latest.items()
        if status not in terminal
    ]
    if not dirty:
        return

    # If every dirty row is from a rebuild whose plan matches ours, allow
    # resume. Otherwise refuse.
    plan_str = json.dumps(plan)
    non_matching = [d for d in dirty if d[2] != plan_str]
    if non_matching:
        rid_sample = non_matching[0][0]
        raise RebuildInterruptedError(
            f"rebuild_state has unresolved entries from rebuild_id={rid_sample}; "
            "clear them via DELETE FROM rebuild_state or re-run the same plan to resume"
        )


def _persist_rebuild_log(report: "RebuildReport") -> Path:
    log_dir = _rebuild_log_dir(report.db_path)
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{report.rebuild_id}.json"
    payload = {
        "rebuild_id": report.rebuild_id,
        "db_path": str(report.db_path),
        **provenance_payload(report.demo),
        "requested_stages": report.requested_stages,
        "requested_columns": report.requested_columns,
        "requested_tables": report.requested_tables,
        "resolved_plan": report.resolved_plan,
        "started_at": report.started_at,
        "finished_at": report.finished_at,
        "executed": [
            {
                "stage": sr.stage,
                "status": sr.status,
                "started_at": sr.started_at,
                "finished_at": sr.finished_at,
                "message": sr.message,
            }
            for sr in report.executed
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _execute_rebuild(
    report: "RebuildReport",
    cfg: AssayConfig,
    *,
    verbose: bool,
    demo: bool = False,
) -> "RebuildReport":
    """Run each stage in ``report.resolved_plan`` against a fresh
    PipelineContext, journaling progress to ``rebuild_state``."""
    db_path = report.db_path
    staging_dir = db_path.parent / "staging"
    # Start from the recorded history so persisting it at the end appends this
    # rebuild's stages instead of replacing every earlier record; the upstream
    # check of the next rebuild needs those records.
    ctx = PipelineContext(
        cfg, db_path, staging_dir, full_refresh=False, demo=demo,
        stage_history=_load_stage_history(db_path),
    )
    try:
        _preflight_credentials(ctx, report.resolved_plan)
        _clamp_sample_end_for_tape(ctx)
        _preflight_sample_end(ctx, report.resolved_plan)
        _preflight_cz(ctx, report.resolved_plan)
        _preflight_tcost_inputs(ctx, report.resolved_plan)
        _preflight_compustat_variables(ctx, report.resolved_plan)

        _configure_setup_logging(db_path=db_path, verbose=verbose)
        _init_rebuild_state(db_path)
        _check_rebuild_state_clean(db_path, report.resolved_plan)

        rebuild_id = f"rebuild_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        report.rebuild_id = rebuild_id

        stages_by_name = {s.name: s for s in STAGES}
        total = len(report.resolved_plan)
        sr_by_stage = {sr.stage: sr for sr in report.executed}
        last_daily_stage = _last_daily_parquet_stage(report.resolved_plan)

        with run_manifest.recording_inputs() as noted_inputs:
            for idx, name in enumerate(report.resolved_plan, start=1):
                sr = sr_by_stage[name]
                sr.started_at = datetime.now(timezone.utc).isoformat()
                sr.status = "running"
                _write_rebuild_state(db_path, rebuild_id, name, "running", report.resolved_plan)
                msg = f"[rebuild {idx}/{total}] {name}"
                ctx.logger.info(msg)
                print(msg, flush=True)
                try:
                    stages_by_name[name].run(ctx)
                except Exception as exc:
                    sr.status = "failed"
                    sr.finished_at = datetime.now(timezone.utc).isoformat()
                    sr.message = str(exc)
                    _write_rebuild_state(db_path, rebuild_id, name, "failed", report.resolved_plan)
                    report.finished_at = datetime.now(timezone.utc).isoformat()
                    report.log_path = _persist_rebuild_log(report)
                    raise
                if name == last_daily_stage:
                    ctx.release_daily_raw()
                sr.status = "done"
                sr.finished_at = datetime.now(timezone.utc).isoformat()
                _write_rebuild_state(db_path, rebuild_id, name, "done", report.resolved_plan)

        # Merge new successes into metadata.stage_history so the next
        # upstream check sees them.
        ctx.persist_metadata()
        if demo:
            mark_database_demo(db_path, True)
        report.demo = database_is_demo(db_path)
        report.finished_at = datetime.now(timezone.utc).isoformat()
        report.log_path = _persist_rebuild_log(report)
        # The database changed, so the manifest beside it must not describe the
        # build before this one. `ctx.stage_history` already holds the earlier
        # records (it was loaded at the start), so no prior history is needed.
        _write_database_manifest(
            ctx,
            noted_inputs,
            started_at=report.started_at or run_manifest.utc_now(),
            prior_history=[],
            rebuild_id=rebuild_id,
        )
        return report
    finally:
        ctx.close_wrds()


__all__ = [
    "setup_database",
    "rebuild",
    "InsufficientMemoryError",
    "DemoDatabaseError",
    "DownloadFailedError",
    "MissingCredentialsError",
    "NonFatalStageError",
    "RebuildError",
    "RebuildRefetchBlockedError",
    "RebuildAbortedError",
    "RebuildUpstreamMissingError",
    "RebuildInterruptedError",
    "RebuildReport",
    "StageResult",
    "REBUILD_PLAN_SOFT_LIMIT",
]

