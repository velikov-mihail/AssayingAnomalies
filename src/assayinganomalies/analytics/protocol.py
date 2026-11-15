"""
Assay testing protocol orchestrator (MATLAB ``runTestSignal.m``).

Loads signal + library panel + CZ zoo, runs ``make_*`` in
MATLAB order, packs a ResStruct-like :class:`ProtocolResult`, and optionally
``make_res_to_print`` → ``printResults`` and the LaTeX report with its figures.
"""

from __future__ import annotations

import gc
import logging
import pickle
import re
import time
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from ..data_access import _stored_json, get_cz_signal_info, load, load_cz_anomalies
from ..session_cache import query_df
from ..signal_io import (
    SignalInfo,
    get_anomaly_signals,
    get_signal_info,
    month_end_to_yyyymm,
)
from ..logging_utils import safe_print as _safe_print
from .. import run_manifest
from ..config import scratch_dir
from ..provenance import DEMO_LABEL, provenance_payload, require_real_database
from ..transforms.anomaly_fill import check_fill_anomalies, fill_var
from ..tiebreak import NOISE_STREAM_RULE
from ..transforms.compustat import ANNUAL_LAYOUT_JUNE, ANNUAL_LAYOUT_KEY
from ..transforms.tcosts import (
    FF_TC_HELD,
    FF_TC_RECORD_KEY,
    FF_TC_RECORD_VERSION,
    FF_TC_STORED_COLS,
    ff_tc_columns,
    ff_tc_short_columns,
)
from .results import (
    FACTOR_MODELS,
    AnomBenchmarkResults,
    AnomStratResults,
    BasicSortsResults,
    CloseAnomResults,
    CombStratsResults,
    DendrogramResults,
    AnomalyScreenError,
    DendrogramSignalError,
    _basic_sort_long_short,
    dendrogram_signal_window,
    make_anom_benchmark_results,
    make_anom_strat_results,
    make_basic_sorts_results,
    make_close_anom_results,
    make_comb_strats,
    make_dendrogram_results,
    make_fmb_res,
    make_ipca_res,
    make_lasso_res,
)
from .res_to_print import PrintResults, make_res_to_print
from .sorts import check_convention

LOGGER = logging.getLogger("assayinganomalies.analytics.protocol")

__all__ = [
    "FactorCostsError",
    "ProtocolResult",
    "run_test_signal",
    "test_signal",
    "compact_res_struct",
    "require_held_factor_costs",
]


@dataclass
class ProtocolResult:
    """ResStruct-like container for the assay protocol (+ optional printResults).

    Attribute names stick to MATLAB ``ResStruct`` members where possible;
    nested objects are the Python ``make_*`` dataclasses rather than
    MATLAB structs. When ``make_print_results=True``, ``print_results`` holds
    a :class:`PrintResults` (MATLAB ``printResults``).
    """

    signal_info: SignalInfo
    signal_label: str
    test_signal: pd.Series
    time_period: tuple[int, int]
    labels: dict[str, list[str]] = field(default_factory=dict)
    res_basic_sorts: BasicSortsResults | None = None
    res_cond_me_sorts: dict | None = None
    res_anoms: AnomStratResults | None = None
    res_correls: pd.DataFrame | None = None
    res_cond_sort: dict | None = None
    res_fmbs: dict | None = None
    Z: np.ndarray | None = None
    dendrogram_labels: list[str] | None = None
    cutoff: float | None = None
    # The cluster plot's window and anomaly counts: ``window``
    # (YYYYMM, YYYYMM), ``n_months``, ``n_anoms_in``, ``n_anoms_kept``,
    # ``dropped`` (name, first and last return month).
    dendrogram_info: dict[str, Any] | None = None
    res_close_fmb: list | None = None
    res_close_span: list | None = None
    close_labels: dict[str, list[str]] | None = None
    comb_strats: CombStratsResults | None = None
    print_results: PrintResults | None = None
    filled_anoms: dict[str, pd.Series] | None = None
    keep_anoms: pd.Series | None = None
    keep_roll_anoms: pd.DataFrame | None = None
    stage_log: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    path: Path | None = None
    tex_path: Path | None = None
    # `{acronym}_manifest.json` beside the outputs; see `run_manifest`.
    manifest_path: Path | None = None

    # ---- aliases matching MATLAB field casing (read-only convenience) ----
    @property
    def signalInfo(self) -> SignalInfo:
        return self.signal_info

    @property
    def testSignal(self) -> pd.Series:
        return self.test_signal

    @property
    def timePeriod(self) -> tuple[int, int]:
        return self.time_period

    @property
    def printResults(self) -> PrintResults | None:
        return self.print_results

    def to_res_struct_dict(self) -> dict[str, Any]:
        """Flatten to a dict keyed like MATLAB ``ResStruct`` for pickling/inspection."""
        return {
            "signalInfo": self.signal_info.to_dict(),
            "signalLabel": self.signal_label,
            "testSignal": self.test_signal,
            "timePeriod": np.asarray(self.time_period, dtype=int),
            "labels": self.labels,
            "resBasicSorts": self.res_basic_sorts,
            "resCondMeSorts": self.res_cond_me_sorts,
            "resAnoms": self.res_anoms,
            "resCorrels": self.res_correls,
            "resCondSort": self.res_cond_sort,
            "resFMBs": self.res_fmbs,
            "Z": self.Z,
            "dendrogramLabels": self.dendrogram_labels,
            "cutoff": self.cutoff,
            "dendrogramInfo": self.dendrogram_info,
            "resCloseFMB": self.res_close_fmb,
            "resCloseSpan": self.res_close_span,
            "closeLabels": self.close_labels,
            "combStrats": self.comb_strats,
            "stage_log": list(self.stage_log),
            "summary": dict(self.summary),
        }


def _compact_sort_result(sr: Any, *, keep_ptf_panels: bool) -> Any:
    """Drop residual panels and (optionally) stock-count grids from a SortResult."""
    if sr is None or not hasattr(sr, "leg_returns"):
        return sr
    kwargs: dict[str, Any] = {"resid": None}
    if not keep_ptf_panels:
        kwargs["ptf_num_stocks"] = None
        kwargs["ptf_market_cap"] = None
        kwargs["factor_loadings"] = None
        kwargs["factor_loading_tstats"] = None
        kwargs["alphas"] = None
        kwargs["tstats"] = None
        kwargs["r2"] = None
        kwargs["to_ts"] = None
        kwargs["ptf_to"] = None
        kwargs["ptf_costs"] = None
    try:
        return replace(sr, **kwargs)
    except TypeError:
        return sr


def _compact_regression(reg: Any) -> Any:
    """Keep FMB means / t-stats / R²; drop the monthly beta matrix."""
    if reg is None or not hasattr(reg, "bhat"):
        return reg
    try:
        return replace(reg, beta=pd.DataFrame())
    except TypeError:
        return reg


def _finite_values_only(s: Any) -> Any:
    """Replace a stock-month panel with its finite values (RangeIndex)."""
    if s is None:
        return s
    if isinstance(s, pd.Series):
        arr = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)
        finite = arr[np.isfinite(arr)]
        return pd.Series(finite, name=s.name)
    arr = np.asarray(s, dtype=float).reshape(-1)
    return arr[np.isfinite(arr)]


def compact_res_struct(rs: dict[str, Any]) -> dict[str, Any]:
    """Drop full stock-month panels from a ResStruct dict for pickling.

    Report tables live in ``printResults``; the protocol-facing snapshot
    only needs sort/FMB *statistics* and label order, not ``filled_anoms``,
    the test-signal panel, residual grids, or combination-strategy forecasts.
    """
    out = dict(rs)
    out["testSignal"] = pd.Series(dtype="float64")

    basic = out.get("resBasicSorts")
    if basic is not None and hasattr(basic, "basic"):
        new_basic = {
            k: _compact_sort_result(v, keep_ptf_panels=True)
            for k, v in (basic.basic or {}).items()
        }
        new_cond = {
            k: _compact_sort_result(v, keep_ptf_panels=True)
            for k, v in (basic.conditional or {}).items()
        }
        new_ga = {}
        for k, v in (basic.gen_alpha or {}).items():
            if isinstance(v, dict):
                new_ga[k] = {
                    "outcome": v.get("outcome"),
                    "alpha_res": v.get("alpha_res"),
                    "w_x_y": v.get("w_x_y"),
                    "w_x": v.get("w_x"),
                }
            else:
                new_ga[k] = v
        out["resBasicSorts"] = replace(
            basic, basic=new_basic, conditional=new_cond, gen_alpha=new_ga
        )
        out["resCondMeSorts"] = new_cond

    ra = out.get("resAnoms")
    if ra is not None and hasattr(ra, "results"):
        out["resAnoms"] = replace(
            ra,
            results={
                k: _compact_sort_result(v, keep_ptf_panels=False)
                for k, v in (ra.results or {}).items()
            },
        )

    cond = out.get("resCondSort")
    if isinstance(cond, dict):
        out["resCondSort"] = {
            k: _compact_sort_result(v, keep_ptf_panels=False) for k, v in cond.items()
        }

    fmbs = out.get("resFMBs")
    if isinstance(fmbs, dict):
        out["resFMBs"] = {k: _compact_regression(v) for k, v in fmbs.items()}

    close_fmb = out.get("resCloseFMB")
    if isinstance(close_fmb, list):
        out["resCloseFMB"] = [_compact_regression(v) for v in close_fmb]

    comb = out.get("combStrats")
    if comb is not None and hasattr(comb, "strats"):
        new_strats = {}
        for k, strat in (comb.strats or {}).items():
            if hasattr(strat, "eret"):
                new_strats[k] = replace(
                    strat,
                    eret=_finite_values_only(strat.eret),
                    eret_enh=_finite_values_only(getattr(strat, "eret_enh", None)),
                )
            else:
                new_strats[k] = strat
        out["combStrats"] = replace(comb, strats=new_strats)

    return out


def _log_stage(stage_log: list[str], msg: str, *, verbose: bool) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    stage_log.append(line)
    if verbose:
        # Match MATLAB fprintf to stdout as well as logging
        _safe_print(msg)
        LOGGER.info("%s", msg)


def _log_capital_restarts(
    stage_log: list[str], what: str, metadata: Mapping[str, Any] | None, *, verbose: bool
) -> None:
    """One stage-log line per strategy whose capital hit zero or below at a trade.

    ``convention="capital"`` only: such a strategy restarts with $1 in each leg
    at that trade (``analytics/held.py``). The count comes back with each strategy's
    result, so the line is written here, in the parent process, with the
    strategy's name, whether or not the sort ran in a worker.
    """
    restarts = dict((metadata or {}).get("capital_restarts") or {})
    for name, k in restarts.items():
        _log_stage(
            stage_log,
            f"WARNING: {what} {name}: capital zero or negative at {k} trade(s); "
            "the strategy restarted there with $1 in each leg.",
            verbose=verbose,
        )
    if (metadata or {}).get("convention") == "capital":
        _log_stage(
            stage_log,
            f"Capital restarts ({what}): {len(restarts)} strateg"
            f"{'y' if len(restarts) == 1 else 'ies'}, {sum(restarts.values())} trade(s).",
            verbose=verbose,
        )


def _coerce_series(obj: pd.Series | pd.DataFrame, name: str) -> pd.Series:
    if isinstance(obj, pd.Series):
        return obj.rename(name) if obj.name is None else obj
    if isinstance(obj, pd.DataFrame):
        if name in obj.columns:
            return obj[name]
        if obj.shape[1] == 1:
            return obj.iloc[:, 0].rename(name)
        raise ValueError(f"cannot pick column {name!r} from frame with {list(obj.columns)}")
    raise TypeError(f"{name} must be Series or DataFrame")


def _resolve_test_signal(
    signal: pd.Series | pd.DataFrame | str | Path | None,
    signal_info: SignalInfo,
    *,
    panel_index: pd.MultiIndex | None,
    signal_column: str | None,
) -> pd.Series:
    if isinstance(signal, pd.Series):
        s = signal.copy()
        if not isinstance(s.index, pd.MultiIndex):
            raise ValueError("test signal Series must be MultiIndex (date, permno)")
        s.index = s.index.set_names(["date", "permno"])
        return s.astype(float)

    if isinstance(signal, pd.DataFrame):
        if signal_column is not None and signal_column in signal.columns:
            s = signal[signal_column]
        elif signal_info.SignalAcronym and signal_info.SignalAcronym in signal.columns:
            s = signal[signal_info.SignalAcronym]
        elif signal.shape[1] == 1:
            s = signal.iloc[:, 0]
        else:
            raise ValueError(
                f"ambiguous signal DataFrame columns {list(signal.columns)}; "
                "pass signal_column= or a Series"
            )
        if isinstance(s.index, pd.MultiIndex):
            s.index = s.index.set_names(["date", "permno"])
        return s.astype(float)

    # path or null → fileLink
    path: Path | None = None
    if isinstance(signal, (str, Path)):
        path = Path(signal)
    elif signal_info.fileLink:
        path = Path(signal_info.fileLink)

    if path is None:
        raise ValueError("no test signal provided and signalInfo.fileLink is empty")

    if not path.is_file():
        # try relative to cwd; common MATLAB layout
        alt = Path("AssayingAnomalies-MATLAB") / path.name
        if alt.is_file():
            path = alt
        else:
            raise FileNotFoundError(
                f"signal CSV not found: {path} (also tried {alt})"
            )

    names: Sequence[str] | None = None
    if signal_column:
        names = [signal_column]
    elif signal_info.SignalAcronym:
        # Prefer the acronym column when present
        header = list(pd.read_csv(path, nrows=0).columns)
        if signal_info.SignalAcronym in header:
            names = [signal_info.SignalAcronym]

    panel, labels = get_anomaly_signals(
        path,
        "permno",
        "dates",
        anomaly_names=names,
        panel_index=panel_index,
    )
    col = labels[0]
    return panel[col].rename(col)


def _infer_time_period(test_signal: pd.Series) -> tuple[int, int]:
    """The run's window when none is passed: the signal's first month with
    values to the last month of the panel.

    ``test_signal`` is the signal on the panel's index, so the last month of
    its index is the panel's. The window does not end with the signal's last
    value (MATLAB, and this function in earlier versions): the positions formed
    then still earn returns, for a year if the signal has values each June,
    and a window that ended with the value would cut them from every part of
    the report that is cut to the window. A signal that stops early has no
    return after one trading interval past its last trade, whatever the
    window (``held._last_return_row``).
    """
    arr = pd.to_numeric(test_signal, errors="coerce").to_numpy(dtype=float)
    finite = test_signal[np.isfinite(arr)]
    if finite.empty:
        raise ValueError("test signal has no finite observations")
    first = finite.index.get_level_values(0).min()
    last = test_signal.index.get_level_values(0).max()
    return month_end_to_yyyymm(first), month_end_to_yyyymm(last)


def _run_cz_release(db_path: str | Path | None) -> str | None:
    """The C-Z release (``"2026.10"``) of the zoo in the database this run reads.

    ``None`` when the database does not say: its zoo was built before the
    release was recorded, or from a pinned or hand-placed file of unknown
    release. The report then names no release rather than guess one.
    """
    # The database the zoo was read from. persisted_cz_release reads through
    # the session's open connection, so this works mid-run.
    path = _effective_db_path(db_path)
    if path is None:
        return None
    try:
        from ..pipeline import persisted_cz_release

        record = persisted_cz_release(path)
    except Exception:  # pragma: no cover - defensive
        LOGGER.warning("Could not read the C-Z release record of %s", path, exc_info=True)
        return None
    label = str(((record or {}).get("signals") or {}).get("release") or "")
    # Any YYYY.MM: the newest release on Hugging Face may postdate CZ_RELEASES.
    release = label if re.fullmatch(r"\d{4}\.\d{2}", label) else None
    LOGGER.info("C-Z release recorded in the database: %s", release or "none")
    return release


def _run_crsp_format(db_path: str | Path | None) -> str:
    """Which CRSP tape the panel this run reads was built from.

    The two CRSP tapes give databases whose returns, share codes and
    delisting semantics differ by construction, so a set of protocol results
    means nothing without saying which tape produced it. The database's own
    build record is the authority; the ambient config is only the fallback,
    because ``AA_CONFIG_PATH`` can point somewhere else by the time results are
    read back.
    """
    from ..config import LEGACY_CRSP_FORMAT, load_config

    path = db_path
    if path is None:
        try:
            path = load_config().database_path
        except Exception:  # pragma: no cover - defensive
            return LEGACY_CRSP_FORMAT
    try:
        from ..pipeline import _persisted_crsp_format

        built = _persisted_crsp_format(Path(path))
    except Exception:  # pragma: no cover - defensive
        built = None
    if built:
        return built
    try:
        return load_config().crsp_format
    except Exception:  # pragma: no cover - defensive
        return LEGACY_CRSP_FORMAT


def _effective_db_path(db_path: str | Path | None) -> Path | None:
    """The database a run will actually read, resolving ``None`` through config."""
    from ..config import load_config

    if db_path is not None:
        return Path(db_path)
    try:
        return Path(load_config().database_path)
    except Exception:  # pragma: no cover - defensive
        return None


# Factor-leg trading-cost columns stored next to the factors in ``ts_data``.
_FACTOR_TCOST_COLS = ("mkt_tc", "smb_tc", "hml_tc", "rmw_tc", "cma_tc", "umd_tc")

# Stages that consume the factor bundle (factor returns, rf or factor costs).
_FACTOR_STAGES = frozenset({"anom_strats", "basic_sorts", "benchmarks", "close", "comb"})


@dataclass(frozen=True)
class FactorBundle:
    """The single factor source a protocol run uses.

    Resolved once by :func:`_resolve_factor_bundle` at the top of
    :func:`run_test_signal` and handed to every stage, so ordinary sorts,
    conditional sorts, generalized alpha, spanning regressions and pool
    workers all read the same factors, risk-free rate and factor costs.
    Downstream helpers select model subsets from ``factors`` by column name
    and never reopen a database.

    ``frozen=True`` makes the attributes read-only after construction (the
    frames themselves are still ordinary mutable DataFrames).

    Attributes
    ----------
    factors : pd.DataFrame
        Date-indexed factor returns and ``rf`` under canonical names
        (``mkt``, ``smb``, ``hml``, ``mom``, ``smb2``, ``rmw``, ``cma``,
        ``rf``, as available).
    factor_tcosts : pd.DataFrame or None
        Factor-leg trading costs (``mkt_tc`` ...). ``None`` means zero factor
        costs in generalized alpha. Under ``convention="capital"`` the frame
        read from the database also has ``smb_tc_short`` .. ``umd_tc_short``,
        the cost of each factor held short, which the generalized alpha
        charges on a short position; an explicit frame may carry such columns
        too.
    source : str
        ``"explicit"`` for caller-supplied frames, otherwise the database path.
    """

    factors: pd.DataFrame
    factor_tcosts: pd.DataFrame | None
    source: str

    @property
    def rf(self) -> pd.Series | None:
        return self.factors["rf"] if "rf" in self.factors.columns else None


class FactorCostsError(RuntimeError):
    """The database's factor trading costs are not held-leg costs (an older build)."""


def require_held_factor_costs(db_path: str | Path, convention: str = "dollar") -> dict[str, int]:
    """Check that ``db_path`` can serve factor costs for ``convention``.

    The stage ``compute-ff-tcosts`` computes the factor costs on held legs,
    stores them under both conventions and records that in ``metadata``. A
    database built before that has factor costs computed on monthly drifted
    weights, and no record; pairing them with a held-leg test signal would
    price the two sides of a generalized alpha in different ways, so
    :class:`FactorCostsError` is raised, with the command that rebuilds them
    (from ``transform-compustat`` if the database also predates June-only
    annual columns, else from ``compute-ff-tcosts``).
    A database whose ``ts_data`` has no factor-cost column at all passes (the
    caller then uses zero factor costs, with a warning).

    Returns the recorded count of capital restarts per factor
    (``convention="capital"``; empty when there was none).
    """
    path = Path(db_path)
    record = _stored_json(path, "metadata", FF_TC_RECORD_KEY)
    held = isinstance(record, Mapping) and record.get("calculation") == FF_TC_HELD
    if held and record.get("version") == FF_TC_RECORD_VERSION:
        restarts = record.get("capital_restarts") or {}
        return {str(k): int(v) for k, v in restarts.items()} if convention == "capital" else {}
    present = query_df(
        path,
        "SELECT column_name FROM information_schema.columns WHERE table_name = 'ts_data'",
    )["column_name"].tolist()
    if not set(present) & set(FF_TC_STORED_COLS):
        return {}
    # A database that also predates June-only annual columns has to be rebuilt
    # from the Compustat stage: the stages after compute-ff-tcosts refuse it.
    stage = (
        "compute-ff-tcosts"
        if _stored_json(path, "metadata", ANNUAL_LAYOUT_KEY) == ANNUAL_LAYOUT_JUNE
        else "transform-compustat"
    )
    how = (
        "on held legs, but with the first purchase inside the cost series and "
        "other column names"
        if held
        else "on portfolios rebalanced to monthly drifted weights"
    )
    raise FactorCostsError(
        f"The factor trading costs in {path} were computed by an older version of "
        f"the toolkit, {how}. This "
        "version prices the factors as it prices the test signal: on held legs, "
        f"under the run's convention ({convention!r}). Rebuild them:\n"
        f"  aa setup-database --start-from {stage}\n"
        "(a few minutes; it reuses the downloaded extracts, no WRDS login), or "
        "pass factors= and factor_tcosts= explicitly."
    )


def _resolve_factor_bundle(
    factors: pd.DataFrame | None,
    factor_tcosts: pd.DataFrame | None,
    db_path: str | Path | None,
    convention: str = "dollar",
) -> FactorBundle:
    """Resolve the run's factor bundle exactly once.

    Explicit ``factors`` win and open no database; ``factor_tcosts`` is then
    taken as given. Otherwise factors and factor costs come from one
    database: ``db_path`` when given, else the configured library path. That
    path is resolved here a single time, so later stages cannot drift to a
    different ambient source.

    Factor costs read from the database are those stored for ``convention``
    (``smb_tc`` .. for ``"dollar"``, ``smb_tc_capital`` .. for ``"capital"``),
    returned under the canonical names ``mkt_tc`` .. ``umd_tc``; under
    ``"capital"`` the costs of the factors held short come with them, as
    ``smb_tc_short`` .. ``umd_tc_short``. A database
    whose factor costs are not held-leg costs raises
    :class:`FactorCostsError` (:func:`require_held_factor_costs`).
    """
    from . import sorts

    if factors is not None:
        return FactorBundle(
            factors=sorts._canonical_factor_names(factors.copy()),
            factor_tcosts=factor_tcosts,
            source="explicit",
        )

    if db_path is None:
        from ..config import load_config

        db_path = load_config().database_path
    path = Path(db_path)
    loaded = sorts.load_factors(path)

    if factor_tcosts is None:
        restarts = require_held_factor_costs(path, convention)
        if restarts:
            LOGGER.warning(
                "factor trading costs in %s: capital zero or negative at a trade of %s; "
                "those factors restarted with $1 in each side at that trade",
                path, ", ".join(f"{k.upper()} ({v})" for k, v in restarts.items()),
            )
        stored = {**ff_tc_columns(convention), **ff_tc_short_columns(convention)}
        try:
            tc = load(list(stored), path=path, panel=False, common_shares_only=False)
            tc.index = pd.to_datetime(tc.index) + pd.offsets.MonthEnd(0)
            tc = tc.rename(columns=stored)
            keep = (*_FACTOR_TCOST_COLS, *ff_tc_short_columns(convention).values())
            factor_tcosts = tc[[c for c in keep if c in tc.columns]].copy()
        except Exception as exc:
            LOGGER.warning(
                "factor tcosts unavailable in %s (%s); gen-alpha uses zero factor costs", path, exc
            )
            factor_tcosts = None

    return FactorBundle(factors=loaded, factor_tcosts=factor_tcosts, source=str(path))


def _load_library_panel(
    db_path: str | Path | None,
) -> tuple[pd.Series, pd.Series, pd.Series | None, pd.Series | None, pd.DataFrame | None, pd.DataFrame | None]:
    """Stock panel plus the factor bundle from one database (diagnostic helper).

    :func:`run_test_signal` loads the two parts separately so that the factor
    bundle is resolved only once.
    """
    ret, me, nyse, tcost = _load_library_stock_panel(db_path)
    factors = None
    factor_tcosts = None
    try:
        bundle = _resolve_factor_bundle(None, None, db_path)
        factors, factor_tcosts = bundle.factors, bundle.factor_tcosts
    except Exception as exc:
        LOGGER.warning("factor / factor-tcost load failed: %s", exc)
    return ret, me, nyse, tcost, factors, factor_tcosts


def _load_library_stock_panel(
    db_path: str | Path | None,
) -> tuple[pd.Series, pd.Series, pd.Series | None, pd.Series | None]:
    """``ret``, ``me``, ``nyse_flag`` and ``tcost`` (when present) from the library panel."""
    fields = ["ret", "me", "nyse_flag"]
    # tcost may be missing on incomplete DBs
    try:
        probe = load(["ret"], path=db_path, panel=True)
        del probe
        # Prefer including tcost if present
        from ..db.manager import DuckDBManager

        cfg_path = db_path
        if cfg_path is None:
            from ..config import load_config

            cfg_path = load_config().database_path
        with DuckDBManager(Path(cfg_path)) as mgr:
            tcols = mgr.query_df(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'ccm_panel' AND column_name IN ('tcost', 'tcost_gibbs')"
            )
            have_tcost = set(tcols["column_name"].tolist()) if not tcols.empty else set()
        if "tcost" in have_tcost:
            fields.append("tcost")
    except Exception as exc:  # pragma: no cover
        LOGGER.warning("could not probe tcost columns: %s", exc)

    panel = load(fields, path=db_path, panel=True).sort_index()
    ret = _coerce_series(panel, "ret")
    me = _coerce_series(panel, "me")
    nyse = panel["nyse_flag"] if "nyse_flag" in panel.columns else None
    tcost = panel["tcost"] if "tcost" in panel.columns else None
    return ret, me, nyse, tcost


def _load_cz_zoo(
    db_path: str | Path | None,
    *,
    max_anoms: int | None,
    dates: tuple[int, int] | None,
) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    cz = load_cz_anomalies(path=db_path, dates=dates)
    if cz.empty:
        raise RuntimeError("cz_anomalies table is empty; provide anoms= for smoke tests")
    # drop all-null columns
    n_nonnull = cz.notna().sum()
    keep_cols = [c for c in cz.columns if int(n_nonnull.get(c, 0)) > 0]
    cz = cz[keep_cols]

    acr_to_long: dict[str, str] = {}
    acr_to_cased: dict[str, str] = {}
    try:
        info = get_cz_signal_info(path=db_path)
        has_long = "LongDescription" in info.columns
        if "acronym" in info.columns:
            for _, row in info.iterrows():
                key = str(row["acronym"]).lower()
                if has_long:
                    acr_to_long[key] = str(row["LongDescription"])
                cased = row.get("acronym_cased")
                if isinstance(cased, str) and cased:
                    acr_to_cased[key] = cased
    except Exception as exc:
        LOGGER.warning("cz_signal_info unavailable (%s); using short labels as long", exc)

    # The DuckDB columns are lowercased; restore SignalDoc's acronym casing and
    # order the zoo the way MATLAB does (`[labels, I] = sort(labels)` in
    # getChenZimmermanAnomalies, i.e. a code-point sort of the CamelCase
    # acronyms). Every downstream leaf that is indexed by anomaly position --
    # resCorrels, the dendrogram linkage, Fig_Ibbots columns -- inherits this
    # order, so it has to match the reference run.
    cz = cz.rename(columns={c: acr_to_cased.get(str(c).lower(), str(c)) for c in cz.columns})
    cz = cz[sorted(str(c) for c in cz.columns)]
    if max_anoms is not None and max_anoms > 0:
        cz = cz.iloc[:, : int(max_anoms)]

    short = [str(c) for c in cz.columns]
    long_labels = [acr_to_long.get(s.lower(), s) for s in short]

    labels = {"short": short, "long": long_labels}
    return cz, labels


def _filter_labels(
    labels: dict[str, list[str]], kept_names: Sequence[str]
) -> dict[str, list[str]]:
    short = list(labels.get("short", []))
    long_ = list(labels.get("long", short))
    name_to_i = {str(s): i for i, s in enumerate(short)}
    out_s: list[str] = []
    out_l: list[str] = []
    for nm in kept_names:
        i = name_to_i.get(str(nm))
        if i is None:
            out_s.append(str(nm))
            out_l.append(str(nm))
        else:
            out_s.append(short[i])
            out_l.append(long_[i] if i < len(long_) else short[i])
    return {"short": out_s, "long": out_l}


def _comb_signal_summary(comb: CombStratsResults | None) -> dict[str, Any]:
    """Summary keys for the months the combination methods use the signal.

    ``comb_signal_start`` maps each method to the first month (YYYYMM) whose
    forecast uses the test signal (None: never); ``comb_ipca_skipped`` counts
    the months the IPCA solver skipped without and with the signal.
    """
    if comb is None:
        return {}
    md = comb.metadata or {}

    def ym(d: Any) -> int | None:
        return None if d is None else int(pd.Timestamp(d).strftime("%Y%m"))

    return {
        "comb_signal_window": md.get("signal_window"),
        "comb_signal_first_month": ym(md.get("signal_first_month")),
        "comb_signal_start": {k: ym(d) for k, d in (md.get("signal_start") or {}).items()},
        "comb_ipca_skipped": {
            leg: len(months) for leg, months in (md.get("ipca_skipped") or {}).items()
        },
    }


def _comb_signal_line(comb: CombStratsResults) -> str:
    """One stage-log line from :func:`_comb_signal_summary`."""
    sm = _comb_signal_summary(comb)
    starts = sm.get("comb_signal_start") or {}
    rest = sorted({v for k, v in starts.items() if k != "avg_rank" and v is not None})
    skipped = sm.get("comb_ipca_skipped") or {}
    return (
        "Combination strategies: signal's first month with data "
        f"{sm.get('comb_signal_first_month')}; used by the average rank from "
        f"{starts.get('avg_rank')} and by the other methods from "
        f"{rest[0] if rest else 'never'} ({sm.get('comb_signal_window')} months of data). "
        f"IPCA months skipped: {skipped.get('baseline', 0)} without the signal, "
        f"{skipped.get('enhanced', 0)} with it."
    )


def _run_test_signal(
    signal: pd.Series | pd.DataFrame | str | Path | None = None,
    metadata: Mapping[str, Any] | SignalInfo | None = None,
    **kwargs: Any,
) -> ProtocolResult:
    """
    Run the Novy-Marx / Velikov (2026) assay protocol (MATLAB ``runTestSignal``).

    Parameters
    ----------
    signal
        Test-signal panel (MultiIndex Series/DataFrame), CSV path, or ``None``
        to use ``signalInfo.fileLink``.
    metadata
        :class:`SignalInfo`, a mapping of MATLAB/Python field names, or
        ``{"info": ...}`` as produced by :class:`SignalTester`.
    **kwargs
        Keyword options (also accepted for backward-compat positional style)::

            returns, mcap, nyse_flag, tcosts, factors, factor_tcosts
              (``factors``/``factor_tcosts``, or else ``db_path``, fix the
              run's single factor bundle; see :class:`FactorBundle`)
            anoms, labels
            db_path, max_anoms, time_period
            compute_gen_alpha (default True)
            factor_models, n_close, mcap_thresh, n_roll
            out_dir, save (default False)
            verbose (default True)
            signal_column
            make_print_results (default False; True packs printResults via
              make_res_to_print — enable for full assay)
            print_tex (default False; True writes ``.tex`` + figure PDFs via
              ``print_tex_file``; implies ``make_print_results=True``)
            emit_figures (default True when print_tex; PDF emitters)
            tex_dir (default ``{out_dir}/tex``, else ``Scratch/Assay/tex`` in
              the project folder)
            compute_alpha_prctl / compute_comb_sorts (printResults options;
              only used when make_print_results=True)
            tcosts_type (stored in printResults.Text)
            convention — ``"dollar"`` (default) or ``"capital"``: the size of
              the two legs after a trade in the test-signal sorts and the zoo
              strategies (see ``run_univariate_sort``). Recorded in the
              summary, the run manifest's settings, the stage log and
              ``printResults.metadata``.
            stages — optional iterable subset:
                fill, anom_strats, basic_sorts, benchmarks, dendrogram,
                close, comb  (default: all)
            n_jobs — process-pool size for the per-anomaly loops. Default
              is ``AssayConfig.protocol_n_jobs`` or ``cpu_count - 1``.
              Pass 1 to force the serial path.

    Returns
    -------
    ProtocolResult
        In-memory ResStruct-like object with ``stage_log`` and ``summary``.
        When ``save=True``, also writes
        ``{out_dir}/{SignalAcronym}_Results.pkl`` (includes
        ``printResults`` when assembled). When ``print_tex=True``,
        ``tex_path`` points at the written ``.tex`` file.
    """
    # ---- normalize kwargs / legacy signature ----------------------------
    # Old stub: run_test_signal(signal_df, metadata)
    if "signal_df" in kwargs and signal is None:
        signal = kwargs.pop("signal_df")

    verbose = bool(kwargs.pop("verbose", True))
    db_path = kwargs.pop("db_path", None)
    # Refuse a synthetic database before anything is loaded or computed. A
    # demo build's numbers are shaped like results and mean nothing, and the
    # protocol's whole output is a report that looks publishable.
    allow_demo_data = bool(kwargs.pop("allow_demo_data", False))
    demo_data = require_real_database(
        _effective_db_path(db_path),
        allow_demo=allow_demo_data,
        what="The assay protocol",
    )
    if demo_data:
        LOGGER.warning(
            "Running the assay protocol on a demo database by explicit "
            "request. Every output of this run is labelled %r.",
            DEMO_LABEL,
        )
    max_anoms = kwargs.pop("max_anoms", None)
    time_period_kw = kwargs.pop("time_period", None)
    compute_gen_alpha = bool(kwargs.pop("compute_gen_alpha", True))
    factor_models = tuple(kwargs.pop("factor_models", FACTOR_MODELS))
    n_close_kw = kwargs.pop("n_close", None)
    mcap_thresh = float(kwargs.pop("mcap_thresh", 0.40))
    n_roll = int(kwargs.pop("n_roll", 120))
    out_dir = kwargs.pop("out_dir", None)
    save = bool(kwargs.pop("save", False))
    signal_column = kwargs.pop("signal_column", None)
    make_print_results = bool(kwargs.pop("make_print_results", False))
    print_tex = bool(kwargs.pop("print_tex", False))
    # alias of print_tex
    if "emit_tex" in kwargs:
        print_tex = bool(kwargs.pop("emit_tex")) or print_tex
    emit_figures = bool(kwargs.pop("emit_figures", True))
    tex_dir = kwargs.pop("tex_dir", None)
    if print_tex:
        make_print_results = True
    compute_alpha_prctl = bool(kwargs.pop("compute_alpha_prctl", True))
    compute_comb_sorts = bool(kwargs.pop("compute_comb_sorts", True))
    tcosts_type_kw = kwargs.pop("tcosts_type", None)
    convention = check_convention(kwargs.pop("convention", "dollar"))
    n_jobs_kw = kwargs.pop("n_jobs", None)
    from ..config import resolve_protocol_n_jobs

    n_jobs = resolve_protocol_n_jobs(n_jobs_kw)
    stages_opt = kwargs.pop("stages", None)
    all_stages = (
        "fill",
        "anom_strats",
        "basic_sorts",
        "benchmarks",
        "dendrogram",
        "close",
        "comb",
    )
    if stages_opt is None:
        stages: set[str] = set(all_stages)
    else:
        stages = {str(s) for s in stages_opt}

    returns = kwargs.pop("returns", None)
    mcap = kwargs.pop("mcap", None)
    nyse_flag = kwargs.pop("nyse_flag", None)
    tcosts = kwargs.pop("tcosts", None)
    factors = kwargs.pop("factors", None)
    factor_tcosts = kwargs.pop("factor_tcosts", None)
    anoms = kwargs.pop("anoms", None)
    labels = kwargs.pop("labels", None)
    # tolerate typos / leftover
    kwargs.pop("print_results", None)
    if kwargs:
        LOGGER.debug("unused run_test_signal kwargs: %s", sorted(kwargs))

    stage_log: list[str] = []
    t0 = time.perf_counter()
    signal_info = get_signal_info(metadata)

    # ---- run manifest: identify the inputs before anything is loaded ----
    # Only a run that writes outputs gets a manifest beside them. The database
    # is hashed here, before this run opens a DuckDB connection to it, and
    # only if the run will actually read it (panels passed in memory are
    # named instead, unhashed).
    started_at = run_manifest.utc_now()
    write_manifest = save or print_tex
    in_memory_inputs = [
        name
        for name, val in (
            ("signal", signal if isinstance(signal, (pd.Series, pd.DataFrame)) else None),
            ("returns", returns),
            ("mcap", mcap),
            ("nyse_flag", nyse_flag),
            ("tcosts", tcosts),
            ("factors", factors),
            ("factor_tcosts", factor_tcosts),
            ("anoms", anoms),
        )
        if val is not None
    ]
    manifest_db = _effective_db_path(db_path)
    reads_db = returns is None or mcap is None or anoms is None or factors is None
    db_identity: dict[str, Any] | None = None
    signal_identity: dict[str, Any] | None = None
    if write_manifest:
        if reads_db and manifest_db is not None:
            db_identity = run_manifest.file_identity(manifest_db, "database")
        signal_file = _signal_file(signal, signal_info)
        if signal_file is not None:
            signal_identity = run_manifest.file_identity(signal_file, "test signal")

    _log_stage(
        stage_log,
        f"Starting runTestSignal for {signal_info.SignalAcronym or 'signal'} "
        f"at {datetime.now():%Y-%m-%d %H:%M:%S}.",
        verbose=verbose,
    )

    # ---- library panel --------------------------------------------------
    if returns is None or mcap is None:
        _log_stage(stage_log, "Loading library panel (ret/me/nyse/tcosts) from DuckDB…", verbose=verbose)
        ret_l, me_l, nyse_l, tc_l = _load_library_stock_panel(db_path)
        if returns is None:
            returns = ret_l
        if mcap is None:
            mcap = me_l
        if nyse_flag is None:
            nyse_flag = nyse_l
        if tcosts is None:
            tcosts = tc_l

    # ---- factor bundle: resolved once, used by every stage ---------------
    # Every factor consumer below receives this bundle's frames, so no helper
    # falls back to load_factors() on the ambient default database.
    bundle: FactorBundle | None = None
    try:
        bundle = _resolve_factor_bundle(factors, factor_tcosts, db_path, convention)
    except FactorCostsError:
        raise
    except Exception as exc:
        if stages & _FACTOR_STAGES or make_print_results:
            raise RuntimeError(
                f"Could not resolve the factor bundle (db_path={db_path!r}): {exc}. "
                "Pass factors= explicitly or point db_path at a database with ts_data factors."
            ) from exc
        LOGGER.warning("factor bundle unavailable (%s); no factor stages requested", exc)
    if bundle is not None:
        factors, factor_tcosts = bundle.factors, bundle.factor_tcosts
        _log_stage(stage_log, f"Factor bundle source: {bundle.source}", verbose=verbose)

    returns = _coerce_series(returns, "ret")
    mcap = _coerce_series(mcap, "me")
    if nyse_flag is not None:
        nyse_flag = _coerce_series(nyse_flag, "nyse_flag")
    if tcosts is not None:
        tcosts = _coerce_series(tcosts, "tcost")

    # ---- test signal ----------------------------------------------------
    _log_stage(stage_log, "Loading / resolving test signal…", verbose=verbose)
    test_signal = _resolve_test_signal(
        signal,
        signal_info,
        panel_index=mcap.index if isinstance(mcap.index, pd.MultiIndex) else None,
        signal_column=signal_column,
    )
    # Align to me panel and mask stock-months without market cap (runTestSignal.m)
    test_signal = test_signal.reindex(mcap.index)
    test_signal = test_signal.where(mcap.notna())

    if time_period_kw is not None:
        tp0, tp1 = time_period_kw
        if isinstance(tp0, (pd.Timestamp, datetime)):
            time_period = (month_end_to_yyyymm(tp0), month_end_to_yyyymm(tp1))
        else:
            time_period = (int(tp0), int(tp1))
    else:
        time_period = _infer_time_period(test_signal)

    _log_stage(
        stage_log,
        f"timePeriod = [{time_period[0]}, {time_period[1]}]; n_jobs={n_jobs}; "
        f"convention={convention}",
        verbose=verbose,
    )

    # ---- CZ zoo ---------------------------------------------------------
    # The release is known only for a zoo read from the database; one passed
    # in memory has none, and the report then names no release.
    cz_release: str | None = None
    if anoms is None:
        _log_stage(stage_log, "Loading Chen–Zimmerman anomaly zoo…", verbose=verbose)
        anoms_df, labels_loaded = _load_cz_zoo(
            db_path, max_anoms=max_anoms, dates=None
        )
        cz_release = _run_cz_release(db_path)
        anoms = anoms_df
        if labels is None:
            labels = labels_loaded
    else:
        if isinstance(anoms, pd.DataFrame):
            if max_anoms is not None and max_anoms > 0:
                anoms = anoms.iloc[:, : int(max_anoms)]
            short = [str(c) for c in anoms.columns]
        elif isinstance(anoms, Mapping):
            keys = list(anoms.keys())
            if max_anoms is not None and max_anoms > 0:
                keys = keys[: int(max_anoms)]
                anoms = {k: anoms[k] for k in keys}
            short = [str(k) for k in keys]
        else:
            raise TypeError("anoms must be DataFrame or dict[str, Series]")
        if labels is None:
            labels = {"short": short, "long": list(short)}
        if max_anoms is not None and isinstance(labels.get("short"), list):
            labels = {
                "short": list(labels["short"])[: int(max_anoms)],
                "long": list(labels.get("long", labels["short"]))[: int(max_anoms)],
            }

    if not isinstance(labels, dict) or "short" not in labels:
        raise ValueError("labels must be a dict with 'short' and 'long' lists")

    # Normalize anoms → dict for fill / filter
    if isinstance(anoms, pd.DataFrame):
        anoms_dict: dict[str, pd.Series] = {str(c): anoms[c] for c in anoms.columns}
    else:
        anoms_dict = {str(k): v for k, v in anoms.items()}

    result = ProtocolResult(
        signal_info=signal_info,
        signal_label=signal_info.SignalAcronym or "SIGNAL",
        test_signal=test_signal,
        time_period=time_period,
        labels=dict(labels),
        stage_log=stage_log,
    )

    # The zoo before the coverage filter: the count the report's footnote names.
    n_zoo_loaded = len(anoms_dict)
    filled: dict[str, pd.Series] = {}
    keep = pd.Series(True, index=list(anoms_dict.keys()))
    keep_roll = pd.DataFrame()

    # ---- Stage: checkFillAnomalies --------------------------------------
    if "fill" in stages:
        _log_stage(
            stage_log,
            f"\nNow working on checking the anomalies. Run started at "
            f"{datetime.now():%Y-%m-%d %H:%M:%S}.\n",
            verbose=verbose,
        )
        filled, keep, keep_roll = check_fill_anomalies(
            anoms_dict,
            mcap,
            time_period,
            mcap_thresh=mcap_thresh,
            n_roll=n_roll,
        )
        kept_names = [nm for nm, flag in keep.items() if bool(flag)]
        if not kept_names:
            # No fallback to the unscreened anomalies: they are not the zoo
            # the report describes.
            msg = (
                f"No anomaly passes the coverage screen: of the {len(anoms_dict)} "
                f"anomalies loaded, none has values for at least {mcap_thresh:.0%} of "
                f"market capitalization in the window {time_period[0]} to "
                f"{time_period[1]} (rolling {n_roll} months). The zoo-based parts of "
                "the report need at least one anomaly. Check the window, the "
                "anomaly signals and `mcap_thresh`."
            )
            _log_stage(stage_log, f"Stopping: {msg}", verbose=verbose)
            raise AnomalyScreenError(msg)
        anoms_dict = {nm: anoms_dict[nm] for nm in kept_names}
        filled = {nm: filled[nm] for nm in kept_names if nm in filled}
        if not keep_roll.empty:
            keep_roll = keep_roll.reindex(columns=kept_names)
        labels = _filter_labels(labels, kept_names)
        result.labels = labels
        result.filled_anoms = filled
        result.keep_anoms = keep
        result.keep_roll_anoms = keep_roll
        _log_stage(
            stage_log,
            f"Kept {len(kept_names)} anomalies after >={mcap_thresh:.0%} mcap filter.",
            verbose=verbose,
        )
    else:
        filled = {nm: fill_var(s.reindex(mcap.index), mcap) for nm, s in anoms_dict.items()}
        result.filled_anoms = filled
        result.keep_anoms = keep

    short_labels = list(labels["short"])
    anoms_frame = pd.DataFrame(anoms_dict)
    # Every stage from here reads anoms_frame (a copy) or `filled`. Drop the
    # zoo as loaded, all of its columns (~8 GB at full sample), and the
    # column views that keep it alive, before the first worker pool starts.
    zoo_names = list(anoms_dict)
    anoms = anoms_df = anoms_dict = None
    gc.collect()

    # ---- Stage: makeAnomStratResults ------------------------------------
    res_anoms: AnomStratResults | None = None
    if "anom_strats" in stages:
        _log_stage(
            stage_log,
            f"\nNow working on getting the anomaly strategy results. "
            f"Run started at {datetime.now():%Y-%m-%d %H:%M:%S}.\n",
            verbose=verbose,
        )
        res_anoms = make_anom_strat_results(
            anoms_frame,
            returns,
            mcap,
            tcosts=tcosts,
            nyse_flag=nyse_flag,
            time_period=time_period,
            verbose=verbose,
            n_jobs=n_jobs,
            factors=factors,
            convention=convention,
        )
        result.res_anoms = res_anoms
        _log_capital_restarts(
            stage_log, "anomaly strategy", res_anoms.metadata, verbose=verbose
        )

    # ---- Stage: makeBasicSortsResults -----------------------------------
    res_basic: BasicSortsResults | None = None
    if "basic_sorts" in stages:
        _log_stage(
            stage_log,
            f"\nNow working on getting the basic sort results. "
            f"Run started at {datetime.now():%Y-%m-%d %H:%M:%S}.\n",
            verbose=verbose,
        )
        res_basic = make_basic_sorts_results(
            test_signal,
            returns,
            mcap,
            nyse_flag=nyse_flag,
            tcosts=tcosts,
            factor_tcosts=factor_tcosts,
            factors=factors,
            time_period=time_period,
            factor_models=factor_models,
            compute_gen_alpha=compute_gen_alpha,
            verbose=verbose,
            convention=convention,
        )
        result.res_basic_sorts = res_basic
        if "dendrogram" in stages:
            # Stop now, not after the anomaly stage, if the signal cannot be
            # placed in the cluster plot.
            try:
                _sig_ls, _ = _basic_sort_long_short(res_basic)
            except (KeyError, ValueError):
                _sig_ls = None  # the dendrogram stage reports this itself
            if _sig_ls is not None:
                try:
                    dendrogram_signal_window(
                        _sig_ls, time_period, signal_label=result.signal_label
                    )
                except DendrogramSignalError as exc:
                    _log_stage(stage_log, f"Stopping: {exc}", verbose=verbose)
                    raise
        _log_capital_restarts(
            stage_log, f"{result.signal_label} sort", res_basic.metadata, verbose=verbose
        )
        result.res_cond_me_sorts = res_basic.conditional

    # ---- Stage: makeAnomBenchmarkResults --------------------------------
    res_bench: AnomBenchmarkResults | None = None
    if "benchmarks" in stages:
        _log_stage(
            stage_log,
            f"\nNow working on anomaly correlations / conditional sorts / FMBs. "
            f"Run started at {datetime.now():%Y-%m-%d %H:%M:%S}.\n",
            verbose=verbose,
        )
        res_bench = make_anom_benchmark_results(
            anoms_frame,
            test_signal,
            returns,
            mcap,
            nyse_flag=nyse_flag,
            time_period=time_period,
            verbose=verbose,
            n_jobs=n_jobs,
            factors=factors,
        )
        result.res_correls = res_bench.correls
        result.res_cond_sort = res_bench.cond_sort
        result.res_fmbs = res_bench.fmbs

    # ---- Stage: makeDendrogramResults -----------------------------------
    if "dendrogram" in stages and res_anoms is not None and res_basic is not None:
        _log_stage(
            stage_log,
            f"\nNow working on making dendrogram data. "
            f"Run started at {datetime.now():%Y-%m-%d %H:%M:%S}.\n",
            verbose=verbose,
        )
        try:
            dend: DendrogramResults = make_dendrogram_results(
                res_anoms.results,
                result.signal_label,
                short_labels,
                res_basic,
                time_period,
                verbose=verbose,
            )
            result.Z = dend.Z
            result.dendrogram_labels = dend.labels
            result.cutoff = float(dend.cutoff)
            result.dendrogram_info = {
                "window": tuple(dend.metadata["window"]),
                "n_months": dend.metadata["n_months"],
                "n_anoms_in": dend.metadata["n_anoms_in"],
                "n_anoms_kept": dend.metadata["n_anoms_kept"],
                "dropped": dend.metadata["dropped_detail"],
            }
            info = result.dendrogram_info
            _log_stage(
                stage_log,
                f"Cluster plot: window {info['window'][0]} to {info['window'][1]} "
                f"({info['n_months']} months); {info['n_anoms_kept']} of "
                f"{info['n_anoms_in']} anomalies and {result.signal_label} are in "
                "the tree. Dropped (first to last return month): "
                + (
                    "; ".join(
                        f"{d['name']} ({d['first']} to {d['last']})"
                        for d in info["dropped"]
                    )
                    or "none"
                )
                + ".",
                verbose=verbose,
            )
        except DendrogramSignalError:
            # A cluster plot without the signal is not the plot the report
            # describes: stop the run.
            raise
        except Exception as exc:
            _log_stage(stage_log, f"Dendrogram stage failed: {exc}", verbose=verbose)
            LOGGER.exception("dendrogram failed")

    # ---- Stage: makeCloseAnomResults ------------------------------------
    if (
        "close" in stages
        and res_anoms is not None
        and res_basic is not None
        and res_bench is not None
        and len(zoo_names) > 0
    ):
        n_close = int(n_close_kw) if n_close_kw is not None else min(6, len(zoo_names))
        n_close = max(1, min(n_close, len(zoo_names)))
        _log_stage(
            stage_log,
            f"\nNow working on getting the closely-related anomaly results. "
            f"Run started at {datetime.now():%Y-%m-%d %H:%M:%S}.\n",
            verbose=verbose,
        )
        try:
            close_res: CloseAnomResults = make_close_anom_results(
                res_bench.correls,
                res_anoms.results,
                anoms_frame,
                labels,
                test_signal,
                res_basic,
                returns=returns,
                mcap=mcap,
                time_period=time_period,
                n_close=n_close,
                verbose=verbose,
                factors=factors,
            )
            result.res_close_fmb = close_res.fmb
            result.res_close_span = close_res.span
            result.close_labels = close_res.close_labels
        except Exception as exc:
            _log_stage(stage_log, f"Close-anomaly stage failed: {exc}", verbose=verbose)
            LOGGER.exception("close anoms failed")

    # ---- Stage: fillVar + makeCombStrats --------------------------------
    if "comb" in stages and res_anoms is not None and res_basic is not None:
        _log_stage(
            stage_log,
            f"\nNow working on combination strategies. "
            f"Run started at {datetime.now():%Y-%m-%d %H:%M:%S}.\n",
            verbose=verbose,
        )
        try:
            filled_signal = fill_var(test_signal, mcap)
            # make_comb_strats takes the dict as is; a DataFrame of it would be
            # a second full copy of the filled zoo (~5 GB at full sample).
            filled_input = filled if filled else anoms_frame
            if filled:
                # No later stage reads the unfilled zoo; free it for the
                # methods that run in this process.
                anoms_frame = None
                gc.collect()
            # MATLAB's makeCombStrats picks rf out of the `load ff` workspace;
            # here it has to be handed over explicitly for make_ipca_res to
            # form excess returns.
            rf = bundle.rf if bundle is not None else None
            # Checkpoint into the run's own output directory, so a killed
            # comb-strat block resumes from whichever methods finished rather
            # than starting the whole multi-hour stage again.
            comb_ckpt = Path(out_dir) if out_dir is not None else scratch_dir()
            comb = make_comb_strats(
                filled_input,
                filled_signal,
                keep_roll if not keep_roll.empty else None,
                res_anoms.results,
                res_basic,
                returns,
                time_period=time_period,
                rf=rf,
                verbose=verbose,
                n_jobs=n_jobs,
                checkpoint_dir=comb_ckpt,
                signal_window=n_roll,
                # A checkpoint in the output directory is used only if it
                # belongs to this signal, database, window and code.
                checkpoint_identity=_comb_checkpoint_identity(
                    result.signal_label,
                    test_signal,
                    manifest_db if reads_db else None,
                    time_period,
                ),
            )
            result.comb_strats = comb
            # Say when each method starts to use the signal, and how
            # many IPCA months the solver skipped (none are expected).
            _log_stage(stage_log, _comb_signal_line(comb), verbose=verbose)
        except Exception as exc:
            _log_stage(stage_log, f"Combination strategies stage failed: {exc}", verbose=verbose)
            LOGGER.exception("comb strats failed")

    # ---- summary / pack -------------------------------------------------
    elapsed = time.perf_counter() - t0
    n_zoo = len(zoo_names)
    summary = {
        "signal_acronym": result.signal_label,
        "crsp_format": _run_crsp_format(db_path),
        **provenance_payload(demo_data),
        "time_period": time_period,
        "cz_release": cz_release,
        "n_zoo_loaded": n_zoo_loaded,
        "n_anoms": n_zoo,
        "n_test_signal_finite": int(
            np.isfinite(pd.to_numeric(test_signal, errors="coerce").to_numpy(dtype=float)).sum()
        ),
        "stages": sorted(stages),
        "max_anoms": max_anoms,
        "n_jobs": n_jobs,
        "compute_gen_alpha": compute_gen_alpha,
        "convention": convention,
        "capital_restarts": {
            **{
                f"{result.signal_label}:{k}": v
                for k, v in (
                    res_basic.metadata.get("capital_restarts", {}) if res_basic else {}
                ).items()
            },
            **(res_anoms.metadata.get("capital_restarts", {}) if res_anoms else {}),
        },
        # The cost of the first purchase of each of the test signal's sorts
        # (decimal); it is not in the cost series or the net returns.
        "entry_cost": dict(res_basic.metadata.get("entry_cost", {})) if res_basic else {},
        "factor_source": bundle.source if bundle is not None else None,
        "elapsed_seconds": elapsed,
        "has_basic_sorts": result.res_basic_sorts is not None,
        "has_res_anoms": result.res_anoms is not None,
        "has_benchmarks": result.res_correls is not None,
        "has_dendrogram": result.Z is not None,
        "has_close": result.close_labels is not None,
        "has_comb": result.comb_strats is not None,
        **_comb_signal_summary(result.comb_strats),
    }
    # Optional headline Sharpe from baseline VW NYSE-5 CAPM row if available
    if result.res_basic_sorts is not None:
        key = ("vw_nyse_5", factor_models[0] if factor_models else 1)
        sr = result.res_basic_sorts.basic.get(key)
        if sr is not None and getattr(sr, "long_short", None) is not None:
            ls = sr.long_short.dropna()
            if len(ls) > 2 and float(ls.std(ddof=1)) > 0:
                summary["baseline_sharpe_ann"] = float(
                    np.sqrt(12) * ls.mean() / ls.std(ddof=1)
                )
            # The long/short strategy's average excess return (% per month).
            # `xret` has one entry per portfolio and one for "long_short";
            # the first entry is the first portfolio, not the strategy.
            xret = getattr(sr, "xret", None)
            val = None
            if isinstance(xret, pd.Series) and "long_short" in xret.index:
                try:
                    val = float(xret["long_short"])
                except (TypeError, ValueError):
                    val = None
            if val is not None and np.isfinite(val):
                summary["baseline_xret"] = val
    result.summary = summary

    # ---- makeResToPrint → printResults ----------------------------------
    if make_print_results and result.res_basic_sorts is not None:
        _log_stage(
            stage_log,
            f"\nNow working on preparing the results for printing. "
            f"Run started at {datetime.now():%Y-%m-%d %H:%M:%S}.\n",
            verbose=verbose,
        )
        try:
            pr = make_res_to_print(
                result,
                returns=returns,
                mcap=mcap,
                factors=factors,
                factor_tcosts=factor_tcosts,
                tcosts_type=tcosts_type_kw,
                compute_alpha_prctl=compute_alpha_prctl,
                compute_comb_sorts=compute_comb_sorts,
                verbose=verbose,
                convention=convention,
            )
            # Carried on `metadata` rather than `Text`, which is a MATLAB
            # printResults struct with a pinned key set. The LaTeX writer
            # reads it from here to banner the title page and to name the
            # C-Z release and zoo size in the zoo section's footnote.
            pr.metadata.update(provenance_payload(demo_data))
            pr.metadata.update({"cz_release": cz_release, "n_zoo_loaded": n_zoo_loaded})
            # The report's text reads the convention from here.
            pr.metadata["convention"] = convention
            result.print_results = pr
            result.summary["has_print_results"] = True
            if pr.Text is not None:
                result.summary["print_nAnoms"] = pr.Text.nAnoms
                result.summary["print_sharpeChar"] = pr.Text.sharpeChar
                result.summary["print_netSharpeChar"] = pr.Text.netSharpeChar
        except Exception as exc:
            _log_stage(stage_log, f"make_res_to_print failed: {exc}", verbose=verbose)
            LOGGER.exception("make_res_to_print failed")
            result.summary["has_print_results"] = False
    else:
        result.summary["has_print_results"] = False

    # ---- printTexFile → .tex + figure PDFs -------------------------------
    if print_tex and result.print_results is not None:
        from ..reporting.latex import print_tex_file

        if tex_dir is None:
            base = Path(out_dir) if out_dir is not None else scratch_dir()
            tex_dir = Path(base) / "tex"
        _log_stage(
            stage_log,
            f"\nWriting TeX / figures to {tex_dir}. "
            f"Started at {datetime.now():%Y-%m-%d %H:%M:%S}.\n",
            verbose=verbose,
        )
        try:
            tex_path = print_tex_file(
                result.print_results,
                Path(tex_dir),
                signal_acronym=result.signal_label,
                emit_figures=emit_figures,
            )
            result.tex_path = Path(tex_path)
            result.summary["has_tex"] = True
            result.summary["tex_path"] = str(result.tex_path)
            _log_stage(stage_log, f"Wrote {result.tex_path}", verbose=verbose)
        except Exception as exc:
            _log_stage(stage_log, f"print_tex_file failed: {exc}", verbose=verbose)
            LOGGER.exception("print_tex_file failed")
            result.summary["has_tex"] = False
    else:
        result.summary["has_tex"] = False

    elapsed = time.perf_counter() - t0
    result.summary["elapsed_seconds"] = elapsed

    _log_stage(
        stage_log,
        f"Done with runTestSignal for {result.signal_label} in {elapsed:.1f}s. "
        f"n_anoms={n_zoo}, timePeriod={time_period}.",
        verbose=verbose,
    )

    if save:
        if out_dir is None:
            out_dir = scratch_dir()
        out_path = Path(out_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        file_path = out_path / f"{result.signal_label}_Results.pkl"
        pr_payload = (
            result.print_results.to_dict()
            if result.print_results is not None
            else None
        )
        payload = {
            "ResStruct": compact_res_struct(result.to_res_struct_dict()),
            "printResults": pr_payload,
            "compact": True,
        }
        with open(file_path, "wb") as fh:
            pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
        result.path = file_path
        _log_stage(stage_log, f"Saved results to {file_path}", verbose=verbose)

    if write_manifest:
        result.manifest_path = _write_protocol_manifest(
            result,
            out_dir=Path(out_dir) if out_dir is not None else scratch_dir(),
            settings={
                "factor_models": list(factor_models),
                "n_close": n_close_kw,
                "mcap_thresh": mcap_thresh,
                "tcosts_type": tcosts_type_kw,
                "convention": convention,
                "make_print_results": make_print_results,
                "compute_alpha_prctl": compute_alpha_prctl,
                "compute_comb_sorts": compute_comb_sorts,
            },
            warmup=_protocol_warmup(n_roll),
            signal_identity=signal_identity,
            db_identity=db_identity,
            db_path=manifest_db if reads_db else None,
            in_memory_inputs=in_memory_inputs,
            started_at=started_at,
        )
        if result.manifest_path is not None:
            _log_stage(stage_log, f"Wrote run manifest {result.manifest_path}", verbose=verbose)

    return result


def run_test_signal(
    signal: pd.Series | pd.DataFrame | str | Path | None = None,
    metadata: Mapping[str, Any] | SignalInfo | None = None,
    **kwargs: Any,
) -> ProtocolResult:
    # The memory budget is resolved once, here, and every worker pool the run
    # starts sizes itself against it (config.pool_worker_count).
    from ..config import resolve_memory_budget_gb, run_memory_budget

    with run_memory_budget(resolve_memory_budget_gb()):
        return _run_test_signal(signal, metadata, **kwargs)


run_test_signal.__doc__ = _run_test_signal.__doc__


def _signal_file(signal: Any, signal_info: SignalInfo) -> Path | None:
    """The CSV a test signal is read from, mirroring ``_resolve_test_signal``."""
    if isinstance(signal, (str, Path)):
        path = Path(signal)
    elif signal is None and signal_info.fileLink:
        path = Path(signal_info.fileLink)
    else:
        return None
    alt = Path("AssayingAnomalies-MATLAB") / path.name
    return alt if not path.is_file() and alt.is_file() else path


def _protocol_seeds() -> dict[str, Any]:
    """Seeds the protocol runs with.

    The protocol overrides none of them, so they are read off the defaults
    of the functions it calls; a changed default shows up here without a
    second copy of the number to keep in sync.
    """
    import inspect

    def default(fn: Any, name: str) -> Any:
        return inspect.signature(fn).parameters[name].default

    return {
        "anomaly_tiebreak_jitter_seed": default(make_anom_strat_results, "noise_seed"),
        "benchmark_tiebreak_jitter_seed": default(make_anom_benchmark_results, "noise_seed"),
        # The seed of the noise that breaks ties before the anomalies are
        # ranked and filled, and how each anomaly's stream is keyed (all three).
        "anomaly_fill_jitter_seed": default(check_fill_anomalies, "seed"),
        "tiebreak_jitter_stream": NOISE_STREAM_RULE,
        "lasso_random_state": default(make_comb_strats, "lasso_random_state"),
        "lasso_cv_mode": default(make_comb_strats, "lasso_cv_mode"),
    }


def _protocol_warmup(n_roll: int) -> dict[str, int]:
    """Rolling windows (months) that must fill before a stage produces output."""
    import inspect

    def default(fn: Any) -> int:
        return int(inspect.signature(fn).parameters["roll_window"].default)

    return {
        "anomaly_coverage_window_months": int(n_roll),
        "comb_fmb_window_months": default(make_fmb_res),
        "comb_lasso_window_months": default(make_lasso_res),
        "comb_ipca_window_months": default(make_ipca_res),
    }


def _comb_checkpoint_identity(
    signal_label: str,
    test_signal: Any,
    db_path: str | Path | None,
    time_period: tuple[int, int],
) -> dict[str, Any]:
    """The run's part of a combination checkpoint's identity.

    The signal's name and the hash of its values (the manifest's
    ``signal.content_sha256``), the ``scientific_id`` of the database's build
    manifest (None for a run on panels passed in memory, or a database
    without a manifest) and the run's window. ``make_comb_strats`` adds the
    anomalies' names and the code's version and package hash.
    """
    db_id = None
    if db_path is not None:
        bpath = run_manifest.build_manifest_path(db_path)
        if bpath.is_file():
            try:
                db_id = run_manifest.read_manifest(bpath).get("scientific_id")
            except (OSError, ValueError):
                db_id = None
    return {
        "signal": signal_label,
        "signal_sha256": run_manifest.signal_content_sha256(test_signal),
        "database_scientific_id": db_id,
        "window": list(time_period),
    }


def _write_protocol_manifest(
    result: ProtocolResult,
    *,
    out_dir: Path,
    settings: dict[str, Any],
    warmup: dict[str, int],
    signal_identity: dict[str, Any] | None,
    db_identity: dict[str, Any] | None,
    db_path: Path | None,
    in_memory_inputs: list[str],
    started_at: str,
) -> Path | None:
    """Write ``{acronym}_manifest.json`` into ``out_dir``; never raises."""
    try:
        manifest = run_manifest.protocol_manifest(
            summary=result.summary,
            settings=settings,
            seeds=_protocol_seeds(),
            warmup=warmup,
            signal_file=signal_identity,
            signal_sha256=run_manifest.signal_content_sha256(result.test_signal),
            database_file=db_identity,
            db_path=db_path,
            in_memory_inputs=in_memory_inputs,
            outputs={"results_pickle": result.path, "tex": result.tex_path},
            started_at=started_at,
        )
        return run_manifest.write_manifest(
            run_manifest.protocol_manifest_path(out_dir, result.signal_label), manifest
        )
    except Exception:  # noqa: BLE001 - the receipt must not sink the run
        LOGGER.exception("Could not write the protocol run manifest")
        return None


def test_signal(
    signal: pd.Series | pd.DataFrame | str | Path | None = None,
    metadata: Mapping[str, Any] | SignalInfo | None = None,
    *,
    out_dir: str | Path | None = None,
    save: bool = True,
    make_print_results: bool = True,
    print_tex: bool = True,
    emit_figures: bool = True,
    **kwargs: Any,
) -> ProtocolResult:
    """
    High-level twin of MATLAB ``test_signal.m`` (cancel-branch defaults).

    Defaults to MPE metadata when ``metadata`` is omitted, packs ``printResults``,
    writes ``{out_dir}/{acronym}_Results.pkl``, and emits
    ``{out_dir}/tex/{acronym}.tex`` plus the eight figure PDFs.

    Parameters
    ----------
    signal
        CSV path, panel, or ``None`` (uses ``fileLink`` from metadata — default
        ``mpe.csv``; prefer absolute path to
        ``AssayingAnomalies-MATLAB/mpe.csv``).
    metadata
        :class:`SignalInfo` or mapping; ``None`` → MPE cancel-branch defaults.
    out_dir
        Default ``Scratch/Assay`` in the project folder (see
        :func:`~assayinganomalies.config.scratch_dir`; mirrors MATLAB Assay scratch).
    **kwargs
        Forwarded to :func:`run_test_signal` (e.g. ``max_anoms``, ``db_path``,
        ``time_period``, ``tcosts_type``).
    """
    info = get_signal_info(metadata)
    if out_dir is None:
        out_dir = scratch_dir()
    return run_test_signal(
        signal,
        info,
        out_dir=out_dir,
        save=save,
        make_print_results=make_print_results,
        print_tex=print_tex,
        emit_figures=emit_figures,
        **kwargs,
    )
