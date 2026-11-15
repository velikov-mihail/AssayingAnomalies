"""
Utilities for fetching CRSP monthly data.
"""

from __future__ import annotations

import logging
from pathlib import Path
import time

import pandas as pd

from ..config import AssayConfig
from .crsp_source import SIZ_AUX_TABLES, SIZ_MONTHLY_SQL, CRSPSource, crsp_source_for
from .wrds_client import WRDSClient

LOGGER = logging.getLogger("assayinganomalies.ingest.crsp")

# The tape-specific literals now live in ``crsp_source``; these names are kept
# so existing callers (and the parity tooling) still resolve, and always mean
# the legacy SIZ tape.
CRSP_MONTHLY_SQL = SIZ_MONTHLY_SQL
CRSP_AUX_TABLES = SIZ_AUX_TABLES


def generate_placeholder_monthly(config: AssayConfig) -> pd.DataFrame:
    """
    Create a deterministic mini sample that mimics CRSP monthly output.
    """

    # Use real datetimes (not integer YYYYMM) so downstream transforms that call
    # pd.to_datetime() behave consistently for any sample window.
    d1 = pd.Timestamp(f"{config.sample_start}-01-01") + pd.offsets.MonthEnd(0)
    d2 = pd.Timestamp(f"{config.sample_start}-02-01") + pd.offsets.MonthEnd(0)
    data = {
        "date": [d1, d2],
        "permno": [10001, 10002],
        "ret": [0.01, -0.02],
        "me": [1.5e8, 7.2e7],
        "prc": [50.12, 12.34],
        "shrout": [3000.0, 1500.0],
        "siccd": [6020, 2834],
        "shrcd": [10, 11],
        "exchcd": [1, 3],
    }
    return pd.DataFrame(data)


def fetch_crsp_monthly(
    config: AssayConfig,
    destination: Path,
    *,
    wrds_client: WRDSClient | None = None,
    source: CRSPSource | None = None,
) -> Path:
    """
    Download CRSP monthly data from WRDS (full MSF extract) into a Parquet file.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    client = wrds_client or WRDSClient(config.wrds_username)
    source = source or crsp_source_for(config)

    sql = source.monthly_sql(config)

    LOGGER.info(
        "Fetching CRSP monthly (%s tape) from WRDS: sample=%s..%s -> %s",
        source.name,
        config.sample_start,
        config.sample_end,
        destination,
    )
    LOGGER.debug("CRSP MSF SQL: %s", sql.strip())
    t0 = time.perf_counter()
    with client.connect() as conn:  # pragma: no cover - requires live WRDS access
        df = conn.raw_sql(sql)
    LOGGER.info("Fetched CRSP monthly: rows=%d cols=%d in %.2fs", df.shape[0], df.shape[1], time.perf_counter() - t0)

    df.to_parquet(destination, index=False)
    try:
        LOGGER.info("Wrote CRSP monthly parquet: %s bytes=%d", destination, destination.stat().st_size)
    except Exception:
        LOGGER.info("Wrote CRSP monthly parquet: %s", destination)
    return destination


def fetch_crsp_aux_table(
    table: str,
    destination: Path,
    *,
    wrds_client: WRDSClient | None = None,
    source: CRSPSource | None = None,
) -> Path:
    """
    Download an auxiliary CRSP table (e.g., msfhdr, msedelist) with a simple SELECT *.
    """

    aux_tables = (source or crsp_source_for("siz")).aux_tables
    sql = aux_tables[table]
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Prefer provided client; otherwise honor WRDS_USERNAME env var.
    client = wrds_client or WRDSClient()
    LOGGER.info("Fetching CRSP aux table from WRDS: %s -> %s", table, destination)
    LOGGER.debug("CRSP aux SQL (%s): %s", table, sql.strip())
    t0 = time.perf_counter()
    with client.connect() as conn:  # pragma: no cover - requires live WRDS access
        df = conn.raw_sql(sql)
    LOGGER.info("Fetched CRSP aux %s: rows=%d cols=%d in %.2fs", table, df.shape[0], df.shape[1], time.perf_counter() - t0)
    df.to_parquet(destination, index=False)
    try:
        LOGGER.info("Wrote CRSP aux parquet (%s): %s bytes=%d", table, destination, destination.stat().st_size)
    except Exception:
        LOGGER.info("Wrote CRSP aux parquet (%s): %s", table, destination)
    return destination


__all__ = [
    "generate_placeholder_monthly",
    "fetch_crsp_monthly",
    "fetch_crsp_aux_table",
    "CRSP_AUX_TABLES",
]

