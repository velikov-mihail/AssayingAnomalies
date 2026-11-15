"""
Which CRSP tape a build reads, behind one interface.

CRSP froze the legacy stock tape ("SIZ", Flat File Format 1.0: ``crsp.msf``,
``crsp.dsf``, ``msedelist``, ``dsedelist``, ``mseexchdates``, ``stocknames``)
in January 2025. Everything after December 2024 exists only on the new tape
("CIZ", Flat File Format 2.0: ``crsp.msf_v2``, ``crsp.dsf_v2``,
``stkdelists``, ``stksecurityinfohist``, ``stocknames_v2``). The two tapes
disagree about table names, column names, units, the sign of ``prc``, how
share/exchange codes are encoded, and — most consequentially — whether the
monthly return already contains the delisting payoff.

**The strategy pattern, for a MATLAB reader.** In the MATLAB toolkit every one
of those facts is a literal spelled inline wherever it is needed: the table
name sits in the ``fetch`` script, the delisting overlay sits in
``makeCRSPMonthlyData.m``, and supporting a second tape would mean an ``if
strcmp(Params.crspFormat, 'ciz')`` at each of those sites. The Python analogue
of that ``if`` ladder is a *strategy object*: one class per tape, both exposing
the same method names, and the pipeline holding whichever instance the config
selected. Calling ``ctx.source.monthly_sql(cfg)`` runs the SIZ version or the
CIZ version depending only on which object was constructed — the call site
never branches, and never spells a WRDS table name again. `CRSPSource` below
is the interface (an abstract base class: it lists the methods and refuses to
be instantiated), `SIZSource` and `CIZSource` are the two implementations, and
`crsp_source_for` is the factory that reads ``config.crsp_format`` and hands
back the right one.

The practical payoff is that adding a tape is adding a subclass, and that the
SIZ behaviour is now stated in exactly one place, so it cannot drift. Every
literal in `SIZSource` is a verbatim move from `ingest/crsp.py`,
`ingest/crsp_daily.py` and `pipeline.py`; the SIZ path is byte-identical
after the refactor.

The CIZ facts encoded here were verified by querying WRDS — nothing below
assumes a CIZ column name, unit or code mapping that was not checked against
the tables. `CIZSource` is complete for both the monthly and daily paths.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import logging
from pathlib import Path
from typing import Callable, Mapping

import numpy as np
import pandas as pd

from ..config import SIZ_FROZEN_END_YEAR, VALID_CRSP_FORMATS, AssayConfig

LOGGER = logging.getLogger("assayinganomalies.ingest.crsp_source")

# The canonical column names every downstream transform consumes. A source's
# ``normalize_monthly`` is responsible for producing these from its raw tape.
CANONICAL_MONTHLY_COLUMNS: tuple[str, ...] = (
    "date", "permno", "ret", "retx", "prc", "bid", "ask", "bidlo", "askhi",
    "vol", "shrout", "cfacpr", "cfacshr", "siccd", "shrcd", "exchcd",
)


def name_window_columns(path: Path) -> tuple[str, str] | None:
    """
    The (start, end) interval columns of an MSEEXCHDATES-style staging file.

    MATLAB keys the name windows off ``namedt``/``nameendt``, so those win when
    present, and an extract carrying only the exchange-date pair falls back to
    it — the same preference order as `crsp_monthly._merge_name_windows`. Real
    CRSP has both pairs, so this picks ``namedt`` there.

    ``None`` means "no usable windows", which lets the caller take its existing
    fallback branch rather than raising inside pyarrow on a missing field. That
    covers an extract with neither pair, and an empty one: the credential-less
    placeholder written by ``_stage_fetch_crsp_aux`` declares the exchange-date
    pair but no rows, and a window table with no rows would otherwise filter
    the Gibbs expansion grid down to nothing instead of leaving it unrestricted.
    """
    try:
        import pyarrow.parquet as pq

        parquet = pq.ParquetFile(path)
        if parquet.metadata.num_rows == 0:
            return None
        names = set(parquet.schema.names)
    except Exception:  # pragma: no cover - unreadable file behaves as absent
        return None
    for start, end in (("namedt", "nameendt"), ("begexchdate", "endexchdate")):
        if {start, end, "shrcd"} <= names:
            return start, end
    return None


class CRSPSource(ABC):
    """
    One CRSP tape's table names, column names, units and semantics.

    Subclasses own every tape-specific fact. Nothing outside this module may
    hard-code a WRDS table name, a raw CRSP column name, or an assumption about
    whether the delisting overlay applies.
    """

    #: Short identifier persisted in config and stamped into the daily manifest.
    name: str = ""

    #: Whether MATLAB's delisting-replacement overlay must run. SIZ ``msf.ret``
    #: excludes the delisting payoff, so the overlay puts it back; CIZ
    #: ``mthret`` already contains it, so running the
    #: overlay would double-count it.
    apply_delisting_overlay: bool = True

    #: Whether the monthly file must be restricted to name windows from a
    #: separate table. SIZ ``msf`` is not restricted (MATLAB joins
    #: ``mseexchdates``); CIZ ``msf_v2`` carries its own as-of columns and is
    #: not restricted either, but it needs no join because the codes travel
    #: with the row.
    needs_name_window: bool = True

    #: The tape's WRDS monthly stock file and its month-end date column, which
    #: ``sample_end = "latest"`` asks for the tape's last month
    #: (`ingest.sample_end.resolve_latest_sample_end`).
    monthly_table: str = ""
    monthly_date_col: str = ""

    #: Last complete year of a tape CRSP no longer updates, or ``None`` for a
    #: live tape. "latest" resolves to at most this year, and an explicit
    #: ``sample_end`` after it is clamped to it.
    frozen_end_year: int | None = None

    def tape_end_sql(self) -> str:
        """The query for the monthly file's last month and last December."""
        col = self.monthly_date_col
        return (
            f"SELECT max({col}) AS max_date, "
            f"max({col}) FILTER (WHERE extract(month FROM {col}) = 12) AS last_december "
            f"FROM {self.monthly_table}"
        )

    @property
    @abstractmethod
    def aux_tables(self) -> dict[str, str]:
        """Auxiliary table name -> the ``SELECT`` that fetches it whole."""

    @property
    def aux_raw_files(self) -> dict[str, str]:
        """Auxiliary table name -> its staging parquet filename."""
        return {table: f"crsp_{table}_raw.parquet" for table in self.aux_tables}

    @abstractmethod
    def monthly_sql(self, config: AssayConfig) -> str:
        """The monthly stock-file query, already windowed to the sample."""

    @abstractmethod
    def daily_sql(self) -> str:
        """
        The daily stock-file query as a template.

        ``{start_date}`` / ``{end_date}`` are filled in per chunk by
        `ingest.crsp_daily.fetch_crsp_daily`.
        """

    @abstractmethod
    def normalize_monthly(
        self, raw: pd.DataFrame, *, aux: Mapping[str, pd.DataFrame] | None = None
    ) -> pd.DataFrame:
        """Rename/derive the raw monthly extract onto the canonical columns."""

    @abstractmethod
    def delist_events(self, aux: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
        """
        Monthly delisting events keyed ``permno``/``dlstdt``/``dlret``.

        Empty when the tape needs no overlay, which is what keeps
        `crsp_monthly._apply_matlab_delisting_adjustment` a no-op under CIZ.
        """

    @abstractmethod
    def daily_delist_events(
        self, load: Callable[[str], pd.DataFrame | None]
    ) -> pd.DataFrame | None:
        """
        Delisting events for MATLAB-style dlret placement in the daily panel.

        ``load`` takes an auxiliary table name and returns its staged frame (or
        ``None`` when it is missing or empty), so the source decides *which*
        table and in what preference order without doing any IO itself.
        """

    @abstractmethod
    def link_grid(
        self,
        staging_dir: Path,
        msf_file: str,
        config: AssayConfig,
        logger: logging.Logger,
    ) -> pd.DataFrame | None:
        """
        The (permno, month-end) grid Gibbs estimates are expanded onto.

        ``None`` means "no grid available", and the caller falls back to the
        ME panel keys.
        """

    @abstractmethod
    def placeholder_monthly(self, config: AssayConfig) -> pd.DataFrame:
        """A deterministic mini monthly extract, in this tape's raw columns."""

    @abstractmethod
    def placeholder_daily(self, config: AssayConfig) -> pd.DataFrame:
        """A deterministic mini daily extract, in this tape's raw columns."""

    @abstractmethod
    def placeholder_aux_schemas(self) -> dict[str, dict[str, str]]:
        """
        Column -> dtype for each auxiliary table's empty placeholder.

        DuckDB cannot register a DataFrame with 0 columns, so a credential-less
        run still needs a minimal schema per table; rows stay empty.
        """

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{type(self).__name__}(name={self.name!r})"


# ---------------------------------------------------------------------------
# SIZ — the legacy tape (Flat File Format 1.0), frozen January 2025
# ---------------------------------------------------------------------------

SIZ_MONTHLY_SQL = """
SELECT *
FROM crsp.msf
WHERE date BETWEEN '{start_date}' AND '{end_date}'
"""

# Auxiliary CRSP monthly-related tables pulled without filters (schema may vary).
SIZ_AUX_TABLES: dict[str, str] = {
    "msfhdr": "SELECT * FROM crsp.msfhdr",
    "msedelist": "SELECT * FROM crsp.msedelist",
    # Daily delisting events — MATLAB's daily pipeline uses these (not the
    # monthly ones) when placing dlret rows in the dense dret matrix
    # (getCRSPDailyData.m:82-83, makeCRSPDailyDerivedVariables.m:62-109).
    "dsedelist": "SELECT * FROM crsp.dsedelist",
    "mseexchdates": "SELECT * FROM crsp.mseexchdates",
    "stocknames": "SELECT * FROM crsp.stocknames",
    "ccmxpf_lnkhist": "SELECT * FROM crsp.ccmxpf_lnkhist",
}

# Core daily stock file — fetch prc/vol/ret/shrout plus high-low for spread estimators.
SIZ_DAILY_SQL = """
SELECT permno, date, ret, retx, prc, bid, ask,
       bidlo, askhi, vol, shrout, cfacpr, cfacshr
FROM crsp.dsf
WHERE date BETWEEN '{start_date}' AND '{end_date}'
"""

SIZ_AUX_PLACEHOLDER_SCHEMAS: dict[str, dict[str, str]] = {
    "msfhdr": {"permno": "int64"},
    "msedelist": {"permno": "int64", "dlstdt": "datetime64[ns]", "dlret": "float64"},
    "dsedelist": {
        "permno": "int64",
        "dlstdt": "datetime64[ns]",
        "dlret": "float64",
        "dlstcd": "float64",
    },
    "mseexchdates": {
        "permno": "int64",
        "begexchdate": "datetime64[ns]",
        "endexchdate": "datetime64[ns]",
        "shrcd": "float64",
        "exchcd": "float64",
    },
    "stocknames": {"permno": "int64", "namedt": "datetime64[ns]", "nameendt": "datetime64[ns]", "siccd": "float64"},
    "ccmxpf_lnkhist": {
        "gvkey": "str",
        "lpermno": "int64",
        "linktype": "str",
        "linkdt": "datetime64[ns]",
        "linkenddt": "datetime64[ns]",
    },
}


class SIZSource(CRSPSource):
    """
    The legacy CRSP tape the whole package was written against.

    Every literal here is a verbatim move from `ingest/crsp.py`,
    `ingest/crsp_daily.py` and `pipeline.py`. ``normalize_monthly`` is the
    identity because the SIZ column names *are* the canonical names.
    """

    name = "siz"
    apply_delisting_overlay = True
    needs_name_window = True
    monthly_table = "crsp.msf"
    monthly_date_col = "date"
    # Frozen by CRSP in January 2025.
    frozen_end_year = SIZ_FROZEN_END_YEAR

    @property
    def aux_tables(self) -> dict[str, str]:
        return dict(SIZ_AUX_TABLES)

    def monthly_sql(self, config: AssayConfig) -> str:
        return SIZ_MONTHLY_SQL.format(
            start_date=f"{config.sample_start}-01-01",
            end_date=f"{config.sample_end}-12-31",
        )

    def daily_sql(self) -> str:
        return SIZ_DAILY_SQL

    def normalize_monthly(
        self, raw: pd.DataFrame, *, aux: Mapping[str, pd.DataFrame] | None = None
    ) -> pd.DataFrame:
        # SIZ column names are the canonical ones; nothing to do.
        return raw

    def delist_events(self, aux: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
        return aux.get("msedelist", pd.DataFrame())

    def daily_delist_events(
        self, load: Callable[[str], pd.DataFrame | None]
    ) -> pd.DataFrame | None:
        # Prefer the daily delist file (crsp.dsedelist — what MATLAB's daily
        # pipeline reads); fall back to the monthly one for older staging dirs.
        for key in ("dsedelist", "msedelist"):
            df = load(key)
            if df is not None:
                if key == "msedelist":
                    LOGGER.warning(
                        "Daily delist file missing; falling back to monthly "
                        "msedelist for dlret placement"
                    )
                return df
        return None

    def link_grid(
        self,
        staging_dir: Path,
        msf_file: str,
        config: AssayConfig,
        logger: logging.Logger,
    ) -> pd.DataFrame | None:
        # MATLAB expands Gibbs estimates onto crsp_link — the monthly stock file
        # restricted to valid name windows and (with domComEqFlag) shrcd 10/11
        # (makeCRSPMonthlyData.m:60-95). Replicate that grid from the staging
        # files; ccm_panel keys include ~13k extra rows outside name windows.
        msf_path = staging_dir / msf_file
        ex_path = staging_dir / self.aux_raw_files["mseexchdates"]
        interval_cols = name_window_columns(ex_path) if ex_path.exists() else None
        if not (msf_path.exists() and interval_cols is not None):
            return None

        start_col, end_col = interval_cols
        msf_keys = pd.read_parquet(msf_path, columns=["permno", "date"])
        msf_keys["date"] = pd.to_datetime(msf_keys["date"])
        ex = pd.read_parquet(
            ex_path, columns=["permno", start_col, end_col, "shrcd"]
        )
        ex[start_col] = pd.to_datetime(ex[start_col])
        ex[end_col] = pd.to_datetime(ex[end_col])
        lk = msf_keys.merge(ex, on="permno", how="left")
        lk = lk[(lk["date"] >= lk[start_col]) & (lk["date"] <= lk[end_col])]
        if config.dom_com_eq:
            lk = lk[lk["shrcd"].isin([10, 11])]
        link_keys = lk[["permno", "date"]].drop_duplicates()
        # Month-end normalization to match the monthly panel convention
        link_keys["date"] = link_keys["date"] + pd.offsets.MonthEnd(0)
        link_keys = link_keys.drop_duplicates()
        logger.info("Gibbs expansion grid (crsp_link): %d rows", len(link_keys))
        return link_keys

    def placeholder_monthly(self, config: AssayConfig) -> pd.DataFrame:
        from . import crsp as crsp_ingest

        return crsp_ingest.generate_placeholder_monthly(config)

    def placeholder_daily(self, config: AssayConfig) -> pd.DataFrame:
        from . import crsp_daily as crsp_daily_ingest

        return crsp_daily_ingest.generate_placeholder_daily(config)

    def placeholder_aux_schemas(self) -> dict[str, dict[str, str]]:
        return {k: dict(v) for k, v in SIZ_AUX_PLACEHOLDER_SCHEMAS.items()}


# ---------------------------------------------------------------------------
# CIZ — the current tape (Flat File Format 2.0)
# ---------------------------------------------------------------------------

# The monthly stock file. ``msf_v2`` is ``stkmthsecuritydata`` widened with the
# ``stksecurityinfohist`` columns row-for-row, so the
# security-info codes ride along on every row and no hand join is needed here.
#
# What is *not* selected is as deliberate as what is. ``siccd`` on ``msf_v2`` is
# the **header** SIC — it reports a 2025 industry for a 1975 observation — so
# it is left on the server and the as-of value is
# joined from ``stksecurityinfohist`` in `CIZSource.normalize_monthly`. There
# are no monthly quote columns to select: ``msf_v2`` has no ``bid``/``ask``/
# ``bidlo``/``askhi``, so the monthly ``spread`` cannot be built.
#
# The re-signing of ``mthprc`` and the /100 rescale of ``mthvol`` deliberately do
# *not* happen in SQL, although they could be written as a
# ``CASE``. Keeping the staged parquet (and the ``crsp_msf`` DuckDB table) a
# faithful copy of the tape means the provenance flags and the transformed values
# can never disagree; `normalize_monthly` is the single place either conversion
# happens, and it is unit-tested.
CIZ_MONTHLY_SQL = """
SELECT permno, permco, mthcaldt,
       mthret, mthretx, mthretflg,
       mthprc, mthprcflg, mthprcdt, mthdelflg,
       mthvol, mthcap, shrout,
       mthcumfacpr, mthcumfacshr,
       cusip, ticker,
       sharetype, securitytype, securitysubtype, usincflg, issuertype,
       primaryexch, conditionaltype, tradingstatusflg
FROM crsp.msf_v2
WHERE mthcaldt BETWEEN '{start_date}' AND '{end_date}'
"""

# Auxiliary CIZ tables. ``ccmxpf_lnkhist`` is unchanged between tapes; the
# other three replace msfhdr/msedelist/dsedelist/mseexchdates/stocknames.
CIZ_AUX_TABLES: dict[str, str] = {
    "stkdelists": "SELECT * FROM crsp.stkdelists",
    "stksecurityinfohist": "SELECT * FROM crsp.stksecurityinfohist",
    "stocknames_v2": "SELECT * FROM crsp.stocknames_v2",
    "ccmxpf_lnkhist": "SELECT * FROM crsp.ccmxpf_lnkhist",
}

CIZ_AUX_PLACEHOLDER_SCHEMAS: dict[str, dict[str, str]] = {
    "stkdelists": {
        "permno": "int64",
        "delistingdt": "datetime64[ns]",
        "delret": "float64",
        "deldlydt": "datetime64[ns]",
        "delactiontype": "str",
        "delstatustype": "str",
        "delreasontype": "str",
        "delpaymenttype": "str",
    },
    "stksecurityinfohist": {
        "permno": "int64",
        "secinfostartdt": "datetime64[ns]",
        "secinfoenddt": "datetime64[ns]",
        "securityhdrflg": "str",
        "siccd": "float64",
        "sharetype": "str",
        "securitytype": "str",
        "securitysubtype": "str",
        "usincflg": "str",
        "issuertype": "str",
        "primaryexch": "str",
        "conditionaltype": "str",
        "tradingstatusflg": "str",
    },
    "stocknames_v2": {
        "permno": "int64",
        "namedt": "datetime64[ns]",
        "nameenddt": "datetime64[ns]",
        "siccd": "float64",
    },
    "ccmxpf_lnkhist": {
        "gvkey": "str",
        "lpermno": "int64",
        "linktype": "str",
        "linkdt": "datetime64[ns]",
        "linkenddt": "datetime64[ns]",
    },
}

# Raw CIZ monthly column -> canonical name, for the columns that are a plain
# rename. ``prc``, ``vol``, ``shrcd``, ``exchcd`` and ``siccd`` need work and
# are handled separately in ``CIZSource.normalize_monthly``.
CIZ_MONTHLY_RENAMES: dict[str, str] = {
    "mthcaldt": "date",
    "mthret": "ret",
    "mthretx": "retx",
    "mthcumfacpr": "cfacpr",
    "mthcumfacshr": "cfacshr",
}

# The daily stock file, aliased onto the canonical daily columns.
#
# Unlike the monthly path, which stages a faithful copy of the tape and does the
# renames in `normalize_monthly`, the daily path has no normalize hook: the
# chunked fetch in `ingest.crsp_daily` writes every chunk straight onto the
# pinned ``DAILY_SCHEMA`` (`DAILY_COLUMNS` in that module), so the query itself
# has to deliver those names in that order. That is a deliberate asymmetry, and
# it buys something: the staged daily parquet, the merge SQL, the manifest's
# ``columns`` list and the DuckDB ``crsp_dsf`` table are then identical under
# both tapes, and every daily consumer downstream — the transform, tcosts,
# betas, CAR3 — is tape-blind. The 108M-row daily file is also the one place
# where carrying ~35 unused native columns would actually cost real disk.
#
# ``prc`` is re-signed here for the same reason it is re-signed on the monthly
# side: CIZ never writes a negative price and flags a bid/ask midpoint with
# ``dlyprcflg = 'BA'`` instead (every one
# of the 44,388 negative SIZ daily prices in 2024 matches that flag). Downstream code
# reads ``prc.abs()`` and tests ``prc < 0``; emitting the bare ``dlyprc`` would
# silently change what those mean.
#
# Two columns that need *no* conversion, and it matters that this was checked:
# ``dlyvol`` is on the SIZ scale (only *monthly* volume is 100x, section 3), and
# ``shrout`` is thousands of shares on both tapes, so daily ``me = |prc| *
# shrout`` is unchanged.
#
# ``(raw expression, canonical name)`` pairs, in DAILY_COLUMNS order. Kept as
# data rather than one SQL string so the ordering contract with
# `ingest.crsp_daily.DAILY_COLUMNS` is testable without parsing SQL.
CIZ_DAILY_SELECT: tuple[tuple[str, str], ...] = (
    ("permno", "permno"),
    ("dlycaldt", "date"),
    ("dlyret", "ret"),
    ("dlyretx", "retx"),
    ("CASE WHEN dlyprcflg = 'BA' THEN -dlyprc ELSE dlyprc END", "prc"),
    ("dlybid", "bid"),
    ("dlyask", "ask"),
    ("dlylow", "bidlo"),
    ("dlyhigh", "askhi"),
    ("dlyvol", "vol"),
    ("shrout", "shrout"),
    ("dlycumfacpr", "cfacpr"),
    ("dlycumfacshr", "cfacshr"),
)

#: Raw CIZ daily column -> canonical name, for the columns that are a plain
#: rename (everything except ``permno``/``shrout``, which keep their names, and
#: ``prc``, which is an expression).
CIZ_DAILY_RENAMES: dict[str, str] = {
    raw: canonical
    for raw, canonical in CIZ_DAILY_SELECT
    if raw != canonical and raw.isidentifier()
}


def _ciz_daily_sql() -> str:
    selects = ",\n       ".join(
        raw if raw == canonical else f"{raw} AS {canonical}"
        for raw, canonical in CIZ_DAILY_SELECT
    )
    return (
        f"\nSELECT {selects}\n"
        "FROM crsp.dsf_v2\n"
        "WHERE dlycaldt BETWEEN '{start_date}' AND '{end_date}'\n"
    )


CIZ_DAILY_SQL = _ciz_daily_sql()

# CIZ monthly volume is 100x the SIZ ``msf.vol``.
# Dividing on ingest keeps ``vol`` and ``vol_x_adj`` on the SIZ scale. Daily
# volume is unchanged, so there is no daily counterpart.
CIZ_MONTHLY_VOL_SCALE = 100.0


def derive_shrcd(info: pd.DataFrame) -> pd.Series:
    """
    WRDS's documented ``shrcd`` approximation, validated against the SIZ tape.

    The common-stock screen is
    ``sharetype='NS' AND securitytype='EQTY' AND securitysubtype='COM' AND
    usincflg='Y' AND issuertype IN ('ACOR','CORP')``; within it ``ACOR`` is
    SIZ's 10 and ``CORP`` is SIZ's 11 (99.9974% agreement over 1963-2024).
    Anything the screen does not recognise gets ``NaN``, never a code — SIZ's
    ``exchcd = 0`` means "not on a listed exchange", which is a narrower thing
    than "this tape uses a venue SIZ never coded".
    """
    def _s(col: str) -> pd.Series:
        if col in info.columns:
            return info[col].astype("string").str.strip()
        return pd.Series(pd.NA, index=info.index, dtype="string")

    common = (
        _s("sharetype").eq("NS")
        & _s("securitytype").eq("EQTY")
        & _s("securitysubtype").eq("COM")
        & _s("usincflg").eq("Y")
    ).fillna(False)
    issuer = _s("issuertype")
    out = pd.Series(np.nan, index=info.index, dtype="float64")
    out[common & issuer.eq("ACOR").fillna(False)] = 10.0
    out[common & issuer.eq("CORP").fillna(False)] = 11.0
    return out


def derive_exchcd(info: pd.DataFrame) -> pd.Series:
    """
    WRDS's documented ``exchcd`` approximation, validated against the SIZ tape.

    ``conditionaltype='RW' AND tradingstatusflg='A'`` gates the mapping;
    within it ``primaryexch`` N/A/Q are SIZ's 1/2/3, exactly (the 1963-2024
    cross-tab is perfectly diagonal). Everything else — including ARCA (``R``),
    BATS (``B``), ``X`` and ``I`` — gets ``NaN``.
    """
    def _s(col: str) -> pd.Series:
        if col in info.columns:
            return info[col].astype("string").str.strip()
        return pd.Series(pd.NA, index=info.index, dtype="string")

    gate = (_s("conditionaltype").eq("RW") & _s("tradingstatusflg").eq("A")).fillna(False)
    exch = _s("primaryexch")
    out = pd.Series(np.nan, index=info.index, dtype="float64")
    for venue, code in (("N", 1.0), ("A", 2.0), ("Q", 3.0)):
        out[gate & exch.eq(venue).fillna(False)] = code
    return out


class CIZSource(CRSPSource):
    """
    The current CRSP tape (Flat File Format 2.0).

    The monthly path: real ``msf_v2`` SQL, the three CIZ
    aux tables, the rename / re-sign / rescale of `normalize_monthly`, the
    derived ``shrcd``/``exchcd``, the as-of ``siccd`` join, informational-only
    delist events and a name-window-free Gibbs grid. The daily path:
    ``dsf_v2`` SQL aliased onto the pinned daily columns, and
    `daily_delist_events` returning ``None`` because this tape's daily file
    already carries the delisting payoff as its own row.
    """

    name = "ciz"
    # CIZ ``mthret`` already contains the delisting payoff,
    # so the MATLAB overlay must not run: ``dlret`` stays informational and
    # ``ret_x_dl == ret``.
    apply_delisting_overlay = False
    # ``msf_v2`` carries the as-of security-info columns on every row, so there
    # is no separate name-window table to join.
    needs_name_window = False
    monthly_table = "crsp.msf_v2"
    monthly_date_col = "mthcaldt"

    @property
    def aux_tables(self) -> dict[str, str]:
        return dict(CIZ_AUX_TABLES)

    def monthly_sql(self, config: AssayConfig) -> str:
        return CIZ_MONTHLY_SQL.format(
            start_date=f"{config.sample_start}-01-01",
            end_date=f"{config.sample_end}-12-31",
        )

    def daily_sql(self) -> str:
        """
        ``dsf_v2``, aliased onto `ingest.crsp_daily.DAILY_COLUMNS`.

        See `CIZ_DAILY_SELECT` for why the daily path converts in SQL where the
        monthly path converts in `normalize_monthly`.
        """
        return CIZ_DAILY_SQL

    def normalize_monthly(
        self, raw: pd.DataFrame, *, aux: Mapping[str, pd.DataFrame] | None = None
    ) -> pd.DataFrame:
        """
        Map a raw ``msf_v2`` extract onto the canonical monthly columns.

        Four things are not plain renames:

        * ``prc`` — CIZ never writes a negative price; a bid/ask midpoint is
          flagged ``mthprcflg = 'BA'`` instead. Re-signing here keeps every
          downstream ``prc.abs()`` and ``prc < 0`` test behaving as under SIZ.
        * ``vol`` — ``mthvol`` is 100x SIZ's ``msf.vol``.
        * ``shrcd`` / ``exchcd`` — derived from the security-info columns.
        * ``siccd`` — must come from the as-of ``stksecurityinfohist`` row, not
          from ``msf_v2.siccd``, which is the *header* SIC.
        """
        df = raw.copy()
        df.columns = [str(c).lower() for c in df.columns]

        # Renames, not moves: ``mthret`` becomes ``ret`` and the native name is
        # gone, but every column the map does not mention (``mthcap``,
        # ``mthretflg``, ``mthdelflg``, ``mthprcflg``, ``mthprcdt``, ``permco``,
        # ``cusip``, ``ticker``, and the eight security-info code columns)
        # survives untouched. Downstream consumers only read the canonical
        # names, so the natives are pure provenance -- the SIZ path had to infer
        # a delisting month from a separate table where CIZ states it outright.
        renames = {k: v for k, v in CIZ_MONTHLY_RENAMES.items() if k in df.columns}
        df = df.rename(columns=renames)

        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
        # WRDS hands numerics back as ``Decimal`` objects in an ``object``
        # column; the transform does arithmetic on all of these.
        for col in ("ret", "retx", "shrout", "cfacpr", "cfacshr", "mthcap"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if "mthprc" in df.columns:
            prc = pd.to_numeric(df["mthprc"], errors="coerce")
            if "mthprcflg" in df.columns:
                is_ba = df["mthprcflg"].astype("string").str.strip().eq("BA").fillna(False)
                prc = prc.where(~is_ba, -prc)
            df["prc"] = prc

        if "mthvol" in df.columns:
            df["vol"] = pd.to_numeric(df["mthvol"], errors="coerce") / CIZ_MONTHLY_VOL_SCALE

        df["shrcd"] = derive_shrcd(df)
        df["exchcd"] = derive_exchcd(df)

        # ``msf_v2.siccd`` is the header SIC and would report a 2025 industry
        # for a 1975 observation; drop it in favour of the as-of value.
        df = df.drop(columns=["siccd"], errors="ignore")
        info = (aux or {}).get("stksecurityinfohist", pd.DataFrame())
        needed = {"permno", "secinfostartdt", "secinfoenddt", "siccd"}
        if not info.empty and needed <= set(info.columns):
            from ..transforms.crsp_monthly import _merge_on_interval

            windows = info[["permno", "secinfostartdt", "secinfoenddt", "siccd"]].copy()
            windows["permno"] = pd.to_numeric(windows["permno"], errors="coerce").astype("int64")
            for col in ("secinfostartdt", "secinfoenddt"):
                windows[col] = pd.to_datetime(windows[col], errors="coerce")
            windows["siccd"] = pd.to_numeric(windows["siccd"], errors="coerce")
            # A *left* interval join: a check on WRDS found 2,676 of
            # 542,216 monthly rows (2020-2024) with no security-info window at
            # all, nearly all of them delisting months sitting one day past
            # ``secinfoenddt``. Those are exactly the rows the no-overlay design
            # depends on, so they must survive with a missing ``siccd`` rather
            # than being dropped -- hence no ``drop_outside=True`` here, unlike
            # the SIZ ``mseexchdates`` merge. No row matches two windows
            # (verified in the same section), so the join cannot duplicate.
            df = _merge_on_interval(
                df, windows, "secinfostartdt", "secinfoenddt", ["siccd"]
            )
            df["siccd"] = pd.to_numeric(df["siccd"], errors="coerce")
        else:
            LOGGER.warning(
                "CIZ normalize_monthly: no usable stksecurityinfohist windows; "
                "siccd will be missing (industry buckets fall back to Other)"
            )
            df["siccd"] = np.nan
        return df

    def delist_events(self, aux: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
        """
        ``stkdelists`` on the canonical ``permno``/``dlstdt``/``dlret``/``dlstcd``.

        Informational only: `apply_delisting_overlay` is False, so nothing
        applies these to ``ret`` (``mthret`` already
        contains the delisting payoff). They exist so ``dlret`` can still be
        reported alongside the panel by
        `crsp_monthly._attach_informational_dlret`.

        **``dlstcd`` is always NaN under CIZ, on purpose.** SIZ's single numeric
        delisting code is replaced by four categorical reasons
        (``delactiontype`` / ``delstatustype`` / ``delreasontype`` /
        ``delpaymenttype``); there is no numeric code column and
        no mapping onto SIZ's integers has been verified, so
        inventing one here would be an unverified assumption. The column is
        emitted anyway so the frame
        has one shape under both tapes; the four native reason columns ride
        along for anyone who wants to classify a delisting. The only consumer of
        ``dlstcd`` is `betas._insert_matlab_dlret_rows`, which CIZ never reaches
        (`daily_delist_events` returns ``None``).
        """
        raw = aux.get("stkdelists", pd.DataFrame())
        if raw.empty:
            return raw
        df = raw.copy()
        df.columns = [str(c).lower() for c in df.columns]
        df = df.rename(columns={"delistingdt": "dlstdt", "delret": "dlret"})
        if "dlstdt" in df.columns:
            df["dlstdt"] = pd.to_datetime(df["dlstdt"], errors="coerce")
        if "dlret" in df.columns:
            df["dlret"] = pd.to_numeric(df["dlret"], errors="coerce")
        if "permno" in df.columns:
            df["permno"] = pd.to_numeric(df["permno"], errors="coerce").astype("int64")
        df["dlstcd"] = np.nan
        lead = [c for c in ("permno", "dlstdt", "dlret", "dlstcd") if c in df.columns]
        return df[lead + [c for c in df.columns if c not in lead]]

    def daily_delist_events(
        self, load: Callable[[str], pd.DataFrame | None]
    ) -> pd.DataFrame | None:
        """
        ``None``, always.

        The CIZ daily file already carries the delisting payoff as its own row
        on ``stkdelists.deldlydt``, so there is nothing for
        `betas._insert_matlab_dlret_rows` to place.
        """
        return None

    def link_grid(
        self,
        staging_dir: Path,
        msf_file: str,
        config: AssayConfig,
        logger: logging.Logger,
    ) -> pd.DataFrame | None:
        """
        The monthly keys, screened on ``shrcd`` -- but with no name-window join.

        MATLAB's ``crsp_link`` is the monthly stock file restricted to valid
        ``mseexchdates`` name windows and (under ``domComEqFlag``) to
        ``shrcd`` 10/11. Under CIZ the first restriction has no counterpart and
        must not be invented: ``msf_v2`` is not restricted to
        ``stksecurityinfohist`` windows, and the rows
        that fall outside one are almost entirely delisting months, which are
        precisely the rows this tape's no-overlay design keeps. Re-imposing a
        window join would silently drop them from the Gibbs expansion grid.

        What does survive is the ``shrcd`` screen, and it needs no join either
        because the security-info codes travel on every ``msf_v2`` row. So the
        grid here is "every monthly key, common stock only" -- the SIZ grid
        minus a restriction that does not exist on this tape.
        """
        msf_path = staging_dir / msf_file
        if not msf_path.exists():
            return None

        code_cols = [
            "sharetype", "securitytype", "securitysubtype", "usincflg", "issuertype",
        ]
        try:
            import pyarrow.parquet as pq

            available = set(pq.ParquetFile(msf_path).schema.names)
        except Exception:  # pragma: no cover - unreadable file behaves as absent
            return None

        wanted = ["permno", "mthcaldt"]
        if config.dom_com_eq:
            wanted += [c for c in code_cols if c in available]
        if not {"permno", "mthcaldt"} <= available:
            return None

        lk = pd.read_parquet(msf_path, columns=wanted)
        lk["date"] = pd.to_datetime(lk["mthcaldt"], errors="coerce")
        if config.dom_com_eq:
            shrcd = derive_shrcd(lk)
            lk = lk[shrcd.isin([10.0, 11.0])]

        link_keys = lk[["permno", "date"]].dropna().drop_duplicates()
        # Month-end normalization to match the monthly panel convention.
        link_keys["date"] = link_keys["date"] + pd.offsets.MonthEnd(0)
        link_keys = link_keys.drop_duplicates()
        logger.info("Gibbs expansion grid (ciz msf_v2 keys): %d rows", len(link_keys))
        return link_keys

    def placeholder_monthly(self, config: AssayConfig) -> pd.DataFrame:
        """A mini ``msf_v2`` extract, in raw CIZ columns."""
        d1 = pd.Timestamp(f"{config.sample_start}-01-01") + pd.offsets.MonthEnd(0)
        d2 = pd.Timestamp(f"{config.sample_start}-02-01") + pd.offsets.MonthEnd(0)
        return pd.DataFrame({
            "mthcaldt": [d1, d2],
            "permno": [10001, 10002],
            "mthret": [0.01, -0.02],
            "mthretx": [0.01, -0.02],
            "mthprc": [50.12, 12.34],
            "mthprcflg": ["", "BA"],
            "mthvol": [1_000_000.0, 500_000.0],
            "mthcap": [1.5e8, 7.2e7],
            "shrout": [3000.0, 1500.0],
            "mthcumfacpr": [1.0, 1.0],
            "mthcumfacshr": [1.0, 1.0],
            "siccd": [6020, 2834],
            "sharetype": ["NS", "NS"],
            "securitytype": ["EQTY", "EQTY"],
            "securitysubtype": ["COM", "COM"],
            "usincflg": ["Y", "Y"],
            "issuertype": ["ACOR", "CORP"],
            "primaryexch": ["N", "Q"],
            "conditionaltype": ["RW", "RW"],
            "tradingstatusflg": ["A", "A"],
        })

    def placeholder_daily(self, config: AssayConfig) -> pd.DataFrame:
        """
        A mini ``dsf_v2`` extract.

        The daily SQL aliases straight onto the pinned ``DAILY_COLUMNS``, so
        the staged daily file has the same shape
        under both tapes and the SIZ placeholder is reused verbatim.
        """
        from . import crsp_daily as crsp_daily_ingest

        return crsp_daily_ingest.generate_placeholder_daily(config)

    def placeholder_aux_schemas(self) -> dict[str, dict[str, str]]:
        return {k: dict(v) for k, v in CIZ_AUX_PLACEHOLDER_SCHEMAS.items()}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_SOURCES: dict[str, type[CRSPSource]] = {
    "siz": SIZSource,
    "ciz": CIZSource,
}

CRSP_FORMATS: tuple[str, ...] = tuple(_SOURCES)

# ``config`` validates ``crsp_format`` without importing this module (so that
# reading a config never pulls in pandas); this keeps the two lists honest.
assert CRSP_FORMATS == VALID_CRSP_FORMATS, (CRSP_FORMATS, VALID_CRSP_FORMATS)


def crsp_source_for(config: AssayConfig | str) -> CRSPSource:
    """
    The `CRSPSource` a config selects.

    Accepts a bare format string too, which is what the tests and the
    placeholder-schema helpers use.
    """
    fmt = config if isinstance(config, str) else getattr(config, "crsp_format", "siz")
    key = str(fmt or "siz").strip().lower()
    try:
        return _SOURCES[key]()
    except KeyError:
        raise ValueError(
            f"Unknown crsp_format {fmt!r}; expected one of {', '.join(CRSP_FORMATS)}"
        ) from None


__all__ = [
    "CANONICAL_MONTHLY_COLUMNS",
    "CIZSource",
    "CIZ_AUX_TABLES",
    "CIZ_DAILY_RENAMES",
    "CIZ_DAILY_SELECT",
    "CIZ_DAILY_SQL",
    "CIZ_MONTHLY_RENAMES",
    "CIZ_MONTHLY_SQL",
    "CRSPSource",
    "CRSP_FORMATS",
    "SIZSource",
    "SIZ_AUX_TABLES",
    "SIZ_DAILY_SQL",
    "SIZ_MONTHLY_SQL",
    "crsp_source_for",
    "derive_exchcd",
    "derive_shrcd",
    "name_window_columns",
]
