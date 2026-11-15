"""
Lightweight schema/data migrations for the local DuckDB warehouse.

We keep these intentionally small and idempotent: they should be safe to run on
every `aa.setup_database()` call.
"""

from __future__ import annotations

from pathlib import Path

from .manager import DuckDBManager


def _month_end_expr(col: str) -> str:
    """
    DuckDB SQL expression that converts a DATE/TIMESTAMP to the month-end date (same month).
    """
    # date_trunc('month', ts) gives the first day of month at 00:00; then add 1 month and subtract 1 day.
    return f"(date_trunc('month', {col}) + INTERVAL '1 month' - INTERVAL '1 day')"


def migrate_ts_data_monthly_dates_to_month_end(db_path: str | Path) -> None:
    """
    Ensure `ts_data.date` uses end-of-month dates (consistent with `ccm_panel`).

    This is important because WRDS factor tables are typically keyed to month and
    may be stored as the first of month (e.g., 1963-01-01). Downstream analytics
    uses month-end dates as the canonical monthly key.

    Idempotent: running multiple times is safe.
    """
    path = Path(db_path)
    with DuckDBManager(path) as manager:
        exists = manager.connection.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = 'ts_data'"
        ).fetchone()[0]
        if not exists:
            return

        # If there is no `date` column, nothing to do.
        cols = manager.connection.execute("DESCRIBE ts_data").fetchall()
        col_names = {str(r[0]).lower() for r in cols}
        if "date" not in col_names:
            return

        manager.execute(f"UPDATE ts_data SET date = {_month_end_expr('date')}")

        # Detect collisions (e.g., both month-start and month-end rows existed and now collide).
        dup = manager.connection.execute(
            "SELECT date, count(*) AS c FROM ts_data GROUP BY date HAVING c > 1 LIMIT 1"
        ).fetchone()
        if dup:
            raise ValueError(
                "Migration created duplicate ts_data rows for the same month-end date. "
                "Please run a full refresh (aa setup-database --full-refresh) to rebuild ts_data cleanly."
            )


__all__ = ["migrate_ts_data_monthly_dates_to_month_end"]


