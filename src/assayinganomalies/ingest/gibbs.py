"""
Hasbrouck's Gibbs effective-spread estimates: find the input file, or fetch it.

Every ``tcosts_type`` needs ``crspgibbs.csv``, the yearly Gibbs estimates of
the Roll model (Hasbrouck 2009) that ``transforms/tcosts.py`` turns into the
Gibbs spread measure. The file is not on WRDS: it is the output of Hasbrouck's
SAS code run over CRSP daily data. The repository ships it at
``inputs/gibbs/crspgibbs.csv`` (with the SAS code and refresh instructions);
a wheel install does not, so the file is fetched from the public repository's
``gibbs-data-v1`` tag and checked against a SHA-256 pin.

:func:`resolve_gibbs_file` looks in this order and stops at the first hit:

1. ``config.gibbs_path``, an explicit pin (raises if it names a missing file);
2. ``crspgibbs*.csv`` anywhere under the staging directory (a hand-placed file
   or the cache a previous download left);
3. the same pattern anywhere under the database directory;
4. ``inputs/gibbs/crspgibbs.csv`` in a source checkout;
5. the same pattern anywhere under the current directory (MATLAB's
   ``dir(fullfile(Params.directory, '**/crspgibbs*.csv'))``);
6. a download into the staging directory (pinned SHA-256; a mismatch is
   refused and nothing is kept);
7. otherwise :class:`~assayinganomalies.provenance.MissingInputError`, naming
   the manual paths.

Local files are not hashed against the pin: a user may refresh the estimates
with the SAS code, and that file is theirs to use. Only the downloaded copy has
to match, because the URL is the one thing here someone else controls.
"""

from __future__ import annotations

import glob
import hashlib
import logging
from pathlib import Path
from typing import NamedTuple

import requests

from ..provenance import MissingInputError

LOGGER = logging.getLogger("assayinganomalies.ingest.gibbs")

GIBBS_FILENAME = "crspgibbs.csv"
GIBBS_PATTERN = "crspgibbs*.csv"

# The data tag on the public repository. It is separate from the package
# version so every release reads the same URL; a refreshed file gets a new tag
# and a new pin.
GIBBS_DATA_TAG = "gibbs-data-v1"
GIBBS_URL = (
    "https://raw.githubusercontent.com/velikov-mihail/AssayingAnomalies/"
    f"{GIBBS_DATA_TAG}/inputs/gibbs/{GIBBS_FILENAME}"
)
# SHA-256 of inputs/gibbs/crspgibbs.csv (526,126 permno-years, 1926-2024),
# byte-identical to the MATLAB toolkit's Library Update/Inputs/Gibbs copy.
GIBBS_SHA256 = "502d86d9304f99934683f3401e361e44d53ba739c7af526b7952337a7a367a6e"

# Path of the shipped copy inside a source checkout.
SOURCE_TREE_RELPATH = Path("inputs") / "gibbs" / GIBBS_FILENAME

_TIMEOUT = 60  # seconds, per request (connect and between bytes)
_CHUNK = 1024 * 1024

# Where a message sends the user for what each tcosts_type needs. The README
# is the project page on PyPI and on GitHub, so it is there for every install.
DOCS_PAGE = 'the README (section "Trading costs: what you need")'
RESUME_COMMAND = "aa setup-database --start-from compute-tcosts"


class GibbsDownloadError(Exception):
    """The Gibbs file could not be downloaded."""


class GibbsChecksumError(GibbsDownloadError):
    """The downloaded Gibbs file does not match the SHA-256 pin."""


class GibbsFile(NamedTuple):
    """A resolved Gibbs input and where it was found."""

    path: Path
    # "gibbs_path", "staging", "database dir", "source tree",
    # "working dir" or "download"
    origin: str


def gibbs_manual_hint(staging_dir: Path | str | None = None) -> str:
    """How a user supplies the Gibbs file by hand; quoted in every error."""
    where = (
        str(Path(staging_dir) / GIBBS_FILENAME)
        if staging_dir is not None
        else f"<database dir>/staging/{GIBBS_FILENAME}"
    )
    return (
        f"The trading-cost build needs Hasbrouck's Gibbs estimates ({GIBBS_FILENAME}) "
        "for every tcosts_type. Supply it in any one of these ways:\n"
        f"  * download {GIBBS_URL}\n"
        f"    (or copy inputs/gibbs/{GIBBS_FILENAME} from a clone of the repository)\n"
        f"    to {where}\n"
        f"  * pin a file you built yourself: aa set-params --gibbs-path /path/to/{GIBBS_FILENAME}\n"
        f"Then resume with: {RESUME_COMMAND}\n"
        f"See {DOCS_PAGE} for what each tcosts_type needs."
    )


def source_tree_gibbs() -> Path | None:
    """``inputs/gibbs/crspgibbs.csv`` when running from a source checkout, else None."""
    # src/assayinganomalies/ingest/gibbs.py -> parents[3] is the checkout root.
    # In a wheel install parents[3] is the environment's lib directory, which
    # has neither file.
    root = Path(__file__).resolve().parents[3]
    if not (root / "pyproject.toml").is_file():
        return None
    path = root / SOURCE_TREE_RELPATH
    return path if path.is_file() else None


def _glob_first(directory: Path, pattern: str) -> Path | None:
    """The first ``pattern`` match anywhere under ``directory``, in sorted order."""
    if not directory.is_dir():
        return None
    matches = sorted(glob.glob(str(directory / "**" / pattern), recursive=True))
    return Path(matches[0]) if matches else None


def find_local_gibbs(
    config: object,
    staging_dir: Path | str,
    db_dir: Path | str,
    *,
    cwd: Path | str | None = None,
) -> GibbsFile | None:
    """
    Steps 1-5 of :func:`resolve_gibbs_file`: a local Gibbs file, or None.

    Raises ``FileNotFoundError`` if ``config.gibbs_path`` names a missing file:
    an explicit pin that does not resolve is a mistake to report, not a reason
    to fall back to some other file.
    """
    pinned = getattr(config, "gibbs_path", None)
    if pinned:
        path = Path(pinned).expanduser()
        if not path.is_file():
            raise FileNotFoundError(
                f"gibbs_path not found: {path}\n{gibbs_manual_hint(staging_dir)}"
            )
        return GibbsFile(path, "gibbs_path")

    for directory, origin in ((Path(staging_dir), "staging"), (Path(db_dir), "database dir")):
        hit = _glob_first(directory, GIBBS_PATTERN)
        if hit is not None:
            return GibbsFile(hit, origin)

    shipped = source_tree_gibbs()
    if shipped is not None:
        return GibbsFile(shipped, "source tree")

    hit = _glob_first(Path(cwd) if cwd is not None else Path("."), GIBBS_PATTERN)
    if hit is not None:
        return GibbsFile(hit, "working dir")
    return None


def download_gibbs(
    dest_dir: Path | str,
    *,
    session: requests.Session | None = None,
    url: str | None = None,
    sha256: str | None = None,
) -> Path:
    """
    Download the Gibbs file into ``dest_dir`` and return its path.

    Streams to ``crspgibbs.csv.part`` while hashing, and renames it only when
    the SHA-256 matches ``sha256`` (default: :data:`GIBBS_SHA256`, for
    :data:`GIBBS_URL`). On any failure the ``.part`` file is removed, so a
    later run never finds a partial or unverified file in staging.
    """
    url = url or GIBBS_URL
    sha256 = sha256 or GIBBS_SHA256
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / GIBBS_FILENAME
    part = dest.with_name(dest.name + ".part")
    sess = session or requests.Session()
    digest = hashlib.sha256()
    total = 0
    LOGGER.info("Downloading Gibbs estimates from %s", url)
    try:
        with sess.get(url, stream=True, timeout=_TIMEOUT) as resp:
            if resp.status_code != 200:
                raise GibbsDownloadError(f"HTTP {resp.status_code} from {url}")
            with part.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=_CHUNK):
                    if chunk:
                        fh.write(chunk)
                        digest.update(chunk)
                        total += len(chunk)
    except requests.RequestException as exc:
        part.unlink(missing_ok=True)
        raise GibbsDownloadError(f"{type(exc).__name__}: {exc}") from exc
    except BaseException:
        part.unlink(missing_ok=True)
        raise

    got = digest.hexdigest()
    if got != sha256:
        part.unlink(missing_ok=True)
        raise GibbsChecksumError(
            f"SHA-256 mismatch for {url}: expected {sha256}, got {got} "
            f"({total:,} bytes). The file was not saved."
        )
    part.replace(dest)
    LOGGER.info("Downloaded Gibbs estimates: %.1f MB -> %s", total / (1024 * 1024), dest)
    return dest


def resolve_gibbs_file(
    config: object,
    staging_dir: Path | str,
    db_dir: Path | str,
    *,
    download: bool = True,
    session: requests.Session | None = None,
    cwd: Path | str | None = None,
) -> GibbsFile:
    """
    Find the Gibbs file, downloading it into staging if no local copy exists.

    See the module docstring for the order. ``download=False`` skips step 6.
    Raises :class:`~assayinganomalies.provenance.MissingInputError` when
    nothing resolves, with the manual paths in the message.
    """
    found = find_local_gibbs(config, staging_dir, db_dir, cwd=cwd)
    if found is not None:
        return found
    if not download:
        raise MissingInputError(
            f"No {GIBBS_FILENAME} found and downloading is off.\n"
            f"{gibbs_manual_hint(staging_dir)}"
        )
    try:
        path = download_gibbs(staging_dir, session=session)
    except GibbsDownloadError as exc:
        raise MissingInputError(
            f"No {GIBBS_FILENAME} found locally, and the download failed: {exc}\n"
            f"{gibbs_manual_hint(staging_dir)}"
        ) from exc
    return GibbsFile(path, "download")


__all__ = [
    "GIBBS_DATA_TAG",
    "GIBBS_FILENAME",
    "GIBBS_PATTERN",
    "GIBBS_SHA256",
    "GIBBS_URL",
    "GibbsChecksumError",
    "GibbsDownloadError",
    "GibbsFile",
    "download_gibbs",
    "find_local_gibbs",
    "gibbs_manual_hint",
    "resolve_gibbs_file",
    "source_tree_gibbs",
]
