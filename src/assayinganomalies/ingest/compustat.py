"""
Utilities for fetching COMPUSTAT data from WRDS.

Downloads annual (funda) and quarterly (fundq) fundamentals data.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from importlib import resources
import logging
from pathlib import Path
import re
import time

import numpy as np
import pandas as pd

from ..config import AssayConfig
from ..provenance import MissingInputError
from .wrds_client import WRDSClient

LOGGER = logging.getLogger("assayinganomalies.ingest.compustat")

# Core annual variables needed for derived calculations
# Based on MATLAB's "COMPUSTAT Variable Names.csv", with some differences.
# Note: MATLAB CSV uses some different names than WRDS (e.g., DIV -> dv)
# The packaged ingest/data/compustat_variables.csv is generated from these two
# lists and must stay equal to them.
ANNUAL_VARS = [
    # Identifiers
    "gvkey", "datadate", "fyear", "fyr",
    # Balance sheet
    "at", "lt", "seq", "ceq", "txditc", "txdb", "itcb",
    "pstkl", "pstkrv", "pstk", "mib", "act", "lct", "che", "invt",
    "rect", "ap", "dlc", "dltt", "ppegt", "ppent",
    # Income statement
    "revt", "sale", "cogs", "xsga", "xrd", "xad", "xint", "dp",
    "txt", "ib", "ni", "oibdp", "oiadp", "gp", "ebit", "ebitda", "pi",
    # Cash flow
    "oancf", "capx", "dvc", "prstkc", "prstkcc", "prstkpc",
    "wcapch", "chech", "fopt", "scstkc",
    # Other
    "emp", "sich",
    # For CFO calculation
    "xido", "txdc", "esubc", "sppiv", "fopo", "recch", "invch",
    "apalch", "txach", "aoloch",
    # Debt details
    "dd1", "dd2", "dd3", "dd4", "dd5", "np",
    # Other items
    "fca", "wcap", "txp", "xlr", "xssd", "xpp",
    "drc", "drlt", "xacc", "dvp", "bast", "dv",  # Note: MATLAB CSV says DIV but WRDS uses dv
]

# Core quarterly variables
QUARTERLY_VARS = [
    # Identifiers
    "gvkey", "datadate", "rdq", "fyearq", "fqtr",
    # Balance sheet
    "atq", "ltq", "seqq", "ceqq", "txditcq", "txdbq",
    "pstkq", "pstkrq", "pstknq", "mibq", "actq", "lctq", "cheq",
    "invtq", "rectq", "dlcq", "dlttq", "ppegtq", "ppentq", "wcapq",
    # Income statement
    "revtq", "saleq", "cogsq", "xsgaq", "xrdq", "xintq", "dpq",
    "ibq", "niq", "oibdpq", "oiadpq", "piq", "epspxq",
    # Adjustment factor
    "ajexq", "cshoq",
]

# Identifier columns every Compustat download carries: what links a row to
# CRSP and places it on the monthly calendar. ``fetch_compustat_columns``
# always selects them, whatever else is asked for.
ANNUAL_KEY_COLS = ("gvkey", "datadate", "fyear", "fyr")
QUARTERLY_KEY_COLS = ("gvkey", "datadate", "rdq", "fyearq", "fqtr")
_KEY_COLS = {"annual": ANNUAL_KEY_COLS, "quarterly": QUARTERLY_KEY_COLS}
_TABLES = {"annual": "funda", "quarterly": "fundq"}
_VARIABLE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


# AssayConfig.compustat_variables: the packaged list (default), MATLAB's file
# name (the default in earlier versions, still stored in older configs; it
# means the packaged list too, never the MATLAB file), a user CSV, or "All".
VARIABLES_FILE = "compustat_variables.csv"
LEGACY_VARIABLES_FILE = "COMPUSTAT Variable Names.csv"
ALL_VARIABLES = "All"
_VARIABLES_COLUMNS = {"annual": "Annual", "quarterly": "Quarterly"}


def packaged_variables_file() -> Path:
    """The variable list shipped with the package (``ingest/data/``)."""
    pkg = resources.files("assayinganomalies.ingest")
    return Path(str(pkg.joinpath("data").joinpath(VARIABLES_FILE)))


def _is_all(variables: list[str] | str | None) -> bool:
    """True for MATLAB's 'All': download every column (``select *``)."""
    return isinstance(variables, str) and variables.strip().lower() == ALL_VARIABLES.lower()


def resolve_variables_file(
    value: str,
    find_input: Callable[[str], Path | None],
) -> Path | None:
    """
    The CSV ``compustat_variables`` names, or None for ``'All'``.

    A bare file name is looked up with ``find_input`` (the pipeline's
    ``_find_input_file`` search), except the packaged name and MATLAB's old
    name, which always mean the packaged copy. A path with a directory part
    is used as given. A file that is not there raises
    :class:`MissingInputError`.
    """
    text = str(value).strip()
    if _is_all(text):
        return None
    if text in (VARIABLES_FILE, LEGACY_VARIABLES_FILE):
        return packaged_variables_file()
    hint = (
        "Set compustat_variables to a CSV with columns Annual,Quarterly "
        f"(aa set-params --compustat-variables PATH), to {VARIABLES_FILE!r} for "
        f"the packaged list, or to {ALL_VARIABLES!r} for every column."
    )
    if len(Path(text).parts) > 1 or text.startswith("~"):
        path = Path(text).expanduser()
        if not path.is_file():
            raise MissingInputError(f"Compustat variable list not found: {path}. {hint}")
        return path
    found = find_input(text)
    if found is None:
        raise MissingInputError(
            f"Compustat variable list {text!r} not found under the staging "
            "directory, the database directory, the project folder or the "
            f"current directory. {hint}"
        )
    return found


def read_variables_file(path: Path | str) -> dict[str, list[str]]:
    """
    ``{"annual": [...], "quarterly": [...]}`` from a variable-list CSV.

    Columns ``Annual`` and ``Quarterly``, as in MATLAB's
    ``COMPUSTAT Variable Names.csv``. Blank cells are dropped and names are
    trimmed and lower-cased (``getCOMPUSTATQuery.m``).
    """
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in _VARIABLES_COLUMNS.values() if c not in df.columns]
    if missing:
        raise ValueError(
            f"Compustat variable list {path} has no {', '.join(missing)} column; "
            f"expected columns Annual,Quarterly, found {list(df.columns)}"
        )
    return {
        freq: [v.strip().lower() for v in df[col] if v.strip()]
        for freq, col in _VARIABLES_COLUMNS.items()
    }


def _validate_columns(
    requested: set[str],
    available: set[str],
    table_name: str,
) -> set[str]:
    """Filter requested columns to only those available in the table."""
    missing = requested - available
    if missing:
        LOGGER.warning(
            "Columns not found in %s (will be skipped): %s",
            table_name, sorted(missing)
        )
    return requested & available


def _select_from(table: str, cols: str, config: AssayConfig) -> str:
    """SELECT ``cols`` from ``comp.<table>``: standard industrial records, sample window."""
    return f"""
    SELECT {cols}
    FROM comp.{table}
    WHERE indfmt = 'INDL'
      AND datafmt = 'STD'
      AND consol = 'C'
      AND popsrc = 'D'
      AND datadate BETWEEN '{config.sample_start}-01-01' AND '{config.sample_end}-12-31'
    """


def _build_annual_query(
    config: AssayConfig,
    variables: list[str] | str | None = None,
    available_cols: set[str] | None = None,
) -> str:
    """Build SQL query for COMPUSTAT annual data (``variables='All'``: every column)."""
    if _is_all(variables):
        return _select_from("funda", "*", config)
    if variables is None:
        variables = ANNUAL_VARS

    # Deduplicate and ensure lowercase
    vars_set = set(v.lower() for v in variables)
    # Always include identifiers
    vars_set.update(["gvkey", "datadate"])

    # Validate against available columns if provided
    if available_cols is not None:
        vars_set = _validate_columns(vars_set, available_cols, "comp.funda")

    vars_list = sorted(vars_set)
    return _select_from("funda", ", ".join(vars_list), config)


def _build_quarterly_query(
    config: AssayConfig,
    variables: list[str] | str | None = None,
    available_cols: set[str] | None = None,
) -> str:
    """Build SQL query for COMPUSTAT quarterly data (``variables='All'``: every column)."""
    if _is_all(variables):
        return _select_from("fundq", "*", config)
    if variables is None:
        variables = QUARTERLY_VARS

    # Deduplicate and ensure lowercase
    vars_set = set(v.lower() for v in variables)
    # Always include identifiers
    vars_set.update(["gvkey", "datadate", "rdq"])

    # Validate against available columns if provided
    if available_cols is not None:
        vars_set = _validate_columns(vars_set, available_cols, "comp.fundq")

    vars_list = sorted(vars_set)
    return _select_from("fundq", ", ".join(vars_list), config)


def _get_table_columns(conn, schema: str, table: str) -> set[str]:
    """Get the list of column names for a WRDS table."""
    sql = f"""
    SELECT column_name
    FROM information_schema.columns
    WHERE table_schema = '{schema}' AND table_name = '{table}'
    """
    result = conn.raw_sql(sql)
    return set(result["column_name"].str.lower())


def fetch_compustat_annual(
    config: AssayConfig,
    destination: Path,
    *,
    wrds_client: WRDSClient | None = None,
    variables: list[str] | str | None = None,
) -> Path:
    """
    Download COMPUSTAT annual (funda) data from WRDS into a Parquet file.

    Parameters
    ----------
    config : AssayConfig
        Configuration with sample window and WRDS credentials.
    destination : Path
        Output parquet file path.
    wrds_client : WRDSClient, optional
        Existing WRDS client to reuse.
    variables : list[str] or 'All', optional
        List of variables to download, or ``'All'`` for every column.
        Defaults to ANNUAL_VARS.

    Returns
    -------
    Path
        Path to the written parquet file.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    client = wrds_client or WRDSClient(config.wrds_username)

    LOGGER.info(
        "Fetching COMPUSTAT annual (comp.funda) from WRDS: sample=%s..%s -> %s",
        config.sample_start,
        config.sample_end,
        destination,
    )

    t0 = time.perf_counter()
    with client.connect() as conn:
        # Get available columns to validate against
        available_cols = _get_table_columns(conn, "comp", "funda")
        LOGGER.debug("Available columns in comp.funda: %d", len(available_cols))

        sql = _build_annual_query(config, variables, available_cols)
        LOGGER.debug("COMPUSTAT funda SQL: %s", sql.strip())

        df = conn.raw_sql(sql)
    elapsed = time.perf_counter() - t0

    LOGGER.info(
        "Fetched COMPUSTAT annual: rows=%d cols=%d in %.2fs",
        df.shape[0], df.shape[1], elapsed
    )

    df.to_parquet(destination, index=False)
    try:
        LOGGER.info(
            "Wrote COMPUSTAT annual parquet: %s bytes=%d",
            destination, destination.stat().st_size
        )
    except Exception:
        LOGGER.info("Wrote COMPUSTAT annual parquet: %s", destination)

    return destination


def fetch_compustat_quarterly(
    config: AssayConfig,
    destination: Path,
    *,
    wrds_client: WRDSClient | None = None,
    variables: list[str] | str | None = None,
) -> Path:
    """
    Download COMPUSTAT quarterly (fundq) data from WRDS into a Parquet file.

    Parameters
    ----------
    config : AssayConfig
        Configuration with sample window and WRDS credentials.
    destination : Path
        Output parquet file path.
    wrds_client : WRDSClient, optional
        Existing WRDS client to reuse.
    variables : list[str] or 'All', optional
        List of variables to download, or ``'All'`` for every column.
        Defaults to QUARTERLY_VARS.

    Returns
    -------
    Path
        Path to the written parquet file.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    client = wrds_client or WRDSClient(config.wrds_username)

    LOGGER.info(
        "Fetching COMPUSTAT quarterly (comp.fundq) from WRDS: sample=%s..%s -> %s",
        config.sample_start,
        config.sample_end,
        destination,
    )

    t0 = time.perf_counter()
    with client.connect() as conn:
        # Get available columns to validate against
        available_cols = _get_table_columns(conn, "comp", "fundq")
        LOGGER.debug("Available columns in comp.fundq: %d", len(available_cols))

        sql = _build_quarterly_query(config, variables, available_cols)
        LOGGER.debug("COMPUSTAT fundq SQL: %s", sql.strip())

        df = conn.raw_sql(sql)
    elapsed = time.perf_counter() - t0

    LOGGER.info(
        "Fetched COMPUSTAT quarterly: rows=%d cols=%d in %.2fs",
        df.shape[0], df.shape[1], elapsed
    )

    df.to_parquet(destination, index=False)
    try:
        LOGGER.info(
            "Wrote COMPUSTAT quarterly parquet: %s bytes=%d",
            destination, destination.stat().st_size
        )
    except Exception:
        LOGGER.info("Wrote COMPUSTAT quarterly parquet: %s", destination)

    return destination


def parse_variable_names(text: str | Sequence[str] | None) -> list[str]:
    """
    Compustat column names from ``"xrd,mib"``-style text (or a list of such).

    Names are split on commas and white space, lower-cased and de-duplicated
    in order. A name must look like a Compustat column (a letter, then
    letters, digits or underscores); anything else raises ``ValueError``.
    """
    if text is None:
        return []
    parts = [text] if isinstance(text, str) else list(text)
    names: list[str] = []
    for part in parts:
        for name in re.split(r"[,\s]+", str(part).strip().lower()):
            if not name:
                continue
            if not _VARIABLE_NAME.match(name):
                raise ValueError(
                    f"{name!r} is not a Compustat column name (expected a letter "
                    "followed by letters, digits or underscores, e.g. xrd)"
                )
            if name not in names:
                names.append(name)
    return names


def fetch_compustat_columns(
    config: AssayConfig,
    destination: Path,
    *,
    wrds_client: WRDSClient,
    freq: str,
    columns: Sequence[str],
) -> Path:
    """
    Download only ``columns`` (plus the identifiers) of comp.funda or comp.fundq.

    The rows are the ones the build's own fetch selects (standard industrial
    records in the sample window, ``_select_from``), so the columns line up
    with the build's extracts. The table's column list is checked first: a
    name WRDS does not have raises ``ValueError`` naming it, before any data
    are downloaded.

    Parameters
    ----------
    config : AssayConfig
        Configuration whose ``sample_start``/``sample_end`` (a year) bound the rows.
    destination : Path
        Output parquet file.
    wrds_client : WRDSClient
        The client to query through (its open session, when there is one).
    freq : {"annual", "quarterly"}
        comp.funda or comp.fundq.
    columns : sequence of str
        Column names, lower case (``parse_variable_names``).

    Returns
    -------
    Path
        ``destination``, holding the identifier columns (``ANNUAL_KEY_COLS``
        or ``QUARTERLY_KEY_COLS``) and ``columns``.
    """
    if freq not in _TABLES:
        raise ValueError(f"freq must be 'annual' or 'quarterly', got {freq!r}")
    table = _TABLES[freq]
    keys = _KEY_COLS[freq]
    wanted = [c.lower() for c in columns]
    destination.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    with wrds_client.connect() as conn:
        available = _get_table_columns(conn, "comp", table)
        unknown = [c for c in wanted if c not in available]
        if unknown:
            raise ValueError(
                f"comp.{table} has no column(s) {', '.join(unknown)}. Check the "
                f"names against the WRDS variable list for comp.{table}; nothing "
                "was downloaded."
            )
        select = list(keys) + [c for c in wanted if c not in keys]
        sql = _select_from(table, ", ".join(select), config)
        LOGGER.info(
            "Fetching comp.%s columns %s: sample=%s..%s -> %s",
            table, wanted, config.sample_start, config.sample_end, destination,
        )
        LOGGER.debug("COMPUSTAT %s SQL: %s", table, sql.strip())
        df = conn.raw_sql(sql)
    df.columns = [str(c).lower() for c in df.columns]
    df.to_parquet(destination, index=False)
    LOGGER.info(
        "Fetched comp.%s columns: rows=%d cols=%d in %.2fs",
        table, df.shape[0], df.shape[1], time.perf_counter() - t0,
    )
    return destination


def generate_placeholder_annual(config: AssayConfig) -> pd.DataFrame:
    """
    Create a deterministic placeholder for COMPUSTAT annual data.

    Used when WRDS credentials are not available (tests, CI).
    """
    rng = np.random.default_rng(42)
    # Columns added to the defaults later draw from their own stream, so the
    # older placeholder columns keep their values.
    rng_added = np.random.default_rng(142)

    # Create a small sample: 2 firms, 3 years
    years = list(range(config.sample_start, min(config.sample_start + 3, config.sample_end + 1)))
    gvkeys = ["001000", "001001"]

    rows = []
    for gvkey in gvkeys:
        for year in years:
            row = {
                "gvkey": gvkey,
                "datadate": pd.Timestamp(f"{year}-12-31"),
                "fyear": year,
                "fyr": 12,
                # Balance sheet
                "at": rng.uniform(100, 10000),
                "lt": rng.uniform(50, 5000),
                "seq": rng.uniform(50, 5000),
                "ceq": rng.uniform(40, 4000),
                "pstk": rng.uniform(0, 100),
                "txditc": rng.uniform(0, 50),
                # Income
                "revt": rng.uniform(100, 5000),
                "sale": rng.uniform(100, 5000),
                "cogs": rng.uniform(50, 3000),
                "gp": rng.uniform(20, 2000),
                "ib": rng.uniform(-100, 500),
                "ni": rng.uniform(-100, 500),
                # Cash flow
                "oancf": rng.uniform(-50, 300),
                "capx": rng.uniform(0, 200),
                # Other
                "sich": rng.choice([2000, 3500, 5000, 7000]),
            }
            row["mib"] = rng_added.uniform(0, 50)
            rows.append(row)

    return pd.DataFrame(rows)


def generate_placeholder_quarterly(config: AssayConfig) -> pd.DataFrame:
    """
    Create a deterministic placeholder for COMPUSTAT quarterly data.

    Used when WRDS credentials are not available (tests, CI).
    """
    rng = np.random.default_rng(43)
    # Columns added to the defaults later draw from their own stream, so the
    # older placeholder columns keep their values.
    rng_added = np.random.default_rng(143)

    # Create a small sample: 2 firms, 4 quarters
    gvkeys = ["001000", "001001"]
    quarters = [
        (config.sample_start, 3, 31),
        (config.sample_start, 6, 30),
        (config.sample_start, 9, 30),
        (config.sample_start, 12, 31),
    ]

    rows = []
    for gvkey in gvkeys:
        for year, month, day in quarters:
            datadate = pd.Timestamp(f"{year}-{month:02d}-{day:02d}")
            # RDQ is typically 1-2 months after quarter end
            rdq = datadate + pd.DateOffset(months=1, days=15)
            row = {
                "gvkey": gvkey,
                "datadate": datadate,
                "rdq": rdq,
                "fyearq": year,
                "fqtr": (month - 1) // 3 + 1,
                # Balance sheet
                "atq": rng.uniform(100, 10000),
                "ltq": rng.uniform(50, 5000),
                "seqq": rng.uniform(50, 5000),
                "ceqq": rng.uniform(40, 4000),
                # Income
                "revtq": rng.uniform(25, 1250),
                "saleq": rng.uniform(25, 1250),
                "cogsq": rng.uniform(12, 750),
                "ibq": rng.uniform(-25, 125),
                "epspxq": rng.uniform(-0.5, 2.0),
            }
            row["mibq"] = rng_added.uniform(0, 12)
            row["xrdq"] = rng_added.uniform(0, 60)
            rows.append(row)

    return pd.DataFrame(rows)


__all__ = [
    "ALL_VARIABLES",
    "ANNUAL_KEY_COLS",
    "ANNUAL_VARS",
    "QUARTERLY_KEY_COLS",
    "LEGACY_VARIABLES_FILE",
    "QUARTERLY_VARS",
    "VARIABLES_FILE",
    "packaged_variables_file",
    "read_variables_file",
    "resolve_variables_file",
    "fetch_compustat_annual",
    "fetch_compustat_quarterly",
    "fetch_compustat_columns",
    "parse_variable_names",
    "generate_placeholder_annual",
    "generate_placeholder_quarterly",
]
