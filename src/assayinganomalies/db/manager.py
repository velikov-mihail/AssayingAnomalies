"""
Context manager wrapping DuckDB connections.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


class DuckDBManager:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._con: duckdb.DuckDBPyConnection | None = None

    def __enter__(self) -> "DuckDBManager":
        # A kept-alive aa.load connection would hold the file lock (and could
        # serve pre-write pages). Drop it before a writer/reader context opens.
        from ..session_cache import close_cached_connection

        close_cached_connection(self.path)
        self._con = duckdb.connect(str(self.path))
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._con is not None:
            self._con.close()
            self._con = None

    @property
    def connection(self) -> duckdb.DuckDBPyConnection:
        if self._con is None:
            from ..session_cache import close_cached_connection

            close_cached_connection(self.path)
            self._con = duckdb.connect(str(self.path))
        return self._con

    def execute(self, sql: str, *params: Any) -> None:
        self.connection.execute(sql, params)

    def query_df(self, sql: str) -> pd.DataFrame:
        return self.connection.execute(sql).df()

