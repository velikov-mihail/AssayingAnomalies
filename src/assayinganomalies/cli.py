"""
Command-line interface for the toolkit.
"""

from __future__ import annotations

import dataclasses
import json
import os
import typing
from pathlib import Path

import click

from .config import (
    CONFIG_PATH_ENV,
    LATEST_SAMPLE_END,
    SAMPLE_END_RESOLVED_KEY,
    VALID_CRSP_FORMATS,
    VALID_TCOSTS_TYPES,
    AssayConfig,
    PROJECT_DIR_ENV,
    DatabaseNotFoundError,
    ProjectDirError,
    SampleEndUnresolvedError,
    _default_database_path,
    _get_config_file_path,
    load_config,
    normalize_sample_end,
    read_metadata_value,
    require_database,
    resolve_project_dir,
    scratch_dir,
    set_params,
    set_project_dir,
)
from .compustat_extras import add_compustat_vars, persisted_extra_vars
from .data_access import AnnualLayoutError
from .ingest.cz_release import CZ_RELEASES, parse_release_label
from .pipeline import InsufficientMemoryError, persisted_cz_release, setup_database
from .provenance import DEMO_LABEL, ProvenanceError
from .run_manifest import build_manifest_path


# Returned by an option callback for "clear this setting", since the command
# drops options left at None (not given).
_CLEAR = object()


def _check_cz_release(ctx, param, value):
    """Validate --cz-release-version; 'latest' (or '') clears the pin."""
    if value is None:
        return None
    if value.strip().lower() in ("", "latest", "newest", "none"):
        return _CLEAR
    try:
        return parse_release_label(value)
    except ValueError as exc:
        raise click.BadParameter(str(exc)) from exc


def _check_sample_end(ctx, param, value):
    """Validate --sample-end: a year, or 'latest' for the last complete year on WRDS."""
    if value is None:
        return None
    try:
        return normalize_sample_end(value)
    except ValueError as exc:
        raise click.BadParameter(str(exc)) from exc


def _path_or_clear(ctx, param, value):
    """'' clears a path setting; anything else is stored as an absolute path."""
    if value is None:
        return None
    if not str(value).strip():
        return _CLEAR
    return str(Path(value).expanduser().resolve())


def _database_path(ctx, param, value):
    """Resolve --database-path; only a config JSON can remember it."""
    if value is None:
        return None
    if _get_config_file_path() is None:
        # Without AA_CONFIG_PATH the settings live inside the database, which
        # is always <project folder>/Data/aa.duckdb, so a path given here
        # could not be read back by the next command.
        raise click.BadParameter(
            "the database is always <project folder>/Data/aa.duckdb. To use "
            "a database elsewhere, choose its project folder (the folder that "
            "holds Data/aa.duckdb) with: aa set-params --project-dir <folder>. "
            f"(--database-path is only kept when {CONFIG_PATH_ENV} names a "
            "config JSON.)"
        )
    return Path(value).expanduser().resolve()


# --------------------------------------------------------------- set-params
#
# set-params has one option per AssayConfig field, and those options are
# generated from the dataclass rather than written out by hand. For a MATLAB
# reader: it is as if, instead of an inputParser with one addParameter line
# per Params field, you looped over fieldnames(Params) and added a parameter
# for each. Two Python facts make that work here:
#
# * dataclasses.fields(AssayConfig) lists the fields in order, and
#   typing.get_type_hints(AssayConfig) gives each one's declared type (the
#   annotation, e.g. ``int`` or ``str | None``), from which we pick the click
#   type.
# * ``@click.option(...)`` above a function is only shorthand for
#   ``f = click.option(...)(f)``: click.option returns a function that takes
#   the command function and hands it back with one more option attached. So
#   the decorators can be applied in a loop (_with_config_options below).
#
# A new AssayConfig field therefore gets a flag with no CLI change, and
# show-config names it from the same function (config_flag). What the
# annotation cannot say -- help text, the allowed choices, a validator -- is
# in the three tables that follow.

_FIELD_HELP: dict[str, str] = {
    "database_path": "Only with AA_CONFIG_PATH set: the database path to "
    "store in that config JSON. Otherwise the database is always <project "
    "folder>/Data/aa.duckdb; choose the folder with --project-dir.",
    "sample_start": "First year of the sample, e.g. 1963.",
    "sample_end": "Last year of the sample: a year such as 2024, or 'latest' "
    "(default) for the last complete calendar year on the WRDS tapes when "
    "setup-database runs; the SIZ tape ends at 2024.",
    "dom_com_eq": "Keep only domestic common equity (CRSP share codes 10 and "
    "11); --no-dom-com-eq keeps all share codes.",
    "compustat_variables": "Compustat variable list: a CSV with columns "
    "Annual,Quarterly (a path, or a file name found under staging, the "
    "database folder or the current folder), 'compustat_variables.csv' for "
    "the packaged list (default), or 'All' for every funda/fundq column.",
    "tcosts_type": "Trading-cost model: 'lf_combo' (default; Gibbs plus three "
    "low-frequency spreads), 'full' (adds the high-frequency TAQ/ISSM "
    "spreads) or 'gibbs' (Gibbs only). See the README, section \"Trading costs: "
    "what you need\".",
    "wrds_username": "WRDS user name. The password is never taken on the "
    "command line.",
    "cz_release_version": "Chen-Zimmerman release to download, e.g. 2026.10 "
    "(default: the newest on Hugging Face when the build runs; known: "
    f"{', '.join(CZ_RELEASES)}). 'latest' clears a pin.",
    "cz_signal_doc_path": "Local SignalDoc.csv to read instead of downloading "
    "the matching release's. '' clears it.",
    "cz_signals_path": "Local signed_predictors_dl_wide .parquet, .csv or .zip "
    "to read instead of downloading the CZ signal panel. '' clears it.",
    "gibbs_path": "Local crspgibbs.csv (Hasbrouck's Gibbs estimates) to use "
    "instead of the shipped or downloaded copy, e.g. one refreshed with the "
    "SAS code. '' clears it.",
    "protocol_n_jobs": "Process-pool size for the protocol's per-anomaly "
    "loops (default: cores-1; 1 = serial).",
    "memory_budget_gb": "RAM in GiB the protocol may use in all (its own "
    "process plus its workers); caps the worker count of each pool (default: "
    "75% of physical RAM or of a container's memory limit; 0 = no cap).",
    "crsp_format": "Which CRSP tape to build from: 'ciz' (Flat File Format "
    "2.0, the default, and the only tape updated past 2024) or 'siz' (legacy, "
    "frozen Jan 2025, required for MATLAB parity runs). Changing it on an "
    "existing database requires `setup-database --full-refresh`.",
}

_FIELD_CHOICES: dict[str, tuple[str, ...]] = {
    "crsp_format": VALID_CRSP_FORMATS,
    "tcosts_type": VALID_TCOSTS_TYPES,
}

_FIELD_CALLBACKS = {
    "sample_end": _check_sample_end,
    "cz_release_version": _check_cz_release,
    "database_path": _database_path,
}


def config_flag(name: str) -> str:
    """The set-params flag for config field ``name`` (sample_start -> --sample-start)."""
    return "--" + name.replace("_", "-")


def _base_type(hint):
    """``int | None`` -> int; a hint with several non-None types -> str."""
    args = [a for a in typing.get_args(hint) if a is not type(None)]
    if not args:
        return hint
    return args[0] if len(args) == 1 else str


def _config_option(fld: dataclasses.Field, hint):
    """One click option for one AssayConfig field, both spellings accepted."""
    name = fld.name
    dashed, underscored = config_flag(name), "--" + name
    kind = _base_type(hint)
    kw: dict = {"default": None, "help": _FIELD_HELP.get(name)}
    if kind is bool:
        # An on/off pair: --dom-com-eq / --no-dom-com-eq. default=None keeps
        # "not given" apart from "turned off".
        no_dashed = "--no-" + dashed[2:]
        no_underscored = "--no_" + name
        decls = [f"{dashed}/{no_dashed}"]
        if underscored != dashed:
            decls.append(f"{underscored}/{no_underscored}")
    else:
        decls = [dashed] if underscored == dashed else [dashed, underscored]
        if name in _FIELD_CHOICES:
            kw["type"] = click.Choice(_FIELD_CHOICES[name], case_sensitive=False)
        elif kind in (int, float):
            kw["type"] = kind
        elif kind is Path or name.endswith("_path"):
            kw["type"] = click.Path()
            kw["callback"] = _path_or_clear
    if name in _FIELD_CALLBACKS:
        kw["callback"] = _FIELD_CALLBACKS[name]
    # The trailing bare name tells click which keyword argument to fill.
    return click.option(*decls, name, **kw)


def _with_config_options(func):
    """Attach one option per AssayConfig field to the command ``func``."""
    hints = typing.get_type_hints(AssayConfig)
    # click lists options in the reverse of the order they are attached, so
    # attach in reverse to keep the dataclass order in --help.
    for fld in reversed(dataclasses.fields(AssayConfig)):
        func = _config_option(fld, hints[fld.name])(func)
    return func


def _database_source() -> tuple[Path, str]:
    """The configured database and, in words, where its location came from.

    Only resolves the path: the database is not opened or created.
    """
    cfg_file = _get_config_file_path()
    if cfg_file is not None:
        # A missing JSON is created on first load, with the default path.
        db = load_config().database_path if cfg_file.is_file() else _default_database_path()
        return Path(db), f"from {CONFIG_PATH_ENV}={cfg_file}"
    folder, source = resolve_project_dir()
    return folder / "Data" / "aa.duckdb", f"project folder: {folder}, from {source}"


def _echo_database() -> None:
    db, source = _database_source()
    click.echo(f"Using database: {db} ({source})", err=True)


class _Command(click.Command):
    """A command that first says, on stderr, which database it will use.

    Printed from ``invoke``, which runs after the options are parsed, so
    ``--help`` (which exits while parsing) prints nothing extra.
    ``set-params --project-dir`` prints it itself, once the new folder is
    saved.
    """

    def invoke(self, ctx):
        if ctx.params.get("project_dir") is None:
            _echo_database()
        return super().invoke(ctx)


class _Group(click.Group):
    command_class = _Command

    def invoke(self, ctx):
        # A missing project folder or database is a user error with its own
        # instructions, not a crash: print the message without a traceback.
        try:
            return super().invoke(ctx)
        except (ProjectDirError, DatabaseNotFoundError) as exc:
            raise click.ClickException(str(exc)) from exc


@click.group(cls=_Group)
@click.version_option(package_name="assayinganomalies", prog_name="aa")
def main():
    """Assaying Anomalies command-line interface."""


@main.command("set-params")
@click.option(
    "--project-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Project folder: holds Data/aa.duckdb (the database and these "
    "settings) and Scratch/Assay (outputs). Saved for every later command, "
    "from any folder; created if missing. AA_PROJECT_DIR overrides it for one "
    "terminal session.",
)
@_with_config_options
def set_params_cmd(project_dir: Path | None, **kwargs):
    """
    Change saved settings; only the options you pass are changed.

    Every setting has a flag; `aa show-config` lists them with their current
    values. Both spellings work: --sample-start and --sample_start.
    --project-dir is saved outside the database, and any other flags given
    with it go to the new project's database.
    """
    updates = {
        k: (None if v is _CLEAR else v) for k, v in kwargs.items() if v is not None
    }
    if project_dir is not None:
        project_dir = set_project_dir(project_dir)
        click.echo(f"Project folder saved: {project_dir}")
        if os.getenv(PROJECT_DIR_ENV):
            click.secho(
                f"Note: {PROJECT_DIR_ENV} is set in this terminal and overrides "
                "the saved folder until you unset it or open a new terminal.",
                fg="yellow",
                err=True,
            )
        else:
            _echo_database()
    elif _get_config_file_path() is None:
        folder, source = resolve_project_dir()
        if source == "current folder":
            click.secho(
                f"No project folder set; using the current folder {folder}. "
                "Run aa set-params --project-dir <folder> to fix one.",
                fg="yellow",
                err=True,
            )
    cfg = set_params(project_dir=project_dir, **updates)
    click.echo(f"Config saved (database: {cfg.database_path})")


@main.command("show-config")
@click.option(
    "--json", "as_json", is_flag=True, help="Print the settings as JSON instead."
)
def show_config_cmd(as_json: bool):
    """Print each setting, its value, and the set-params flag that changes it."""
    cfg = load_config()
    payload = cfg.to_dict()
    in_json = _get_config_file_path() is not None
    if not in_json:
        folder, source = resolve_project_dir()
    if as_json:
        if not in_json:
            payload["project_dir"] = str(folder)
        click.echo(json.dumps(payload, indent=2))
        return
    flags = [config_flag(f.name) for f in dataclasses.fields(AssayConfig)]
    if not in_json:
        flags.insert(0, "--project-dir")
    width = max(len(f) for f in flags)
    if not in_json:
        click.echo(f"{'--project-dir':<{width}}  {folder}  (from {source})")
    for fld in dataclasses.fields(AssayConfig):
        value = payload[fld.name]
        shown = "(not set)" if value is None else str(value)
        if fld.name == "sample_end" and value == LATEST_SAMPLE_END:
            resolved = read_metadata_value(cfg.database_path, SAMPLE_END_RESOLVED_KEY)
            if resolved is not None:
                shown += f"  (resolved to {resolved} by the last build)"
        click.echo(f"{config_flag(fld.name):<{width}}  {shown}")
    # What the zoo in the database was built from, as the C-Z stage recorded it
    # (cz_release_version above is only what the next build will fetch).
    record = persisted_cz_release(cfg.database_path)
    recorded = str(((record or {}).get("signals") or {}).get("release") or "")
    click.echo(f"\ncz release recorded in database: {recorded or 'not recorded'}")
    extras = persisted_extra_vars(cfg.database_path)
    if extras["annual"] or extras["quarterly"]:
        click.echo("\nCompustat columns added with aa add-compustat-vars (re-applied by setup-database):")
        for freq in ("annual", "quarterly"):
            click.echo(f"  {freq:<9}  {', '.join(extras[freq]) or '(none)'}")
    click.echo(
        "\nChange one with: aa set-params <flag> <value> "
        "(either spelling works: --sample-start or --sample_start)."
    )
    if not in_json:
        click.echo(
            "The database is always <project folder>/Data/aa.duckdb; "
            "change the folder with aa set-params --project-dir <folder>."
        )


@main.command("setup-database")
@click.option("--full-refresh", is_flag=True, help="Rebuild all tables from scratch.")
@click.option("--verbose", is_flag=True, help="Enable verbose setup logging.")
@click.option(
    "--demo",
    is_flag=True,
    help="Build from deterministic synthetic stand-ins wherever a real input "
    "is unavailable, instead of failing. The database is stamped as synthetic "
    "and production protocol runs refuse it. Never use for research.",
)
@click.option(
    "--start-from",
    type=str,
    default=None,
    help="Skip stages before this one (e.g. 'transform-crsp-daily'). "
    "Earlier stages must have already completed successfully. All WRDS "
    "downloads come first (stages 3-9), so starting at any later stage "
    "needs no WRDS credentials.",
)
@click.option(
    "--skip-memory-check",
    is_flag=True,
    help="Start even if this machine has less RAM than the sample is "
    "estimated to need (see the README's Memory table).",
)
def setup_database_cmd(
    full_refresh: bool,
    verbose: bool,
    start_from: str | None,
    demo: bool,
    skip_memory_check: bool,
):
    """
    Build the library database from CRSP, COMPUSTAT and the CZ zoo.

    Without --demo this needs WRDS credentials and network access; a missing
    credential or a failed download stops the run rather than substituting
    synthetic data. The exception is the Chen-Zimmerman zoo (stage 23): if it
    cannot be fetched, the rest of the database is still built, the run ends
    with a summary of what did not complete, and
    `aa setup-database --start-from fetch-cz-anomalies` fetches it later.

    With sample_end 'latest' (the default) the build asks WRDS, right after
    the login, for the last complete calendar year on the CRSP tape and
    Compustat, and builds through it; a run that fetches nothing (--start-from
    a later stage) reuses the year the last build recorded. The year is stored
    in the database (metadata.sample_end_resolved) and the run manifest; pin
    one with `aa set-params --sample-end <year>`.

    Writes a JSON run manifest beside the database (aa.duckdb ->
    aa.manifest.json): code version, tape, sample, input-file hashes, WRDS
    pull dates and package versions.
    """
    if demo:
        click.secho(
            f"DEMO MODE: {DEMO_LABEL}. This database is for trying the "
            "toolkit out, not for research.",
            fg="yellow",
            err=True,
        )
    try:
        path = setup_database(
            full_refresh=full_refresh,
            verbose=verbose,
            start_from=start_from,
            demo=demo,
            skip_memory_check=skip_memory_check,
        )
    except (ProvenanceError, InsufficientMemoryError, SampleEndUnresolvedError) as exc:
        raise click.ClickException(str(exc)) from exc
    suffix = f"  [{DEMO_LABEL}]" if demo else ""
    click.echo(f"Database ready at {path}{suffix}")
    manifest = build_manifest_path(path)
    if manifest.is_file():
        click.echo(f"Run manifest: {manifest}")


@main.command("add-compustat-vars")
@click.option(
    "--annual",
    default="",
    metavar="NAMES",
    help="comp.funda columns, comma-separated (e.g. xrd,mib).",
)
@click.option(
    "--quarterly",
    default="",
    metavar="NAMES",
    help="comp.fundq columns, comma-separated (e.g. xrdq).",
)
@click.option("--verbose", is_flag=True, help="Log at debug level (shows the SQL).")
def add_compustat_vars_cmd(annual: str, quarterly: str, verbose: bool):
    """
    Add Compustat columns to ccm_panel of an existing database.

    Downloads only the named columns from WRDS (comp.funda for --annual,
    comp.fundq for --quarterly; one login, one Duo push) and adds them to
    ccm_panel without rebuilding anything else. The database must already be
    built (aa setup-database).

    Names are kept as they are in Compustat: --annual xrd gives a column xrd.
    Annual columns are aligned like at: a fiscal-year filing is available at
    the end of June of the next calendar year, and its value is stored in
    that June only (aa.load(..., fill_annual=True) fills June to May).
    Quarterly columns are aligned like ibq: placed at the
    announcement (RDQ) month and forward-filled until two months past the last
    announcement.

    The names are remembered in the database, so a later setup-database (also
    with --full-refresh) fetches and adds them again; aa show-config lists
    them. A name already on ccm_panel, or one the build writes (at, be, ibq,
    ...), is refused; a name this command added before is downloaded again
    and replaced.

    Do not run it while setup-database or another command is writing the
    database.
    """
    try:
        report = add_compustat_vars(annual, quarterly, verbose=verbose)
    except (AnnualLayoutError, ProvenanceError, SampleEndUnresolvedError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    for name in report.columns:
        what = "replaced" if name in report.refreshed else "added"
        click.echo(
            f"{what} {name}: {report.non_missing.get(name, 0):,} of "
            f"{report.panel_rows:,} ccm_panel rows have a value"
        )
    click.echo(
        f"Sample through {report.sample_end}; done in {report.seconds:.0f}s. "
        "Load with aa.load([...])."
    )
    if report.manifest is not None:
        click.echo(f"Run manifest: {report.manifest}")


# The signal-metadata flags of run-protocol, as SignalInfo field names.
_SIGNAL_INFO_FLAGS = {
    "SignalAcronym": "--acronym",
    "SignalName": "--signal-name",
    "Authors": "--authors",
    "PaperTitle": "--paper-title",
    "email": "--email",
}


def _csv_signal_column(path: Path) -> str | None:
    """The one signal column of a ``permno,dates,<SIGNAL>`` CSV, or None."""
    import pandas as pd

    try:
        header = [str(c) for c in pd.read_csv(path, nrows=0).columns]
    except Exception:  # missing or unreadable: the protocol reports it
        return None
    rest = [c for c in header if c not in ("permno", "dates")]
    return rest[0] if len(rest) == 1 else None


def _cli_signal_info(signal_path: Path, given: dict[str, str | None]):
    """
    The report metadata for ``run-protocol``: the flags given, then defaults.

    The acronym is ``--acronym``, else the CSV's signal column, else ``MPE``.
    For the paper's example signal (acronym ``MPE``) every unset field keeps
    its default, as before these flags existed. For any other signal the
    signal name defaults to the acronym, and unset authors, paper title and
    email stay blank (with a warning) rather than putting the example's
    authors on someone else's report.
    """
    from .signal_io import SignalInfo, default_mpe_signal_info

    default = default_mpe_signal_info(file_link=signal_path)
    acronym = given.get("SignalAcronym") or _csv_signal_column(signal_path) or default.SignalAcronym
    fields = {name: given.get(name) for name in _SIGNAL_INFO_FLAGS}
    fields["SignalAcronym"] = acronym
    if acronym == default.SignalAcronym:
        for name in _SIGNAL_INFO_FLAGS:
            if fields[name] is None:
                fields[name] = getattr(default, name)
    else:
        if fields["SignalName"] is None:
            fields["SignalName"] = acronym
        # PaperTitle is stored but not printed, so only a missing
        # author list shows on the report.
        if fields["Authors"] is None:
            click.secho(
                f"Note: no {_SIGNAL_INFO_FLAGS['Authors']} given; the report for {acronym} "
                "leaves the author line blank.",
                fg="yellow",
                err=True,
            )
        for name in _SIGNAL_INFO_FLAGS:
            if fields[name] is None:
                fields[name] = ""
    return SignalInfo(**fields, fileLink=str(signal_path))


@main.command("run-protocol")
@click.option(
    "--signal",
    "signal_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Signal CSV (permno,dates,<ACRONYM>). Default: mpe.csv via signalInfo.fileLink "
    "or AssayingAnomalies-MATLAB/mpe.csv if present.",
)
@click.option(
    "--out-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Assay output root (default: Scratch/Assay in the project folder).",
)
@click.option(
    "--tex-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="TeX / PDF output dir (default: {out-dir}/tex).",
)
@click.option(
    "--acronym",
    default=None,
    help="Signal acronym: names the output files and labels the report "
    "(default: the CSV's signal column, else MPE).",
)
@click.option(
    "--signal-name",
    default=None,
    help="Signal name for the report title (default: the acronym; "
    "'Monetary Policy Exposure' for MPE).",
)
@click.option(
    "--authors",
    default=None,
    help="Authors for the report, separated by ' and ', e.g. 'Jane Doe and John Roe' "
    "(default: blank; the paper's authors for MPE).",
)
@click.option(
    "--paper-title",
    default=None,
    help="Title of the paper that introduces the signal, stored with the signal metadata; "
    "the report does not print it (default: blank; 'Assaying Anomalies' for MPE).",
)
@click.option("--email", default=None, help="Contact email stored with the signal metadata.")
@click.option("--max-anoms", type=int, default=None, help="Cap CZ zoo size (dev smoke only).")
@click.option(
    "--time-period",
    nargs=2,
    type=int,
    default=None,
    help="Sample window as two YYYYMM ints, e.g. --time-period 197501 202112.",
)
@click.option("--tcosts-type", default=None, help="Label stored in printResults.Text (default config).")
@click.option(
    "--no-tex",
    is_flag=True,
    help="Skip print_tex_file (still packs printResults unless --no-print-results).",
)
@click.option("--no-figures", is_flag=True, help="Write .tex without the eight PDF figures.")
@click.option(
    "--no-pdf",
    is_flag=True,
    help="Do not run latexmk on the written .tex after the protocol finishes.",
)
@click.option(
    "--no-print-results",
    is_flag=True,
    help="Skip make_res_to_print / TeX entirely (ResStruct pack only).",
)
@click.option("--no-save", is_flag=True, help="Do not write {acronym}_Results.pkl.")
@click.option(
    "--db-path",
    "--database-path",
    "db_path",
    type=click.Path(path_type=Path),
    default=None,
    help="DuckDB file to run on (default: the configured database). "
    "--database-path is the same option, spelled as in set-params.",
)
@click.option(
    "--allow-demo-data",
    is_flag=True,
    help="Run even when the database is stamped as synthetic demo data. "
    "Every output is labelled accordingly. Never use for research.",
)
@click.option("--quiet", is_flag=True, help="Less stage logging.")
@click.option(
    "--n-jobs",
    "--protocol-n-jobs",
    "n_jobs",
    type=int,
    default=None,
    help="Process-pool size for per-anomaly loops (default: config / cores-1). "
    "--protocol-n-jobs is the same option, spelled as in set-params.",
)
@click.option(
    "--convention",
    type=click.Choice(["capital", "dollar"]),
    default=None,
    help="Size of the two legs of a long/short strategy after a trade. 'dollar' "
    "(default): each leg goes back to $1. 'capital': both legs are set to the "
    "strategy's capital, 1 plus the long leg's gain minus the short leg's since "
    "the last trade. Gross returns are the same; trading costs and turnover differ.",
)
def run_protocol_cmd(
    signal_path: Path | None,
    out_dir: Path | None,
    tex_dir: Path | None,
    acronym: str | None,
    signal_name: str | None,
    authors: str | None,
    paper_title: str | None,
    email: str | None,
    max_anoms: int | None,
    time_period: tuple[int, int] | None,
    tcosts_type: str | None,
    no_tex: bool,
    no_figures: bool,
    no_pdf: bool,
    no_print_results: bool,
    no_save: bool,
    db_path: Path | None,
    allow_demo_data: bool,
    quiet: bool,
    n_jobs: int | None,
    convention: str | None,
):
    """
    Run the assay protocol (MATLAB test_signal / runTestSignal twin).

    The report is labelled with --acronym / --signal-name / --authors;
    --paper-title is stored with the signal metadata only. Without them the acronym is the CSV's signal column, and
    the paper's example signal (Monetary Policy Exposure, MPE, and mpe.csv
    when --signal is omitted) keeps its full default metadata.
    Full-library acceptance needs a real CZ zoo (n~157 after >=40% mcap
    filter), tcostsType=full, sample ~1975-2021, and multi-hour runtime. A
    database built with `setup-database --demo` is refused unless
    --allow-demo-data is given.

    After the protocol returns, the written .tex is compiled to PDF with
    latexmk as a separate post-step (skip with --no-pdf). Compilation is
    not part of the protocol: a missing or failing latexmk only logs a
    warning and leaves the .tex in place.

    Writes {ACRONYM}_manifest.json into --out-dir: code version, tape,
    sample and warm-up windows, settings, seeds, hashes of the signal file
    and database, and package versions.
    """
    from .analytics.protocol import test_signal

    # Fail before any work, and before DuckDB could create an empty file.
    require_database(db_path)
    if db_path is not None:
        click.echo(f"--db-path: running on {db_path} instead", err=True)
    repo_mpe = Path("AssayingAnomalies-MATLAB") / "mpe.csv"
    if signal_path is None:
        if repo_mpe.is_file():
            signal_path = repo_mpe.resolve()
        else:
            signal_path = Path("mpe.csv")
    info = _cli_signal_info(
        signal_path,
        {
            "SignalAcronym": acronym,
            "SignalName": signal_name,
            "Authors": authors,
            "PaperTitle": paper_title,
            "email": email,
        },
    )
    if out_dir is None:
        out_dir = scratch_dir()

    make_pr = not no_print_results
    print_tex = make_pr and not no_tex
    kwargs: dict = {
        "out_dir": out_dir,
        "save": not no_save,
        "make_print_results": make_pr,
        "print_tex": print_tex,
        "emit_figures": not no_figures,
        "verbose": not quiet,
        "allow_demo_data": allow_demo_data,
    }
    if tex_dir is not None:
        kwargs["tex_dir"] = tex_dir
    if max_anoms is not None:
        kwargs["max_anoms"] = max_anoms
    if time_period is not None:
        kwargs["time_period"] = (int(time_period[0]), int(time_period[1]))
    if tcosts_type is not None:
        kwargs["tcosts_type"] = tcosts_type
    if db_path is not None:
        kwargs["db_path"] = db_path
    if n_jobs is not None:
        kwargs["n_jobs"] = n_jobs
    if convention is not None:
        kwargs["convention"] = convention

    click.echo(
        f"Assay protocol: signal={signal_path} acronym={info.SignalAcronym} out_dir={out_dir}"
    )
    try:
        result = test_signal(signal_path, info, **kwargs)
    except ProvenanceError as exc:
        raise click.ClickException(str(exc)) from exc
    if result.summary.get("demo_data"):
        click.secho(f"*** {DEMO_LABEL} ***", fg="red", err=True)
    click.echo(json.dumps({k: v for k, v in result.summary.items() if k != "stage_log"}, indent=2, default=str))
    if result.path is not None:
        click.echo(f"Results pickle: {result.path}")
    if result.manifest_path is not None:
        click.echo(f"Run manifest: {result.manifest_path}")
    if result.tex_path is not None:
        click.echo(f"TeX: {result.tex_path}")
        if not no_pdf:
            # Post-step, outside the protocol: the .tex is the deliverable,
            # the PDF is a convenience. compile_pdf degrades to a warning.
            from .reporting.latex import compile_pdf

            pdf_path = compile_pdf(result.tex_path)
            if pdf_path is not None:
                click.echo(f"PDF: {pdf_path}")
            else:
                click.secho("PDF: not compiled (see warning above); .tex kept.", fg="yellow", err=True)
    click.echo("Done.")
