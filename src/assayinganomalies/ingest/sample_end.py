"""
Resolve ``sample_end = "latest"`` against the WRDS tapes.

"latest" is the last *complete* calendar year on the tapes when
``setup-database`` runs: the year of the last December month on the CRSP
monthly stock file of the configured tape, and of the last December fiscal
year end on Compustat ``comp.funda``, whichever is earlier. A year whose
December has not been published yet is incomplete, so a build in, say, March
2026 resolves to 2025. A frozen tape caps the year (SIZ ends in 2024).

The pipeline asks once, in a preflight, on the shared WRDS session, and works
on a copy of the config holding the year; the year and the dates behind it are
written to the database's ``metadata`` table and the run manifest
(:meth:`SampleEndResolution.as_metadata`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from ..config import LATEST_SAMPLE_END
from .crsp_source import CRSPSource

# Where a build's sample end came from.
SAMPLE_END_SOURCES: tuple[str, ...] = ("explicit", "wrds", "metadata", "demo", "clamped-siz")

# Compustat annual table and the standard filters every Compustat fetch uses
# (ingest/compustat.py), so "latest" sees the same records the build keeps.
COMPUSTAT_TABLE = "comp.funda"
COMPUSTAT_DATE_COL = "datadate"
COMPUSTAT_FILTERS = "indfmt = 'INDL' AND datafmt = 'STD' AND consol = 'C' AND popsrc = 'D'"


def compustat_end_sql() -> str:
    """The query for Compustat's last ``datadate`` and last December ``datadate``."""
    col = COMPUSTAT_DATE_COL
    return (
        f"SELECT max({col}) AS max_date, "
        f"max({col}) FILTER (WHERE extract(month FROM {col}) = 12) AS last_december "
        f"FROM {COMPUSTAT_TABLE} WHERE {COMPUSTAT_FILTERS}"
    )


@dataclass(frozen=True)
class SampleEndResolution:
    """The sample end a build uses, and where it came from.

    ``requested`` is the configured value (a year or ``"latest"``),
    ``resolved`` the year the build uses, ``source`` one of
    :data:`SAMPLE_END_SOURCES`. The dates (ISO ``YYYY-MM-DD``) are filled in
    when the tapes were asked (``source == "wrds"``) or carried over from the
    build that asked them (``"metadata"``), and are ``None`` otherwise.
    """

    requested: int | str
    resolved: int
    source: str
    crsp_max_date: str | None = None
    crsp_last_december: str | None = None
    compustat_max_date: str | None = None
    compustat_last_december: str | None = None

    def __post_init__(self) -> None:
        if self.source not in SAMPLE_END_SOURCES:
            raise ValueError(
                f"source must be one of {', '.join(SAMPLE_END_SOURCES)}; got {self.source!r}"
            )

    def as_metadata(self) -> dict[str, Any]:
        """The ``metadata`` / manifest keys this resolution writes."""
        return {
            "sample_end_requested": self.requested,
            "sample_end_resolved": int(self.resolved),
            "sample_end_source": self.source,
            "crsp_tape_max_date": self.crsp_max_date,
            "crsp_tape_last_december": self.crsp_last_december,
            "compustat_max_datadate": self.compustat_max_date,
            "compustat_last_december": self.compustat_last_december,
        }


def _iso_date(value: Any) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return pd.Timestamp(value).date().isoformat()


def _tape_end(conn: Any, sql: str, what: str) -> tuple[str, str]:
    """``(max date, last December date)`` from one ``max``/``last_december`` query."""
    frame = conn.raw_sql(sql)
    if not isinstance(frame, pd.DataFrame) or frame.empty or not {
        "max_date", "last_december"
    } <= set(frame.columns):
        raise ValueError(
            f"Could not read the last month of {what} from WRDS: the query returned "
            f"{frame!r}, not max_date and last_december.\nQuery: {sql}"
        )
    max_date = _iso_date(frame["max_date"].iloc[0])
    last_december = _iso_date(frame["last_december"].iloc[0])
    if max_date is None or last_december is None:
        raise ValueError(
            f"{what} on WRDS has no {'rows' if max_date is None else 'December month'}, "
            "so sample_end = 'latest' cannot be resolved. Pin a year with "
            f"`aa set-params --sample-end <year>`.\nQuery: {sql}"
        )
    return max_date, last_december


def resolve_latest_sample_end(conn: Any, source: CRSPSource) -> SampleEndResolution:
    """Ask WRDS for the last complete year on ``source``'s tape and on Compustat.

    ``conn`` is an open WRDS connection (anything with ``raw_sql`` returning a
    DataFrame). Raises ``ValueError`` when either table returns no December.
    """
    crsp_max, crsp_dec = _tape_end(
        conn, source.tape_end_sql(), f"the CRSP {source.name.upper()} tape ({source.monthly_table})"
    )
    comp_max, comp_dec = _tape_end(conn, compustat_end_sql(), f"Compustat ({COMPUSTAT_TABLE})")
    years = [int(crsp_dec[:4]), int(comp_dec[:4])]
    if source.frozen_end_year is not None:
        years.append(int(source.frozen_end_year))
    return SampleEndResolution(
        requested=LATEST_SAMPLE_END,
        resolved=min(years),
        source="wrds",
        crsp_max_date=crsp_max,
        crsp_last_december=crsp_dec,
        compustat_max_date=comp_max,
        compustat_last_december=comp_dec,
    )


__all__ = [
    "COMPUSTAT_TABLE",
    "SAMPLE_END_SOURCES",
    "SampleEndResolution",
    "compustat_end_sql",
    "resolve_latest_sample_end",
]
