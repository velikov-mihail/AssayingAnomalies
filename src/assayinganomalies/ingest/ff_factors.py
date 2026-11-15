from __future__ import annotations

import logging
import time
import pandas as pd

from ..config import AssayConfig
from .wrds_client import WRDSClient

LOGGER = logging.getLogger("assayinganomalies.ingest.ff_factors")


# FF3 + momentum (mktrf, smb, hml, rf, umd)
FF3_MONTHLY_SQL = """
SELECT date, mktrf, smb, hml, rf, umd
FROM ff.factors_monthly
WHERE date BETWEEN '{start_date}' AND '{end_date}'
"""

# FF5 factors (smb2, rmw, cma) - joined by date.
# smb2 is the *five-factor* SMB (MATLAB `makeFFFactors` keeps it as smb2);
# it differs from the three-factor smb because the 2x3 sorts add rmw/cma legs.
FF5_MONTHLY_SQL = """
SELECT date, smb AS smb2, rmw, cma
FROM ff.fivefactors_monthly
WHERE date BETWEEN '{start_date}' AND '{end_date}'
"""


def _to_month_end(ts: pd.Series) -> pd.Series:
    """
    Convert a date-like series to canonical month-end (00:00:00).

    WRDS factor tables are keyed by month (often stored as the first of month).
    The rest of this project (e.g. `ccm_panel`) uses month-end dates as the
    canonical key, so we enforce that here for consistency.
    """
    dt = pd.to_datetime(ts, errors="coerce")
    return (dt + pd.offsets.MonthEnd(0)).dt.normalize()


def fetch_ff_monthly(
    config: AssayConfig,
    *,
    wrds_client: WRDSClient | None = None,
) -> pd.DataFrame:
    """
    Fetch Fama-French monthly factors from WRDS.
    
    Pulls FF3 + momentum from ff.factors_monthly and
    smb2/rmw/cma from ff.fivefactors_monthly, then merges on date.
    
    Returns a DataFrame with: date, mktrf, smb, hml, rf, umd, smb2, rmw, cma
    """
    client = wrds_client or WRDSClient(config.wrds_username)
    start_date = f"{config.sample_start}-01-01"
    end_date = f"{config.sample_end}-12-31"

    LOGGER.info("Fetching Fama-French monthly factors from WRDS: sample=%s..%s", config.sample_start, config.sample_end)
    LOGGER.debug("FF3+UMD SQL: %s", FF3_MONTHLY_SQL.format(start_date=start_date, end_date=end_date).strip())
    LOGGER.debug("FF5 (RMW/CMA) SQL: %s", FF5_MONTHLY_SQL.format(start_date=start_date, end_date=end_date).strip())
    t0 = time.perf_counter()
    with client.connect() as conn:  # pragma: no cover - requires WRDS
        # Fetch FF3 + momentum
        sql_ff3 = FF3_MONTHLY_SQL.format(start_date=start_date, end_date=end_date)
        df_ff3 = conn.raw_sql(sql_ff3)

        # Fetch FF5 (rmw, cma)
        sql_ff5 = FF5_MONTHLY_SQL.format(start_date=start_date, end_date=end_date)
        df_ff5 = conn.raw_sql(sql_ff5)
    LOGGER.info(
        "Fetched WRDS factors in %.2fs: ff3+umd rows=%d cols=%d; ff5 rows=%d cols=%d",
        time.perf_counter() - t0,
        df_ff3.shape[0],
        df_ff3.shape[1],
        df_ff5.shape[0],
        df_ff5.shape[1],
    )

    # Canonicalize to month-end dates for downstream joins/alignment.
    df_ff3["date"] = _to_month_end(df_ff3["date"])
    df_ff5["date"] = _to_month_end(df_ff5["date"])

    # Merge on date
    df = df_ff3.merge(df_ff5, on="date", how="left")

    # Defensive: ensure one row per month key.
    df = df.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)

    LOGGER.info("Merged factors: rows=%d cols=%d", df.shape[0], df.shape[1])
    return df


# --- Daily factors ---

FF3_DAILY_SQL = """
SELECT date, mktrf, smb, hml, rf, umd
FROM ff.factors_daily
WHERE date BETWEEN '{start_date}' AND '{end_date}'
"""


def fetch_ff_daily(
    config: AssayConfig,
    *,
    wrds_client: WRDSClient | None = None,
) -> pd.DataFrame:
    """
    Fetch Fama-French daily factors from WRDS.

    Returns a DataFrame with: date, mktrf, smb, hml, rf, umd.
    """
    client = wrds_client or WRDSClient(config.wrds_username)
    start_date = f"{config.sample_start}-01-01"
    end_date = f"{config.sample_end}-12-31"

    LOGGER.info(
        "Fetching Fama-French daily factors from WRDS: sample=%s..%s",
        config.sample_start, config.sample_end,
    )
    t0 = time.perf_counter()
    with client.connect() as conn:  # pragma: no cover - requires WRDS
        sql = FF3_DAILY_SQL.format(start_date=start_date, end_date=end_date)
        df = conn.raw_sql(sql)
    LOGGER.info(
        "Fetched FF daily factors in %.2fs: rows=%d cols=%d",
        time.perf_counter() - t0, df.shape[0], df.shape[1],
    )

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
    return df


__all__ = ["fetch_ff_monthly", "fetch_ff_daily", "_to_month_end"]

