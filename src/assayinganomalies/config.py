"""
Configuration management for the Assaying Anomalies toolkit.

Config resolution order:
1. If AA_CONFIG_PATH env var is set → use JSON file at that path
2. Otherwise → config stored in the DuckDB database, <project>/Data/aa.duckdb

The project folder holds ``Data/`` (the database, logs, staging files) and
``Scratch/Assay/`` (outputs). It is, in order: a ``project_dir`` argument, the
AA_PROJECT_DIR env var, the folder saved by ``aa set-params --project-dir``
(see :func:`set_project_dir`), or the current folder. See
:func:`resolve_project_dir`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass, field, replace
import json
import os
import logging
from pathlib import Path
import tempfile
from typing import Any

LOGGER = logging.getLogger("assayinganomalies.config")

# Kept here rather than imported from ``ingest.crsp_source`` so that validating
# a config never drags pandas/pyarrow in; the source module asserts it agrees.
VALID_CRSP_FORMATS: tuple[str, ...] = ("siz", "ciz")

# The cost models ``transforms.tcosts.make_trading_costs`` accepts, listed here so
# the CLI can offer them without importing the transform.
VALID_TCOSTS_TYPES: tuple[str, ...] = ("full", "lf_combo", "gibbs")

# Tape a *new* build reads when nothing says otherwise.
DEFAULT_CRSP_FORMAT = "ciz"

# Marker for "this database was built before crsp_format existed". A config
# persisted without the key can only have come from the legacy tape, so it
# keeps loading as SIZ regardless of what DEFAULT_CRSP_FORMAT is today.
LEGACY_CRSP_FORMAT = "siz"

# ``sample_end`` sentinel: the last complete calendar year on the WRDS tapes,
# looked up when ``setup-database`` runs (see ``ingest/sample_end.py``). The
# config keeps the sentinel; the build works on a copy holding the year, and
# records that year in the database's ``metadata`` table and run manifest.
LATEST_SAMPLE_END = "latest"

# CRSP froze the SIZ tape (Flat File Format 1.0) in January 2025, so its last
# complete year is 2024; "latest" on SIZ resolves to it, and an explicit later
# year is clamped to it.
SIZ_FROZEN_END_YEAR = 2024

# What "latest" means in a demo build, which has no tape to ask. A constant,
# so demo databases and the tests that build them do not depend on the date.
DEMO_SAMPLE_END = 2024

# ``metadata`` key holding the year the last build resolved ``sample_end`` to.
SAMPLE_END_RESOLVED_KEY = "sample_end_resolved"


class SampleEndUnresolvedError(RuntimeError):
    """``sample_end`` is "latest" and no build has recorded what year that is."""


def normalize_sample_end(value: Any) -> int | str:
    """``sample_end`` as an int year, or :data:`LATEST_SAMPLE_END`.

    Accepts an int or a numeric string (``2024``, ``"2024"``); ``"latest"``
    (any case), an empty string and ``None`` mean the sentinel. Anything else
    raises ``ValueError``.
    """
    if value is None:
        return LATEST_SAMPLE_END
    if isinstance(value, bool):
        raise ValueError(f"sample_end must be a year or {LATEST_SAMPLE_END!r}; got {value!r}")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = str(value).strip()
    if text == "" or text.lower() == LATEST_SAMPLE_END:
        return LATEST_SAMPLE_END
    try:
        return int(text)
    except ValueError:
        raise ValueError(
            f"sample_end must be a year such as 2024 or {LATEST_SAMPLE_END!r}; got {value!r}"
        ) from None


def read_metadata_value(db_path: str | Path, key: str) -> Any:
    """``key`` from the database's ``metadata`` table, JSON-decoded; ``None`` when absent.

    Absent covers a missing file, a database without a ``metadata`` table and
    a missing key. The database is opened read-only.
    """
    return _read_key_value(db_path, "metadata", key)


def read_db_setting(db_path: str | Path, key: str) -> Any:
    """``key`` from the database's ``config`` table, JSON-decoded; ``None`` when absent."""
    return _read_key_value(db_path, "config", key)


def write_db_setting(db_path: str | Path, key: str, value: Any) -> None:
    """Store ``value`` (as JSON) under ``key`` in the database's ``config`` table.

    For settings that are not :class:`AssayConfig` fields: ``from_db_dict``
    ignores unknown keys and ``_save_config_to_db`` writes only its own, so a
    key written here survives ``set-params`` and a full refresh.
    """
    import duckdb

    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    try:
        _ensure_config_table(con)
        con.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            [key, json.dumps(value)],
        )
    finally:
        con.close()


def _read_key_value(db_path: str | Path, table: str, key: str) -> Any:
    path = Path(db_path).expanduser()
    if not path.is_file():
        return None
    import duckdb

    try:
        con = duckdb.connect(str(path), read_only=True)
    except Exception:  # pragma: no cover - unreadable file behaves as absent
        return None
    try:
        rows = con.execute(f"SELECT value FROM {table} WHERE key = ?", [key]).fetchall()
    except Exception:  # no such table
        return None
    finally:
        con.close()
    if not rows or rows[0][0] is None:
        return None
    try:
        return json.loads(rows[0][0])
    except (json.JSONDecodeError, TypeError):
        return rows[0][0]


# Env override for protocol process-pool size. Takes precedence
# over the persisted config value when ``n_jobs`` is not passed explicitly.
PROTOCOL_N_JOBS_ENV = "AA_PROTOCOL_N_JOBS"

# Env override for the RAM budget the protocol may spend across all workers,
# in gibibytes. Takes precedence over the
# persisted config value.
MEMORY_BUDGET_ENV = "AA_MEMORY_GB"

# Resident-set estimate for one protocol worker, in GiB. Measured on a
# fresh run: the 157-anomaly protocol at ``n_jobs=15`` peaked at
# 41-58 GB RSS, i.e. roughly 2.7-3.9 GB per worker. We take the top of that
# range and round up, because being one worker short costs wall time whereas
# being one worker over gets the job OOM-killed on a shared cluster node.
PROTOCOL_WORKER_GB = 4.0

# Fraction of physical RAM the protocol claims when no explicit budget is set.
# The remaining quarter is left for the OS page cache, DuckDB's buffer pool and
# whatever else shares the node.
DEFAULT_MEMORY_FRACTION = 0.75

# Recommended RAM for `aa setup-database`: the maintainer's figures for
# samples ending in 2025, as (sample start, CRSP daily rows, GiB). This is the
# README's Memory table. Other windows are interpolated from it; see
# `crsp_daily_rows` and `required_setup_ram_gb`.
SETUP_RAM_ANCHOR_END = 2025
SETUP_RAM_ANCHORS: tuple[tuple[int, float, float], ...] = (
    (1925, 110e6, 80.0),
    (1963, 101e6, 72.0),
    (1973, 95e6, 68.0),
    (1990, 70e6, 52.0),
)

# No build is estimated below this, however short the sample.
SETUP_RAM_FLOOR_GB = 8.0

# Legacy env var (still supported for backwards compatibility)
LEGACY_CONFIG_PATH_ENV = "ASSAYINGANOMALIES_CONFIG_PATH"
# New shorter env var
CONFIG_PATH_ENV = "AA_CONFIG_PATH"
# Project folder for this shell session, ahead of the saved one.
PROJECT_DIR_ENV = "AA_PROJECT_DIR"


class ProjectDirError(RuntimeError):
    """The configured project folder does not exist or cannot be read."""


class DatabaseNotFoundError(RuntimeError):
    """The database to read is missing, or holds nothing but settings."""


def _user_settings_path() -> Path:
    """Per-user file holding the saved project folder (and nothing else).

    A function rather than a constant so tests can point it at a temp file.
    """
    from platformdirs import user_config_dir

    return Path(user_config_dir("assayinganomalies", appauthor=False)) / "settings.json"


def _read_user_settings() -> dict[str, Any]:
    path = _user_settings_path()
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise ProjectDirError(
            f"Cannot read the saved project folder from {path} ({exc}). Fix or "
            "delete that file, or run: aa set-params --project-dir <folder>"
        ) from exc
    return data if isinstance(data, dict) else {}


def _write_user_settings(data: dict[str, Any]) -> Path:
    """Write the settings file atomically: a temp file, then a rename."""
    path = _user_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".settings-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def _absolute(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def resolve_project_dir(project_dir: str | Path | None = None) -> tuple[Path, str]:
    """``(folder, source)``: the project folder and where it came from.

    Order: the ``project_dir`` argument, the AA_PROJECT_DIR env var, the folder
    saved by :func:`set_project_dir`, the current folder. ``source`` is
    ``"argument"``, ``"AA_PROJECT_DIR"``, ``"saved in <file>"`` or
    ``"current folder"``. A folder named by the env var or the saved file
    that does not exist raises :class:`ProjectDirError` rather than
    falling back to the current folder.
    """
    if project_dir is not None:
        return _absolute(project_dir), "argument"
    env = os.getenv(PROJECT_DIR_ENV)
    if env and env.strip():
        path = _absolute(env.strip())
        if not path.is_dir():
            raise ProjectDirError(
                f"{PROJECT_DIR_ENV} is set to {env!r}, but {path} is not a "
                f"folder. Create it, or unset {PROJECT_DIR_ENV}."
            )
        return path, PROJECT_DIR_ENV
    saved = _read_user_settings().get("project_dir")
    if saved:
        settings = _user_settings_path()
        path = _absolute(saved)
        if not path.is_dir():
            raise ProjectDirError(
                f"The saved project folder {path} (in {settings}) does not "
                "exist. Reconnect the drive, or choose another folder with: "
                "aa set-params --project-dir <folder>"
            )
        return path, f"saved in {settings}"
    return Path.cwd(), "current folder"


def set_project_dir(path: str | Path) -> Path:
    """Remember ``path`` as the project folder for every later run.

    The folder is created if missing. Returns its absolute path.
    """
    folder = _absolute(path)
    folder.mkdir(parents=True, exist_ok=True)
    data = _read_user_settings()
    data["project_dir"] = str(folder)
    _write_user_settings(data)
    return folder


def scratch_dir(project_dir: str | Path | None = None) -> Path:
    """Default output root: ``<project>/Scratch/Assay``."""
    return resolve_project_dir(project_dir)[0] / "Scratch" / "Assay"


def _database_path_for(project_dir: str | Path | None) -> Path:
    return resolve_project_dir(project_dir)[0] / "Data" / "aa.duckdb"


def _default_database_path() -> Path:
    """Default database location: ``<project>/Data/aa.duckdb``.

    See :func:`resolve_project_dir` for how the project folder is found.
    """
    return _database_path_for(None)


def _get_config_file_path() -> Path | None:
    """
    Check if user has explicitly set a config file path via env var.
    Returns None if no env var is set (meaning: use database-based config).
    """
    # Check new env var first, then legacy
    env = os.getenv(CONFIG_PATH_ENV) or os.getenv(LEGACY_CONFIG_PATH_ENV)
    if env:
        p = Path(env).expanduser()
        if p.suffix.lower() != ".json":
            p = p / "config.json"
        return p
    return None


@dataclass
class AssayConfig:
    """Container for persisted configuration values."""

    # database_path is special: derived from the project folder (see
    # resolve_project_dir), not stored in the database
    database_path: Path = field(default_factory=_default_database_path)
    sample_start: int = 1963
    # Last year of the sample: a year, or LATEST_SAMPLE_END ("latest") for the
    # last complete calendar year on the WRDS tapes when setup-database runs.
    # The resolved year is stored in metadata.sample_end_resolved; see
    # resolved_sample_end. A persisted int is kept as it is.
    sample_end: int | str = LATEST_SAMPLE_END
    dom_com_eq: bool = True
    # Compustat variable list: the packaged CSV (ingest/data/), a user CSV
    # (bare name: searched for like the other inputs; or a path), or "All".
    # MATLAB's "COMPUSTAT Variable Names.csv", stored by older configs, also
    # means the packaged list. See ingest/compustat.py resolve_variables_file.
    compustat_variables: str = "compustat_variables.csv"
    # Default lf_combo: Gibbs + 3 LF spreads; no HF TAQ required (safer on new machines).
    # For numeric parity with reference tcosts.mat (built with Params.tcostsType='full'),
    # set tcosts_type='full' and ensure hf_monthly.csv is discoverable — MATLAB must match.
    tcosts_type: str = "lf_combo"
    wrds_username: str | None = None
    # Chen-Zimmerman release, as a label such as "2026.10" (legacy "2022-03"
    # and integers such as 202408 also parse; see ingest/cz_release.py).
    # None means the newest release on Hugging Face when the C-Z stage runs,
    # so a rebuild can pick up a new release; pin one for a paper.
    cz_release_version: str | int | None = None
    # Local SignalDoc.csv to use instead of downloading. The signal
    # documentation must come from the same CZ release as the signal panel:
    # newer releases drop/recategorize predictors, which changes both the
    # anomaly labels and the acronym casing used to order the zoo.
    cz_signal_doc_path: str | None = None
    # Local CZ signal panel (signed_predictors_dl_wide .parquet, .csv or .zip)
    # to read instead of the staging files or a download. The same-release
    # rule above applies: pair it with that release's cz_release_version or
    # SignalDoc.
    cz_signals_path: str | None = None
    # Local crspgibbs.csv (Hasbrouck's Gibbs estimates) to use instead of the
    # staging/source-tree lookup and the download; e.g. one refreshed with the
    # SAS code in inputs/gibbs/. See ingest/gibbs.py.
    gibbs_path: str | None = None
    # Process-pool size for the protocol's per-anomaly loops (correlations /
    # conditional sorts / FMB, and the zoo strategy sorts). ``None`` (default)
    # means ``max(1, cpu_count - 1)``. Set to 1 to force the serial path.
    protocol_n_jobs: int | None = None
    # RAM the protocol may use in all, in GiB: its own process plus every
    # worker. ``None`` (default) means 75% of the machine's memory (the smaller
    # of physical RAM and a container limit) when ``psutil`` is importable, and
    # no cap at all when it is not. See ``resolve_protocol_n_jobs`` and
    # ``pool_worker_count``.
    memory_budget_gb: float | None = None
    # Which CRSP tape the database is built from: "ciz" (Flat File Format 2.0,
    # the only tape carrying data after 2024 — the default)
    # or "siz" (Flat File Format 1.0, frozen by CRSP in January 2025 — what the
    # MATLAB parity checks use). See
    # ``ingest/crsp_source.py``. A *persisted* config
    # that predates this field still loads as "siz" (see LEGACY_CRSP_FORMAT), so
    # flipping the default changes nothing under an existing build.
    crsp_format: str = DEFAULT_CRSP_FORMAT

    # Fields that are stored in database (everything except database_path)
    _DB_FIELDS = (
        "sample_start",
        "sample_end",
        "dom_com_eq",
        "compustat_variables",
        "tcosts_type",
        "wrds_username",
        "cz_release_version",
        "cz_signal_doc_path",
        "cz_signals_path",
        "gibbs_path",
        "protocol_n_jobs",
        "memory_budget_gb",
        "crsp_format",
    )

    def __post_init__(self) -> None:
        fmt = str(self.crsp_format or "").strip().lower()
        if fmt not in VALID_CRSP_FORMATS:
            raise ValueError(
                f"crsp_format must be one of {', '.join(VALID_CRSP_FORMATS)}; "
                f"got {self.crsp_format!r}"
            )
        self.crsp_format = fmt
        self.sample_end = normalize_sample_end(self.sample_end)
        # Local-file pins: an empty value means "not set", and a Path given
        # through the API is stored as text so the config stays JSON.
        for name in ("cz_signal_doc_path", "cz_signals_path", "gibbs_path"):
            value = getattr(self, name)
            if value is not None:
                text = str(value).strip()
                setattr(self, name, text or None)

    @property
    def sample_end_is_latest(self) -> bool:
        """Whether ``sample_end`` is the "latest" sentinel rather than a year."""
        return self.sample_end == LATEST_SAMPLE_END

    def with_sample_end(self, year: int) -> "AssayConfig":
        """A copy of this config with ``sample_end`` set to ``year``."""
        return replace(self, sample_end=int(year))

    def resolved_sample_end(self, db_path: str | Path | None = None) -> int:
        """``sample_end`` as a year.

        An explicit year is returned as it is. For "latest", the year the last
        build of the database (``db_path``, else ``database_path``) resolved it
        to, from ``metadata.sample_end_resolved``; raises
        :class:`SampleEndUnresolvedError` when no build has recorded one.
        """
        if not self.sample_end_is_latest:
            return int(self.sample_end)
        path = Path(db_path if db_path is not None else self.database_path)
        stored = read_metadata_value(path, SAMPLE_END_RESOLVED_KEY)
        if stored is not None:
            try:
                return int(stored)
            except (TypeError, ValueError):
                pass
        raise SampleEndUnresolvedError(
            f"sample_end is {LATEST_SAMPLE_END!r}, and {path} does not record which "
            "year that resolved to (metadata.sample_end_resolved), because no "
            "complete setup-database has run against it since sample_end became "
            "'latest'. Run `aa setup-database` (a run that fetches from WRDS looks "
            "the year up), or pin a year with `aa set-params --sample-end 2024`."
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["database_path"] = str(self.database_path)
        return payload

    def to_db_dict(self) -> dict[str, Any]:
        """Return only the fields that should be stored in the database."""
        return {k: getattr(self, k) for k in self._DB_FIELDS}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AssayConfig":
        data = payload.copy()
        if "database_path" in data:
            data["database_path"] = Path(data["database_path"])
        # Remove deprecated fields
        data.pop("cz_data_path", None)
        return cls(**data)

    @classmethod
    def from_db_dict(cls, payload: dict[str, Any], database_path: Path) -> "AssayConfig":
        """Create config from database values, setting database_path explicitly."""
        data = payload.copy()
        data["database_path"] = database_path
        # Remove deprecated fields
        data.pop("cz_data_path", None)
        # Filter to known fields only
        known = {f.name for f in cls.__dataclass_fields__.values()}
        data = {k: v for k, v in data.items() if k in known}
        return cls(**data)


def _ensure_config_table(con) -> None:
    """Create the config table if it doesn't exist."""
    con.execute(
        "CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)"
    )


def _load_config_from_db(db_path: Path) -> AssayConfig:
    """Load config from the database. Returns defaults if DB doesn't exist."""
    if not db_path.exists():
        return AssayConfig(database_path=db_path)

    import duckdb

    try:
        con = duckdb.connect(str(db_path))
        try:
            # Check if config table exists
            tables = con.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name = 'config'"
            ).fetchall()
            if not tables:
                return AssayConfig(database_path=db_path)

            # Load all config values
            rows = con.execute("SELECT key, value FROM config").fetchall()
            data = {}
            for key, value in rows:
                # Parse JSON value
                try:
                    data[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    data[key] = value

            if not data:
                # A table with no rows holds no saved settings, so it is no
                # evidence of a legacy build either.
                return AssayConfig(database_path=db_path)

            if "crsp_format" not in data:
                # A database built before the CIZ tape was supported has no crsp_format key. It
                # can only have been built from the legacy tape, so default it
                # rather than silently adopting whatever the current default is.
                LOGGER.info(
                    "Config in %s has no crsp_format; defaulting to %r (legacy build)",
                    db_path,
                    LEGACY_CRSP_FORMAT,
                )
                data["crsp_format"] = LEGACY_CRSP_FORMAT

            return AssayConfig.from_db_dict(data, db_path)
        finally:
            con.close()
    except Exception as exc:
        # If we can't read the database for any reason, return defaults, but
        # say so: silently running on default settings is the worse failure.
        LOGGER.warning(
            "Could not read settings from %s (%s); using default settings",
            db_path,
            exc,
        )
        return AssayConfig(database_path=db_path)


def _save_config_to_db(config: AssayConfig) -> None:
    """Save config to the database."""
    import duckdb

    db_path = config.database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db_path))
    try:
        _ensure_config_table(con)

        # One transaction: crsp_format is the last field, and a save cut short
        # before it would make ``_load_config_from_db`` read a legacy build.
        con.execute("BEGIN TRANSACTION")
        try:
            for key, value in config.to_db_dict().items():
                json_value = json.dumps(value)
                con.execute(
                    "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
                    [key, json_value],
                )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
    finally:
        con.close()


def _load_config_from_file(cfg_path: Path) -> AssayConfig:
    """Load config from a JSON file."""
    if not cfg_path.exists():
        cfg = AssayConfig()
        # Auto-create with absolute database path for stability
        cfg.database_path = _default_database_path().resolve()
        _save_config_to_file(cfg, cfg_path)
        return cfg

    with cfg_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if "crsp_format" not in data:
        # Same legacy rule as ``_load_config_from_db``: a config file written
        # before the CIZ tape was supported describes a legacy-tape build, so it must not pick up
        # today's default.
        LOGGER.info(
            "Config in %s has no crsp_format; defaulting to %r (legacy build)",
            cfg_path,
            LEGACY_CRSP_FORMAT,
        )
        data["crsp_format"] = LEGACY_CRSP_FORMAT
    return AssayConfig.from_dict(data)


def _save_config_to_file(config: AssayConfig, cfg_path: Path) -> None:
    """Save config to a JSON file."""
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with cfg_path.open("w", encoding="utf-8") as fh:
        json.dump(config.to_dict(), fh, indent=2)


def load_config(
    path: Path | None = None, *, project_dir: str | Path | None = None
) -> AssayConfig:
    """
    Load configuration.

    Resolution order:
    1. If `path` argument is provided → use that JSON file
    2. If AA_CONFIG_PATH env var is set → use that JSON file
    3. Otherwise → load from the database, <project>/Data/aa.duckdb, where
       the project folder is `project_dir` (this call only) or as found by
       :func:`resolve_project_dir`
    """
    if path is not None:
        return _load_config_from_file(Path(path).expanduser())

    cfg_file = _get_config_file_path()
    if cfg_file is not None:
        return _load_config_from_file(cfg_file)

    # Default: load from database
    return _load_config_from_db(_database_path_for(project_dir))


def save_config(
    config: AssayConfig,
    path: Path | None = None,
    *,
    project_dir: str | Path | None = None,
) -> None:
    """
    Save configuration.

    If path is provided or AA_CONFIG_PATH is set, saves to JSON file.
    Otherwise saves to the database: ``config.database_path``, or the
    database of `project_dir` when that is given.
    """
    if path is not None:
        _save_config_to_file(config, Path(path).expanduser())
        return

    cfg_file = _get_config_file_path()
    if cfg_file is not None:
        _save_config_to_file(config, cfg_file)
        return

    # Default: save to database
    if project_dir is not None:
        config.database_path = _database_path_for(project_dir)
    _save_config_to_db(config)


def _project_source_note(db_path: Path) -> str:
    """Where ``db_path`` came from, for error messages."""
    cfg_file = _get_config_file_path()
    if cfg_file is not None:
        return f"database_path in {cfg_file} ({CONFIG_PATH_ENV})"
    try:
        folder, source = resolve_project_dir()
    except ProjectDirError as exc:
        return str(exc)
    if _absolute(db_path) == folder / "Data" / "aa.duckdb":
        return f"project folder {folder} (from {source})"
    return "path given explicitly"


def require_database(target: AssayConfig | str | Path | None = None) -> Path:
    """The database to read, after checking it exists and holds data.

    ``target`` is a config (its ``database_path``), a path, or None for
    :func:`load_config`. Raises :class:`DatabaseNotFoundError` when the file
    is missing or has no tables besides ``config`` (only settings were saved),
    instead of letting DuckDB create a new, empty database.
    """
    if target is None:
        target = load_config()
    raw = target.database_path if isinstance(target, AssayConfig) else target
    db_path = Path(raw).expanduser()
    if not db_path.is_file():
        problem = "does not exist"
    else:
        import duckdb

        con = duckdb.connect(str(db_path))
        try:
            n_tables = con.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name <> 'config'"
            ).fetchone()[0]
        finally:
            con.close()
        if n_tables:
            return db_path
        problem = "holds only saved settings, no data"
    raise DatabaseNotFoundError(
        f"The database {db_path} {problem}.\n"
        f"It comes from: {_project_source_note(db_path)}.\n"
        "Fix it with one of:\n"
        "  aa set-params --project-dir <folder>   point at the folder that "
        "holds Data/aa.duckdb\n"
        "  aa setup-database                      build the database in this "
        "project folder"
    )


def default_protocol_n_jobs() -> int:
    """``cpu_count - 1``, floored at 1. Used when ``protocol_n_jobs`` is unset."""
    n = os.cpu_count() or 1
    return max(1, int(n) - 1)


# cgroup files holding a container's memory limit: v2, then v1. A value at or
# above _CGROUP_UNLIMITED (v1 writes ~2**63 for "no limit") means none.
_CGROUP_LIMIT_FILES = (
    Path("/sys/fs/cgroup/memory.max"),
    Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
)
_CGROUP_UNLIMITED = 2**60


def container_memory_limit_gb() -> float | None:
    """The cgroup memory limit in GiB (Linux containers), or None if there is none.

    In a Docker or Kubernetes container ``psutil`` reports the host's RAM, but
    the kernel kills the container's processes at this limit.
    """
    for path in _CGROUP_LIMIT_FILES:
        try:
            text = path.read_text().strip()
        except OSError:
            continue
        if text == "max":
            return None
        try:
            value = int(text)
        except ValueError:
            continue
        if 0 < value < _CGROUP_UNLIMITED:
            return value / (1024.0**3)
        return None
    return None


def machine_memory_gb() -> tuple[float | None, str]:
    """``(GiB, source)``: the smaller of physical RAM and a container limit.

    ``source`` is ``"container memory limit"`` or ``"physical RAM"``;
    ``(None, "unknown")`` when neither can be read.
    """
    physical = total_physical_memory_gb()
    limit = container_memory_limit_gb()
    if limit is not None and (physical is None or limit < physical):
        return limit, "container memory limit"
    if physical is not None:
        return physical, "physical RAM"
    return None, "unknown"


def current_process_memory_gb() -> float | None:
    """Resident memory of this process in GiB, or None without ``psutil``."""
    try:
        import psutil

        return float(psutil.Process().memory_info().rss) / (1024.0**3)
    except Exception:  # pragma: no cover - psutil missing or platform dependent
        return None


def total_physical_memory_gb() -> float | None:
    """Physical RAM in GiB, or None when it cannot be determined."""
    try:
        import psutil
    except ImportError:
        LOGGER.debug("psutil not installed; no memory-based cap on n_jobs")
        return None
    try:
        return float(psutil.virtual_memory().total) / (1024.0**3)
    except Exception as exc:  # pragma: no cover - platform dependent
        LOGGER.warning("could not read physical memory (%s); no cap on n_jobs", exc)
        return None


def resolve_memory_budget_gb(memory_budget_gb: float | None = None) -> float | None:
    """Resolve the protocol's RAM budget in GiB, or None for "no cap".

    Precedence: explicit argument, then ``AA_MEMORY_GB``, then
    ``AssayConfig.memory_budget_gb``, then :data:`DEFAULT_MEMORY_FRACTION` of
    :func:`machine_memory_gb` (physical RAM, or a container's limit when that
    is smaller). A non-positive value anywhere in that chain means "no cap".
    The budget covers the protocol's own process as well as its workers.
    """
    requested = memory_budget_gb
    if requested is None:
        env = os.getenv(MEMORY_BUDGET_ENV)
        if env is not None and str(env).strip() != "":
            try:
                requested = float(env)
            except ValueError:
                LOGGER.warning(
                    "ignoring %s=%r: not a number", MEMORY_BUDGET_ENV, env
                )
    if requested is None:
        try:
            requested = load_config().memory_budget_gb
        except Exception:
            requested = None
    if requested is None:
        total, _ = machine_memory_gb()
        if total is None:
            return None
        return total * DEFAULT_MEMORY_FRACTION
    requested = float(requested)
    return None if requested <= 0 else requested


def _linear(x: float, xs: list[float], ys: list[float]) -> float:
    """Piecewise-linear through ``(xs, ys)`` (``xs`` increasing), extending the
    nearest segment's slope outside them."""
    import numpy as np

    if x < xs[0]:
        i = 0
    elif x > xs[-1]:
        i = len(xs) - 2
    else:
        return float(np.interp(x, xs, ys))
    slope = (ys[i + 1] - ys[i]) / (xs[i + 1] - xs[i])
    return ys[i] + slope * (x - xs[i])


def _rows_from(year: float) -> float:
    """CRSP daily rows from ``year`` through 2025, from the anchor table.

    Linear in the start year between the anchors, and down to zero rows for a
    sample starting in 2026, the year after the table ends; extended linearly
    past that, and flat before the first anchor (CRSP daily starts in 1925).
    """
    xs = [float(y) for y, _, _ in SETUP_RAM_ANCHORS] + [SETUP_RAM_ANCHOR_END + 1.0]
    ys = [rows for _, rows, _ in SETUP_RAM_ANCHORS] + [0.0]
    return _linear(max(float(year), xs[0]), xs, ys)


def crsp_daily_rows(sample_start: int, sample_end: int) -> int:
    """Estimated CRSP daily rows for ``sample_start..sample_end``.

    Interpolated from :data:`SETUP_RAM_ANCHORS`: the rows from the start year
    on, less the rows from the year after the end year on.
    """
    rows = _rows_from(int(sample_start)) - _rows_from(int(sample_end) + 1)
    return max(int(round(rows)), 0)


def required_setup_ram_gb(sample_start: int, sample_end: int) -> int:
    """Recommended RAM in GiB for building ``sample_start..sample_end``.

    Piecewise-linear in the window's CRSP daily rows through
    :data:`SETUP_RAM_ANCHORS`; outside them the nearest segment's slope is
    extended. Floored at :data:`SETUP_RAM_FLOOR_GB` and rounded up to a whole
    GiB.
    """
    import math

    anchors = sorted(SETUP_RAM_ANCHORS, key=lambda a: a[1])
    gb = _linear(
        float(crsp_daily_rows(sample_start, sample_end)),
        [rows for _, rows, _ in anchors],
        [ram for _, _, ram in anchors],
    )
    # Round before the ceiling so float noise at an anchor (72.0000001)
    # does not add a GiB.
    return int(math.ceil(round(max(gb, SETUP_RAM_FLOOR_GB), 6)))


def resolve_protocol_n_jobs(
    n_jobs: int | None = None,
    *,
    memory_budget_gb: float | None = None,
    worker_gb: float = PROTOCOL_WORKER_GB,
) -> int:
    """Resolve a protocol worker count to an integer ``>= 1``.

    Precedence: explicit ``n_jobs`` argument, then ``AA_PROTOCOL_N_JOBS``,
    then ``AssayConfig.protocol_n_jobs``, then :func:`default_protocol_n_jobs`.
    ``None`` / negative values mean "default" (cores-1). ``0`` is treated as 1
    (serial) so callers can disable the pool without a sentinel.

    The result is then capped at ``floor(budget / worker_gb)`` (see
    :func:`resolve_memory_budget_gb` and :data:`PROTOCOL_WORKER_GB`), floored at
    1. This is what stops a machine with many cores but modest RAM — a shared
    cluster node, typically — from being OOM-killed part-way through a run.
    """
    requested = n_jobs
    if requested is None:
        env = os.getenv(PROTOCOL_N_JOBS_ENV)
        if env is not None and str(env).strip() != "":
            requested = int(env)
    if requested is None:
        try:
            requested = load_config().protocol_n_jobs
        except Exception:
            requested = None
    if requested is None or int(requested) < 0:
        resolved = default_protocol_n_jobs()
    else:
        resolved = max(1, int(requested))

    budget = resolve_memory_budget_gb(memory_budget_gb)
    if budget is None or worker_gb <= 0:
        return resolved

    capped = max(1, int(budget // worker_gb))
    if capped < resolved:
        LOGGER.info(
            "capping n_jobs %d -> %d: %.1f GiB budget / %.1f GiB per worker",
            resolved,
            capped,
            budget,
            worker_gb,
        )
        return capped
    return resolved


# The budget a protocol run resolved at its start, so a pool started hours in
# does not reread the config (from whatever database the cwd points at).
_UNSET: Any = object()
_RUN_MEMORY_BUDGET: ContextVar[Any] = ContextVar("aa_run_memory_budget", default=_UNSET)


@contextmanager
def run_memory_budget(budget_gb: float | None) -> Iterator[None]:
    """Fix the budget :func:`pool_worker_count` uses inside this block."""
    token = _RUN_MEMORY_BUDGET.set(budget_gb)
    try:
        yield
    finally:
        _RUN_MEMORY_BUDGET.reset(token)


def pool_worker_count(
    requested: int,
    *,
    worker_gb: float = PROTOCOL_WORKER_GB,
    what: str = "pool",
) -> int:
    """Workers to start a pool with now: ``requested``, capped by free budget.

    :func:`resolve_protocol_n_jobs` divides the whole budget by ``worker_gb``
    at the start of a run, before anything is loaded. By the time a pool
    starts, this process may already hold tens of GiB (the zoo, its filled
    copy, stage results), and the workers come on top of that. So the cap here
    is ``floor((budget - this process's resident memory) / worker_gb)``,
    floored at 1. The budget is the one fixed by :func:`run_memory_budget`,
    else :func:`resolve_memory_budget_gb`.
    """
    requested = max(1, int(requested))
    if requested <= 1 or worker_gb <= 0:
        return requested
    budget = _RUN_MEMORY_BUDGET.get()
    if budget is _UNSET:
        budget = resolve_memory_budget_gb()
    if budget is None:
        return requested
    used = current_process_memory_gb()
    if used is None:
        return requested
    capped = max(1, int((budget - used) // worker_gb))
    if capped < requested:
        LOGGER.info(
            "%s: starting %d worker(s) instead of %d: %.1f GiB budget, %.1f GiB "
            "already in use by this process, %.1f GiB per worker",
            what,
            capped,
            requested,
            budget,
            used,
            worker_gb,
        )
        return capped
    return requested


def set_params(
    *,
    path: Path | None = None,
    project_dir: str | Path | None = None,
    **kwargs: Any,
) -> AssayConfig:
    """
    Update configuration values programmatically.

    If path is provided or AA_CONFIG_PATH is set, updates JSON file.
    Otherwise updates the database config (of `project_dir`, if given; it is
    not saved as the project folder, see :func:`set_project_dir`).
    """
    cfg = load_config(path, project_dir=project_dir)
    for key, value in kwargs.items():
        if not hasattr(cfg, key):
            raise AttributeError(f"Unknown config field: {key}")
        setattr(cfg, key, value)
    # setattr skips __post_init__, so validate and normalize the result the
    # way a freshly loaded config would be ("2021" -> 2021, a bad tape raises).
    cfg = AssayConfig.from_dict(cfg.to_dict())
    save_config(cfg, path)
    return cfg


# Legacy exports for backwards compatibility
DEFAULT_CONFIG_DIR = Path.home() / ".assayinganomalies"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.json"


def ensure_config_dir(path: Path = DEFAULT_CONFIG_DIR) -> None:
    """Legacy function - only used when explicitly writing to home dir."""
    path.mkdir(parents=True, exist_ok=True)


__all__ = [
    "AssayConfig",
    "LATEST_SAMPLE_END",
    "SIZ_FROZEN_END_YEAR",
    "DEMO_SAMPLE_END",
    "SAMPLE_END_RESOLVED_KEY",
    "SampleEndUnresolvedError",
    "normalize_sample_end",
    "read_metadata_value",
    "read_db_setting",
    "write_db_setting",
    "CONFIG_PATH_ENV",
    "LEGACY_CONFIG_PATH_ENV",
    "PROJECT_DIR_ENV",
    "DatabaseNotFoundError",
    "ProjectDirError",
    "resolve_project_dir",
    "set_project_dir",
    "scratch_dir",
    "require_database",
    "PROTOCOL_N_JOBS_ENV",
    "load_config",
    "save_config",
    "set_params",
    "default_protocol_n_jobs",
    "resolve_protocol_n_jobs",
    "resolve_memory_budget_gb",
    "run_memory_budget",
    "pool_worker_count",
    "container_memory_limit_gb",
    "machine_memory_gb",
    "current_process_memory_gb",
    "total_physical_memory_gb",
    "crsp_daily_rows",
    "required_setup_ram_gb",
    # Legacy exports
    "DEFAULT_CONFIG_DIR",
    "DEFAULT_CONFIG_PATH",
    "ensure_config_dir",
]
