"""
Stage registry for scoped pipeline rebuilds.

This module provides three hand-maintained lookup tables used by
``pipeline.rebuild(...)`` and the self-healing parity loop's fixer Agent:

* ``COLUMN_TO_STAGE``: column name -> (table, last_writer_stage). The last
  writer wins because pipeline stages use DROP+CREATE writes.
* ``TABLE_WRITER_CHAIN``: table -> ordered list of stages that write it.
  When rebuilding stage S writing table T, the cascade must include every
  *later* stage in the chain — otherwise the table silently rots.
* ``STAGE_READS``: stage -> set of upstream stages whose output it reads.
  Used to validate that a rebuild plan has its dependencies satisfied.

These maps are hand-maintained and grep-verified against the
``write_table`` calls in ``pipeline.py``.

Only the ``ccm_panel`` chain is genuinely multi-writer — every other
table has one writer stage.
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple


TABLE_WRITER_CHAIN: Dict[str, List[str]] = {
    # ccm_panel is built by transform-crsp-monthly and re-written (merge)
    # by every downstream enrichment stage. Each re-write is a DROP+CREATE,
    # so the last writer wins — skipping cascade rots columns.
    "ccm_panel": [
        "transform-crsp-monthly",
        "transform-crsp-daily",
        "transform-compustat",
        "compute-tcosts",
        "compute-betas",
        "compute-car3",
    ],
    "crsp_msf": ["load-crsp-msf"],
    "crsp_dsf": ["load-crsp-dsf"],
    "crsp_daily_panel": ["transform-crsp-daily"],
    "ts_data_daily": ["transform-crsp-daily"],
    "ts_data": ["fetch-ff-factors", "compute-ff-tcosts"],
    "tcosts": ["compute-tcosts"],
    "betas": ["compute-betas"],
    "nmv_anomalies": ["compute-nmv-anomalies"],
    "validation_bm_hml": ["validate-bm-hml"],
    "cz_anomalies": ["fetch-cz-anomalies"],
    "cz_signal_info": ["fetch-cz-anomalies"],
    "field_catalog": ["generate-field-catalog"],
    # CRSP aux raw tables loaded together in load-crsp-aux, under the bare
    # WRDS table names (their staging parquets carry a crsp_ prefix, the
    # tables do not).
    "msfhdr": ["load-crsp-aux"],
    "msedelist": ["load-crsp-aux"],
    "dsedelist": ["load-crsp-aux"],
    "mseexchdates": ["load-crsp-aux"],
    "stocknames": ["load-crsp-aux"],
    "ccmxpf_lnkhist": ["load-crsp-aux"],
    # CIZ-tape aux tables (crsp_format="ciz"); load-crsp-aux writes whichever
    # set the active CRSPSource names.
    "stkdelists": ["load-crsp-aux"],
    "stksecurityinfohist": ["load-crsp-aux"],
    "stocknames_v2": ["load-crsp-aux"],
    # The cleaned CCM link (clean_ccm_link), written by transform-compustat
    # from the staged ccmxpf_lnkhist extract.
    "ccm_link": ["transform-compustat"],
    # Compustat raw tables loaded together in load-compustat
    "compustat_funda": ["load-compustat"],
    "compustat_fundq": ["load-compustat"],
}


# column -> (table, last_writer_stage). Last writer wins because
# pipeline stages DROP+CREATE the target table.
# Columns a user adds with ``aa add-compustat-vars`` are not registered here:
# they differ per database (recorded in its ``config`` table under
# ``compustat_extra_vars``). ``transform-compustat`` writes them on a rebuild,
# and the command refreshes them.
COLUMN_TO_STAGE: Dict[str, Tuple[str, str]] = {
    # --- ccm_panel: produced by transform-crsp-monthly ---
    # Keys (informational — not usually rebuilt as a drift target)
    "date": ("ccm_panel", "transform-crsp-monthly"),
    "permno": ("ccm_panel", "transform-crsp-monthly"),
    "yyyymm": ("ccm_panel", "transform-crsp-monthly"),
    # CRSP monthly fields
    "ret": ("ccm_panel", "transform-crsp-monthly"),
    "ret_adj": ("ccm_panel", "transform-crsp-monthly"),
    "ret_x_dl": ("ccm_panel", "transform-crsp-monthly"),
    "retx": ("ccm_panel", "transform-crsp-monthly"),
    "dlret": ("ccm_panel", "transform-crsp-monthly"),
    "prc": ("ccm_panel", "transform-crsp-monthly"),
    "bid": ("ccm_panel", "transform-crsp-monthly"),
    "ask": ("ccm_panel", "transform-crsp-monthly"),
    "bidlo": ("ccm_panel", "transform-crsp-monthly"),
    "askhi": ("ccm_panel", "transform-crsp-monthly"),
    "vol_x_adj": ("ccm_panel", "transform-crsp-monthly"),
    "shrout": ("ccm_panel", "transform-crsp-monthly"),
    "shrout_adj": ("ccm_panel", "transform-crsp-monthly"),
    "cfacpr": ("ccm_panel", "transform-crsp-monthly"),
    "cfacshr": ("ccm_panel", "transform-crsp-monthly"),
    "spread": ("ccm_panel", "transform-crsp-monthly"),
    "sic": ("ccm_panel", "transform-crsp-monthly"),
    "shrcd": ("ccm_panel", "transform-crsp-monthly"),
    "exchcd": ("ccm_panel", "transform-crsp-monthly"),
    "me": ("ccm_panel", "transform-crsp-monthly"),
    "nyse_flag": ("ccm_panel", "transform-crsp-monthly"),
    "ff10": ("ccm_panel", "transform-crsp-monthly"),
    "ff17": ("ccm_panel", "transform-crsp-monthly"),
    "ff49": ("ccm_panel", "transform-crsp-monthly"),
    "R12_2": ("ccm_panel", "transform-crsp-monthly"),
    "R60_13": ("ccm_panel", "transform-crsp-monthly"),
    "R6_1": ("ccm_panel", "transform-crsp-monthly"),
    "issuance_delta": ("ccm_panel", "transform-crsp-monthly"),
    "issuance_pct": ("ccm_panel", "transform-crsp-monthly"),
    # --- ccm_panel: daily aggregates (transform-crsp-daily) ---
    "rvol_1m": ("ccm_panel", "transform-crsp-daily"),
    "rvol_3m": ("ccm_panel", "transform-crsp-daily"),
    "rvol_6m": ("ccm_panel", "transform-crsp-daily"),
    "rvol_12m": ("ccm_panel", "transform-crsp-daily"),
    "rvol_36m": ("ccm_panel", "transform-crsp-daily"),
    "rvol_60m": ("ccm_panel", "transform-crsp-daily"),
    "amihud": ("ccm_panel", "transform-crsp-daily"),
    "idiovol": ("ccm_panel", "transform-crsp-daily"),
    "idiovol_3m": ("ccm_panel", "transform-crsp-daily"),
    "idiovol_ff": ("ccm_panel", "transform-crsp-daily"),
    "idiovol_ff_3m": ("ccm_panel", "transform-crsp-daily"),
    "maxret": ("ccm_panel", "transform-crsp-daily"),
    # --- ccm_panel: compustat annual + quarterly derived (transform-compustat) ---
    "be": ("ccm_panel", "transform-compustat"),
    "bm": ("ccm_panel", "transform-compustat"),
    "fin_firm": ("ccm_panel", "transform-compustat"),
    "at": ("ccm_panel", "transform-compustat"),
    "lt": ("ccm_panel", "transform-compustat"),
    "gp": ("ccm_panel", "transform-compustat"),
    "revt": ("ccm_panel", "transform-compustat"),
    "sale": ("ccm_panel", "transform-compustat"),
    "ib": ("ccm_panel", "transform-compustat"),
    "ni": ("ccm_panel", "transform-compustat"),
    "oancf": ("ccm_panel", "transform-compustat"),
    "capx": ("ccm_panel", "transform-compustat"),
    "sich": ("ccm_panel", "transform-compustat"),
    "act": ("ccm_panel", "transform-compustat"),
    "che": ("ccm_panel", "transform-compustat"),
    "lct": ("ccm_panel", "transform-compustat"),
    "dlc": ("ccm_panel", "transform-compustat"),
    "txp": ("ccm_panel", "transform-compustat"),
    "dp": ("ccm_panel", "transform-compustat"),
    "dltt": ("ccm_panel", "transform-compustat"),
    "cogs": ("ccm_panel", "transform-compustat"),
    "ppegt": ("ccm_panel", "transform-compustat"),
    "invt": ("ccm_panel", "transform-compustat"),
    "oc": ("ccm_panel", "transform-compustat"),
    "d": ("ccm_panel", "transform-compustat"),
    "inv_capital": ("ccm_panel", "transform-compustat"),
    "fcf": ("ccm_panel", "transform-compustat"),
    "div": ("ccm_panel", "transform-compustat"),
    "wcap": ("ccm_panel", "transform-compustat"),
    "cfo": ("ccm_panel", "transform-compustat"),
    "comp_datadate": ("ccm_panel", "transform-compustat"),
    "comp_avail_date": ("ccm_panel", "transform-compustat"),
    "be_source": ("ccm_panel", "transform-compustat"),
    "be_avail_date": ("ccm_panel", "transform-compustat"),
    "beq": ("ccm_panel", "transform-compustat"),
    "gpq": ("ccm_panel", "transform-compustat"),
    "roa": ("ccm_panel", "transform-compustat"),
    "sue": ("ccm_panel", "transform-compustat"),
    "droe": ("ccm_panel", "transform-compustat"),
    "sue2": ("ccm_panel", "transform-compustat"),
    "droa": ("ccm_panel", "transform-compustat"),
    "amonth": ("ccm_panel", "transform-compustat"),
    "ibq": ("ccm_panel", "transform-compustat"),
    "niq": ("ccm_panel", "transform-compustat"),
    "ltq": ("ccm_panel", "transform-compustat"),
    "cheq": ("ccm_panel", "transform-compustat"),
    "mib": ("ccm_panel", "transform-compustat"),
    "mibq": ("ccm_panel", "transform-compustat"),
    "xrdq": ("ccm_panel", "transform-compustat"),
    # --- ccm_panel: tcosts column (compute-tcosts) ---
    "tcost": ("ccm_panel", "compute-tcosts"),
    "tcosts": ("ccm_panel", "compute-tcosts"),
    "tcost_gibbs": ("ccm_panel", "compute-tcosts"),
    # --- ccm_panel: betas (compute-betas) ---
    "bols": ("ccm_panel", "compute-betas"),
    "bdim": ("ccm_panel", "compute-betas"),
    "bsw": ("ccm_panel", "compute-betas"),
    "bvck": ("ccm_panel", "compute-betas"),
    "bstd": ("ccm_panel", "compute-betas"),
    "bfp": ("ccm_panel", "compute-betas"),
    # --- ccm_panel: car3 (compute-car3) ---
    "car3": ("ccm_panel", "compute-car3"),
    # --- ts_data: Fama-French monthly factors (fetch-ff-factors) ---
    "mktrf": ("ts_data", "fetch-ff-factors"),
    "smb": ("ts_data", "fetch-ff-factors"),
    "smb2": ("ts_data", "fetch-ff-factors"),
    "hml": ("ts_data", "fetch-ff-factors"),
    "umd": ("ts_data", "fetch-ff-factors"),
    "rmw": ("ts_data", "fetch-ff-factors"),
    "cma": ("ts_data", "fetch-ff-factors"),
    "rf": ("ts_data", "fetch-ff-factors"),
    "mkt": ("ts_data", "fetch-ff-factors"),
    # --- ts_data: FF factor trading costs (compute-ff-tcosts) ---
    "mkt_tc": ("ts_data", "compute-ff-tcosts"),
    "smb_tc": ("ts_data", "compute-ff-tcosts"),
    "hml_tc": ("ts_data", "compute-ff-tcosts"),
    "rmw_tc": ("ts_data", "compute-ff-tcosts"),
    "cma_tc": ("ts_data", "compute-ff-tcosts"),
    "umd_tc": ("ts_data", "compute-ff-tcosts"),
    # The plain columns are the costs under convention="dollar" (the default);
    # these are the same under "capital" (mkt_tc is zero under both).
    "smb_tc_capital": ("ts_data", "compute-ff-tcosts"),
    "hml_tc_capital": ("ts_data", "compute-ff-tcosts"),
    "rmw_tc_capital": ("ts_data", "compute-ff-tcosts"),
    "cma_tc_capital": ("ts_data", "compute-ff-tcosts"),
    "umd_tc_capital": ("ts_data", "compute-ff-tcosts"),
    # "capital", the factor held short (its two sides exchanged).
    "smb_tc_capital_short": ("ts_data", "compute-ff-tcosts"),
    "hml_tc_capital_short": ("ts_data", "compute-ff-tcosts"),
    "rmw_tc_capital_short": ("ts_data", "compute-ff-tcosts"),
    "cma_tc_capital_short": ("ts_data", "compute-ff-tcosts"),
    "umd_tc_capital_short": ("ts_data", "compute-ff-tcosts"),
    # --- crsp_daily_panel (transform-crsp-daily) ---
    # The full daily panel is written separately; columns typically queried
    # from it match the monthly aggregate source columns but at daily grain.
    # The fixer rarely targets this table directly.
}


# stage -> set of upstream stages whose output it consumes.
# Used to validate rebuild plans (a stage can only rebuild if its upstream
# has already run successfully, either earlier in this plan or previously).
STAGE_READS: Dict[str, Set[str]] = {
    "initialize-database": set(),
    "generate-field-catalog": {"initialize-database"},
    "fetch-crsp-monthly": {"initialize-database"},
    "load-crsp-msf": {"fetch-crsp-monthly"},
    "fetch-crsp-aux": {"initialize-database"},
    "transform-crsp-monthly": {"load-crsp-msf", "fetch-crsp-aux"},
    "load-crsp-aux": {"fetch-crsp-aux"},
    "fetch-crsp-daily": {"initialize-database"},
    "load-crsp-dsf": {"fetch-crsp-daily"},
    "fetch-ff-daily": {"initialize-database"},
    "transform-crsp-daily": {
        "load-crsp-dsf",
        "load-crsp-aux",
        "fetch-ff-daily",
        "transform-crsp-monthly",
    },
    "fetch-compustat-annual": {"initialize-database"},
    "fetch-compustat-quarterly": {"initialize-database"},
    "load-compustat": {"fetch-compustat-annual", "fetch-compustat-quarterly"},
    "transform-compustat": {"load-compustat", "transform-crsp-monthly"},
    "fetch-ff-factors": {"initialize-database"},
    "validate-bm-hml": {"transform-compustat", "fetch-ff-factors"},
    "compute-tcosts": {"transform-compustat", "transform-crsp-daily"},
    # compute-ff-tcosts and compute-car3 read ccm_link (transform-compustat).
    "compute-ff-tcosts": {"compute-tcosts", "fetch-ff-factors", "transform-compustat"},
    "compute-betas": {"transform-crsp-daily", "compute-tcosts"},
    "compute-car3": {"transform-crsp-daily", "transform-compustat", "compute-betas"},
    "compute-nmv-anomalies": {"compute-car3"},
    # Reads ccm_panel's prc/ret/me, which no compute-* stage rewrites; it
    # runs after them so that a C-Z failure cannot stop the WRDS stages.
    "fetch-cz-anomalies": {"transform-crsp-monthly"},
    "finalize": {"fetch-cz-anomalies"},
}


# Stages that hit external systems (WRDS, web). Guarded by ``allow_refetch``
# in ``rebuild`` — the fixer must never trigger a refetch.
FETCH_STAGES: frozenset = frozenset({
    "fetch-crsp-monthly",
    "fetch-crsp-aux",
    "fetch-crsp-daily",
    "fetch-ff-daily",
    "fetch-compustat-annual",
    "fetch-compustat-quarterly",
    "fetch-ff-factors",
    "fetch-cz-anomalies",
})


def stage_writes(stage: str) -> List[str]:
    """Return the tables a stage writes. Derived from TABLE_WRITER_CHAIN."""
    out: List[str] = []
    for table, chain in TABLE_WRITER_CHAIN.items():
        if stage in chain:
            out.append(table)
    return out


def stages_in_order() -> List[str]:
    """Return pipeline stage names in execution order.

    Imported lazily to avoid a circular import with ``pipeline``.
    """
    from . import pipeline  # local import to break cycle

    return [s.name for s in pipeline.STAGES]


def downstream_of(stage: str) -> List[str]:
    """Return stages that must run after ``stage`` to keep written
    tables consistent (cascade rule). Includes ``stage`` itself.

    For each table this stage writes, every later stage in that
    table's writer chain must re-run. Returned list is unique and
    ordered by pipeline execution order.
    """
    needed: Set[str] = {stage}
    for table in stage_writes(stage):
        chain = TABLE_WRITER_CHAIN[table]
        if stage not in chain:
            continue
        i = chain.index(stage)
        for downstream in chain[i:]:
            needed.add(downstream)
    order = stages_in_order()
    # Preserve execution order; include only stages present in the pipeline.
    return [s for s in order if s in needed]


def stages_for_columns(columns: List[str]) -> List[str]:
    """Map a list of columns to the set of root stages that write them.

    Downstream cascade is applied by ``pipeline.rebuild`` itself, not here.
    Unknown columns raise KeyError.
    """
    roots: List[str] = []
    seen: Set[str] = set()
    for col in columns:
        if col not in COLUMN_TO_STAGE:
            raise KeyError(
                f"unknown column {col!r} in COLUMN_TO_STAGE. A Compustat column "
                "added with `aa add-compustat-vars` is written by "
                "transform-compustat (rebuild that stage) or refreshed by running "
                "the command again."
            )
        _, stage = COLUMN_TO_STAGE[col]
        if stage not in seen:
            seen.add(stage)
            roots.append(stage)
    return roots


def stages_for_tables(tables: List[str]) -> List[str]:
    """Map a list of tables to the first writer stage for each.

    Downstream cascade is applied by ``pipeline.rebuild`` itself.
    Unknown tables raise KeyError.
    """
    roots: List[str] = []
    seen: Set[str] = set()
    for t in tables:
        if t not in TABLE_WRITER_CHAIN:
            raise KeyError(f"unknown table {t!r} in TABLE_WRITER_CHAIN")
        first = TABLE_WRITER_CHAIN[t][0]
        if first not in seen:
            seen.add(first)
            roots.append(first)
    return roots
