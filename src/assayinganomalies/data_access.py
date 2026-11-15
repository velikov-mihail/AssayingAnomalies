"""
Data-access helpers for querying the local DuckDB database.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

import pandas as pd

from .config import load_config, require_database
from .db.reader import _normalize_field_expr, _yyyymm_to_date_literal, build_select_statement
from .session_cache import query_df


def _db_path(path: str | Path | None) -> Path:
    """The database to read: ``path``, else the configured one.

    Raises :class:`~assayinganomalies.config.DatabaseNotFoundError` when it is
    missing or empty, rather than letting DuckDB create an empty file there.
    """
    return require_database(path if path else load_config())


class AnnualLayoutError(RuntimeError):
    """The database stores annual Compustat columns filled June to May (an older build)."""


_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _stored_json(db_path: Path, table: str, key: str) -> Any:
    """``key`` of a key/value table, JSON-decoded; ``None`` when the table or key is absent."""
    try:
        rows = query_df(db_path, f"SELECT value FROM {table} WHERE key = '{key}'")
    except Exception:  # no such table
        return None
    if rows.empty or rows["value"].iloc[0] is None:
        return None
    raw = rows["value"].iloc[0]
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def annual_columns(path: str | Path | None = None) -> list[str]:
    """
    The annual Compustat columns of ``ccm_panel``: those stored in June only.

    ``ANNUAL_VALUE_COLS`` (``be``, ``bm``, ``at``, ``gp``, ...) plus the columns
    added with ``aa add-compustat-vars --annual``, which the database records.
    These are the columns ``aa.load(..., fill_annual=True)`` fills.
    """
    from .compustat_extras import EXTRA_VARS_KEY
    from .transforms.compustat import ANNUAL_VALUE_COLS

    stored = _stored_json(_db_path(path), "config", EXTRA_VARS_KEY)
    extras = (stored.get("annual") or []) if isinstance(stored, dict) else []
    return [*ANNUAL_VALUE_COLS, *(str(c) for c in extras if c not in ANNUAL_VALUE_COLS)]


def require_june_annual_layout(db_path: str | Path, what: str) -> None:
    """Raise :class:`AnnualLayoutError` unless ``db_path`` records June-only annual columns.

    The stage ``transform-compustat`` writes the record. A database built
    before annual columns were stored in June only has none; its annual
    columns are filled June to May, and reading them as June-only would make
    an annual signal trade every month without any sign of it.
    """
    from .transforms.compustat import ANNUAL_LAYOUT_JUNE, ANNUAL_LAYOUT_KEY

    if _stored_json(Path(db_path), "metadata", ANNUAL_LAYOUT_KEY) == ANNUAL_LAYOUT_JUNE:
        return
    raise annual_layout_error(db_path, what)


def annual_layout_error(db_path: str | Path, what: str) -> AnnualLayoutError:
    """The error for reading or extending annual columns of a database filled June to May."""
    return AnnualLayoutError(
        f"{what}: the database {db_path} was built by an older version of the "
        "toolkit, in which annual Compustat columns were filled June to May. "
        "This version stores them in the June they become available only, and "
        "reads them that way. Rebuild the Compustat part of the database:\n"
        "  aa setup-database --start-from transform-compustat\n"
        "(it reuses the downloaded extracts; no WRDS login). Columns added "
        "with `aa add-compustat-vars` are rebuilt by the same command."
    )


def _annual_fields(
    fields: Iterable[str] | Mapping[str, str], annual: set[str], provenance: set[str]
) -> tuple[list[str], list[str], bool]:
    """Sort the requested fields by what they have to do with annual columns.

    Returns ``(fill, in_expression, touches)``: the output columns that are a
    plain annual value column (to fill); the output columns whose SQL
    expression mentions an annual value column without being one; and whether
    any field reads an annual value or provenance column at all.
    """
    if isinstance(fields, Mapping):
        items = [(str(alias), _normalize_field_expr(str(expr))) for alias, expr in fields.items()]
    else:
        items = [(_normalize_field_expr(str(f)),) * 2 for f in fields]
    fill: list[str] = []
    in_expression: list[str] = []
    touches = False
    for out_name, expr in items:
        plain = expr.strip().strip('"')
        if plain in annual:
            fill.append(out_name)
            touches = True
            continue
        if plain in provenance or plain == "*":
            touches = True
            continue
        names = set(_IDENTIFIER.findall(expr))
        if names & annual:
            in_expression.append(out_name)
        if names & (annual | provenance):
            touches = True
    return fill, in_expression, touches


def _shift_yyyymm(yyyymm: int | str, months: int) -> int:
    year, month = divmod(int(yyyymm), 100)
    k = year * 12 + (month - 1) + months
    return (k // 12) * 100 + (k % 12) + 1


def load(
    fields: Iterable[str] | Mapping[str, str],
    *,
    path: str | Path | None = None,
    filters: Mapping[str, Any] | None = None,
    panel: bool = True,
    wide: bool = False,
    lag: Mapping[str, int] | None = None,
    universe: str | None = None,
    dates: tuple[int, int] | None = None,
    common_shares_only: bool = True,
    table: str | None = None,
    fill_annual: bool = False,
) -> pd.DataFrame:
    """
    Fetch a set of fields from the DuckDB database.

    Parameters
    ----------
    fields : Iterable[str] or Mapping[str, str]
        Column names to select, or a mapping of alias -> expression.
    common_shares_only : bool, default True
        If True, filter to US ordinary common shares (shrcd 10 or 11).
        Set to False to include all share types.
    fill_annual : bool, default False
        What the annual Compustat columns (``at``, ``be``, ``bm``, ``gp``, ...,
        and columns added with ``aa add-compustat-vars --annual``;
        :func:`annual_columns` lists them) look like.

        - ``False``: as stored. A value appears only in the June in which the
          record becomes available and is missing in the other eleven months.
          A signal built from such columns has values once a year, so a sort
          on it trades once a year.
        - ``True``: each annual column among ``fields`` is passed through
          :func:`aa.fill_months <assayinganomalies.fill_months>` with 11
          months, so the June value runs through the following May. A signal
          built from these has values every month and a sort on it trades
          every month.

        Only plain column names are filled (also under an alias, as in
        ``{"assets": "at"}``). An SQL expression is not: with
        ``fill_annual=True`` one that mentions an annual column raises
        ``ValueError``; load the columns and compute in pandas. The
        provenance columns (``comp_datadate``, ``comp_avail_date``,
        ``be_source``, ``be_avail_date``) are never filled. The fill runs
        before ``filters`` and reads the 11 months before ``dates``, so
        neither changes a filled value; it runs after ``common_shares_only``.
        Quarterly columns are stored filled and are not affected.

    Raises
    ------
    AnnualLayoutError
        When an annual column is requested from a database built before
        annual columns were stored in June only.
    """

    db_path = _db_path(path)

    fill_cols: list[str] = []
    is_ccm_panel = panel and (table is None or table == "ccm_panel")
    if is_ccm_panel:
        from .transforms.compustat import ANNUAL_PROVENANCE_COLS

        to_fill, in_expression, touches = _annual_fields(
            fields, set(annual_columns(db_path)), set(ANNUAL_PROVENANCE_COLS)
        )
        if touches:
            require_june_annual_layout(db_path, "aa.load of an annual Compustat column")
        if fill_annual:
            if in_expression:
                raise ValueError(
                    "fill_annual=True fills plain column names only, and "
                    f"{', '.join(in_expression)} "
                    f"{'is an SQL expression' if len(in_expression) == 1 else 'are SQL expressions'} "
                    "that read an annual Compustat column. Load the columns "
                    "themselves with fill_annual=True and compute in pandas, or "
                    "load with fill_annual=False and apply aa.fill_months to the result."
                )
            fill_cols = to_fill
    elif fill_annual:
        raise ValueError("fill_annual=True applies to the stock panel (ccm_panel) only")

    if not fill_cols:
        stmt = build_select_statement(
            fields,
            filters=filters,
            lag=lag,
            universe=universe,
            dates=dates,
            panel=panel,
            common_shares_only=common_shares_only,
            table=table,
        )
        df = query_df(db_path, stmt)
    else:
        df = _load_filled(
            db_path, fields, fill_cols,
            filters=filters, lag=lag, universe=universe, dates=dates,
            common_shares_only=common_shares_only, table=table,
        )

    if not panel:
        # Prefer date-indexed time-series when available.
        if "date" in df.columns:
            out = df.copy()
            out["date"] = pd.to_datetime(out["date"], errors="coerce")
            out = out.set_index("date").sort_index()
            return out
        return df.reset_index(drop=True)

    # Normalize panel index names for downstream code
    if isinstance(df.index, pd.MultiIndex):
        df.index = df.index.set_names(["date", "permno"])
    elif {"date", "permno"}.issubset(df.columns):
        df = df.set_index(["date", "permno"])
    else:
        # Fallback to a safe reset; callers can reindex if needed
        df = df.reset_index(drop=True)

    if wide and {"date", "permno"}.issubset(df.index.names):
        return df.reset_index().pivot(index="date", columns="permno")

    return df


def _load_filled(
    db_path: Path,
    fields: Iterable[str] | Mapping[str, str],
    fill_cols: list[str],
    *,
    filters: Mapping[str, Any] | None,
    lag: Mapping[str, int] | None,
    universe: str | None,
    dates: tuple[int, int] | None,
    common_shares_only: bool,
    table: str | None,
) -> pd.DataFrame:
    """The panel query of :func:`load` with ``fill_cols`` filled by ``fill_months``.

    The query leaves ``filters`` out and starts 11 months before ``dates``, so
    the fill sees every row of a stock that can hold the value in force; the
    filters and the window are applied afterwards.
    """
    from .analytics.sorts import fill_months
    from .transforms.compustat import ANNUAL_VALIDITY_MONTHS

    carry = ANNUAL_VALIDITY_MONTHS - 1
    if isinstance(fields, Mapping):
        query_fields: Any = dict(fields)
        out_names = [str(a) for a in fields]
    else:
        query_fields = list(fields)
        out_names = [_normalize_field_expr(str(f)) for f in query_fields]
    # The columns the filters test are read too, and dropped at the end unless
    # they were asked for: {column in the frame: column of the panel}.
    filter_cols: dict[str, str] = {}
    added: list[str] = []
    for i, key in enumerate(filters or {}):
        if isinstance(query_fields, dict):
            filter_cols[f"__filter_{i}"] = key
            query_fields[f"__filter_{i}"] = key
            added.append(f"__filter_{i}")
        else:
            filter_cols[key] = key
            if key not in out_names and key not in ("date", "permno"):
                query_fields.append(key)
                added.append(key)

    query_dates = (_shift_yyyymm(dates[0], -carry), dates[1]) if dates else None
    stmt = build_select_statement(
        query_fields,
        lag=lag,
        universe=universe,
        dates=query_dates,
        panel=True,
        common_shares_only=common_shares_only,
        table=table,
    )
    df = query_df(db_path, stmt)
    df["date"] = pd.to_datetime(df["date"])
    if len(df):
        keyed = df[fill_cols].set_axis(pd.MultiIndex.from_frame(df[["date", "permno"]]), axis=0)
        df[fill_cols] = fill_months(keyed, carry).to_numpy()

    keep = pd.Series(True, index=df.index)
    for name, value in zip(filter_cols, (filters or {}).values()):
        if isinstance(value, (list, tuple, set)):
            keep &= df[name].isin(list(value))
        else:
            keep &= df[name] == value
    if dates:
        keep &= df["date"] >= pd.Timestamp(_yyyymm_to_date_literal(dates[0]).strip("'"))
    return df[keep.to_numpy()].drop(columns=added).reset_index(drop=True)


class MissingCZAnomaliesError(LookupError):
    """``cz_anomalies`` is not in the database (the C-Z build stage did not complete)."""


def _require_cz_anomalies(db_path: str | Path) -> None:
    """Raise :class:`MissingCZAnomaliesError` unless ``db_path`` has ``cz_anomalies``."""
    found = query_df(
        db_path,
        "SELECT 1 FROM information_schema.tables WHERE table_name = 'cz_anomalies'",
    )
    if found.empty:
        raise MissingCZAnomaliesError(
            f"cz_anomalies is not in {db_path}; the C-Z stage did not complete. "
            "Fetch it with `aa setup-database --start-from fetch-cz-anomalies`."
        )


def load_cz_anomalies(
    signals: Iterable[str] | None = None,
    *,
    path: str | Path | None = None,
    dates: tuple[int, int] | None = None,
    wide: bool = False,
) -> pd.DataFrame:
    """
    Load Chen-Zimmerman anomaly characteristics from the cz_anomalies table.

    Parameters
    ----------
    signals : Iterable[str] or None
        Anomaly signal columns to select. If None, returns all signals.
        Examples: ["bm", "mom12m", "ep"] or {"bm", "size", "price"}
    path : str or Path, optional
        Database path. Uses default from config if not specified.
    dates : tuple[int, int], optional
        Date range filter as (start_yyyymm, end_yyyymm).
    wide : bool, default False
        If True, pivot to wide format with permnos as columns.

    Returns
    -------
    pd.DataFrame
        Panel data indexed by (date, permno) with requested signal columns.

    Examples
    --------
    >>> import assayinganomalies as aa
    >>> # Load all signals
    >>> cz = aa.load_cz_anomalies()
    >>> # Load specific signals
    >>> cz = aa.load_cz_anomalies(["bm", "mom12m", "size", "price"])
    >>> # Load with date filter
    >>> cz = aa.load_cz_anomalies(["bm"], dates=(196307, 202312))
    """
    db_path = _db_path(path)
    _require_cz_anomalies(db_path)

    # If no signals specified, get all columns from the table
    if signals is None:
        cols_df = query_df(
            db_path,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'cz_anomalies' "
            "AND column_name NOT IN ('date', 'permno')",
        )
        signals = cols_df["column_name"].tolist()

    return load(
        signals,
        path=db_path,
        table="cz_anomalies",
        panel=True,
        wide=wide,
        dates=dates,
        common_shares_only=False,  # CZ table doesn't have shrcd
    )


def list_cz_signals(*, path: str | Path | None = None) -> list[str]:
    """
    List available Chen-Zimmerman anomaly signal names.

    Returns
    -------
    list[str]
        Sorted list of signal column names in the cz_anomalies table.
    """
    db_path = _db_path(path)

    cols_df = query_df(
        db_path,
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'cz_anomalies' "
        "AND column_name NOT IN ('date', 'permno') "
        "ORDER BY column_name",
    )
    return cols_df["column_name"].tolist()


def get_cz_signal_info(
    signal: str | None = None,
    *,
    path: str | Path | None = None,
) -> pd.DataFrame:
    """
    Get metadata/documentation for Chen-Zimmerman anomaly signals.

    Parameters
    ----------
    signal : str, optional
        Signal name (e.g., "bm", "mom12m"). If None, returns info for all signals.
    path : str or Path, optional
        Database path. Uses default from config if not specified.

    Returns
    -------
    pd.DataFrame
        Signal metadata with columns like:
        - acronym: lowercase signal name (matches cz_anomalies columns)
        - Acronym: original case signal name
        - Authors, Year, Journal: publication info
        - LongDescription: what the signal measures
        - SampleStartYear, SampleEndYear: original sample period
        - StockWeight: weighting scheme ("VW", "EW")
        - LSQuantile: long-short quantile (10 = deciles)
        - PortfolioPeriod: holding period in months

    Examples
    --------
    >>> import assayinganomalies as aa
    >>> # Get info for a specific signal
    >>> aa.get_cz_signal_info("bm")
    >>> # Get all signal info as a DataFrame
    >>> info = aa.get_cz_signal_info()
    >>> info[["acronym", "Authors", "Year", "LongDescription"]].head()
    """
    db_path = _db_path(path)

    tables = query_df(
        db_path,
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_name = 'cz_signal_info'",
    )
    if tables.empty:
        raise ValueError(
            "cz_signal_info table not found. Run 'aa setup-database' first."
        )

    if signal is not None:
        signal_lower = signal.lower()
        df = query_df(
            db_path,
            f"SELECT * FROM cz_signal_info WHERE acronym = '{signal_lower}'",
        )
        if df.empty:
            raise KeyError(f"Signal '{signal}' not found in cz_signal_info")
    else:
        df = query_df(db_path, "SELECT * FROM cz_signal_info ORDER BY acronym")

    return df


def load_nmv_anomalies(
    signals: Iterable[str] | None = None,
    *,
    path: str | Path | None = None,
    dates: tuple[int, int] | None = None,
    wide: bool = False,
) -> pd.DataFrame:
    """
    Load Novy-Marx & Velikov (2016) anomaly signals from the nmv_anomalies table.

    Parameters
    ----------
    signals : Iterable[str] or None
        Signal columns to select. If None, returns all 23 signals.
        Examples: ["size", "value", "momentum", "reversals"]
    path : str or Path, optional
        Database path. Uses default from config if not specified.
    dates : tuple[int, int], optional
        Date range filter as (start_yyyymm, end_yyyymm).
    wide : bool, default False
        If True, pivot to wide format with permnos as columns.

    Returns
    -------
    pd.DataFrame
        Panel data indexed by (date, permno) with requested signal columns.
    """
    db_path = _db_path(path)

    if signals is None:
        cols_df = query_df(
            db_path,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'nmv_anomalies' "
            "AND column_name NOT IN ('date', 'permno')",
        )
        signals = cols_df["column_name"].tolist()

    return load(
        signals,
        path=db_path,
        table="nmv_anomalies",
        panel=True,
        wide=wide,
        dates=dates,
        common_shares_only=False,
    )


def describe_cz_signal(signal: str, *, path: str | Path | None = None) -> str:
    """
    Get a human-readable description of a Chen-Zimmerman signal.

    Parameters
    ----------
    signal : str
        Signal name (e.g., "bm", "mom12m").
    path : str or Path, optional
        Database path.

    Returns
    -------
    str
        Formatted description of the signal.

    Examples
    --------
    >>> import assayinganomalies as aa
    >>> print(aa.describe_cz_signal("bm"))
    """
    info = get_cz_signal_info(signal, path=path)
    if info.empty:
        return f"No information available for signal '{signal}'"

    row = info.iloc[0]
    lines = [f"Signal: {row.get('Acronym', signal)}"]

    if pd.notna(row.get("LongDescription")):
        lines.append(f"Description: {row['LongDescription']}")

    if pd.notna(row.get("Authors")):
        cite = row["Authors"]
        if pd.notna(row.get("Year")):
            cite += f" ({int(row['Year'])})"
        if pd.notna(row.get("Journal")):
            cite += f", {row['Journal']}"
        lines.append(f"Source: {cite}")

    if pd.notna(row.get("SampleStartYear")) and pd.notna(row.get("SampleEndYear")):
        lines.append(f"Original sample: {int(row['SampleStartYear'])}-{int(row['SampleEndYear'])}")

    if pd.notna(row.get("StockWeight")):
        lines.append(f"Weighting: {row['StockWeight']}")

    if pd.notna(row.get("LSQuantile")):
        lines.append(f"Long-short quantile: {int(row['LSQuantile'])}")

    return "\n".join(lines)


__all__ = [
    "AnnualLayoutError",
    "MissingCZAnomaliesError",
    "annual_columns",
    "require_june_annual_layout",
    "load",
    "load_cz_anomalies",
    "load_nmv_anomalies",
    "list_cz_signals",
    "get_cz_signal_info",
    "describe_cz_signal",
]

