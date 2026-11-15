"""
Where a database's numbers came from, and what refuses to use them.

The pipeline can build a database out of deterministic synthetic stand-ins
instead of CRSP, COMPUSTAT and the Chen-Zimmerman zoo. That is useful for
tests, CI and a first look at the toolkit on a machine with no WRDS
subscription, and it is ruinous if it happens by accident:
a run with no credentials, or a run whose CZ download failed, quietly
produced a database that looks exactly like a real one.

So synthetic data is opt-in (``demo=True`` / ``--demo``), it is stamped into
the database where later code can see it, and production entry points refuse
a database carrying the stamp.

The stamp lives in the ``config`` table rather than ``metadata`` because
``metadata`` is dropped and rewritten by ``setup-database --full-refresh``
while ``config`` survives, and because ``config`` is the table an ordinary
read path already opens. It is written to both, and :func:`database_is_demo`
believes either one: a demo marker anywhere wins.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

LOGGER = logging.getLogger(__name__)

# Key used in both the `config` and `metadata` tables.
DEMO_KEY = "demo_data"

# Short label stamped into report titles and manifest-like payloads. Deliberately
# shouty: its whole job is to be impossible to mistake for a real result.
DEMO_LABEL = "SYNTHETIC DEMO DATA — NOT REAL RESEARCH OUTPUT"

# How a user supplies the WRDS credentials the production path requires.
CREDENTIAL_HELP = (
    "Supply WRDS credentials in any one of these ways:\n"
    "  * export WRDS_USERNAME and WRDS_PASSWORD (or PGPASSWORD) in the same "
    "terminal you run from; exports last only for that terminal\n"
    "  * add a 'wrds-pgdata.wharton.upenn.edu:9737:wrds:<user>:<password>' "
    "line to ~/.pgpass (chmod 600; on Windows %APPDATA%\\postgresql\\pgpass.conf), "
    "which lasts across terminals\n"
    "  * store the password in your keyring under service 'wrds'\n"
    "  * run interactively, without AA_NO_PROMPT set, to be prompted\n"
    "Or build a synthetic database instead with --demo (CLI) / demo=True (API). "
    "A demo database is stamped as synthetic and is refused by production "
    "protocol runs."
)


class ProvenanceError(RuntimeError):
    """Base class for refusals based on where the data came from."""


class MissingCredentialsError(ProvenanceError):
    """
    Raised when a production build needs WRDS and no credentials resolve.

    Replaces the previous behavior of silently substituting a placeholder
    extract, which produced an apparently real database from no data at all.
    """


class DownloadFailedError(ProvenanceError):
    """
    Raised when a production build cannot obtain a required external download.

    Replaces the previous behavior of logging a warning and substituting a
    placeholder table.
    """


class MissingInputError(ProvenanceError):
    """
    Raised when a production build cannot find a required input file.

    Used for the trading-cost inputs (Hasbrouck's Gibbs estimates and, under
    ``tcosts_type='full'``, the high-frequency spreads). It replaces the
    previous behavior of logging a warning and building trading costs without
    the Gibbs measure, which MATLAB refuses to do (``makeTradingCosts.m``).
    """


class AmbiguousInputError(MissingInputError):
    """
    Raised when a search for a hand-placed input file finds more than one copy.

    The build does not pick one: under ``tcosts_type='full'`` the spreads file
    changes every net return, so which copy is read has to be the user's
    choice. A subclass of :class:`MissingInputError` because the remedy is the
    same (put the file where the build looks first) and callers that catch a
    missing input should stop here too.
    """


class DemoDatabaseError(ProvenanceError):
    """Raised when production code is pointed at a database built in demo mode."""


def missing_credentials_error(purpose: str) -> MissingCredentialsError:
    """A :class:`MissingCredentialsError` naming ``purpose`` and the remedies."""
    return MissingCredentialsError(
        f"{purpose} requires WRDS credentials and none were found.\n"
        f"{CREDENTIAL_HELP}"
    )


def download_failed_error(
    what: str, exc: BaseException, *, hint: str | None = None
) -> DownloadFailedError:
    """
    A :class:`DownloadFailedError` naming the failed download and the remedies.

    ``hint`` is a download-specific remedy, added on its own line unless the
    underlying error already carries it.
    """
    detail = str(exc)
    if hint and hint not in detail:
        detail = f"{detail}\n{hint}"
    return DownloadFailedError(
        f"Could not download {what}: {detail}\n"
        "The production pipeline will not substitute synthetic data for a "
        "failed download. Fix the network or proxy, check the configured "
        "release version, or pin a local copy in the config; rerun with "
        "--demo (CLI) / demo=True (API) only if you want a synthetic "
        "database, which is stamped as such and refused by production "
        "protocol runs."
    )


# ---------------------------------------------------------------------------
# Reading and writing the stamp
# ---------------------------------------------------------------------------


def _read_key(db_path: Path, table: str) -> object | None:
    """The stored ``DEMO_KEY`` value from ``table``, or None if unavailable."""
    import duckdb

    try:
        con = duckdb.connect(str(db_path), read_only=True)
    except Exception:  # pragma: no cover - locked or unreadable file
        return None
    try:
        tables = con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = ?",
            [table],
        ).fetchall()
        if not tables:
            return None
        rows = con.execute(
            f"SELECT value FROM {table} WHERE key = ?", [DEMO_KEY]  # noqa: S608
        ).fetchall()
    except Exception:  # pragma: no cover - defensive
        return None
    finally:
        con.close()
    return rows[0][0] if rows else None


def _as_bool(raw: object | None) -> bool:
    """Interpret a stored value, which may be JSON, a SQL string, or a bool."""
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    text = str(raw).strip().strip('"').lower()
    if text in ("true", "1"):
        return True
    if text in ("false", "0", "", "null", "none"):
        return False
    try:
        return bool(json.loads(text))
    except (TypeError, ValueError):
        return False


def database_is_demo(db_path: str | Path | None) -> bool:
    """
    True when ``db_path`` was built, wholly or partly, from synthetic data.

    A missing file, a database with neither table, or any read failure is
    reported as *not* demo. That direction is deliberate: the stamp is what
    triggers a refusal, and a database that predates the stamp is an ordinary
    production database as far as this function can tell. The refusal is a
    guard against the accidental demo build, not a proof of provenance.
    """
    if db_path is None:
        return False
    path = Path(db_path).expanduser()
    if not path.exists():
        return False
    for table in ("config", "metadata"):
        if _as_bool(_read_key(path, table)):
            return True
    return False


def mark_database_demo(db_path: str | Path, demo: bool) -> None:
    """
    Record whether ``db_path`` holds synthetic data, in ``metadata`` and ``config``.

    ``metadata`` is created if absent. ``config`` is only *updated*, never
    created: ``config.load_config`` treats the presence of that table as "this
    database carries its own settings" and fills in defaults for every key it
    does not find, so conjuring one here would silently reinterpret an
    unconfigured database as a legacy-tape build. A database that has a config
    table gets the stamp there too, because ``config`` survives the
    ``--full-refresh`` that drops and rewrites ``metadata``.

    Writing ``demo=False`` clears an existing stamp, so callers must only do
    that when the whole database has genuinely been rebuilt from real inputs.
    """
    import duckdb

    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    value = json.dumps(bool(demo))
    con = duckdb.connect(str(path))
    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT)"
        )
        targets = ["metadata"]
        existing = con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = 'config'"
        ).fetchall()
        if existing:
            targets.append("config")
        for table in targets:
            con.execute(
                f"INSERT OR REPLACE INTO {table} (key, value) VALUES (?, ?)",  # noqa: S608
                [DEMO_KEY, value],
            )
    finally:
        con.close()
    LOGGER.info("Marked %s demo_data=%s (tables: %s)", path, bool(demo), targets)


# ---------------------------------------------------------------------------
# Refusing, and labelling what is not refused
# ---------------------------------------------------------------------------


def require_real_database(
    db_path: str | Path | None,
    *,
    allow_demo: bool = False,
    what: str = "This command",
) -> bool:
    """
    Raise unless ``db_path`` holds real data or the caller opted in.

    Returns the demo flag so the caller can label its own output when it did
    opt in.
    """
    demo = database_is_demo(db_path)
    if demo and not allow_demo:
        raise DemoDatabaseError(
            f"{db_path} was built in demo mode and holds synthetic stand-in "
            f"data, not CRSP, COMPUSTAT or Chen-Zimmerman data. {what} refuses "
            "to run on it because its output would look like a research "
            "result. Rebuild the database without --demo, point at a "
            "production database, or pass --allow-demo-data to run anyway and "
            "have the output labelled synthetic."
        )
    return demo


def label_title(title: str, demo: bool) -> str:
    """Prefix a human-readable title with the demo banner when ``demo``."""
    if not demo:
        return title
    return f"[{DEMO_LABEL}] {title}"


def provenance_payload(demo: bool) -> dict[str, object]:
    """The provenance fields every manifest-like output carries."""
    payload: dict[str, object] = {"demo_data": bool(demo)}
    if demo:
        payload["data_provenance"] = DEMO_LABEL
    return payload


__all__ = [
    "AmbiguousInputError",
    "CREDENTIAL_HELP",
    "DEMO_KEY",
    "DEMO_LABEL",
    "DemoDatabaseError",
    "DownloadFailedError",
    "MissingCredentialsError",
    "MissingInputError",
    "ProvenanceError",
    "database_is_demo",
    "download_failed_error",
    "label_title",
    "mark_database_demo",
    "missing_credentials_error",
    "provenance_payload",
    "require_real_database",
]
