"""
Add your own Compustat variables to an existing database (``aa add-compustat-vars``).

The build fetches a fixed list of Compustat columns (``compustat_variables``)
and carries a fixed set of them onto ``ccm_panel``. This module adds more to a
database that is already built, without rebuilding it: it downloads only the
named columns from comp.funda / comp.fundq, aligns them to the panel months the
way the build aligns its own, and adds them to ``ccm_panel`` under their
Compustat names (``xrd`` stays ``xrd``).

- **Annual** columns follow ``at``: a fiscal-year filing becomes available at
  the end of June of the next calendar year, and its value is stored on the
  panel row of that June only. ``aa.load(..., fill_annual=True)`` or
  ``aa.fill_months`` carries it through the following May.
- **Quarterly** columns follow ``ibq``: each quarter is placed at the end of
  its announcement (RDQ) month and forward-filled until two months past the
  last announcement.

The names are recorded in the database's ``config`` table under
``EXTRA_VARS_KEY``, which a full refresh keeps, so a later ``setup-database``
fetches and carries them like the built-in columns. A name already on the
panel, or one the build itself writes, is refused, unless it is a recorded
extra being refreshed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import time
from typing import Any, Sequence

import pandas as pd

from . import run_manifest
from .config import AssayConfig, load_config, read_db_setting, require_database, write_db_setting
from .db.manager import DuckDBManager
from .db.writer import add_columns_from_frame
from .ingest import compustat as compustat_ingest
from .provenance import database_is_demo
from .stage_registry import COLUMN_TO_STAGE
from .transforms import compustat as compustat_tf

LOGGER = logging.getLogger("assayinganomalies.compustat_extras")

# Key in the database's ``config`` table: {"annual": [...], "quarterly": [...]}.
# Not an AssayConfig field, so `set-params` neither shows nor overwrites it, and
# the ``config`` table survives `setup-database --full-refresh`.
EXTRA_VARS_KEY = "compustat_extra_vars"
# ``metadata`` key: what the last `add-compustat-vars` run added, and when.
EXTRA_VARS_APPLIED_KEY = "compustat_extra_vars_applied"

# Staging files holding every recorded extra column, beside the build's own
# extracts. A rebuild takes from them any extra its main extract lacks.
EXTRA_ANNUAL_FILE = "compustat_extra_funda_raw.parquet"
EXTRA_QUARTERLY_FILE = "compustat_extra_fundq_raw.parquet"
EXTRA_FILES = {"annual": EXTRA_ANNUAL_FILE, "quarterly": EXTRA_QUARTERLY_FILE}

FREQS = ("annual", "quarterly")

# Names a user column may not take: what the build writes to ccm_panel (or any
# table the registry knows) and the identifiers the alignment itself uses.
RESERVED_PANEL_COLUMNS = frozenset(
    {
        *compustat_tf.ANNUAL_VALUE_COLS,
        *compustat_tf.ANNUAL_PROVENANCE_COLS,
        *compustat_tf.QUARTERLY_DERIVED_COLS,
        *COLUMN_TO_STAGE,
        "fin_firm",
        *compustat_ingest.ANNUAL_KEY_COLS,
        *compustat_ingest.QUARTERLY_KEY_COLS,
    }
)


@dataclass
class AddVarsReport:
    """What :func:`add_compustat_vars` did."""

    database: Path
    annual: list[str] = field(default_factory=list)
    quarterly: list[str] = field(default_factory=list)
    # Names that were already recorded extras and were replaced.
    refreshed: list[str] = field(default_factory=list)
    sample_end: int | None = None
    panel_rows: int = 0
    # Panel rows with a value, per added column.
    non_missing: dict[str, int] = field(default_factory=dict)
    manifest: Path | None = None
    seconds: float = 0.0

    @property
    def columns(self) -> list[str]:
        return [*self.annual, *self.quarterly]


def _normalize(value: Any) -> dict[str, list[str]]:
    stored = value if isinstance(value, dict) else {}
    return {freq: [str(n) for n in (stored.get(freq) or [])] for freq in FREQS}


def persisted_extra_vars(db_path: str | Path) -> dict[str, list[str]]:
    """The recorded extra columns, ``{"annual": [...], "quarterly": [...]}`` (empty lists if none)."""
    return _normalize(read_db_setting(db_path, EXTRA_VARS_KEY))


def record_extra_vars(
    db_path: str | Path,
    annual: Sequence[str] = (),
    quarterly: Sequence[str] = (),
) -> dict[str, list[str]]:
    """Add names to the recorded extras (kept in order, no duplicates); returns the new record."""
    recorded = persisted_extra_vars(db_path)
    for freq, names in (("annual", annual), ("quarterly", quarterly)):
        for name in names:
            if name not in recorded[freq]:
                recorded[freq].append(name)
    write_db_setting(db_path, EXTRA_VARS_KEY, recorded)
    return recorded


def _panel_columns(db_path: Path) -> list[str]:
    with DuckDBManager(db_path) as mgr:
        cols = mgr.query_df(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'ccm_panel' ORDER BY ordinal_position"
        )["column_name"].tolist()
    if not cols:
        raise ValueError(
            f"{db_path} has no ccm_panel table. Build the database first: aa setup-database"
        )
    return cols


def _check_names(
    requested: dict[str, list[str]],
    panel_cols: Sequence[str],
    recorded: dict[str, list[str]],
) -> list[str]:
    """Refuse colliding names; return the ones that refresh a recorded extra."""
    if not any(requested.values()):
        raise ValueError("Name at least one Compustat column (--annual and/or --quarterly).")
    both = sorted(set(requested["annual"]) & set(requested["quarterly"]))
    if both:
        raise ValueError(
            f"{', '.join(both)} named as both annual and quarterly; a panel column "
            "has one meaning. Quarterly names usually end in q (xrdq)."
        )
    # DuckDB column names are case-insensitive.
    on_panel = {c.lower() for c in panel_cols}
    refreshed: list[str] = []
    refused: list[str] = []
    for freq in FREQS:
        other = "quarterly" if freq == "annual" else "annual"
        for name in requested[freq]:
            if name in recorded[freq]:
                refreshed.append(name)
            elif name in recorded[other]:
                refused.append(f"{name} (already added as a {other} column)")
            elif name in RESERVED_PANEL_COLUMNS:
                refused.append(f"{name} (written by the build)")
            elif name in on_panel:
                refused.append(f"{name} (already a ccm_panel column)")
    if refused:
        raise ValueError(
            "Cannot add: " + "; ".join(refused) + ". Names are kept as they are in "
            "Compustat, so a name already on ccm_panel would overwrite a column the "
            "build or another step wrote. Use the existing column."
        )
    return refreshed


def _probe(client, requested: dict[str, list[str]]) -> None:
    """Check every requested name against the WRDS column lists before downloading."""
    problems = []
    with client.connect() as conn:
        for freq in FREQS:
            if not requested[freq]:
                continue
            table = compustat_ingest._TABLES[freq]
            available = compustat_ingest._get_table_columns(conn, "comp", table)
            unknown = [c for c in requested[freq] if c not in available]
            if unknown:
                problems.append(f"comp.{table} has no column(s) {', '.join(unknown)}")
    if problems:
        raise ValueError(
            "; ".join(problems) + ". Check the names against the WRDS variable "
            "lists for comp.funda and comp.fundq; nothing was downloaded or changed."
        )


def _check_numeric(raw: pd.DataFrame, columns: Sequence[str], table: str) -> None:
    bad = []
    for col in columns:
        values = raw[col]
        if values.notna().any() and pd.to_numeric(values, errors="coerce").notna().sum() < values.notna().sum():
            bad.append(col)
    if bad:
        raise ValueError(
            f"comp.{table} column(s) {', '.join(bad)} are not numeric; only numeric "
            "columns can be added to ccm_panel. Nothing was changed."
        )


def _write_metadata(db_path: Path, key: str, value: Any) -> None:
    with DuckDBManager(db_path) as mgr:
        mgr.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)")
        mgr.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            key,
            json.dumps(value),
        )


def add_compustat_vars(
    annual: str | Sequence[str] = (),
    quarterly: str | Sequence[str] = (),
    *,
    config: AssayConfig | None = None,
    verbose: bool = False,
) -> AddVarsReport:
    """
    Download Compustat columns and add them to ``ccm_panel`` of a built database.

    Parameters
    ----------
    annual : str or sequence of str
        comp.funda columns, e.g. ``"xrd,mib"`` or ``["xrd"]``. Aligned like
        ``at``: available the June after the fiscal year and stored in that
        June only (``aa.load(..., fill_annual=True)`` fills June to May).
    quarterly : str or sequence of str
        comp.fundq columns, e.g. ``"xrdq"``. Aligned like ``ibq``: placed at
        the RDQ month, forward-filled two months past the last announcement.
    config : AssayConfig, optional
        Configuration naming the database; :func:`load_config` when omitted.
    verbose : bool
        Log at DEBUG level (the SQL sent to WRDS).

    Returns
    -------
    AddVarsReport

    Notes
    -----
    Needs a built database (``ccm_panel``, and ``ccm_link`` or the raw link
    table) and WRDS credentials: it logs in once (one Duo push). Names are
    kept as they are in Compustat. A name already on the panel or written by
    the build is refused, unless an earlier run of this command added it, in
    which case it is downloaded again and replaced. The names are recorded in
    the database, so ``aa setup-database`` (also with ``--full-refresh``)
    fetches and carries them from then on. Do not run it while a build or
    another command writes the database.
    """
    from . import pipeline as pl

    t0 = time.perf_counter()
    cfg = config or load_config()
    db_path = require_database(cfg)
    # The build's logging: console plus Data/logs/setup_database.log.
    pl._configure_setup_logging(db_path=db_path, verbose=verbose)
    if database_is_demo(db_path):
        LOGGER.warning(
            "%s is a demo database (synthetic data); the columns are added from "
            "WRDS all the same.", db_path,
        )

    requested = {
        "annual": compustat_ingest.parse_variable_names(annual),
        "quarterly": compustat_ingest.parse_variable_names(quarterly),
    }
    recorded = persisted_extra_vars(db_path)
    refreshed = _check_names(requested, _panel_columns(db_path), recorded)
    if requested["annual"]:
        # A June-only column beside columns filled June to May would be read
        # wrongly by one rule or the other.
        from .data_access import annual_layout_error

        if not pl.has_june_annual_layout(db_path):
            raise annual_layout_error(db_path, "aa add-compustat-vars --annual")

    # The year the build ran through; "latest" reads it from the database
    # (raises SampleEndUnresolvedError when no build recorded one).
    cfg.resolved_sample_end(db_path)
    staging_dir = db_path.parent / "staging"
    ctx = pl.PipelineContext(cfg, db_path, staging_dir, full_refresh=False)
    pl._clamp_sample_end_for_tape(ctx)
    pl._preflight_sample_end(ctx, [])
    run_cfg = ctx.config
    LOGGER.info(
        "Adding Compustat columns to %s: annual=%s quarterly=%s (sample %s..%s)",
        db_path, requested["annual"], requested["quarterly"],
        run_cfg.sample_start, run_cfg.sample_end,
    )

    fetch_stages = {"annual": "fetch-compustat-annual", "quarterly": "fetch-compustat-quarterly"}
    planned = [fetch_stages[f] for f in FREQS if requested[f]]
    started_at = run_manifest.utc_now()
    prior_history = pl._load_stage_history(db_path)
    raw: dict[str, pd.DataFrame] = {}
    try:
        with run_manifest.recording_inputs() as noted:
            pl._preflight_credentials(ctx, planned)
            client = ctx.get_wrds_client(prompt=False)
            _probe(client, requested)
            for freq in FREQS:
                if not requested[freq]:
                    continue
                # The staging file holds every recorded extra of this
                # frequency, so a rebuild can re-apply all of them from it.
                names = [*recorded[freq], *(n for n in requested[freq] if n not in recorded[freq])]
                dest = staging_dir / EXTRA_FILES[freq]
                compustat_ingest.fetch_compustat_columns(
                    run_cfg, dest, wrds_client=client, freq=freq, columns=names
                )
                run_manifest.note_input(dest, f"compustat extra {freq}")
                ctx.record_stage(f"fetch-compustat-extra-{freq}", "succeeded")
                raw[freq] = pd.read_parquet(dest)
                _check_numeric(raw[freq], requested[freq], compustat_ingest._TABLES[freq])
    finally:
        ctx.close_wrds()

    with DuckDBManager(db_path) as mgr:
        link = pl._read_ccm_link(ctx, mgr)
        keys = mgr.query_df("SELECT permno, date FROM ccm_panel")
    if link is None:
        raise ValueError(
            f"{db_path} has no CCM link (ccm_link or ccmxpf_lnkhist); rebuild "
            "transform-compustat first."
        )

    frame = compustat_tf._panel_keys(keys)
    if requested["annual"]:
        aligned = compustat_tf.align_extra_annual(
            raw["annual"], link, keys, run_cfg, requested["annual"]
        )
        for col in requested["annual"]:
            frame[col] = aligned[col].to_numpy()
    if requested["quarterly"]:
        aligned = compustat_tf.align_extra_quarterly(
            raw["quarterly"], link, keys, run_cfg, requested["quarterly"]
        )
        for col in requested["quarterly"]:
            frame[col] = aligned[col].to_numpy()

    n_rows = add_columns_from_frame(db_path, "ccm_panel", frame, replace=refreshed)
    record_extra_vars(db_path, requested["annual"], requested["quarterly"])
    report = AddVarsReport(
        database=db_path,
        annual=requested["annual"],
        quarterly=requested["quarterly"],
        refreshed=refreshed,
        sample_end=int(run_cfg.sample_end),
        panel_rows=n_rows,
        non_missing={c: int(frame[c].notna().sum()) for c in [*requested["annual"], *requested["quarterly"]]},
    )
    _write_metadata(db_path, EXTRA_VARS_APPLIED_KEY, {
        "annual": report.annual,
        "quarterly": report.quarterly,
        "refreshed": report.refreshed,
        "sample_end": report.sample_end,
        "applied_at": run_manifest.utc_now(),
    })
    report.manifest = pl._write_database_manifest(
        ctx,
        noted,
        started_at=started_at,
        prior_history=prior_history,
        command="add-compustat-vars",
    )
    report.seconds = time.perf_counter() - t0
    LOGGER.info(
        "Added %s to ccm_panel (%d rows; non-missing %s) in %.1fs",
        report.columns, n_rows, report.non_missing, report.seconds,
    )
    return report


__all__ = [
    "EXTRA_VARS_KEY",
    "EXTRA_VARS_APPLIED_KEY",
    "EXTRA_ANNUAL_FILE",
    "EXTRA_QUARTERLY_FILE",
    "RESERVED_PANEL_COLUMNS",
    "AddVarsReport",
    "persisted_extra_vars",
    "record_extra_vars",
    "add_compustat_vars",
]
