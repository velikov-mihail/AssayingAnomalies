"""
Run manifests: a JSON receipt written next to every database build and protocol run.

Why
---
A number in a results table is only reproducible if you can say what produced
it: which code, which CRSP tape, which sample, which input files, which random
seeds, which library versions. "Same code, current WRDS" is a weaker promise
than "same numerical result", and the manifest keeps the two apart.

``aa setup-database`` writes ``<database>.manifest.json`` beside the DuckDB
file (``Data/aa.duckdb`` -> ``Data/aa.manifest.json``); ``aa run-protocol``
writes ``<ACRONYM>_manifest.json`` beside ``<ACRONYM>_Results.pkl``. The field
list is in the manual (section "Run manifests").

How to read it, for a MATLAB user
---------------------------------
Think of the manifest as a MATLAB struct saved with ``jsonencode`` and read
back with ``jsondecode(fileread(path))``. It has four top-level parts that
answer different questions:

* ``scientific`` -- everything that determines the numbers: package version
  and git commit, tape, sample and warm-up windows, methodology settings, seeds,
  and the SHA-256 of every input file. Nothing in it is a clock reading.
* ``scientific_id`` -- the SHA-256 of ``scientific`` itself, written in a
  canonical form (sorted keys, no whitespace). Two runs with the same id used
  the same code, settings and input bytes. Rerunning tomorrow on the same
  files gives the same id; changing one input byte gives a different one. It
  plays the role of a checksum on the experiment design.
* ``data_vintage`` -- when the data were pulled (WRDS fetch dates, file
  modification times, the Chen-Zimmerman release asked for). These are dates,
  so they are kept *out* of the id: re-pulling identical bytes is the same
  experiment.
* ``environment`` / ``execution`` -- Python and package versions, platform,
  start and finish times, paths, and (for the protocol) the run's own
  ``summary`` dict. Useful for diagnosis, never part of the identity.

Two conventions run throughout:

* What is not known is written as ``null`` or ``"unknown"``, never guessed.
  An installed wheel has no git checkout, so ``git_sha`` is ``null``; a
  configured Chen-Zimmerman release of ``null`` means "latest" (the newest on
  Hugging Face when the build ran), and ``cz_release_resolved`` says which
  release that was. A file read from the release cache records its branch,
  but its commit only if this run looked the commit up.
* No credential is ever written. The WRDS username and password are not in
  the manifest, and the configuration is copied field by field from an
  allowlist (:data:`SCIENTIFIC_CONFIG_FIELDS`) rather than wholesale.

Design notes
------------
The manifest reuses what the pipeline already records instead of keeping a
second copy of the truth: the build's ``stage_history`` (also stored in the
database's ``metadata`` table and in the scoped-rebuild logs) supplies the
WRDS pull dates, and the protocol's ``ProtocolResult.summary`` supplies the
tape, factor source and stage outcomes.

Input files are hashed in 16 MiB blocks, so memory stays flat; a full build's
staging directory (~13 GB) and a protocol run's database file (~14 GB) each
take on the order of a minute. Inputs read outside ``staging/`` (Gibbs
estimates, HF spreads, CPI, the Davis-Fama-French book equity, a pinned CZ
signal document) are registered by the code that opens them through
:func:`note_input`. That call does nothing unless a build is recording, so the
transforms behave exactly as before when used on their own.

Writing a manifest never changes a number, and a failure to write one is
logged rather than raised: a five-hour build is not thrown away over its
receipt.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import subprocess
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

LOGGER = logging.getLogger(__name__)

# Bump when a field changes meaning or moves; readers can branch on it.
MANIFEST_VERSION = 1

BUILD_MANIFEST_SUFFIX = ".manifest.json"
PROTOCOL_MANIFEST_SUFFIX = "_manifest.json"

UNKNOWN = "unknown"

# Distribution names, as `pip` knows them (scikit-learn, not sklearn).
KEY_PACKAGES = (
    "numpy",
    "pandas",
    "scipy",
    "scikit-learn",
    "statsmodels",
    "duckdb",
)

# Config fields that change what a build computes. Everything else on
# AssayConfig is about where things live or how fast they run, and
# `wrds_username` is credential-adjacent: never copied.
SCIENTIFIC_CONFIG_FIELDS = (
    "crsp_format",
    "sample_start",
    "sample_end",
    "dom_com_eq",
    "tcosts_type",
    "compustat_variables",
    "cz_release_version",
    "cz_signal_doc_path",
    "cz_signals_path",
    "gibbs_path",
)

# 16 MiB blocks: a 14 GB file is ~900 reads, and memory stays flat.
_CHUNK = 16 * 1024 * 1024


def utc_now() -> str:
    """Current UTC time, ISO 8601, to the second."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Hashing input files
# ---------------------------------------------------------------------------


def sha256_file(path: str | Path) -> str:
    """SHA-256 of a file's bytes, read in blocks."""
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        while True:
            block = fh.read(_CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def file_identity(path: str | Path, role: str) -> dict[str, Any]:
    """
    The scientific identity of one input file: role, name, size and hash.

    The full path and modification time are *not* here -- a copy of the same
    bytes elsewhere is the same input -- see :func:`file_location`.
    """
    p = Path(path)
    record: dict[str, Any] = {"role": role, "name": p.name}
    if not p.is_file():
        record.update(bytes=None, sha256=None, note="file not found")
        return record
    record["bytes"] = p.stat().st_size
    try:
        record["sha256"] = sha256_file(p)
    except OSError as exc:  # pragma: no cover - locked or vanished file
        record.update(sha256=None, note=f"could not read: {exc}")
    return record


def file_location(path: str | Path) -> dict[str, Any]:
    """Where an input file was and when it was last written (not identity)."""
    p = Path(path)
    loc: dict[str, Any] = {"path": str(p)}
    if p.is_file():
        mtime = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)
        loc["modified_utc"] = mtime.isoformat(timespec="seconds")
    return loc


# ---------------------------------------------------------------------------
# Registering inputs read outside staging/
# ---------------------------------------------------------------------------

# A list while a build is recording, None otherwise. A ContextVar rather than
# a module global so two builds in one process (tests) cannot share a list.
_RECORDER: ContextVar[list[dict[str, str]] | None] = ContextVar(
    "aa_manifest_inputs", default=None
)


@contextmanager
def recording_inputs() -> Iterator[list[dict[str, str]]]:
    """Collect every :func:`note_input` call made inside the ``with`` block."""
    noted: list[dict[str, str]] = []
    token = _RECORDER.set(noted)
    try:
        yield noted
    finally:
        _RECORDER.reset(token)


def note_input(source: str | Path, role: str) -> None:
    """
    Register an input the current build read. A no-op when nothing records.

    ``source`` is a local path or a URL. URLs are listed but cannot be hashed
    after the fact, so their hash is reported as unknown.
    """
    noted = _RECORDER.get()
    if noted is None:
        return
    text = str(source)
    if "://" in text:
        noted.append({"role": role, "url": text})
    else:
        noted.append({"role": role, "path": str(Path(text).expanduser().resolve())})


def note_cz_release(
    what: str,
    release: str | None,
    *,
    origin: str | None = None,
    branch: str | None = None,
    commit: str | None = None,
) -> None:
    """
    Record which Chen-Zimmerman release a build read. A no-op when nothing records.

    ``what`` is ``"signals"`` or ``"signal_doc"``. ``release`` is the label
    (``"2025.10"``), or None when the file does not say (one the user placed or
    pinned); ``origin`` then names where it came from. ``branch`` and
    ``commit`` are the Hugging Face branch and commit it came from, when known.
    """
    noted = _RECORDER.get()
    if noted is None:
        return
    value = release if release is not None else f"unknown ({origin or 'local file'})"
    item = {"cz_release": what, "release": value}
    if branch is not None:
        item["branch"] = branch
        item["commit"] = commit if commit is not None else UNKNOWN
    noted.append(item)


def noted_cz_releases() -> dict[str, dict[str, str]]:
    """
    What the current build noted about its C-Z files, or {} when nothing records.

    ``{"signals": {"release", ...}, "signal_doc": {...}}``; ``branch`` and
    ``commit`` are present for a file that came from a Hugging Face release.
    The C-Z stage stores this in the database, so a protocol run can say which
    release its zoo is.
    """
    noted = _RECORDER.get() or []
    return {
        item["cz_release"]: {k: v for k, v in item.items() if k != "cz_release"}
        for item in noted
        if "cz_release" in item
    }


def _cz_releases_read(noted: Sequence[Mapping[str, str]]) -> dict[str, str]:
    """``{"signals": label, "signal_doc": label}`` from :func:`note_cz_release` calls."""
    return {item["cz_release"]: item["release"] for item in noted if "cz_release" in item}


def _cz_release_sources(noted: Sequence[Mapping[str, str]]) -> dict[str, dict[str, str]]:
    """``{"signals": {"release", "branch", "commit"}, ...}`` for files from a release."""
    return {
        item["cz_release"]: {k: item[k] for k in ("release", "branch", "commit")}
        for item in noted
        if "cz_release" in item and "branch" in item
    }


# ---------------------------------------------------------------------------
# Code and environment
# ---------------------------------------------------------------------------


def _run_git(args: Sequence[str], cwd: Path) -> str | None:
    """stdout of ``git <args>`` in ``cwd``, or None when git is absent or fails.

    Kept separate so tests can replace it with a fake repository state.
    """
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout


def git_state(where: str | Path | None = None) -> dict[str, Any]:
    """
    Commit and dirty flag of the checkout this package was imported from.

    ``git_dirty`` counts modified tracked files only; untracked scratch files
    (data, outputs) do not make a checkout dirty. Outside a git checkout
    (an installed wheel) both fields are None.
    """
    cwd = Path(where) if where is not None else Path(__file__).resolve().parent
    sha = _run_git(["rev-parse", "HEAD"], cwd)
    if not sha or not sha.strip():
        return {"git_sha": None, "git_dirty": None}
    status = _run_git(["status", "--porcelain", "--untracked-files=no"], cwd)
    dirty = None if status is None else bool(status.strip())
    return {"git_sha": sha.strip(), "git_dirty": dirty}


def _dist_version(name: str) -> str | None:
    from importlib import metadata

    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def code_identity() -> dict[str, Any]:
    """Package version plus git state: which code produced the numbers."""
    return {"package_version": _dist_version("assayinganomalies") or UNKNOWN, **git_state()}


def package_sha256(record_text: str) -> str | None:
    """Hash of the package's files as an installed distribution's ``RECORD`` lists them.

    The lines of ``RECORD`` that start with ``assayinganomalies/`` and contain
    ``,sha256=``, each cut to its first two comma-separated fields (path and
    hash, without the size), sorted, joined by a newline and hashed with
    SHA-256. The value is the same for a wheel file and for every
    installation of it, and differs when one packaged file differs. None when
    ``RECORD`` lists no such line, as for an editable install.

    The replication package of the paper pins this value and compares it with
    the one a protocol manifest records, so the definition must not change.
    """
    lines = sorted(
        ",".join(line.split(",")[:2])
        for line in record_text.splitlines()
        if line.startswith("assayinganomalies/") and ",sha256=" in line
    )
    if not lines:
        return None
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def installed_package_sha256() -> str | None:
    """:func:`package_sha256` of the installed ``assayinganomalies``; None if unknown."""
    from importlib import metadata

    try:
        record = metadata.distribution("assayinganomalies").read_text("RECORD")
    except (metadata.PackageNotFoundError, OSError):
        return None
    return package_sha256(record or "")


def protocol_code_identity() -> dict[str, Any]:
    """:func:`code_identity` plus the hash of the installed package's files.

    A wheel carries no git state, so version and commit cannot tell two
    wheels of one version apart; the hash can. It is recorded when the
    protocol runs, so a summary rewritten later can name the code of the
    estimation. A database manifest keeps :func:`code_identity`: the
    definition of a database's ``scientific_id`` is unchanged.
    """
    return {**code_identity(), "package_sha256": installed_package_sha256()}


def environment() -> dict[str, Any]:
    """Interpreter, platform and key package versions (None = not installed)."""
    return {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "byteorder": sys.byteorder,
        "packages": {name: _dist_version(name) for name in KEY_PACKAGES},
    }


# ---------------------------------------------------------------------------
# Assembling, identifying, writing, reading
# ---------------------------------------------------------------------------


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def scientific_id(scientific: Mapping[str, Any]) -> str:
    """SHA-256 of the canonical JSON of the ``scientific`` block."""
    return hashlib.sha256(_canonical(scientific).encode("utf-8")).hexdigest()


def make_manifest(
    kind: str,
    scientific: Mapping[str, Any],
    *,
    data_vintage: Mapping[str, Any],
    execution: Mapping[str, Any],
    env: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble a manifest; the id is computed here, from ``scientific`` alone."""
    # Round-trip through JSON first so the id is computed over exactly what
    # gets written (tuples become lists, paths become strings).
    sci = json.loads(_canonical(scientific))
    return {
        "manifest_version": MANIFEST_VERSION,
        "kind": kind,
        "scientific_id": scientific_id(sci),
        "scientific": sci,
        "data_vintage": dict(data_vintage),
        "environment": dict(env) if env is not None else environment(),
        "execution": dict(execution),
    }


def write_manifest(path: str | Path, manifest: Mapping[str, Any]) -> Path:
    """Write ``manifest`` as indented JSON, atomically (temp file + rename)."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, dest)
    return dest


def read_manifest(path: str | Path) -> dict[str, Any]:
    """Load a manifest written by :func:`write_manifest`."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_manifest(manifest: Mapping[str, Any]) -> bool:
    """True when ``scientific_id`` still matches the ``scientific`` block."""
    return manifest.get("scientific_id") == scientific_id(manifest.get("scientific", {}))


def build_manifest_path(db_path: str | Path) -> Path:
    """``Data/aa.duckdb`` -> ``Data/aa.manifest.json``."""
    p = Path(db_path)
    return p.with_name(p.stem + BUILD_MANIFEST_SUFFIX)


def protocol_manifest_path(out_dir: str | Path, acronym: str) -> Path:
    """``<out_dir>/<ACRONYM>_manifest.json``, beside ``<ACRONYM>_Results.pkl``."""
    return Path(out_dir) / f"{acronym}{PROTOCOL_MANIFEST_SUFFIX}"


# ---------------------------------------------------------------------------
# The two manifests
# ---------------------------------------------------------------------------


def wrds_pull_dates(*histories: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """
    Latest successful run of each ``fetch-*`` stage across ``histories``.

    Fetch stages always re-query WRDS (or re-check a download cache), so the
    time a fetch stage succeeded is the data's pull date. Later histories win.
    """
    pulls: dict[str, str] = {}
    for history in histories:
        for entry in history or ():
            name = str(entry.get("name", ""))
            if name.startswith("fetch-") and entry.get("status") == "succeeded":
                ts = str(entry.get("timestamp", ""))
                if ts and ts >= pulls.get(name, ""):
                    pulls[name] = ts
    return dict(sorted(pulls.items()))


def _collect_inputs(
    staging_files: Sequence[Path], noted: Sequence[Mapping[str, str]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Hash staging files plus noted inputs, de-duplicated by path.

    Returns the identity list (sorted, for a stable id) and a name -> location
    map for ``data_vintage``. A noted input inside staging keeps the role the
    reading code gave it rather than the generic "staging extract".
    """
    by_path: dict[str, tuple[Path, str]] = {}
    for f in staging_files:
        by_path[os.path.normcase(str(f.resolve()))] = (f, "staging extract")
    urls: list[dict[str, Any]] = []
    for item in noted:
        if "cz_release" in item:  # a release label, not a file
            continue
        if "url" in item:
            entry = {"role": item["role"], "url": item["url"], "sha256": None,
                     "note": "downloaded; bytes not retained"}
            if entry not in urls:
                urls.append(entry)
            continue
        p = Path(item["path"])
        by_path[os.path.normcase(str(p.resolve()))] = (p, item["role"])

    identities: list[dict[str, Any]] = []
    locations: dict[str, Any] = {}
    for p, role in by_path.values():
        identities.append(file_identity(p, role))
        locations[f"{role}: {p.name}"] = file_location(p)
    identities.sort(key=lambda r: (r["role"], r["name"]))
    identities.extend(sorted(urls, key=lambda r: (r["role"], r["url"])))
    return identities, dict(sorted(locations.items()))


def database_manifest(
    *,
    config: Any,
    db_path: str | Path,
    staging_dir: str | Path,
    crsp_format: str,
    demo: bool,
    stage_history: Sequence[Mapping[str, Any]],
    prior_history: Sequence[Mapping[str, Any]] = (),
    noted_inputs: Sequence[Mapping[str, str]] = (),
    started_at: str | None = None,
    full_refresh: bool = False,
    start_from: str | None = None,
    rebuild_id: str | None = None,
    sample_end: Any = None,
    compustat_extra_vars: Mapping[str, Sequence[str]] | None = None,
    command: str | None = None,
) -> dict[str, Any]:
    """
    The manifest for a database build (``setup-database`` or a scoped rebuild).

    Inputs are every file directly in ``staging_dir`` (the WRDS extracts and
    the CZ download cache, as they stood when the build finished) plus
    whatever the stages registered through :func:`note_input`.

    ``sample_end`` is the build's
    :class:`~assayinganomalies.ingest.sample_end.SampleEndResolution` (or its
    ``as_metadata()`` mapping). The identity always carries the resolved year,
    never ``"latest"``; what was requested and how it resolved go under
    ``data_vintage``.

    ``compustat_extra_vars`` are the columns ``aa add-compustat-vars`` added
    (``{"annual": [...], "quarterly": [...]}``); they go into
    ``settings["compustat_extra_vars"]`` only when there are some, so the id
    of a database without them is what it always was. ``command`` names the
    run in ``execution`` (default: ``rebuild`` or ``setup-database``).
    """
    cfg = config.to_dict() if hasattr(config, "to_dict") else dict(config)
    resolution: Mapping[str, Any] = {}
    if sample_end is not None:
        resolution = sample_end.as_metadata() if hasattr(sample_end, "as_metadata") else dict(sample_end)
    if resolution.get("sample_end_resolved") is not None:
        cfg["sample_end"] = int(resolution["sample_end_resolved"])
    settings = {k: cfg.get(k) for k in SCIENTIFIC_CONFIG_FIELDS}
    settings["crsp_format"] = crsp_format
    extras = {
        freq: list(names)
        for freq, names in (compustat_extra_vars or {}).items()
        if names
    }
    if extras:
        settings["compustat_extra_vars"] = extras

    staging = Path(staging_dir)
    staging_files = (
        sorted(p for p in staging.iterdir() if p.is_file()) if staging.is_dir() else []
    )
    inputs, locations = _collect_inputs(staging_files, noted_inputs)

    scientific = {
        "kind": "database",
        "code": code_identity(),
        "crsp_format": crsp_format,
        "sample": {"start_year": cfg.get("sample_start"), "end_year": cfg.get("sample_end")},
        # The build itself has no warm-up: every stage reads the full sample
        # window. Rolling estimators (betas, Gibbs) start where the data do.
        "warmup": None,
        "settings": settings,
        # No stage draws random numbers; recorded so the absence is explicit.
        "seeds": {},
        "demo_data": bool(demo),
        "inputs": inputs,
    }
    cz_release = cfg.get("cz_release_version")
    data_vintage = {
        "crsp_format": crsp_format,
        "cz_release_requested": cz_release
        if cz_release is not None
        else "latest (the newest release on Hugging Face when the build ran)",
        # What this run actually read, per file; absent when no CZ stage ran.
        "cz_release_resolved": _cz_releases_read(noted_inputs) or UNKNOWN,
        # The Hugging Face branch and commit of each file read from a release.
        "cz_release_source": _cz_release_sources(noted_inputs) or UNKNOWN,
        "sample_end_requested": resolution.get("sample_end_requested", cfg.get("sample_end")),
        "sample_end_resolved": cfg.get("sample_end"),
        "sample_end_source": resolution.get("sample_end_source", UNKNOWN),
        # The tapes' last months, when this build (or the one it reused the
        # year from) asked WRDS for them.
        "crsp_tape_max_date": resolution.get("crsp_tape_max_date") or UNKNOWN,
        "compustat_max_datadate": resolution.get("compustat_max_datadate") or UNKNOWN,
        "wrds_pulls": wrds_pull_dates(prior_history, stage_history) or UNKNOWN,
        "files": locations,
    }
    execution = {
        "command": command or ("rebuild" if rebuild_id else "setup-database"),
        "started_at": started_at,
        "finished_at": utc_now(),
        "database_path": str(db_path),
        "staging_dir": str(staging),
        "full_refresh": bool(full_refresh),
        "start_from": start_from,
        "rebuild_id": rebuild_id,
        "stage_history": list(stage_history),
    }
    return make_manifest("database", scientific, data_vintage=data_vintage, execution=execution)


# Summary keys that are configuration and so belong in the identity; the rest
# of ProtocolResult.summary is outcomes and timings, kept under `execution`.
# `time_period` is also configuration; it goes in as `sample`.
_PROTOCOL_SUMMARY_SCIENTIFIC = (
    "signal_acronym",
    "crsp_format",
    "cz_release",
    "demo_data",
    "stages",
    "max_anoms",
    "compute_gen_alpha",
    "factor_source",
)


def signal_content_sha256(signal: Any) -> str | None:
    """Hash of a resolved test-signal Series (index and values), or None."""
    import pandas as pd

    if not isinstance(signal, (pd.Series, pd.DataFrame)):
        return None
    hashed = pd.util.hash_pandas_object(signal, index=True)
    return hashlib.sha256(hashed.to_numpy().tobytes()).hexdigest()


def protocol_manifest(
    *,
    summary: Mapping[str, Any],
    settings: Mapping[str, Any],
    seeds: Mapping[str, Any],
    warmup: Mapping[str, Any],
    signal_file: Mapping[str, Any] | None,
    signal_sha256: str | None,
    database_file: Mapping[str, Any] | None,
    db_path: str | Path | None,
    in_memory_inputs: Sequence[str] = (),
    outputs: Mapping[str, str | Path | None] | None = None,
    started_at: str | None = None,
) -> dict[str, Any]:
    """
    The manifest for one protocol run.

    ``summary`` is the run's ``ProtocolResult.summary``: its configuration keys
    go into the identity and the whole dict is kept under ``execution``.
    ``database_file`` is the hashed database record, or None when the run did
    not read a database (all panels passed in memory). Panels passed in
    memory are named in ``in_memory_inputs`` and are not hashed.
    """
    build = None
    if db_path is not None:
        bpath = build_manifest_path(db_path)
        if bpath.is_file():
            try:
                bm = read_manifest(bpath)
                build = {
                    "scientific_id": bm.get("scientific_id"),
                    "sample": bm.get("scientific", {}).get("sample"),
                    "settings": bm.get("scientific", {}).get("settings"),
                }
            except (OSError, ValueError):
                build = None

    scientific = {
        "kind": "protocol",
        "code": protocol_code_identity(),
        **{k: summary.get(k) for k in _PROTOCOL_SUMMARY_SCIENTIFIC},
        "sample": {"time_period": summary.get("time_period")},
        "warmup": dict(warmup),
        "settings": dict(settings),
        "seeds": dict(seeds),
        "signal": {"file": signal_file, "content_sha256": signal_sha256},
        "database": {
            "file": database_file,
            # The build's own identity, when its manifest sits next to it.
            "build": build if build is not None else UNKNOWN,
        },
        "in_memory_inputs": sorted(in_memory_inputs),
    }
    data_vintage = {
        "crsp_format": summary.get("crsp_format"),
        "factor_source": summary.get("factor_source"),
        "database": file_location(db_path) if db_path is not None else None,
        "database_build_manifest": str(build_manifest_path(db_path))
        if build is not None
        else UNKNOWN,
    }
    execution = {
        "command": "run-protocol",
        "started_at": started_at,
        "finished_at": utc_now(),
        "n_jobs": summary.get("n_jobs"),
        "outputs": {k: (str(v) if v is not None else None) for k, v in (outputs or {}).items()},
        "summary": {k: v for k, v in summary.items() if k != "stage_log"},
    }
    return make_manifest("protocol", scientific, data_vintage=data_vintage, execution=execution)


__all__ = [
    "BUILD_MANIFEST_SUFFIX",
    "KEY_PACKAGES",
    "MANIFEST_VERSION",
    "PROTOCOL_MANIFEST_SUFFIX",
    "SCIENTIFIC_CONFIG_FIELDS",
    "UNKNOWN",
    "build_manifest_path",
    "code_identity",
    "database_manifest",
    "environment",
    "file_identity",
    "file_location",
    "git_state",
    "make_manifest",
    "note_cz_release",
    "note_input",
    "package_sha256",
    "installed_package_sha256",
    "protocol_code_identity",
    "protocol_manifest",
    "protocol_manifest_path",
    "read_manifest",
    "recording_inputs",
    "scientific_id",
    "sha256_file",
    "signal_content_sha256",
    "utc_now",
    "verify_manifest",
    "wrds_pull_dates",
]
