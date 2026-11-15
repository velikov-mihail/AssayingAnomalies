"""
Helpers for composing SELECT statements.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping

# SQL reserved words that must be quoted when used as column names.
# This is not exhaustive but covers common COMPUSTAT/CRSP columns.
SQL_RESERVED_WORDS = frozenset({
    "at",  # COMPUSTAT total assets - conflicts with AT TIME ZONE
    "in", "is", "as", "by", "or", "on", "to", "if", "do", "no",
    "all", "and", "any", "for", "not", "key", "set", "end", "add",
    "date", "year", "month", "day", "time", "order", "group", "index",
    "table", "select", "from", "where", "join", "left", "right", "inner",
    "outer", "cross", "full", "union", "except", "intersect", "having",
    "limit", "offset", "distinct", "between", "like", "null", "true", "false",
})


def _yyyymm_to_date_literal(val: int | str) -> str:
    """Convert a YYYYMM integer (e.g. 196307) to a SQL date literal like '1963-07-31'.

    Uses month-end convention consistent with the rest of the codebase.
    """
    import calendar

    val = int(val)
    year, month = divmod(val, 100)
    day = calendar.monthrange(year, month)[1]
    return f"'{year:04d}-{month:02d}-{day:02d}'"


def _quote_identifier(name: str) -> str:
    """Quote an identifier if it's a SQL reserved word."""
    if name.lower() in SQL_RESERVED_WORDS:
        return f'"{name}"'
    return name


def _normalize_field_expr(expr: str) -> str:
    """
    Backward-compat field aliases for SQL expressions.

    This keeps example code stable while the API settles.
    """
    alias_map = {
        "dates": "date",
        "NYSE": "nyse_flag",
    }
    return alias_map.get(expr, expr)


def build_select_statement(
    fields: Iterable[str] | Mapping[str, str],
    *,
    filters: Mapping[str, Any] | None = None,
    lag: Mapping[str, int] | None = None,
    universe: str | None = None,
    dates: tuple[int, int] | None = None,
    panel: bool = True,
    common_shares_only: bool = True,
    table: str | None = None,
) -> str:
    selected: list[str] = []
    if isinstance(fields, Mapping):
        for alias, expr in fields.items():
            norm_expr = _normalize_field_expr(expr)
            quoted_expr = _quote_identifier(norm_expr)
            selected.append(f"{quoted_expr} AS {alias}")
    else:
        for f in fields:
            norm_f = _normalize_field_expr(f)
            selected.append(_quote_identifier(norm_f))

    # Choose source table.
    source_table = table or ("ccm_panel" if panel else "ts_data")

    # Tables that are panel-structured (date, permno)
    panel_tables = {"ccm_panel", "cz_anomalies"}
    is_panel_table = source_table in panel_tables

    # Always include date and permno for panel data so we can set the index.
    # Track unquoted names for membership check
    selected_unquoted = {s.strip('"') for s in selected}
    if panel or is_panel_table:
        for key_col in ("date", "permno"):
            if key_col not in selected_unquoted:
                selected.insert(0, _quote_identifier(key_col))
    else:
        # For time-series tables, always include date for alignment.
        if "date" not in selected_unquoted:
            selected.insert(0, _quote_identifier("date"))

    sql_parts = ["SELECT", ", ".join(selected) or "*", f"FROM {source_table}"]

    clauses: list[str] = []

    # Default: US ordinary common shares only (shrcd 10 or 11)
    if common_shares_only and panel and source_table == "ccm_panel":
        clauses.append("shrcd IN (10, 11)")

    if filters:
        for key, value in filters.items():
            quoted_key = _quote_identifier(key)
            if isinstance(value, (list, tuple, set)):
                values = ", ".join(repr(v) for v in value)
                clauses.append(f"{quoted_key} IN ({values})")
            else:
                clauses.append(f"{quoted_key} = {repr(value)}")

    if dates:
        lo, hi = dates
        lo_date = _yyyymm_to_date_literal(lo)
        hi_date = _yyyymm_to_date_literal(hi)
        clauses.append(f"{_quote_identifier('date')} BETWEEN {lo_date} AND {hi_date}")

    if clauses:
        sql_parts.append("WHERE " + " AND ".join(clauses))

    return " ".join(sql_parts)

