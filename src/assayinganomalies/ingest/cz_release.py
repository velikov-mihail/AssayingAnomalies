"""
Chen-Zimmerman release lookup and Hugging Face downloads.

Chen and Zimmermann publish every Open Source Asset Pricing release on the
Hugging Face dataset ``OpenSourceAP/CrossSection``, one branch per release
(Google Drive, the earlier host, could not handle the download volume). This
module maps a release label to its branch, finds the newest release when none
is configured, and downloads the two files the toolkit reads:

* ``Firm Level Characteristics/signed_predictors_dl_wide.parquet`` (the
  signal panel, ~1.9 GB in 2026.10), and
* ``SignalDoc.csv`` (the signal documentation, at the branch's top level).

:func:`resolve_release` turns a release into a branch and the commit that
branch points to, and both files are downloaded from that commit, so a signal
panel and its SignalDoc never come from two states of the branch. The tree API
gives each file's size and checksum (the sha256 of a Git LFS file, the git
blob sha1 of a plain one); every download is checked against them before it
is renamed into place (:func:`verify_file`).

The dataset is public, so no token is needed. ``huggingface.co`` answers a
large file's request with a redirect to its CDN (``*.hf.co``), so both hosts
must be reachable. :func:`download_file` streams the file to ``<dest>.part``:
a dropped connection, a timeout, HTTP 429/5xx or a body short of its
``Content-Length`` is retried up to five times with exponential backoff, each
retry resuming the ``.part`` with an HTTP ``Range`` request. A missing file is
never retried. Progress is logged about every 256 MB.
"""

from __future__ import annotations

import hashlib
import logging
import random
import re
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import NamedTuple
from urllib.parse import quote

import requests

LOGGER = logging.getLogger("assayinganomalies.ingest.cz_release")

# Release label -> Hugging Face branch, oldest first. An explicitly configured
# ``cz_release_version`` must be one of these; with none configured, the
# newest release on Hugging Face is used (see :func:`resolve_release`). The
# branch names are those in openassetpricing 0.1.0's ``urls.py``.
CZ_RELEASES: dict[str, str] = {
    "2022.03": "2022.03",
    "2022.04": "2022.04",
    "2023.08": "2023.08",
    "2024.08": "2024.08",
    "2024.10": "2024.10",
    "2025.10": "2025.10",
    "2026.10": "Data-Release-2026.10",
}
# The newest release this package knows; the default when Hugging Face cannot
# be asked which release is the newest.
NEWEST_RELEASE = list(CZ_RELEASES)[-1]

# The oldest release with the files and layout this module reads; older
# branches (2020.05 to 2021.04) are never picked as the default.
OLDEST_RELEASE = "2022.03"

# A bare year names the release openassetpricing's OpenAP(<year>) reads.
_YEAR_ALIASES = {"2022": "2022.03"}

# Branches named like a release: "2025.10" or "Data-Release-2026.10". Others
# ("main", "upload-test", "Test-Data-2026.10") are never a release.
_RELEASE_BRANCH = re.compile(r"(?:Data-Release-)?(\d{4})\.(\d{2})")

# Where the two files sit on a release branch.
SIGNALS_PATH = "Firm Level Characteristics/signed_predictors_dl_wide.parquet"
SIGNAL_DOC_PATH = "SignalDoc.csv"

HF_REPO = "OpenSourceAP/CrossSection"
HF_API_URL = f"https://huggingface.co/api/datasets/{HF_REPO}"
HF_DATASET_URL = f"https://huggingface.co/datasets/{HF_REPO}"

_TIMEOUT = 60  # seconds, per request (connect and between bytes)

# download_file: seconds to wait before attempts 2, 3, 4 and 5 (each scaled by
# a random 0.8-1.2), and how often to log progress.
RETRY_DELAYS = (5, 15, 45, 120)
_PROGRESS_EVERY = 256 * 1024 * 1024
_HASH_BLOCK = 16 * 1024 * 1024
_sleep = time.sleep  # patched out in tests


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DownloadError(Exception):
    """A Chen-Zimmerman file could not be downloaded."""


class NotFoundError(DownloadError):
    """The branch or file does not exist on Hugging Face, or is not public."""


class ListingError(DownloadError):
    """The branch list or a branch's file list could not be read."""


class ChecksumError(DownloadError):
    """A downloaded file does not match the size or checksum Hugging Face lists."""


class RetryableDownloadError(DownloadError):
    """A transient failure (HTTP 429/5xx, a short body) worth another attempt."""


class _RestartDownloadError(RetryableDownloadError):
    """The ``.part`` cannot be resumed (HTTP 416, a mismatched range); start over."""


# ---------------------------------------------------------------------------
# Release labels
# ---------------------------------------------------------------------------


def parse_release_label(value: str | int | None) -> str | None:
    """
    Normalise a requested release to a ``CZ_RELEASES`` label (``"2025.10"``).

    ``None`` (or an empty string) stays ``None``: the newest release on
    Hugging Face, which only :func:`resolve_release` can name. Accepted
    spellings of a release are ``2025.10``, ``2025-10`` (the legacy
    ``2022-03`` label older databases and configs persist), ``2025_10`` and
    ``202510``, as text or integer, plus a bare year when only one release
    has it (``2023``, ``2025``; openassetpricing's ``OpenAP(2023)`` spelling)
    and ``2022`` for 2022.03, as openassetpricing reads it.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    known = ", ".join(CZ_RELEASES)
    m = re.fullmatch(r"(\d{4})[.\-_/]?(\d{2})", text)
    if m:
        label = f"{m.group(1)}.{m.group(2)}"
        if label in CZ_RELEASES:
            return label
        raise ValueError(f"Unknown Chen-Zimmerman release {value!r}; known releases: {known}")
    if re.fullmatch(r"\d{4}", text):
        if text in _YEAR_ALIASES:
            return _YEAR_ALIASES[text]
        matches = [lab for lab in CZ_RELEASES if lab.startswith(text + ".")]
        if len(matches) == 1:
            return matches[0]
        if matches:
            raise ValueError(
                f"Chen-Zimmerman release {value!r} is ambiguous ({', '.join(matches)}); "
                "give the month too, e.g. " + matches[-1]
            )
    raise ValueError(f"Unknown Chen-Zimmerman release {value!r}; known releases: {known}")


def releases_on_branches(branches: Iterable[str]) -> dict[str, str]:
    """
    Release label -> branch, for the branches named like a release.

    A branch counts when it is named ``YYYY.MM`` or ``Data-Release-YYYY.MM``
    and is :data:`OLDEST_RELEASE` or later. Should one release have two such
    branches, the one :data:`CZ_RELEASES` names wins, else the first by name.
    """
    found: dict[str, str] = {}
    for name in sorted(branches):
        m = _RELEASE_BRANCH.fullmatch(name)
        if m is None:
            continue
        label = f"{m.group(1)}.{m.group(2)}"
        if label < OLDEST_RELEASE:
            continue
        if label not in found or name == CZ_RELEASES.get(label):
            found[label] = name
    return found


def branch_url(branch: str | None = None) -> str:
    """The web page listing a branch's files (the dataset's front page for None)."""
    if branch is None:
        return HF_DATASET_URL
    return f"{HF_DATASET_URL}/tree/{quote(branch, safe='')}"


def file_url(revision: str, path: str) -> str:
    """The download URL of ``path`` at a branch or commit."""
    return f"{HF_DATASET_URL}/resolve/{quote(revision, safe='')}/{quote(path)}"


# ---------------------------------------------------------------------------
# Branches and file lists
# ---------------------------------------------------------------------------


def new_session() -> requests.Session:
    """A ``requests`` session for the Hugging Face API and downloads."""
    return requests.Session()


def _json(resp: requests.Response, what: str):
    try:
        return resp.json()
    except ValueError as exc:
        raise ListingError(f"{what}: Hugging Face answered with something not JSON") from exc


def list_branches(session: requests.Session | None = None) -> dict[str, str]:
    """Every branch of the dataset and the commit it points to: ``{name: sha}``."""
    sess = session or new_session()
    resp = sess.get(f"{HF_API_URL}/refs", timeout=_TIMEOUT)
    if resp.status_code >= 400:
        raise ListingError(f"Hugging Face branch list: HTTP {resp.status_code}")
    try:
        return {b["name"]: b["targetCommit"] for b in _json(resp, "branch list")["branches"]}
    except (KeyError, TypeError) as exc:
        raise ListingError(f"Hugging Face branch list has an unexpected shape ({exc!r})") from exc


class CZRelease(NamedTuple):
    """One release on Hugging Face: its label, branch and (once known) commit."""

    label: str
    branch: str
    commit: str | None  # None when the branch list could not be read
    source: str  # "configured", "newest on Hugging Face" or "newest in the package"


def resolve_release(
    release: str | int | None = None, *, session: requests.Session | None = None
) -> CZRelease:
    """
    Resolve a release to its branch and the commit the branch points to.

    An explicit release is looked up in :data:`CZ_RELEASES` (``ValueError``
    for an unknown label) and its branch must exist on Hugging Face
    (:class:`NotFoundError`); a branch list that cannot be read raises.

    With ``None``, the newest branch named like a release (see
    :func:`releases_on_branches`) is used. If the branch list cannot be read
    or holds no release, :data:`NEWEST_RELEASE` is used with a warning; that
    never raises, so a build can still find the release's cache offline. The
    commit is then None until :func:`with_commit` looks it up.
    """
    label = parse_release_label(release)
    sess = session or new_session()
    if label is not None:
        branch = CZ_RELEASES[label]
        branches = list_branches(sess)
        if branch not in branches:
            raise NotFoundError(
                f"Hugging Face has no branch {branch!r} for the CZ {label} release "
                f"(see {branch_url()})"
            )
        return CZRelease(label, branch, branches[branch], "configured")

    fallback = CZRelease(NEWEST_RELEASE, CZ_RELEASES[NEWEST_RELEASE], None, "newest in the package")
    try:
        branches = list_branches(sess)
    except (DownloadError, requests.RequestException) as exc:
        LOGGER.warning(
            "Could not list the Hugging Face releases (%s); using %s, the newest "
            "release this package knows",
            exc,
            NEWEST_RELEASE,
        )
        return fallback
    found = releases_on_branches(branches)
    if not found:
        LOGGER.warning(
            "No Hugging Face branch is named like a release; using %s, the newest "
            "release this package knows",
            NEWEST_RELEASE,
        )
        return fallback._replace(commit=branches.get(fallback.branch))
    label = max(found)
    branch = found[label]
    if label not in CZ_RELEASES:
        LOGGER.info(
            "The newest CZ release on Hugging Face, %s, is newer than this package "
            "knows (newest known: %s); using it",
            label,
            NEWEST_RELEASE,
        )
    return CZRelease(label, branch, branches[branch], "newest on Hugging Face")


def with_commit(release: CZRelease, session: requests.Session | None = None) -> CZRelease:
    """``release`` with its commit filled in (one branch-list request if missing)."""
    if release.commit is not None:
        return release
    branches = list_branches(session)
    if release.branch not in branches:
        raise NotFoundError(
            f"Hugging Face has no branch {release.branch!r} for the CZ {release.label} release"
        )
    return release._replace(commit=branches[release.branch])


class RemoteFile(NamedTuple):
    """One file on a release branch, with what the tree API says about it."""

    path: str
    size: int
    sha256: str | None  # a Git LFS file's content hash; None for a plain git file
    git_oid: str  # the git blob sha1 (of the LFS pointer, for an LFS file)


def list_release_files(
    release: CZRelease, session: requests.Session | None = None
) -> dict[str, RemoteFile]:
    """
    Every file at ``release``'s commit, by path, from the (paged) tree API.

    Uses the branch name when the commit is not known.
    """
    sess = session or new_session()
    revision = release.commit or release.branch
    url: str | None = f"{HF_API_URL}/tree/{quote(revision, safe='')}?recursive=true"
    files: dict[str, RemoteFile] = {}
    while url:
        resp = sess.get(url, timeout=_TIMEOUT)
        if resp.status_code == 404:
            raise NotFoundError(
                f"Hugging Face has no revision {revision!r} for the CZ {release.label} release"
            )
        if resp.status_code >= 400:
            raise ListingError(
                f"Hugging Face file list of {release.branch}: HTTP {resp.status_code}"
            )
        try:
            for entry in _json(resp, f"file list of {release.branch}"):
                if entry.get("type") != "file":
                    continue
                lfs = entry.get("lfs") or {}
                files[entry["path"]] = RemoteFile(
                    entry["path"], int(entry["size"]), lfs.get("oid"), entry["oid"]
                )
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise ListingError(
                f"Hugging Face file list of {release.branch} has an unexpected shape ({exc!r})"
            ) from exc
        url = resp.links.get("next", {}).get("url")
    return files


def release_file(files: dict[str, RemoteFile], path: str, release: CZRelease) -> RemoteFile:
    """``files[path]``, or :class:`NotFoundError` naming the branch and commit."""
    try:
        return files[path]
    except KeyError:
        raise NotFoundError(
            f"{path!r} is not on the Hugging Face branch {release.branch} "
            f"(commit {release.commit or 'unknown'})"
        ) from None


# ---------------------------------------------------------------------------
# Checksums
# ---------------------------------------------------------------------------


def verify_file(path: Path, remote: RemoteFile, what: str) -> None:
    """
    Check ``path`` against ``remote``'s size and checksum; raise :class:`ChecksumError`.

    A Git LFS file is checked against its sha256; a plain git file (such as
    ``SignalDoc.csv``) against its git blob sha1, the sha1 of
    ``b"blob <size>\\0"`` followed by the bytes.
    """
    size = Path(path).stat().st_size
    if size != remote.size:
        raise ChecksumError(
            f"{what}: {size:,} bytes downloaded, but Hugging Face lists {remote.size:,}"
        )
    if remote.sha256 is not None:
        digest, expected, kind = hashlib.sha256(), remote.sha256, "sha256"
    else:
        digest, expected, kind = hashlib.sha1(), remote.git_oid, "git blob sha1"
        digest.update(b"blob %d\0" % size)
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(_HASH_BLOCK), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        raise ChecksumError(
            f"{what}: the {kind} of the download ({digest.hexdigest()}) is not the "
            f"one Hugging Face lists ({expected})"
        )


# ---------------------------------------------------------------------------
# Downloads
# ---------------------------------------------------------------------------


def _check_response(resp: requests.Response, what: str) -> None:
    """
    Raise for a response that does not carry the file.

    :class:`NotFoundError` for 404 and 401/403 (the dataset is public, so a
    refusal means the file is gone), :class:`RetryableDownloadError` for 429
    and 5xx, :class:`DownloadError` for any other error or an HTML page in
    place of the file (a captive portal or proxy). The body is not read, so a
    streaming file response is left untouched.
    """
    status = resp.status_code
    if status == 404:
        raise NotFoundError(f"{what}: Hugging Face says the file does not exist (HTTP 404)")
    if status in (401, 403):
        raise NotFoundError(
            f"{what}: Hugging Face refused access (HTTP {status}); the file is not public"
        )
    if status == 416:
        raise _RestartDownloadError(f"{what}: the server cannot resume (HTTP 416)")
    if status == 429 or status >= 500:
        raise RetryableDownloadError(f"{what}: the server returned HTTP {status}")
    if status >= 400:
        raise DownloadError(f"{what}: the server returned HTTP {status}")
    if "text/html" in resp.headers.get("Content-Type", "").lower():
        raise DownloadError(
            f"{what}: received a web page instead of the file (a proxy or "
            "captive portal may be in the way)"
        )


def open_download(
    url: str, what: str, session: requests.Session | None = None, *, start: int = 0
) -> requests.Response:
    """
    Open a streaming response that carries ``url``'s bytes.

    Redirects (``huggingface.co`` to its CDN) are followed. ``start`` > 0 asks
    for the bytes from that offset on (HTTP ``Range``); the server may still
    answer 200 with the whole file. The caller must close the response.
    """
    sess = session or new_session()
    headers = {"Range": f"bytes={start}-"} if start > 0 else None
    resp = sess.get(url, stream=True, timeout=_TIMEOUT, headers=headers)
    try:
        _check_response(resp, what)
    except Exception:
        resp.close()
        raise
    return resp


# Failures download_file retries; anything else is final.
_RETRYABLE = (
    requests.ConnectionError,
    requests.Timeout,
    requests.exceptions.ChunkedEncodingError,
    RetryableDownloadError,
)


def _int_header(resp: requests.Response, name: str) -> int | None:
    value = resp.headers.get(name)
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def _resume_offset(resp: requests.Response, have: int, what: str) -> tuple[int, int | None]:
    """
    Where ``resp``'s body starts in the file, and the file's full size if known.

    A 206 must start at ``have`` (the ``.part`` size); a 200 is the whole
    file, so the ``.part`` is started over. The size comes from
    ``Content-Range`` or ``Content-Length``, ignored when the body is
    content-encoded (its length then differs from the decoded bytes).
    """
    encoded = resp.headers.get("Content-Encoding", "identity").lower() not in ("", "identity")
    if resp.status_code == 206:
        m = re.fullmatch(
            r"bytes (\d+)-(\d+)/(\d+|\*)", resp.headers.get("Content-Range", "").strip()
        )
        if m is None or int(m.group(1)) != have:
            raise _RestartDownloadError(
                f"{what}: asked to resume at byte {have} but the server sent "
                f"Content-Range {resp.headers.get('Content-Range')!r}"
            )
        full = None if m.group(3) == "*" else int(m.group(3))
        return have, full
    if have:
        LOGGER.info("%s: the server ignored the resume request; starting over", what)
    length = None if encoded else _int_header(resp, "Content-Length")
    return 0, length


def _stream_to_part(
    resp: requests.Response, part: Path, offset: int, full: int | None, what: str, chunk_size: int
) -> int:
    """Write ``resp``'s body to ``part`` from ``offset``; return the size reached."""
    done = offset
    t0 = time.monotonic()
    next_report = offset + _PROGRESS_EVERY
    with part.open("ab" if offset else "wb") as fh:
        for chunk in resp.iter_content(chunk_size=chunk_size):
            if not chunk:
                continue
            fh.write(chunk)
            done += len(chunk)
            if done >= next_report:
                rate = (done - offset) / max(time.monotonic() - t0, 1e-6) / 1e6
                total = f" / {full / 1e6:,.0f}" if full else ""
                LOGGER.info(
                    "%s: %s%s MB downloaded (%.1f MB/s)", what, f"{done / 1e6:,.0f}", total, rate
                )
                next_report += _PROGRESS_EVERY
    if full is not None and done < full:
        raise RetryableDownloadError(
            f"{what}: the download stopped at {done:,} of {full:,} bytes"
        )
    if full is not None and done > full:
        part.unlink(missing_ok=True)
        raise DownloadError(f"{what}: received {done:,} bytes, more than the {full:,} announced")
    return done


def download_file(
    url: str,
    dest: Path,
    what: str,
    *,
    session: requests.Session | None = None,
    check: Callable[[Path], None] | None = None,
    chunk_size: int = 16 * 1024 * 1024,
    attempts: int = len(RETRY_DELAYS) + 1,
) -> int:
    """
    Stream ``url`` to ``dest`` and return its size in bytes.

    Writes ``dest`` + ``.part`` first and renames it once complete, so an
    interrupted download never leaves a file that looks complete. Transient
    failures are retried (``attempts`` in all, backing off per
    :data:`RETRY_DELAYS`), each retry resuming the ``.part`` where it stopped;
    after the last one the ``.part`` stays, so a later call resumes it too.
    ``check``, when given, is called on the complete ``.part`` before the
    rename and raises to reject it. The ``.part`` is deleted only when the
    server's answer is rejected outright (not found, a web page), the final
    size check fails or ``check`` rejects it.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    sess = session or new_session()
    for attempt in range(1, attempts + 1):
        have = part.stat().st_size if part.is_file() else 0
        resp = None
        try:
            if have:
                LOGGER.info("%s: resuming %s at %.1f MB", what, part, have / 1e6)
            resp = open_download(url, what, sess, start=have)
            offset, full = _resume_offset(resp, have, what)
            total = _stream_to_part(resp, part, offset, full, what, chunk_size)
            break
        except _RETRYABLE as exc:
            if isinstance(exc, _RestartDownloadError):
                part.unlink(missing_ok=True)
            if attempt == attempts:
                raise DownloadError(
                    f"{what}: gave up after {attempts} attempts ({exc}); the partial "
                    f"file {part} is kept, and the next download resumes it"
                ) from exc
            delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS)) - 1] * random.uniform(0.8, 1.2)
            LOGGER.warning(
                "%s: attempt %d of %d failed (%s); retrying in %.0fs",
                what,
                attempt,
                attempts,
                exc,
                delay,
            )
            _sleep(delay)
        except DownloadError:
            part.unlink(missing_ok=True)
            raise
        finally:
            if resp is not None:
                resp.close()
    if check is not None:
        try:
            check(part)
        except Exception:
            part.unlink(missing_ok=True)
            raise
    part.replace(dest)
    LOGGER.info("Downloaded %s: %.1f MB -> %s", what, total / (1024 * 1024), dest)
    return total


def download_release_file(
    release: CZRelease,
    remote: RemoteFile,
    dest: Path,
    what: str,
    *,
    session: requests.Session | None = None,
) -> int:
    """
    Download ``remote`` from ``release``'s commit to ``dest``, verified.

    The commit must be known (see :func:`with_commit`). The download is
    checked against the size and checksum the tree API lists before it is
    renamed to ``dest``; a mismatch raises :class:`ChecksumError` and leaves
    neither ``dest`` nor a ``.part``.
    """
    if release.commit is None:
        raise ValueError("download_release_file needs the release's commit")
    return download_file(
        file_url(release.commit, remote.path),
        dest,
        what,
        session=session,
        check=lambda part: verify_file(part, remote, what),
    )


__all__ = [
    "CZ_RELEASES",
    "CZRelease",
    "ChecksumError",
    "DownloadError",
    "ListingError",
    "NEWEST_RELEASE",
    "NotFoundError",
    "RETRY_DELAYS",
    "RemoteFile",
    "RetryableDownloadError",
    "SIGNALS_PATH",
    "SIGNAL_DOC_PATH",
    "branch_url",
    "download_file",
    "download_release_file",
    "list_branches",
    "list_release_files",
    "open_download",
    "parse_release_label",
    "release_file",
    "releases_on_branches",
    "resolve_release",
    "verify_file",
    "with_commit",
]
