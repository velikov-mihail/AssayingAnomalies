"""
High-level session class for user workflows.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import pandas as pd

from . import data_access
from .analytics.regressions import run_fama_macbeth
from .analytics.sorts import run_univariate_sort
from .config import AssayConfig, load_config


@dataclass(slots=True)
class AssayClient:
    """Stateful helper exposing ergonomic methods for everyday analysis."""

    config: AssayConfig
    db_path: Path

    @classmethod
    def from_config(cls, cfg: AssayConfig | None = None) -> "AssayClient":
        config = cfg or load_config()
        return cls(config=config, db_path=config.database_path)

    def load(self, fields: Iterable[str] | Mapping[str, str], **kwargs: Any) -> pd.DataFrame:
        return data_access.load(fields, path=self.db_path, **kwargs)

    def lag(self, series: pd.Series, periods: int = 1) -> pd.Series:
        if isinstance(series.index, pd.MultiIndex):
            level = series.index.names.index("permno") if "permno" in series.index.names else 0
            return series.groupby(level=level).shift(periods)
        return series.shift(periods)

    def run_univariate_sort(self, *args: Any, **kwargs: Any):
        return run_univariate_sort(*args, **kwargs)

    def run_fama_macbeth(self, *args: Any, **kwargs: Any):
        return run_fama_macbeth(*args, **kwargs)


__all__ = ["AssayClient"]

