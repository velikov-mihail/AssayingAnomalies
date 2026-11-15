"""
Database writing helpers.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from .manager import DuckDBManager


def write_table(path: Path, table: str, df: pd.DataFrame, *, mode: str = "append") -> None:
    with DuckDBManager(path) as manager:
        manager.connection.register("tmp_df", df)
        if mode == "replace":
            manager.execute(f"DROP TABLE IF EXISTS {table}")
            manager.execute(f"CREATE TABLE {table} AS SELECT * FROM tmp_df")
        else:
            manager.execute(f"CREATE TABLE IF NOT EXISTS {table} AS SELECT * FROM tmp_df WHERE 0")
            manager.execute(f"INSERT INTO {table} SELECT * FROM tmp_df")



def add_columns_from_frame(
    path: Path,
    table: str,
    frame: pd.DataFrame,
    *,
    keys: Sequence[str] = ("permno", "date"),
    replace: Sequence[str] = (),
) -> int:
    """
    Add the non-key columns of ``frame`` to ``table``, joined on ``keys``.

    The table is rebuilt in one transaction (``CREATE TABLE ... AS SELECT``
    with a left join, then drop and rename), so it is never read into pandas
    and a failure leaves it as it was. The new columns come last; rows of
    ``table`` with no match in ``frame`` get NULL. Columns named in
    ``replace`` are dropped from ``table`` first, so a refreshed column is
    replaced rather than duplicated; any other column already in ``table``
    raises ``ValueError``.

    ``frame`` must be unique on ``keys``. Its other columns are stored as
    DOUBLE; a ``date`` key is normalized to midnight ``datetime64[ns]``.

    Returns the table's row count, which the rebuild leaves unchanged
    (checked).
    """
    keys = list(keys)
    replace = list(replace)
    extras = [c for c in frame.columns if c not in keys]
    if not extras:
        raise ValueError("frame has no columns besides the keys")
    missing = [k for k in keys if k not in frame.columns]
    if missing:
        raise ValueError(f"frame lacks key column(s) {missing}")
    if frame.duplicated(subset=keys).any():
        raise ValueError(f"frame has duplicate {tuple(keys)} keys")

    data = frame[keys + extras].copy()
    if "date" in keys:
        data["date"] = pd.to_datetime(data["date"]).dt.normalize().astype("datetime64[ns]")
    for col in extras:
        data[col] = pd.to_numeric(data[col], errors="raise").astype("float64")

    new = f"{table}__new"
    with DuckDBManager(path) as manager:
        con = manager.connection
        existing = [
            r[0] for r in con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = ? ORDER BY ordinal_position",
                [table],
            ).fetchall()
        ]
        if not existing:
            raise ValueError(f"table {table!r} does not exist")
        clash = [c for c in extras if c in existing and c not in replace]
        if clash:
            raise ValueError(f"{table} already has column(s) {clash}")
        n_before = con.execute(f"SELECT count(*) FROM {table}").fetchall()[0][0]
        dropped = [c for c in replace if c in existing]
        exclude = f" EXCLUDE ({', '.join(dropped)})" if dropped else ""
        added = ", ".join(f"x.{c}" for c in extras)
        con.register("tmp_extra", data)
        try:
            con.execute("BEGIN TRANSACTION")
            try:
                con.execute(f"DROP TABLE IF EXISTS {new}")
                con.execute(
                    f"CREATE TABLE {new} AS SELECT p.*{exclude}, {added} "
                    f"FROM {table} p LEFT JOIN tmp_extra x USING ({', '.join(keys)})"
                )
                n_after = con.execute(f"SELECT count(*) FROM {new}").fetchall()[0][0]
                if n_after != n_before:
                    raise RuntimeError(
                        f"adding columns to {table} changed its row count "
                        f"({n_before} -> {n_after}); nothing was changed"
                    )
                con.execute(f"DROP TABLE {table}")
                con.execute(f"ALTER TABLE {new} RENAME TO {table}")
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise
        finally:
            con.unregister("tmp_extra")
    return int(n_before)
