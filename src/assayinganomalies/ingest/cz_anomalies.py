"""
Chen-Zimmerman Open Source Asset Pricing anomaly characteristics ingestion.

Downloads firm characteristics from the Open Source Asset Pricing dataset
(Chen and Zimmermann, 2022) and filters to permnos present in the local ccm_panel.

Release lookup and the Hugging Face downloads live in :mod:`.cz_release`:
``cz_release_version`` picks a release, and None means the newest release on
Hugging Face, looked up when the C-Z stage runs (:class:`CZReleaseChoice`).
This module decides which local file to read (a configured pin, a file the
user downloaded by hand, the per-release cache) and caches downloads under
release-labelled names, so a signal panel and a SignalDoc from two different
releases are never paired by accident.

A file downloaded by hand is found under its OSAP name
(``signed_predictors_dl_wide.parquet``, ``.csv`` or ``.zip``,
``SignalDoc.csv``) anywhere under the same directories the Gibbs file is
searched in: staging, the database directory, ``inputs/`` of a source
checkout, then the current directory. See :func:`find_local_cz_signals` and
:func:`find_local_signal_doc`.
"""

from __future__ import annotations

import glob
import logging
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import NamedTuple
from zipfile import ZipFile, is_zipfile

import pandas as pd
import requests

from ..config import AssayConfig
from ..db.manager import DuckDBManager
from ..run_manifest import note_cz_release, note_input
from .cz_release import (
    CZ_RELEASES,
    NEWEST_RELEASE,
    SIGNAL_DOC_PATH,
    SIGNALS_PATH,
    CZRelease,
    DownloadError,
    NotFoundError,
    RemoteFile,
    branch_url,
    download_release_file,
    list_release_files,
    parse_release_label,
    release_file,
    resolve_release,
    with_commit,
)

LOGGER = logging.getLogger("assayinganomalies.ingest.cz_anomalies")

# Files a user may download by hand (no release in the name), and the
# release-labelled names this module caches downloads under.
MANUAL_PARQUET_NAME = "signed_predictors_dl_wide.parquet"
MANUAL_CSV_NAME = "signed_predictors_dl_wide.csv"
MANUAL_OSAP_ZIP_NAME = "signed_predictors_dl_wide.zip"
MANUAL_ZIP_NAME = "cz_firm_char.zip"
MANUAL_DOC_NAME = "SignalDoc.csv"
CACHED_PARQUET_TEMPLATE = "cz_firm_char_{label}.parquet"
# Downloads from Google Drive (before 2026.10) were cached as zips; still read.
CACHED_ZIP_TEMPLATE = "cz_firm_char_{label}.zip"
CACHED_DOC_TEMPLATE = "cz_signal_doc_{label}.csv"

# Glob patterns for hand-downloaded files, in preference order within one
# directory: a parquet (what Hugging Face serves) or an unzipped CSV needs no
# extraction, so either wins over a zip. The ``*`` takes a browser's " (1)"
# suffix. Release caches are never matched by pattern, so a cache of another
# release is not picked up by accident.
MANUAL_SIGNALS_PATTERNS = (
    "signed_predictors_dl_wide*.parquet",
    "signed_predictors_dl_wide*.csv",
    "signed_predictors_dl_wide*.zip",
    MANUAL_ZIP_NAME,
)
MANUAL_DOC_PATTERN = "SignalDoc*.csv"

# A real signal panel CSV is gigabytes; anything this small is a stub.
_MIN_SIGNALS_CSV_BYTES = 1_000_000


def _is_valid_zip(data: bytes) -> bool:
    """Check if data is a valid zip file by checking magic bytes and structure."""
    if len(data) < 100:
        return False
    # ZIP files start with PK\x03\x04 or PK\x05\x06 (empty) or PK\x07\x08
    if not data[:2] == b"PK":
        return False
    try:
        with ZipFile(BytesIO(data)) as zf:
            # Try to read the file list
            zf.namelist()
        return True
    except Exception:
        return False


def _is_valid_zip_file(path: Path) -> bool:
    """:func:`_is_valid_zip` for a file on disk, without reading it into memory."""
    path = Path(path)
    if not path.is_file() or path.stat().st_size < 100 or not is_zipfile(path):
        return False
    try:
        with ZipFile(path) as zf:
            zf.namelist()
        return True
    except Exception:
        return False


def _is_valid_parquet_file(path: Path) -> bool:
    """True if ``path`` looks like a complete parquet file: ``PAR1`` at both ends."""
    path = Path(path)
    try:
        if not path.is_file() or path.stat().st_size < 12:
            return False
        with path.open("rb") as fh:
            head = fh.read(4)
            fh.seek(-4, 2)
            tail = fh.read(4)
    except OSError:
        return False
    return head == tail == b"PAR1"


def _is_valid_signals_file(path: Path) -> bool:
    """A usable cached or hand-placed signal panel: a parquet or zip, checked by type."""
    if Path(path).suffix.lower() == ".parquet":
        return _is_valid_parquet_file(path)
    return _is_valid_zip_file(path)


def _is_signal_doc_file(path: Path) -> bool:
    """True if ``path`` is a SignalDoc CSV: its header starts with ``Acronym``."""
    try:
        with Path(path).open("rb") as fh:
            head = fh.read(64).lstrip(b"\xef\xbb\xbf")
    except OSError:
        return False
    return head.startswith(b"Acronym")


def cz_release_label(config: AssayConfig) -> str | None:
    """The release ``config`` names, as a label; None = the newest on Hugging Face."""
    return parse_release_label(getattr(config, "cz_release_version", None))


class CZReleaseChoice:
    """
    The release one C-Z stage reads, settled the first time it is needed.

    A configured release is known offline. With none configured, the newest
    release on Hugging Face is looked up the first time the label is asked
    for, and only then, so a stage that reads pinned or hand-placed files
    makes no request. The commit and the release's file list are fetched
    once, the first time a file must be downloaded, and both files come from
    that commit. One choice is shared by the signal panel and the SignalDoc.
    """

    def __init__(self, config: AssayConfig, *, session: requests.Session | None = None):
        self.requested = cz_release_label(config)  # ValueError on a bad label
        self._session = session
        self._release: CZRelease | None = None
        self._files: dict[str, RemoteFile] | None = None

    def _resolve(self) -> CZRelease:
        if self._release is None:
            self._release = resolve_release(self.requested, session=self._session)
            LOGGER.info(
                "CZ release %s: Hugging Face branch %s, commit %s (%s)",
                self._release.label,
                self._release.branch,
                self._release.commit or "not known yet",
                self._release.source,
            )
        return self._release

    @property
    def label(self) -> str:
        """The release label; never raises (an offline default falls back)."""
        if self.requested is not None:
            return self.requested
        return self._resolve().label

    @property
    def branch(self) -> str:
        if self.requested is not None:
            return CZ_RELEASES[self.requested]
        return self._resolve().branch

    @property
    def commit(self) -> str | None:
        """The commit, if this choice has looked it up; never makes a request."""
        return self._release.commit if self._release is not None else None

    def remote(self, path: str) -> tuple[CZRelease, RemoteFile]:
        """The release, with its commit, and what the tree API lists for ``path``."""
        release = self._release = with_commit(self._resolve(), self._session)
        if self._files is None:
            self._files = list_release_files(release, self._session)
        return release, release_file(self._files, path, release)

    def download(self, path: str, dest: Path, what: str) -> Path:
        """Download ``path`` from this release's commit to ``dest``, verified."""
        release, remote = self.remote(path)
        LOGGER.info(
            "Downloading %s (%.2f GB) from Hugging Face, branch %s, commit %s...",
            what,
            remote.size / 1e9,
            release.branch,
            release.commit,
        )
        download_release_file(release, remote, dest, what, session=self._session)
        return dest

    def note(self, what: str) -> None:
        """Record for the run manifest that ``what`` came from this release."""
        note_cz_release(what, self.label, branch=self.branch, commit=self.commit)


def cz_manual_hint(db_path: Path, what: str = "signals", branch: str | None = None) -> str:
    """
    What a user can do when a CZ download fails; quoted in every such error.

    ``what`` is ``"signals"`` (the panel) or ``"SignalDoc"``. ``branch`` is
    the release's Hugging Face branch, when known; without it the hint points
    to the dataset's front page.
    """
    staging = Path(db_path).parent / "staging"
    source = branch_url(branch)
    where = (
        f"{staging}, the database directory, inputs/ or the directory you run "
        "aa from (any subfolder; keep the name it downloads with)"
    )
    if what == "SignalDoc":
        manual = (
            f"download {SIGNAL_DOC_PATH} from {source} and save it under {where}, "
            "or keep it anywhere and pin it with `aa set-params --cz-signal-doc-path <file>`"
        )
    else:
        manual = (
            f"download {MANUAL_PARQUET_NAME} (under 'Firm Level Characteristics/') "
            f"from {source} and save it under {where}, or keep it anywhere and pin "
            "it with `aa set-params --cz-signals-path <file>`"
        )
    return (
        f"To continue: {manual}. If a firewall blocked the download, allow "
        "huggingface.co and *.hf.co (its download CDN) instead. Then resume "
        "without repeating the WRDS stages: "
        "`aa setup-database --start-from fetch-cz-anomalies`."
    )


def _download_error(
    exc: Exception, what: str, label: str, db_path: Path, branch: str | None = None
) -> DownloadError:
    """Wrap a failed CZ download with the release and the manual-path hint."""
    cls = type(exc) if isinstance(exc, DownloadError) else DownloadError
    hint = cz_manual_hint(db_path, what, branch)
    err = cls(f"Could not download the CZ {label} {what}: {exc}. {hint}")
    err.hint = hint  # read by pipeline._cz_stage_error, so it is said once
    return err


def _missing_pin_error(field: str, flag: str, path: Path) -> FileNotFoundError:
    """A pinned CZ file is gone: say how to restore it or clear the pin."""
    return FileNotFoundError(
        f"{field} not found: {path}. Restore the file, or clear the pin to use "
        f'a hand-placed file, the release cache or a download: aa set-params {flag} ""'
    )


def _month_end(ts: pd.Series) -> pd.Series:
    """Normalize datetimes to month-end (00:00:00)."""
    dt = pd.to_datetime(ts, errors="coerce")
    return (dt + pd.offsets.MonthEnd(0)).dt.normalize()


def _get_ccm_panel_permnos(db_path: Path) -> set[int]:
    """Query ccm_panel for the set of distinct permnos."""
    with DuckDBManager(db_path) as manager:
        result = manager.query_df("SELECT DISTINCT permno FROM ccm_panel")
        permnos = set(result["permno"].dropna().astype(int).tolist())
    LOGGER.info("Found %d distinct permnos in ccm_panel", len(permnos))
    return permnos


def _add_crsp_derived_signals(df: pd.DataFrame, db_path: Path) -> pd.DataFrame:
    """
    Add Price, STreversal, and Size signals from ccm_panel.

    Per MATLAB getChenZimmermanAnomalies.m, WRDS licensing prevents CZ from
    sharing these three signals, so we compute them from CRSP data:
    - Price: -abs(prc)
    - STreversal: -ret (short-term reversal)
    - Size: -me (negative so high rank = small)
    """
    with DuckDBManager(db_path) as manager:
        crsp = manager.query_df("SELECT date, permno, prc, ret, me FROM ccm_panel")

    # Normalize dates to month-end for merging
    crsp["date"] = _month_end(crsp["date"])
    crsp["permno"] = crsp["permno"].astype("Int64")

    # Compute the three CRSP-derived signals (signed per MATLAB convention)
    # Use lowercase names to match other CZ signals
    crsp["price"] = -crsp["prc"].abs()
    crsp["streversal"] = -pd.to_numeric(crsp["ret"], errors="coerce")
    crsp["size"] = -pd.to_numeric(crsp["me"], errors="coerce")

    # Keep only what we need for merging
    crsp_signals = crsp[["date", "permno", "price", "streversal", "size"]].copy()

    # Merge into the anomaly DataFrame
    df = df.merge(crsp_signals, on=["date", "permno"], how="left")
    LOGGER.info("Added Price, STreversal, Size from ccm_panel")

    return df


def _staging_dir(db_path: Path) -> Path:
    staging = Path(db_path).parent / "staging"
    staging.mkdir(parents=True, exist_ok=True)
    return staging


class CZSignalsFile(NamedTuple):
    """A local CZ signal panel and the release it is from (None = not known)."""

    path: Path
    release: str | None
    origin: str  # "cz_signals_path", "manual file (<where>)" or "release cache"


def _cached_cz_parquet_path(db_path: Path, label: str) -> Path:
    """Where a downloaded signal panel of release ``label`` is cached."""
    return _staging_dir(db_path) / CACHED_PARQUET_TEMPLATE.format(label=label)


def _find_cached_signals(db_path: Path, label: str) -> CZSignalsFile | None:
    """Release ``label``'s cached panel: the parquet, else a zip from the Drive era."""
    staging = Path(db_path).parent / "staging"
    for template in (CACHED_PARQUET_TEMPLATE, CACHED_ZIP_TEMPLATE):
        cached = staging / template.format(label=label)
        if not cached.is_file():
            continue
        if _is_valid_signals_file(cached):
            return CZSignalsFile(cached, label, "release cache")
        LOGGER.warning("Cached CZ file %s is invalid; ignoring it", cached)
    return None


def _find_cached_signal_doc(db_path: Path, label: str) -> CZSignalsFile | None:
    """Release ``label``'s cached SignalDoc, if there is a non-empty one."""
    cached = Path(db_path).parent / "staging" / CACHED_DOC_TEMPLATE.format(label=label)
    if cached.is_file() and cached.stat().st_size > 0:
        return CZSignalsFile(cached, label, "release cache")
    return None


def _cached_signal_doc_path(db_path: Path, label: str) -> Path:
    """Where a downloaded SignalDoc.csv of release ``label`` is cached."""
    return _staging_dir(db_path) / CACHED_DOC_TEMPLATE.format(label=label)


def source_tree_inputs() -> Path | None:
    """``inputs/`` when running from a source checkout, else None."""
    # Same rule as ingest/gibbs.source_tree_gibbs: parents[3] is the checkout
    # root, and a wheel install's lib directory has no pyproject.toml.
    root = Path(__file__).resolve().parents[3]
    if not (root / "pyproject.toml").is_file():
        return None
    path = root / "inputs"
    return path if path.is_dir() else None


def _working_dir() -> Path:
    """The directory searched last for hand-downloaded files (the cwd)."""
    return Path(".")


def _manual_search_dirs(db_path: Path) -> list[tuple[Path, str]]:
    """Where hand-downloaded CZ files are looked for, in order, with labels."""
    db_dir = Path(db_path).parent
    dirs = [(db_dir / "staging", "staging"), (db_dir, "database dir")]
    shipped = source_tree_inputs()
    if shipped is not None:
        dirs.append((shipped, "source tree inputs"))
    dirs.append((_working_dir(), "working dir"))
    return dirs


def _glob_all(directory: Path, pattern: str) -> list[Path]:
    """Every ``pattern`` match anywhere under ``directory``, in sorted order."""
    if not directory.is_dir():
        return []
    root = glob.escape(str(directory))
    return [Path(m) for m in sorted(glob.glob(f"{root}/**/{pattern}", recursive=True))]


def _find_manual_signals(db_path: Path) -> tuple[Path, str] | None:
    """The first usable hand-downloaded signal panel, and where it was found."""
    for directory, where in _manual_search_dirs(db_path):
        for pattern in MANUAL_SIGNALS_PATTERNS:
            for hit in _glob_all(directory, pattern):
                suffix = hit.suffix.lower()
                if suffix == ".csv":
                    if hit.stat().st_size > _MIN_SIGNALS_CSV_BYTES:
                        return hit, where
                    LOGGER.warning("Ignoring %s: too small to be the CZ signal panel", hit)
                elif _is_valid_signals_file(hit):
                    return hit, where
                elif suffix == ".parquet":
                    LOGGER.warning(
                        "Ignoring %s: not a complete parquet file (no PAR1 marker at "
                        "both ends; an interrupted download?)",
                        hit,
                    )
                else:
                    LOGGER.warning("Ignoring %s: not a valid zip file", hit)
    return None


def _find_manual_signal_doc(db_path: Path) -> tuple[Path, str] | None:
    """The first hand-downloaded SignalDoc CSV, and where it was found."""
    for directory, where in _manual_search_dirs(db_path):
        for hit in _glob_all(directory, MANUAL_DOC_PATTERN):
            if _is_signal_doc_file(hit):
                return hit, where
            LOGGER.warning("Ignoring %s: its header does not start with 'Acronym'", hit)
    return None


def find_local_cz_signals(
    config: AssayConfig, db_path: Path, label: str | None = None
) -> CZSignalsFile | None:
    """
    The local CZ signal panel a build would read, or None if it must download.

    Preference order:
      1. ``config.cz_signals_path`` (raises if it names a missing file)
      2. a hand-downloaded file: ``signed_predictors_dl_wide*.parquet``, then
         ``signed_predictors_dl_wide*.csv``, then
         ``signed_predictors_dl_wide*.zip``, then ``cz_firm_char.zip``,
         anywhere under staging, the database directory, ``inputs/`` of a
         source checkout, then the current directory (the first directory
         with a usable file wins)
      3. ``<db dir>/staging/cz_firm_char_<release>.parquet`` (an earlier
         download), else a ``.zip`` cached by an older version of the package

    A file placed by hand wins over the cache because placing it is what the
    download error tells a user to do; its release cannot be read off it.

    Step 3 needs the release: ``label``, else the configured one. With
    neither, the cache is not looked at (which release is the newest is
    known only online, when the stage runs) and None is returned.
    """
    pinned = getattr(config, "cz_signals_path", None)
    if pinned:
        path = Path(pinned).expanduser()
        if not path.is_file():
            raise _missing_pin_error("cz_signals_path", "--cz-signals-path", path)
        return CZSignalsFile(path, None, "cz_signals_path")

    manual = _find_manual_signals(db_path)
    if manual is not None:
        return CZSignalsFile(manual[0], None, f"manual file ({manual[1]})")

    label = label or cz_release_label(config)
    return _find_cached_signals(db_path, label) if label is not None else None


def download_cz_signals(
    config: AssayConfig,
    db_path: Path,
    *,
    release: CZReleaseChoice | None = None,
) -> Path:
    """
    Download the release's signal panel into the release cache.

    ``release`` is the stage's shared :class:`CZReleaseChoice` (a new one
    from ``config`` if not given). The parquet is verified against the sha256
    Hugging Face lists. Every failure raises :class:`DownloadError` (or a
    subclass) carrying :func:`cz_manual_hint`.
    """
    choice = release or CZReleaseChoice(config)
    label = choice.label
    dest = _cached_cz_parquet_path(db_path, label)
    try:
        choice.download(SIGNALS_PATH, dest, f"CZ {label} signals")
    except (DownloadError, requests.RequestException) as exc:
        raise _download_error(exc, "signals", label, db_path, choice.branch) from exc
    LOGGER.info("Cached CZ %s panel to %s (%.1f GB)", label, dest, dest.stat().st_size / 1e9)
    return dest


def resolve_cz_signals_source(
    config: AssayConfig,
    db_path: Path,
    *,
    source: Path | None = None,
    download: bool = True,
    release: CZReleaseChoice | None = None,
) -> Path:
    """
    Resolve a local path to CZ signed predictors (parquet, CSV or zip).

    Preference order:
      1. Explicit ``source``
      2. :func:`find_local_cz_signals` (``cz_signals_path``, a hand-placed
         file, then the release cache)
      3. Download + cache ``cz_firm_char_<release>.parquet`` (when ``download=True``)

    With no release configured, the newest on Hugging Face is looked up only
    when steps 1-2 find no pinned or hand-placed file. The release the panel
    is from is logged and recorded for the run manifest.
    """
    if source is not None:
        src = Path(source)
        if not src.is_file():
            raise FileNotFoundError(f"CZ source not found: {src}")
        note_input(src, "CZ signed predictors")
        note_cz_release("signals", None)
        return src

    choice = release or CZReleaseChoice(config)
    found = find_local_cz_signals(config, db_path)
    if found is None and choice.requested is None:
        found = _find_cached_signals(db_path, choice.label)
    if found is not None:
        size_gb = found.path.stat().st_size / 1e9
        if found.release is None:
            LOGGER.info(
                "Using CZ signals from %s %s (%.1f GB); its release is not known "
                "from the file, so the SignalDoc follows cz_release_version (%s)",
                found.origin,
                found.path,
                size_gb,
                choice.requested or "the newest on Hugging Face",
            )
            note_input(found.path, "CZ signed predictors")
            note_cz_release("signals", None)
        else:
            LOGGER.info(
                "Using CZ %s signals from %s (%.1f GB)", found.release, found.path, size_gb
            )
            note_input(found.path, "CZ signed predictors")
            choice.note("signals")
        return found.path

    if not download:
        raise FileNotFoundError(
            f"No CZ signals under {_staging_dir(db_path)} and download=False"
        )

    path = download_cz_signals(config, db_path, release=choice)
    note_input(path, "CZ signed predictors")
    choice.note("signals")
    return path


def _sql_path(path: Path) -> str:
    """``path`` as a single-quoted DuckDB string literal (forward slashes)."""
    return "'" + Path(path).as_posix().replace("'", "''") + "'"


def _cz_read_sql(source: Path) -> str:
    """
    DuckDB FROM-clause fragment for a CZ parquet or plain CSV.

    See :func:`_cz_file_for_duckdb` for a zip.
    """
    if Path(source).suffix.lower() == ".parquet":
        return f"read_parquet({_sql_path(source)})"
    return (
        f"read_csv({_sql_path(source)}, header=true, auto_detect=true, "
        f"sample_size=-1, ignore_errors=false)"
    )


@contextmanager
def _cz_file_for_duckdb(source: Path, staging: Path) -> Iterator[Path]:
    """
    A parquet or plain CSV DuckDB can read for the CZ panel at ``source``.

    A parquet or CSV is yielded as is. A zip has its CSV member streamed to
    ``staging/.cz_extract_<zip stem>.csv``, which is deleted on exit: DuckDB's
    own ``zip://`` paths need the community ``zipfs`` extension, which a build
    does not install. The member is ~8 GB uncompressed, so free space in
    ``staging`` is checked first.
    """
    src = Path(source)
    if src.suffix.lower() != ".zip":
        yield src
        return
    with ZipFile(src) as zf:
        names = zf.namelist()
        csv_name = next((n for n in names if n.lower().endswith(".csv")), names[0])
        member = zf.getinfo(csv_name)
        staging.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(staging).free
        if member.file_size > free:
            raise OSError(
                f"Not enough free space in {staging} to extract {csv_name} from {src}: "
                f"needs {member.file_size / 1e9:.1f} GB, {free / 1e9:.1f} GB free. "
                f"Free some space, or unzip it yourself to {staging / MANUAL_CSV_NAME}."
            )
        tmp = staging / f".cz_extract_{src.stem}.csv"
        LOGGER.info(
            "Extracting %s from %s (%.1f GB) to %s...",
            csv_name,
            src,
            member.file_size / 1e9,
            tmp,
        )
        try:
            with zf.open(member) as fin, tmp.open("wb") as fout:
                shutil.copyfileobj(fin, fout, 16 * 1024 * 1024)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    try:
        yield tmp
    finally:
        tmp.unlink(missing_ok=True)


def write_cz_anomalies_table(
    config: AssayConfig,
    db_path: Path,
    *,
    source: Path | None = None,
    download: bool = True,
    release: CZReleaseChoice | None = None,
) -> dict[str, int | float | str]:
    """
    Load the full Chen–Zimmerman zoo into DuckDB ``cz_anomalies`` (replace).

    Streams via DuckDB (reads the parquet directly; avoids materializing the
    panel in pandas). Does **not** pre-trim to the protocol's post-coverage
    n≈157 — that filter runs later in ``check_fill_anomalies`` over the test
    signal's ``timePeriod``.

    Adds CRSP-derived ``price``, ``streversal``, ``size`` from ``ccm_panel``.
    ``release`` is the stage's shared :class:`CZReleaseChoice`.
    """
    src = resolve_cz_signals_source(
        config, db_path, source=source, download=download, release=release
    )
    lo = int(config.sample_start) * 100 + 1
    hi = int(config.sample_end) * 100 + 12

    LOGGER.info(
        "Writing cz_anomalies from %s (sample yyyymm %d–%d) via DuckDB...",
        src,
        lo,
        hi,
    )

    # A zip is extracted for the DESCRIBE probe and the CREATE TABLE alike.
    with _cz_file_for_duckdb(src, _staging_dir(db_path)) as read_path, DuckDBManager(
        db_path
    ) as manager:
        read_sql = _cz_read_sql(read_path)
        con = manager.connection
        # Discover signal columns (exclude keys); lowercase for storage.
        probe = con.execute(f"DESCRIBE SELECT * FROM {read_sql}").fetchall()
        raw_cols = [r[0] for r in probe]
        lower_map = {c: c.lower() for c in raw_cols}
        if "permno" not in {c.lower() for c in raw_cols}:
            raise ValueError(f"CZ source missing permno; columns={raw_cols[:20]}")
        has_yyyymm = "yyyymm" in {c.lower() for c in raw_cols}
        has_date = "date" in {c.lower() for c in raw_cols} and not has_yyyymm
        if not has_yyyymm and not has_date:
            raise ValueError("CZ signals missing date/yyyymm column")

        # WRDS licensing: CZ omits price/size/streversal; we always add from ccm_panel.
        skip = {"permno", "yyyymm", "date", "price", "streversal", "size"}
        signal_pairs: list[tuple[str, str]] = []
        for c in raw_cols:
            lc = lower_map[c]
            if lc in skip:
                continue
            # Prefer first occurrence if case collisions
            if any(s == lc for _, s in signal_pairs):
                continue
            signal_pairs.append((c, lc))

        # Build SELECT list with quoted identifiers for source cols.
        # Force DOUBLE so nullable Int64 inference cannot break FM winsor/clip.
        signal_select = ",\n            ".join(
            f'TRY_CAST(raw."{src_c}" AS DOUBLE) AS {dst_c}' for src_c, dst_c in signal_pairs
        )
        if has_yyyymm:
            ycol = next(c for c in raw_cols if c.lower() == "yyyymm")
            yyyymm_expr = f'TRY_CAST(raw."{ycol}" AS INTEGER)'
            date_expr = f"last_day(strptime(CAST(({yyyymm_expr}) AS VARCHAR), '%Y%m'))"
            date_filter = f"{yyyymm_expr} BETWEEN {lo} AND {hi}"
        else:
            dcol = next(c for c in raw_cols if c.lower() == "date")
            date_expr = f'last_day(CAST(raw."{dcol}" AS DATE))'
            date_filter = (
                f"(year({date_expr}) * 100 + month({date_expr})) BETWEEN {lo} AND {hi}"
            )

        pcol = next(c for c in raw_cols if c.lower() == "permno")
        con.execute("DROP TABLE IF EXISTS cz_anomalies")
        sql = f"""
        CREATE TABLE cz_anomalies AS
        WITH raw AS (
            SELECT * FROM {read_sql}
        ),
        filtered AS (
            SELECT
                {date_expr} AS date,
                TRY_CAST(raw."{pcol}" AS BIGINT) AS permno,
                {signal_select}
            FROM raw
            WHERE {date_filter}
              AND TRY_CAST(raw."{pcol}" AS BIGINT) IN (
                    SELECT DISTINCT permno FROM ccm_panel WHERE permno IS NOT NULL
              )
        )
        SELECT
            f.date,
            f.permno,
            {", ".join("f." + s for _, s in signal_pairs)},
            -abs(c.prc) AS price,
            -CAST(c.ret AS DOUBLE) AS streversal,
            -CAST(c.me AS DOUBLE) AS size
        FROM filtered f
        LEFT JOIN ccm_panel c
          ON f.permno = c.permno
         AND f.date = last_day(CAST(c.date AS DATE))
        ORDER BY f.date, f.permno
        """
        LOGGER.info("Executing DuckDB CREATE TABLE cz_anomalies (%d signal cols)...", len(signal_pairs))
        con.execute(sql)

        n_rows = con.execute("SELECT COUNT(*) FROM cz_anomalies").fetchone()[0]
        n_perm = con.execute("SELECT COUNT(DISTINCT permno) FROM cz_anomalies").fetchone()[0]
        dmin, dmax = con.execute("SELECT MIN(date), MAX(date) FROM cz_anomalies").fetchone()
        n_cols = len(con.execute("DESCRIBE cz_anomalies").fetchall())

    stats: dict[str, int | float | str] = {
        "rows": int(n_rows),
        "permnos": int(n_perm),
        "columns": int(n_cols),
        "signals": int(len(signal_pairs) + 3),  # + price/streversal/size
        "date_min": str(dmin),
        "date_max": str(dmax),
        "source": str(src),
    }
    LOGGER.info("cz_anomalies loaded: %s", stats)
    return stats


def fetch_cz_anomalies(config: AssayConfig, db_path: Path) -> pd.DataFrame:
    """
    Download Chen-Zimmerman anomaly characteristics and filter to ccm_panel permnos.

    Returns a wide DataFrame with columns: date, permno, and ~212 anomaly signals.

    Prefer ``write_cz_anomalies_table`` for production loads (streams via DuckDB).
    This pandas path remains for small tests / callers that need a DataFrame.
    """
    # Prefer writing via DuckDB then reading back when the source is large;
    # for unit-scale callers this still works once the table exists.
    src = resolve_cz_signals_source(config, db_path, download=True)
    # If source is huge, refuse pandas full load — use DuckDB path instead.
    size = Path(src).stat().st_size
    if size > 200_000_000:  # >200MB compressed/raw → stream to DB; do not pandas-load
        LOGGER.info(
            "CZ source is %.1f GB; writing via DuckDB (use load_cz_anomalies / SQL to read)",
            size / 1e9,
        )
        write_cz_anomalies_table(config, db_path, source=src, download=False)
        with DuckDBManager(db_path) as manager:
            # Schema-only return — full panel stays in DuckDB (multi-GB).
            return manager.query_df("SELECT * FROM cz_anomalies LIMIT 0")

    # Small-file pandas path (tests / tiny caches)
    if Path(src).suffix.lower() == ".parquet":
        df = pd.read_parquet(src)
    elif Path(src).suffix.lower() == ".zip":
        with ZipFile(src) as zf:
            csv_filename = zf.namelist()[0]
            csv_data = zf.read(csv_filename)
        df = pd.read_csv(BytesIO(csv_data), low_memory=False)
    else:
        df = pd.read_csv(src, low_memory=False)

    LOGGER.info("Loaded firm characteristics: shape=%s (%d signals)", df.shape, len(df.columns) - 2)
    df.columns = df.columns.str.lower()

    if "yyyymm" in df.columns and "date" not in df.columns:
        df["date"] = (
            pd.to_datetime(df["yyyymm"].astype(str) + "01", format="%Y%m%d")
            + pd.offsets.MonthEnd(0)
        )
    elif "date" in df.columns:
        df["date"] = _month_end(df["date"])
    else:
        raise ValueError("CZ signals missing date/yyyymm column")

    df["permno"] = pd.to_numeric(df["permno"], errors="coerce").astype("Int64")

    lo = config.sample_start * 100 + 1
    hi = config.sample_end * 100 + 12
    if "yyyymm" in df.columns:
        df = df[df["yyyymm"].between(lo, hi)]
    else:
        df_yyyymm = df["date"].dt.year * 100 + df["date"].dt.month
        df = df[df_yyyymm.between(lo, hi)]
    LOGGER.info("After date filter (%d-%d): shape=%s", config.sample_start, config.sample_end, df.shape)

    valid_permnos = _get_ccm_panel_permnos(db_path)
    df = df[df["permno"].isin(valid_permnos)]
    LOGGER.info("After permno filter: shape=%s", df.shape)

    df = _add_crsp_derived_signals(df, db_path)
    cols = ["date", "permno"] + [c for c in df.columns if c not in ("date", "permno", "yyyymm")]
    df = df[cols]
    LOGGER.info("Final CZ anomalies DataFrame: shape=%s, columns=%d", df.shape, len(df.columns))
    return df


def generate_placeholder_cz_anomalies(config: AssayConfig, db_path: Path) -> pd.DataFrame:
    """
    Generate a minimal placeholder DataFrame for testing/CI when download fails.

    Returns a small DataFrame with the expected schema but minimal data.
    """
    # Get a sample of permnos from ccm_panel
    try:
        valid_permnos = _get_ccm_panel_permnos(db_path)
        sample_permnos = list(valid_permnos)[:10]
    except Exception:
        sample_permnos = [10001, 10002, 10003]

    # Generate a few months of placeholder data
    dates = pd.date_range(
        start=f"{config.sample_start}-01-31",
        periods=3,
        freq="ME",
    )

    rows = []
    for date in dates:
        for permno in sample_permnos:
            rows.append({"date": date, "permno": permno})

    df = pd.DataFrame(rows)

    # Add placeholder anomaly columns (a representative subset)
    placeholder_signals = [
        "bm", "mom12m", "size", "price", "streversal",
        "ep", "cfp", "dp", "sp", "agr",
    ]
    for sig in placeholder_signals:
        df[sig] = pd.NA

    df["permno"] = df["permno"].astype("Int64")
    LOGGER.info("Generated placeholder CZ anomalies: shape=%s", df.shape)
    return df


def find_local_signal_doc(
    config: AssayConfig, db_path: Path, label: str | None = None
) -> CZSignalsFile | None:
    """
    The local SignalDoc a build would read, or None if it must download.

    Preference order, as for the signal panel (:func:`find_local_cz_signals`):
      1. ``config.cz_signal_doc_path`` (raises if it names a missing file)
      2. a hand-downloaded ``SignalDoc*.csv`` whose header starts with
         ``Acronym``, anywhere under staging, the database directory,
         ``inputs/`` of a source checkout, then the current directory
      3. ``<db dir>/staging/cz_signal_doc_<release>.csv`` (an earlier
         download), for ``label`` or the configured release; skipped when
         neither is known
    """
    pinned = getattr(config, "cz_signal_doc_path", None)
    if pinned:
        path = Path(pinned).expanduser()
        if not path.exists():
            raise _missing_pin_error("cz_signal_doc_path", "--cz-signal-doc-path", path)
        return CZSignalsFile(path, None, "cz_signal_doc_path")

    manual = _find_manual_signal_doc(db_path)
    if manual is not None:
        return CZSignalsFile(manual[0], None, f"manual file ({manual[1]})")

    label = label or cz_release_label(config)
    return _find_cached_signal_doc(db_path, label) if label is not None else None


def fetch_cz_signal_info(
    config: AssayConfig,
    db_path: Path,
    *,
    demo: bool = False,
    release: CZReleaseChoice | None = None,
) -> pd.DataFrame:
    """
    Download Chen-Zimmerman signal documentation/metadata.

    Returns a DataFrame with one row per signal containing:
    - Acronym: signal name (lowercase, matches cz_anomalies columns)
    - Authors, Year, Journal: publication info
    - SampleStartYear, SampleEndYear: original sample period
    - StockWeight: weighting scheme (e.g., "VW", "EW")
    - LSQuantile: long-short quantile (e.g., 10 for deciles)
    - PortfolioPeriod: holding period in months
    - Filter, QuantileFilter: universe filters
    - LongDescription: what the signal measures

    ``demo=True`` allows the synthetic stand-in table when the documentation
    cannot be downloaded. In production a failure raises, because the protocol
    reads this table for anomaly names, weighting schemes and holding periods.
    ``release`` is the stage's shared :class:`CZReleaseChoice`, so the
    SignalDoc comes from the same release and commit as the signal panel.
    """
    # A pinned or hand-downloaded doc; the release cache and the download are
    # ensure_cz_signal_doc's, which also serves callers that need only a path.
    found = find_local_signal_doc(config, db_path)
    if found is not None and found.release is None:
        LOGGER.info("Using CZ signal docs from %s %s", found.origin, found.path)
        note_input(found.path, "CZ signal documentation")
        origin = found.origin if found.origin == "cz_signal_doc_path" else "manual file"
        note_cz_release("signal_doc", None, origin=origin)
        return _normalize_signal_info(pd.read_csv(found.path))

    choice = release or CZReleaseChoice(config)
    try:
        docs_path = ensure_cz_signal_doc(config, db_path, release=choice)
    except DownloadError as exc:
        if not demo:
            raise
        LOGGER.warning(
            "DEMO MODE: failed to download signal docs (%s); using placeholder",
            exc,
        )
        return _generate_placeholder_signal_info()

    note_input(docs_path, "CZ signal documentation")
    choice.note("signal_doc")
    return _normalize_signal_info(pd.read_csv(docs_path))


def ensure_cz_signal_doc(
    config: AssayConfig, db_path: Path, *, release: CZReleaseChoice | None = None
) -> Path:
    """
    The release's ``SignalDoc.csv``, from cache or downloaded.

    Cached as ``cz_signal_doc_<release>.csv``, so it always comes from the same
    release as a downloaded signal panel; a download is verified against the
    git blob sha1 Hugging Face lists. ``cz_signal_doc_path`` is handled by
    the caller and bypasses this.
    """
    choice = release or CZReleaseChoice(config)
    label = choice.label
    docs_path = _cached_signal_doc_path(db_path, label)
    if docs_path.is_file() and docs_path.stat().st_size > 0:
        LOGGER.info("Using cached CZ %s signal docs from %s", label, docs_path)
        return docs_path
    try:
        choice.download(SIGNAL_DOC_PATH, docs_path, f"CZ {label} SignalDoc")
        if not _is_signal_doc_file(docs_path):
            docs_path.unlink(missing_ok=True)
            raise DownloadError("downloaded data is not a SignalDoc CSV")
    except (DownloadError, requests.RequestException) as exc:
        raise _download_error(exc, "SignalDoc", label, db_path, choice.branch) from exc
    return docs_path


def _normalize_signal_info(df: pd.DataFrame) -> pd.DataFrame:
    """Shape a raw SignalDoc table into the `cz_signal_info` schema."""
    # Normalize column names: remove dots/spaces, convert to snake_case
    col_renames = {
        "Cat.Signal": "Cat_Signal",
        "Cat.Form": "Cat_Form",
        "Cat.Data": "Cat_Data",
        "Cat.Economic": "Cat_Economic",
        "Stock Weight": "StockWeight",
        "LS Quantile": "LSQuantile",
        "Quantile Filter": "QuantileFilter",
        "Portfolio Period": "PortfolioPeriod",
        "Start Month": "StartMonth",
    }
    df = df.rename(columns=col_renames)

    # Filter to predictors only (Cat_Signal == 'Predictor')
    cat_col = "Cat_Signal" if "Cat_Signal" in df.columns else None
    if cat_col:
        df = df[df[cat_col] == "Predictor"].copy()

    # Create lowercase acronym column (primary identifier matching cz_anomalies
    # columns) while keeping the case-preserved acronym: the zoo is ordered and
    # labelled by MATLAB's `sort(labels)` over these CamelCase names.
    if "Acronym" in df.columns:
        df["acronym"] = df["Acronym"].str.lower()
        df["acronym_cased"] = df["Acronym"].astype(str)
        df = df.drop(columns=["Acronym"])

    # WRDS licensing keeps three predictors out of the CZ signal panel, so we
    # rebuild them from CRSP (-abs(prc), -ret, -me). SignalDoc documents them
    # anyway; only fall back to our own text when the release does not.
    crsp_signals = pd.DataFrame([
        {
            "acronym": "price",
            "acronym_cased": "Price",
            "Authors": "CRSP-derived",
            "LongDescription": "Price",
            "Cat_Signal": "Predictor",
            "StockWeight": "VW",
            "LSQuantile": 0.1,
            "PortfolioPeriod": 1,
        },
        {
            "acronym": "streversal",
            "acronym_cased": "STreversal",
            "Authors": "CRSP-derived",
            "LongDescription": "Short term reversal",
            "Cat_Signal": "Predictor",
            "StockWeight": "VW",
            "LSQuantile": 0.1,
            "PortfolioPeriod": 1,
        },
        {
            "acronym": "size",
            "acronym_cased": "Size",
            "Authors": "CRSP-derived",
            "LongDescription": "Size",
            "Cat_Signal": "Predictor",
            "StockWeight": "VW",
            "LSQuantile": 0.1,
            "PortfolioPeriod": 1,
        },
    ])
    have = set(df["acronym"]) if "acronym" in df.columns else set()
    missing = crsp_signals[~crsp_signals["acronym"].isin(have)]
    if not missing.empty:
        df = pd.concat([df, missing], ignore_index=True)

    LOGGER.info("Loaded CZ signal info: %d signals", len(df))
    return df


def _generate_placeholder_signal_info() -> pd.DataFrame:
    """Generate minimal placeholder signal info for testing."""
    return pd.DataFrame([
        {"acronym": "bm", "LongDescription": "Book-to-market ratio"},
        {"acronym": "mom12m", "LongDescription": "12-month momentum"},
        {"acronym": "size", "LongDescription": "Market capitalization (negative)"},
        {"acronym": "price", "LongDescription": "Stock price (negative)"},
        {"acronym": "streversal", "LongDescription": "Short-term reversal"},
    ])


__all__ = [
    # Re-exported from .cz_release so callers need one import.
    "CZ_RELEASES",
    "NEWEST_RELEASE",
    "DownloadError",
    "NotFoundError",
    # This module.
    "CZReleaseChoice",
    "CZSignalsFile",
    "cz_manual_hint",
    "cz_release_label",
    "download_cz_signals",
    "ensure_cz_signal_doc",
    "fetch_cz_anomalies",
    "fetch_cz_signal_info",
    "find_local_cz_signals",
    "find_local_signal_doc",
    "generate_placeholder_cz_anomalies",
    "resolve_cz_signals_source",
    "write_cz_anomalies_table",
]
