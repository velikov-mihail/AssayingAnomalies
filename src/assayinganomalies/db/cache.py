"""
Lightweight metadata cache used by session classes.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Mapping


@dataclass
class FieldCatalog:
    fields: Mapping[str, str]


def cache_path(db_path: Path) -> Path:
    return db_path.with_suffix(".catalog.json")


def load_field_catalog(db_path: Path) -> FieldCatalog:
    path = cache_path(db_path)
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return FieldCatalog(fields=data)
    return FieldCatalog(fields={})


def save_field_catalog(db_path: Path, catalog: FieldCatalog) -> None:
    path = cache_path(db_path)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(catalog.fields, fh, indent=2)


__all__ = ["FieldCatalog", "load_field_catalog", "save_field_catalog"]

