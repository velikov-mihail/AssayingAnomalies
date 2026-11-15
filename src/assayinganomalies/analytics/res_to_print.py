"""
Assemble ``printResults`` from a protocol ``ResStruct``-like pack.

MATLAB equivalent: ``Functions/Assay functions/makeResToPrint.m``.

Produces the nested ``Fig_*`` / ``Tab_*`` / ``Text`` / ``signalInfo``
object that the LaTeX tables and figure emitters read. Does not
write ``.tex`` or PDF figures.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from ..config import load_config
from ..signal_io import SignalInfo, month_end_to_yyyymm, yyyymm_to_month_end
from .gen_alpha import (
    GenAlphaOutcome,
    _complete_obs,
    classify_gen_alpha,
    estimate_gen_alpha,
    factor_matrix_for_gen_alpha,
    factor_short_tcosts_for_gen_alpha,
    summarize_gen_alpha_outcomes,
)
from .ols import nanols
from .results import BASIC_SORT_LABELS, FACTOR_MODELS, BasicSortsResults, CombStratsResults
from .sorts import (
    SortResult,
    _matlab_prctile,
    _matlab_style_sort_outputs,
    _resolve_factor_model,
    _time_mask,
    average_firm_size,
    run_univariate_sort,
)
from .subsamples import subsample_windows

LOGGER = logging.getLogger("assayinganomalies.analytics.res_to_print")

__all__ = [
    "PrintText",
    "PrintResults",
    "make_res_to_print",
    "invprctile",
    "yyyymm_to_pdate",
    "dates_to_pdates",
]

# Robustness table row labels (MATLAB Tab_RobustSort.PanelA/B.h).
_ROBUST_ROW_HEADERS: tuple[str, ...] = (
    "Quintile & NYSE & VW",
    "Quintile & NYSE & EW",
    "Quintile & Name & VW",
    "Quintile & Cap & VW",
    "Decile & NYSE & VW",
)

_PANEL_A_ROW_HEADERS: tuple[str, ...] = (
    r"$r^e$",
    r"$\alpha_{CAPM}$",
    r"$\alpha_{FF3}$",
    r"$\alpha_{FF4}$",
    r"$\alpha_{FF5}$",
    r"$\alpha_{FF6}$",
)

_PANEL_C_ROW_HEADERS: tuple[str, ...] = (r"$n$", r"me $(\$10^6)$")

# Factor-model column labels of Tab_SubSample.
_ALPHA_COL_LABELS: dict[int, str] = {
    1: r"$\alpha_{\text{CAPM}}$",
    3: r"$\alpha_{\text{FF3}}$",
    4: r"$\alpha_{\text{FF4}}$",
    5: r"$\alpha_{\text{FF5}}$",
    6: r"$\alpha_{\text{FF6}}$",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
def _period_or_none(period: Any) -> np.ndarray | None:
    return None if period is None else np.asarray(period, dtype=int)


def _first_last(months: np.ndarray, has: np.ndarray) -> tuple[int, int] | None:
    """First and last of ``months`` (YYYYMM) flagged in ``has``; None if none is."""
    rows = np.flatnonzero(np.asarray(has, dtype=bool))
    if rows.size == 0:
        return None
    months = np.asarray(months, dtype=int)
    return int(months[rows[0]]), int(months[rows[-1]])


@dataclass
class PrintText:
    """Prose scalars used by section writers (MATLAB ``printResults.Text``)."""

    timePeriod: np.ndarray  # shape (2,) YYYYMM ints
    nAnoms: str
    signalChar: str
    sharpeChar: str
    netSharpeChar: str
    nCloseAnoms: int
    closeAnoms: str
    closeAnomLabels: list[str]
    tcostsType: str
    # The months the signal's own numbers use, each a (first, last)
    # YYYYMM pair, or None when the signal has no such month:
    # valuePeriod: months of timePeriod in which the signal has values;
    # sortPeriod: months in which the baseline sort has a return (the sorts
    #   ignore timePeriod, as in MATLAB);
    # returnPeriod: the months of sortPeriod that lie in timePeriod.
    valuePeriod: np.ndarray | None = None
    sortPeriod: np.ndarray | None = None
    returnPeriod: np.ndarray | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "valuePeriod": _period_or_none(self.valuePeriod),
            "sortPeriod": _period_or_none(self.sortPeriod),
            "returnPeriod": _period_or_none(self.returnPeriod),
            "timePeriod": np.asarray(self.timePeriod, dtype=int),
            "nAnoms": self.nAnoms,
            "signalChar": self.signalChar,
            "sharpeChar": self.sharpeChar,
            "netSharpeChar": self.netSharpeChar,
            "nCloseAnoms": int(self.nCloseAnoms),
            "closeAnoms": self.closeAnoms,
            "closeAnomLabels": list(self.closeAnomLabels),
            "tcostsType": self.tcostsType,
        }


@dataclass
class PrintResults:
    """Container mirroring MATLAB ``printResults`` from ``makeResToPrint``."""

    Fig_Cov: dict[str, Any] = field(default_factory=dict)
    Tab_BasicSort: dict[str, Any] = field(default_factory=dict)
    Tab_RobustSort: dict[str, Any] = field(default_factory=dict)
    # Python-only: the baseline strategy over subperiods.
    Tab_SubSample: dict[str, Any] = field(default_factory=dict)
    Tab_CondSizeSort: dict[str, Any] = field(default_factory=dict)
    Fig_SharpeDist: dict[str, Any] = field(default_factory=dict)
    Fig_CondAnoms: dict[str, Any] = field(default_factory=dict)
    Fig_Correls: dict[str, Any] = field(default_factory=dict)
    Fig_Ibbots: dict[str, Any] = field(default_factory=dict)
    Fig_AlphaPrctl: dict[str, Any] = field(default_factory=dict)
    Fig_Dendrogram: dict[str, Any] = field(default_factory=dict)
    Tab_CloseFMB: dict[str, Any] = field(default_factory=dict)
    Tab_CloseSpan: dict[str, Any] = field(default_factory=dict)
    Fig_CombStrat: dict[str, Any] = field(default_factory=dict)
    Text: PrintText | None = None
    signalInfo: dict[str, Any] = field(default_factory=dict)
    # Python-only diagnostics (no MATLAB counterpart): generalized-alpha
    # outcome summaries for Tab_RobustSort Panel B ("gen_alpha_table") and
    # Fig_AlphaPrctl ("alpha_prctl").
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Flatten for pickling / inspection (MATLAB-keyed)."""
        return {
            "Fig_Cov": self.Fig_Cov,
            "Tab_BasicSort": self.Tab_BasicSort,
            "Tab_RobustSort": self.Tab_RobustSort,
            "Tab_SubSample": self.Tab_SubSample,
            "Tab_CondSizeSort": self.Tab_CondSizeSort,
            "Fig_SharpeDist": self.Fig_SharpeDist,
            "Fig_CondAnoms": self.Fig_CondAnoms,
            "Fig_Correls": self.Fig_Correls,
            "Fig_Ibbots": self.Fig_Ibbots,
            "Fig_AlphaPrctl": self.Fig_AlphaPrctl,
            "Fig_Dendrogram": self.Fig_Dendrogram,
            "Tab_CloseFMB": self.Tab_CloseFMB,
            "Tab_CloseSpan": self.Tab_CloseSpan,
            "Fig_CombStrat": self.Fig_CombStrat,
            "Text": self.Text.to_dict() if self.Text is not None else None,
            "signalInfo": dict(self.signalInfo),
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# Date / percentile helpers
# ---------------------------------------------------------------------------
def yyyymm_to_pdate(yyyymm: int | float) -> float:
    """MATLAB-style plot date: year + (month-1)/12."""
    v = int(float(yyyymm))
    y, m = divmod(v, 100)
    return float(y) + (m - 1) / 12.0


def dates_to_pdates(dates: Sequence[pd.Timestamp | int | float] | pd.Index) -> np.ndarray:
    """Vectorized ``yyyymm_to_pdate`` for Timestamps or YYYYMM ints."""
    out = np.empty(len(dates), dtype=float)
    for i, d in enumerate(dates):
        if isinstance(d, (int, float, np.integer, np.floating)) and not isinstance(
            d, (bool, np.bool_)
        ):
            # Distinguish Timestamps cast incorrectly: YYYYMM are > 190000
            val = float(d)
            if val > 1e5:
                out[i] = yyyymm_to_pdate(val)
            else:
                out[i] = val
        else:
            ts = pd.Timestamp(d)
            out[i] = float(ts.year) + (ts.month - 1) / 12.0
    return out


def invprctile(x: np.ndarray, xq: float | np.ndarray, *, plot_pos: str = "Hazen") -> np.ndarray:
    """Port of MATLAB ``invprctile`` (Hazen default) for a 1-D sample.

    Returns non-exceedance probabilities in **percent** (0–100), same as
    ``Functions/Utilities/invprctile.m``.
    """
    x = np.asarray(x, dtype=float).ravel()
    x = x[np.isfinite(x)]
    xq_arr = np.atleast_1d(np.asarray(xq, dtype=float))
    if x.size == 0:
        return np.full(xq_arr.shape, np.nan)
    if plot_pos.lower() == "hazen":
        p1, p2 = 0.5, 0.0
    elif plot_pos.lower() == "weibull":
        p1, p2 = 0.0, 1.0
    else:
        p1, p2 = 0.5, 0.0

    x_sorted = np.sort(x)
    n = x_sorted.size
    if n == 1:
        return np.where(xq_arr < x_sorted[0], 0.0, 100.0).astype(float)

    # MATLAB unique(x,'last','legacy') on ascending sample
    # Keep last occurrence of each distinct value.
    _, first_idx, counts = np.unique(x_sorted, return_index=True, return_counts=True)
    ind = first_idx + counts - 1  # last indices of each unique value
    xx = x_sorted[ind]
    pp = (np.arange(1, n + 1) - p1) / (n + p2)
    pp = pp[ind]
    p = np.interp(xq_arr, xx, pp, left=0.0, right=1.0) * 100.0
    return p.astype(float)


def _as_1d(a: Any) -> np.ndarray:
    if a is None:
        return np.array([], dtype=float)
    if isinstance(a, (pd.Series, pd.DataFrame)):
        return np.asarray(a, dtype=float).reshape(-1)
    return np.asarray(a, dtype=float).reshape(-1)


def _last(a: Any, default: float = np.nan) -> float:
    arr = _as_1d(a)
    if arr.size == 0:
        return float(default)
    return float(arr[-1])


def _wide_panel(s: pd.Series) -> pd.DataFrame:
    """MultiIndex (date, permno) Series → date × permno matrix."""
    if not isinstance(s.index, pd.MultiIndex):
        raise ValueError("panel Series must be MultiIndex (date, permno)")
    return s.unstack(level=1)


def _signal_info_dict(info: Any) -> dict[str, Any]:
    if info is None:
        return {}
    if isinstance(info, SignalInfo):
        return info.to_dict()
    if isinstance(info, Mapping):
        return dict(info)
    if hasattr(info, "to_dict"):
        return dict(info.to_dict())
    return {}


def _get_attr_or_key(obj: Any, *names: str, default: Any = None) -> Any:
    for n in names:
        if isinstance(obj, Mapping) and n in obj:
            return obj[n]
        if hasattr(obj, n):
            return getattr(obj, n)
    return default


def _unpack_res_struct(src: Any) -> dict[str, Any]:
    """Normalize ProtocolResult / dict to a flat access map."""
    if hasattr(src, "to_res_struct_dict") and hasattr(src, "res_basic_sorts"):
        # ProtocolResult — prefer attributes then dict fallbacks
        return {
            "signalInfo": src.signal_info,
            "signalLabel": src.signal_label,
            "testSignal": src.test_signal,
            "timePeriod": src.time_period,
            "labels": src.labels or {},
            "resBasicSorts": src.res_basic_sorts,
            "resCondMeSorts": src.res_cond_me_sorts
            if src.res_cond_me_sorts is not None
            else (src.res_basic_sorts.conditional if src.res_basic_sorts else None),
            "resAnoms": src.res_anoms,
            "resCorrels": src.res_correls,
            "resCondSort": src.res_cond_sort,
            "resFMBs": src.res_fmbs,
            "Z": src.Z,
            "dendrogramLabels": src.dendrogram_labels,
            "cutoff": src.cutoff,
            "dendrogramInfo": getattr(src, "dendrogram_info", None),
            "resCloseFMB": src.res_close_fmb,
            "resCloseSpan": src.res_close_span,
            "closeLabels": src.close_labels,
            "combStrats": src.comb_strats,
        }
    if isinstance(src, Mapping):
        return dict(src)
    raise TypeError(
        "make_res_to_print expects ProtocolResult or a ResStruct-like mapping"
    )


def _basic_sorts(obj: Any) -> BasicSortsResults:
    if isinstance(obj, BasicSortsResults):
        return obj
    if isinstance(obj, Mapping) and "basic" in obj:
        # already-expanded dict-ish — not supported fully
        raise TypeError("resBasicSorts must be a BasicSortsResults instance")
    raise TypeError(f"unsupported resBasicSorts type: {type(obj)}")


def _anom_results_dict(res_anoms: Any, labels_short: list[str]) -> dict[str, SortResult | None]:
    """Map anomaly name → SortResult (preserve label order)."""
    if res_anoms is None:
        return {nm: None for nm in labels_short}
    if hasattr(res_anoms, "results") and isinstance(res_anoms.results, dict):
        raw = res_anoms.results
    elif isinstance(res_anoms, dict):
        raw = res_anoms
    else:
        raw = {}
    out: dict[str, SortResult | None] = {}
    for nm in labels_short:
        out[nm] = raw.get(nm)
    # append any extras not in labels
    for nm, v in raw.items():
        if nm not in out:
            out[nm] = v
    return out


def _anom_tcosts_ts(sr: SortResult | None, index: pd.Index | None = None) -> pd.Series | None:
    """Portfolio L/S tcosts for an anomaly ``SortResult``.

    Prefer ``sr.tcosts_ts``. Fall back to ``metadata['tcosts_ts']`` (older
    Path B packs) or ``long_short - long_short_net`` when costs were applied
    but not stored on the dedicated field.
    """
    if sr is None:
        return None
    tc = getattr(sr, "tcosts_ts", None)
    if tc is None:
        meta = getattr(sr, "metadata", None) or {}
        if isinstance(meta, dict):
            tc = meta.get("tcosts_ts")
    if tc is None:
        ls = getattr(sr, "long_short", None)
        lsn = getattr(sr, "long_short_net", None)
        if ls is not None and lsn is not None:
            tc = ls.astype(float) - pd.Series(lsn).reindex(ls.index).astype(float)
    if tc is None:
        return None
    ser = pd.Series(tc).astype(float)
    if index is not None:
        ser = ser.reindex(index).astype(float)
    return ser


def _ls_return_series(sr: SortResult | None) -> pd.Series | None:
    if sr is None:
        return None
    if sr.long_short is not None:
        return sr.long_short.astype(float)
    pret = getattr(sr, "pret", None)
    if pret is not None and isinstance(pret, pd.DataFrame) and pret.shape[1] > 0:
        return pret.iloc[:, -1].astype(float)
    return None


def _factor_loadings_b_t(sr: SortResult) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Return (b, t, labels) with factors on rows, portfolios on columns."""
    fl = sr.factor_loadings
    flt = sr.factor_loading_tstats
    if fl is None:
        return np.full((0, 0), np.nan), np.full((0, 0), np.nan), []
    if isinstance(fl, pd.DataFrame):
        # Drop any non-factor columns; portfolios = index; factors = columns.
        b = fl.to_numpy(dtype=float).T  # factors × portfolios
        labels = [str(c).upper() for c in fl.columns]
        if flt is not None and isinstance(flt, pd.DataFrame):
            t = flt.reindex(index=fl.index, columns=fl.columns).to_numpy(dtype=float).T
        else:
            t = np.full_like(b, np.nan)
        return b, t, labels
    # Mapping / matlab-style with .b / .t / .label
    b = np.asarray(_get_attr_or_key(fl, "b", default=np.array([])), dtype=float)
    t = np.asarray(
        _get_attr_or_key(fl, "t", default=_get_attr_or_key(flt, "t", default=np.array([]))),
        dtype=float,
    )
    labels_raw = _get_attr_or_key(fl, "label", "labels", default=[])
    labels = [str(x).upper() for x in list(labels_raw)]
    if b.ndim == 2 and b.shape[0] > b.shape[1]:
        # already factors × ptf?
        pass
    elif b.ndim == 2:
        b = b.T
        if t.ndim == 2:
            t = t.T
    return b, t, labels


def _gen_alpha_outcome(basic: BasicSortsResults, label: str, f: int) -> GenAlphaOutcome:
    """Stored generalized-alpha outcome for one basic-sort cell.

    Results saved before outcomes were recorded are classified from their
    stored ``alpha_res`` and ``w_x_y`` (and the stored inputs, when present,
    for the sample-size check).
    """
    ga = basic.gen_alpha.get((label, f))
    if not ga or not isinstance(ga, Mapping):
        return GenAlphaOutcome("unavailable", reason="generalized alpha not computed")
    stored = ga.get("outcome")
    if isinstance(stored, Mapping):
        return GenAlphaOutcome.from_dict(stored)
    n_obs = -1
    inputs = [ga.get(k) for k in ("anom_ret", "anom_tcosts", "factor_rets", "factor_tcosts")]
    if all(x is not None for x in inputs):
        try:
            n_obs = _complete_obs(*inputs)
        except Exception:  # noqa: BLE001 -- unknown sample size skips the check
            n_obs = -1
    return classify_gen_alpha(ga.get("alpha_res"), ga.get("w_x_y"), n_obs)


def _net_sharpe(netpret: pd.Series | np.ndarray | None) -> float:
    if netpret is None:
        return float("nan")
    arr = np.asarray(pd.Series(netpret).astype(float), dtype=float).ravel()
    arr = arr[np.isfinite(arr)]
    if arr.size < 2:
        return float("nan")
    sd = float(np.std(arr, ddof=1))  # MATLAB default N-1
    if sd <= 0 or not np.isfinite(sd):
        return float("nan")
    return float(np.sqrt(12.0) * float(np.mean(arr)) / sd)


def _sub_sample_table(
    basic: BasicSortsResults,
    models: Sequence[int],
    time_period: tuple[int, int],
    *,
    factors: pd.DataFrame | None,
    row_label: str = "vw_nyse_5",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns and alphas of the Table 1 strategy over the full sample and subperiods.

    No MATLAB counterpart. The long-short return of the baseline sort
    (``row_label``) is cut to ``time_period`` (the basic sorts themselves ignore
    it) and to its first and last valid month, then split into
    :func:`~assayinganomalies.analytics.subsamples.subsample_windows`. Each row
    (the full sample first) is estimated as in Table 1: column 0 the average
    excess return, column j+1 the alpha on ``models[j]``, both in % per month,
    with classical OLS t-stats. A cell that cannot be estimated is NaN and is
    listed in the returned issues.
    """
    issues: dict[str, Any] = {"n_sub": 0, "periods": [], "issues": []}
    empty = {
        "a": np.zeros((0, 0)),
        "tA": np.zeros((0, 0)),
        "h": [],
        "cols": [],
        "periods": [],
        "n_sub": 0,
    }
    sr = basic.basic.get((row_label, models[0]))
    ls = getattr(sr, "long_short", None) if sr is not None else None
    if ls is None:
        issues["issues"].append({"key": "all", "reason": f"no {row_label} long-short series"})
        return empty, issues
    ls = pd.Series(ls, dtype=float)
    ls = ls[_time_mask(ls.index, time_period)]
    valid = ls.index[np.isfinite(ls.to_numpy())]
    if valid.empty:
        issues["issues"].append({"key": "all", "reason": "no finite long-short returns"})
        return empty, issues
    ls = ls.loc[valid[0] : valid[-1]]

    try:
        windows = subsample_windows(ls.index)
    except ValueError as exc:
        LOGGER.warning("subsample table: %s", exc)
        windows = []
        issues["issues"].append({"key": "windows", "reason": str(exc)})
    yyyymm = np.array([month_end_to_yyyymm(d) for d in ls.index], dtype=int)
    segments = [ls] + [ls[(yyyymm >= s) & (yyyymm <= e)] for s, e in windows]
    h = ["Full sample"] + [f"{s}--{e}" for s, e in windows]
    cols = [r"$r^e$"] + [_ALPHA_COL_LABELS.get(int(m), f"model {m}") for m in models]

    a = np.full((len(segments), len(models) + 1), np.nan)
    t = np.full_like(a, np.nan)
    for j, m in enumerate(models):
        try:
            f_full = _resolve_factor_model(ls.index, m, factors=factors)
        except Exception as exc:  # noqa: BLE001 -- recorded, column stays NaN
            reason = f"{type(exc).__name__}: {exc}"
            issues["issues"].append({"key": ("all", m), "reason": reason})
            LOGGER.warning("subsample table: factor model %s unavailable: %s", m, reason)
            continue
        for i, seg in enumerate(segments):
            try:
                stats = _matlab_style_sort_outputs(
                    seg.to_frame("long_short"),
                    factors=f_full.reindex(seg.index),
                    robust_se=False,
                    input_is_excess=True,
                )
            except Exception as exc:  # noqa: BLE001 -- recorded, row stays NaN
                reason = f"{type(exc).__name__}: {exc}"
                issues["issues"].append({"key": (h[i], m), "reason": reason})
                LOGGER.warning("subsample table failed %s model %s: %s", h[i], m, reason)
                continue
            if j == 0:
                a[i, 0] = _last(stats["xret"])
                t[i, 0] = _last(stats["txret"])
            a[i, j + 1] = _last(stats["alpha"])
            t[i, j + 1] = _last(stats["talpha"])

    issues["n_sub"] = len(windows)
    issues["periods"] = list(windows)
    table = {
        "a": a,
        "tA": t,
        "h": h,
        "cols": cols,
        "periods": list(windows),
        "n_sub": len(windows),
    }
    return table, issues


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------
def make_res_to_print(
    res_struct: Any,
    *,
    returns: pd.Series | None = None,
    mcap: pd.Series | None = None,
    factors: pd.DataFrame | None = None,
    factor_tcosts: pd.DataFrame | None = None,
    tcosts_type: str | None = None,
    dates: Sequence[pd.Timestamp] | pd.Index | None = None,
    compute_alpha_prctl: bool = True,
    compute_comb_sorts: bool = True,
    verbose: bool = True,
    convention: str = "dollar",
) -> PrintResults:
    """Port of MATLAB ``makeResToPrint(ResStruct)``.

    ``convention`` (``"capital"`` or ``"dollar"``) is passed to the decile
    sorts on the combination signals (``Fig_CombStrat``), the only sorts run
    here; the protocol passes the convention of its run.

    Parameters
    ----------
    res_struct
        :class:`~assayinganomalies.analytics.protocol.ProtocolResult` or a
        mapping with MATLAB ``ResStruct`` keys.
    returns, mcap
        Stock return / market-cap panels (MultiIndex date, permno). Required
        for ``Fig_CombStrat`` and full ``Fig_Cov`` Panel B. If omitted, those
        fields are left empty or partial.
    factors, factor_tcosts
        Factor returns / costs for ``Fig_AlphaPrctl`` net gen-α. When omitted
        and ``compute_alpha_prctl``, factors are loaded from the library DB.
    tcosts_type
        String stored in ``Text.tcostsType`` (MATLAB ``tcostsType``). Defaults
        to ``AssayConfig.tcosts_type``.
    dates
        Full library month-end date index. Inferred from ``mcap`` / ``returns``
        / ``test_signal`` when omitted.
    compute_alpha_prctl
        If False, skip the per-anomaly gross/net α percentile block (slow on
        full zoo).
    compute_comb_sorts
        If False, skip decile VW sorts of combination forecasts.

    Returns
    -------
    PrintResults
    """
    if verbose:
        LOGGER.info(
            "Now working on preparing the results for printing. Run started at %s.",
            datetime.now().isoformat(timespec="seconds"),
        )
        print(
            f"\nNow working on preparing the results for printing. "
            f"Run started at {datetime.now():%Y-%m-%d %H:%M:%S}.\n",
            flush=True,
        )

    rs = _unpack_res_struct(res_struct)
    basic = _basic_sorts(rs["resBasicSorts"])
    labels = rs.get("labels") or {}
    short_labels = list(labels.get("short") or [])
    close_labels = rs.get("closeLabels") or rs.get("close_labels") or {"long": [], "short": []}
    if not isinstance(close_labels, Mapping):
        close_labels = {"long": list(close_labels), "short": list(close_labels)}
    close_long = list(close_labels.get("long") or [])
    signal_label = str(rs.get("signalLabel") or rs.get("signal_label") or "SIGNAL")
    tp_raw = rs.get("timePeriod") if rs.get("timePeriod") is not None else rs.get("time_period")
    if tp_raw is None:
        raise ValueError("ResStruct missing timePeriod")
    tp_arr = np.asarray(tp_raw, dtype=int).ravel()
    time_period = (int(tp_arr[0]), int(tp_arr[-1]))

    test_signal = rs.get("testSignal") if rs.get("testSignal") is not None else rs.get("test_signal")
    if test_signal is None:
        raise ValueError("ResStruct missing testSignal")
    if not isinstance(test_signal, pd.Series):
        raise TypeError("testSignal must be a MultiIndex Series")

    row0 = BASIC_SORT_LABELS[0]
    models = tuple(basic.metadata.get("factor_models", FACTOR_MODELS))
    if not models:
        models = FACTOR_MODELS

    # Library dates aligned to panel index
    if dates is None:
        if mcap is not None and isinstance(mcap.index, pd.MultiIndex):
            dates = mcap.index.get_level_values(0).unique().sort_values()
        elif returns is not None and isinstance(returns.index, pd.MultiIndex):
            dates = returns.index.get_level_values(0).unique().sort_values()
        else:
            dates = test_signal.index.get_level_values(0).unique().sort_values()
    dates = pd.DatetimeIndex(pd.to_datetime(list(dates))).sort_values().unique()
    yyyymm = np.array([month_end_to_yyyymm(d) for d in dates], dtype=int)
    pdates = dates_to_pdates(dates)

    # Align test_signal / me wide panels on library dates
    sig_wide = _wide_panel(test_signal.astype(float))
    sig_wide = sig_wide.reindex(dates)
    me_wide = None
    if mcap is not None:
        me_wide = _wide_panel(mcap.astype(float)).reindex(dates)

    results = PrintResults()
    results.signalInfo = _signal_info_dict(rs.get("signalInfo") or rs.get("signal_info"))

    # ---- Figure coverage (Fig_Cov) ----------------------------------------
    # MATLAB: [prctile(testSignal, [25 50 75], 2) mean(testSignal, 2, 'omitnan')]
    sig_mat = sig_wide.to_numpy(dtype=float)
    quartiles = np.array([_matlab_prctile(row, [25.0, 50.0, 75.0]) for row in sig_mat])
    y_a = np.column_stack([quartiles, np.nanmean(sig_mat, axis=1)])
    # The x-axis covers the months of the sample in which the signal has
    # values (MATLAB: the whole of timePeriod, empty before a signal
    # that starts late). A signal without a value in the sample keeps
    # MATLAB's axis.
    in_sample = (yyyymm >= time_period[0]) & (yyyymm <= time_period[1])
    value_period = _first_last(yyyymm, in_sample & np.isfinite(sig_mat).any(axis=1))
    xlim_ym = value_period if value_period is not None else time_period
    xlim_idx = np.isin(yyyymm, xlim_ym)
    xlim_p = pdates[xlim_idx]
    if xlim_p.size < 2:
        # fallback: endpoints of the period (a one-month period included)
        xlim_p = np.array(
            [yyyymm_to_pdate(xlim_ym[0]), yyyymm_to_pdate(xlim_ym[1])],
            dtype=float,
        )
    results.Fig_Cov = {
        "PanelA": {
            "x": pdates.copy(),
            "y": y_a,
            "xlim": xlim_p.copy(),
        },
        "PanelB": {
            "x": pdates.copy(),
            "y": np.full((len(dates), 2), np.nan),
            "xlim": xlim_p.copy(),
        },
    }
    if me_wide is not None:
        me_arr = me_wide.to_numpy(dtype=float)
        sig_arr = sig_wide.to_numpy(dtype=float)
        finite_sig = np.isfinite(sig_arr)
        finite_me = np.isfinite(me_arr)
        with np.errstate(invalid="ignore", divide="ignore"):
            cover_n = finite_sig.sum(axis=1) / np.maximum(finite_me.sum(axis=1), 1)
            me_sig = np.where(finite_sig, me_arr, np.nan)
            cover_me = np.nansum(me_sig, axis=1) / np.maximum(np.nansum(me_arr, axis=1), 1e-16)
        results.Fig_Cov["PanelB"]["y"] = np.column_stack([cover_n, cover_me])

    # ---- Table 1 Tab_BasicSort ------------------------------------------
    r0 = basic.basic[(row0, models[0])]
    alpha_rows = [np.asarray(r0.xret, dtype=float).reshape(-1)]
    t_rows = [np.asarray(r0.txret, dtype=float).reshape(-1)]
    for f in models:
        rf = basic.basic[(row0, f)]
        alpha_rows.append(np.asarray(rf.alpha, dtype=float).reshape(-1))
        t_rows.append(np.asarray(rf.talpha, dtype=float).reshape(-1))
    panel_a = {
        "a": np.vstack(alpha_rows),
        "tA": np.vstack(t_rows),
        "h": list(_PANEL_A_ROW_HEADERS),
    }
    # Panel B: MATLAB resBasicSorts(1, 5) → 5th factor-model column = models[4]
    f_panel_b = models[min(4, len(models) - 1)]
    r_ff = basic.basic[(row0, f_panel_b)]
    b_mat, t_mat, fl_labels = _factor_loadings_b_t(r_ff)
    panel_b = {
        "a": b_mat,
        "tA": t_mat,
        "h": [rf"$\beta_{{\text{{{lab}}}}}$" for lab in fl_labels],
    }
    ptf_n = np.asarray(r0.ptf_num_stocks, dtype=float)
    ptf_me = np.asarray(r0.ptf_market_cap, dtype=float)
    n_cols = min(5, ptf_n.shape[1]) if ptf_n.ndim == 2 and ptf_n.size else 0
    if ptf_n.ndim == 2 and ptf_n.size:
        n_row = np.nanmean(ptf_n[:, :n_cols], axis=0)
        # Average firm size in $10^6 (MATLAB printed the total in $10^9).
        me_row = (
            average_firm_size(ptf_me, ptf_n[:, :n_cols])
            if ptf_me.size
            else np.full(n_cols, np.nan)
        )
        panel_c_a = np.vstack([n_row, me_row])
    else:
        panel_c_a = np.full((2, 5), np.nan)
    panel_c = {"a": panel_c_a, "tA": panel_c_a.copy(), "h": list(_PANEL_C_ROW_HEADERS)}
    results.Tab_BasicSort = {"PanelA": panel_a, "PanelB": panel_b, "PanelC": panel_c}

    # ---- Table 2 Tab_RobustSort -----------------------------------------
    n_sorts = len(BASIC_SORT_LABELS)
    n_models = len(models)
    a_r = np.full((n_sorts, n_models + 1), np.nan)
    t_r = np.full((n_sorts, n_models + 1), np.nan)
    a_n = np.full((n_sorts, n_models + 1), np.nan)
    t_n = np.full((n_sorts, n_models + 1), np.nan)
    table_outcomes: dict[tuple[str, int], GenAlphaOutcome] = {}
    for i, lab in enumerate(BASIC_SORT_LABELS):
        sr0 = basic.basic.get((lab, models[0]))
        if sr0 is None:
            continue
        a_r[i, 0] = _last(sr0.xret)
        t_r[i, 0] = _last(sr0.txret)
        a_n[i, 0] = float(sr0.netxret) if sr0.netxret is not None else np.nan
        t_n[i, 0] = float(sr0.tnetxret) if sr0.tnetxret is not None else np.nan
        for j, f in enumerate(models):
            sr = basic.basic.get((lab, f))
            if sr is None:
                continue
            a_r[i, j + 1] = _last(sr.alpha)
            t_r[i, j + 1] = _last(sr.talpha)
            # Net generalized alpha: the estimate when the net MVE portfolio
            # holds the strategy. It is not defined when the strategy gets
            # zero weight (``status == "zero"``), so that cell stays blank in
            # the table like an unavailable or failed one; the status counts
            # in ``metadata["gen_alpha_table"]`` keep the cases apart.
            oc = _gen_alpha_outcome(basic, lab, f)
            table_outcomes[(lab, f)] = oc
            a_n[i, j + 1] = oc.value if oc.status == "success" else np.nan
            t_n[i, j + 1] = oc.tstat
    results.Tab_RobustSort = {
        "PanelA": {
            "a": a_r,
            "tA": t_r,
            "h": list(_ROBUST_ROW_HEADERS),
        },
        "PanelB": {
            "a": a_n,
            "tA": t_n,
            "h": list(_ROBUST_ROW_HEADERS),
        },
    }
    results.metadata["gen_alpha_table"] = summarize_gen_alpha_outcomes(table_outcomes)

    # ---- Tab_SubSample (Python-only) -----------------------------
    results.Tab_SubSample, results.metadata["sub_sample"] = _sub_sample_table(
        basic, models, time_period, factors=factors
    )

    # ---- Table 3 Tab_CondSizeSort ----------------------------------------
    cond = rs.get("resCondMeSorts")
    if cond is None:
        cond = basic.conditional
    n_me = int(basic.metadata.get("n_me_ptfs", 5))
    a_c = np.full((n_me, n_me + n_models + 2), np.nan)
    t_c = np.full((n_me, n_me + n_models + 2), np.nan)
    b_c = np.full((n_me, 2 * n_me + 1), np.nan)
    h_c: list[str] = []
    for i in range(1, n_me + 1):
        h_c.append(f" & ({i})")
        sr_i = cond.get((i, models[0])) if isinstance(cond, dict) else None
        if sr_i is None:
            continue
        xret = _as_1d(sr_i.xret)
        txret = _as_1d(sr_i.txret)
        if xret.size >= n_me + 1:
            a_c[i - 1, :n_me] = xret[:n_me]
            a_c[i - 1, n_me] = np.nan
            a_c[i - 1, n_me + 1] = xret[-1]
            t_c[i - 1, :n_me] = txret[:n_me]
            t_c[i - 1, n_me] = np.nan
            t_c[i - 1, n_me + 1] = txret[-1]
        ptf_n_i = np.asarray(sr_i.ptf_num_stocks, dtype=float)
        ptf_me_i = np.asarray(sr_i.ptf_market_cap, dtype=float)
        if ptf_n_i.ndim == 2 and ptf_n_i.shape[1] >= 5:
            b_c[i - 1, :n_me] = np.nanmean(ptf_n_i[:, :5], axis=0)
        if (
            ptf_me_i.ndim == 2
            and ptf_me_i.shape[1] >= 5
            and ptf_n_i.ndim == 2
            and ptf_n_i.shape[1] >= 5
        ):
            # Average firm size in $10^6.
            b_c[i - 1, n_me + 1 : 2 * n_me + 1] = average_firm_size(
                ptf_me_i[:, :5], ptf_n_i[:, :5]
            )
        for j, f in enumerate(models):
            sr_ij = cond.get((i, f)) if isinstance(cond, dict) else None
            if sr_ij is None:
                continue
            a_c[i - 1, n_me + 2 + j] = _last(sr_ij.alpha)
            t_c[i - 1, n_me + 2 + j] = _last(sr_ij.talpha)
    results.Tab_CondSizeSort = {
        "PanelA": {"a": a_c, "tA": t_c, "h": h_c},
        "PanelB": {"a": b_c, "tA": b_c.copy(), "h": h_c},
    }

    # ---- Anomaly performance matrix (feeds several figures) --------------
    anom_map = _anom_results_dict(rs.get("resAnoms"), short_labels)
    if not short_labels:
        short_labels = list(anom_map.keys())
    correls = rs.get("resCorrels")
    if correls is None:
        correls = pd.DataFrame()
    cond_sort = rs.get("resCondSort") or {}
    fmbs = rs.get("resFMBs") or {}
    pret_baseline = _ls_return_series(r0)
    # The months the signal's own numbers use.
    sort_period: tuple[int, int] | None = None
    return_period: tuple[int, int] | None = None
    if pret_baseline is not None and len(pret_baseline):
        ls_ym = np.array([month_end_to_yyyymm(d) for d in pret_baseline.index], dtype=int)
        ls_has = np.isfinite(pret_baseline.to_numpy(dtype=float))
        sort_period = _first_last(ls_ym, ls_has)
        return_period = _first_last(
            ls_ym, ls_has & (ls_ym >= time_period[0]) & (ls_ym <= time_period[1])
        )

    stats_rows: list[list[float]] = []
    kept_names: list[str] = []
    for nm in short_labels:
        sr = anom_map.get(nm)
        if sr is None or sr.xret is None:
            continue
        # col1: gross Sharpe of L/S
        sh = _last(sr.sharpe)
        # col2: net Sharpe
        nsh = _net_sharpe(sr.netpret if sr.netpret is not None else sr.long_short_net)
        # col3: t-stat on cond double-sort L/S
        cs = cond_sort.get(nm) if isinstance(cond_sort, dict) else None
        t_cond = _last(cs.txret) if cs is not None else np.nan
        # col4: spanning α t-stat: test L/S ~ 1 + anom L/S
        t_span = np.nan
        anom_ls = _ls_return_series(sr)
        if pret_baseline is not None and anom_ls is not None:
            y = pret_baseline.astype(float)
            x = anom_ls.reindex(y.index).astype(float)
            X = np.column_stack([np.ones(len(y)), x.to_numpy()])
            try:
                ols = nanols(y.to_numpy(), X)
                t_span = float(ols.tstat[0]) if ols.tstat.size else np.nan
            except Exception:
                t_span = np.nan
        # col5/6: correlations
        rho_s = rho_p = np.nan
        if isinstance(correls, pd.DataFrame) and not correls.empty:
            if nm in correls.index:
                row = correls.loc[nm]
            elif nm in correls.columns:
                row = correls[nm]
            else:
                row = None
            if row is not None:
                # MATLAB order: [rhoS, rhoP]
                if "spearman" in getattr(row, "index", []):
                    rho_s = float(row.get("spearman", np.nan))
                    rho_p = float(row.get("pearson", np.nan))
                else:
                    vals = _as_1d(row)
                    if vals.size >= 2:
                        rho_s, rho_p = float(vals[0]), float(vals[1])
        # col7: FMB t on anomaly coefficient (t(2) in MATLAB, 1-indexed)
        t_fmb = np.nan
        fmb = fmbs.get(nm) if isinstance(fmbs, dict) else None
        if fmb is not None:
            tseries = getattr(fmb, "t", None)
            if tseries is not None:
                t_arr = _as_1d(tseries)
                if t_arr.size >= 2:
                    t_fmb = float(t_arr[1])
        stats_rows.append([sh, nsh, t_cond, t_span, rho_s, rho_p, t_fmb])
        kept_names.append(nm)

    a_stats = (
        np.asarray(stats_rows, dtype=float)
        if stats_rows
        else np.full((0, 7), np.nan)
    )
    n_anoms_hist = a_stats.shape[0]

    # ---- Fig_SharpeDist --------------------------------------------------
    line_gross = _last(r0.sharpe)
    line_net = _net_sharpe(r0.netpret if r0.netpret is not None else r0.long_short_net)
    results.Fig_SharpeDist = {
        "PanelA": {
            "Hist": a_stats[:, 0] if n_anoms_hist else np.array([]),
            "Line": float(line_gross),
            "xlim": np.array([-2.0, 2.0]),
        },
        "PanelB": {
            "Hist": a_stats[:, 1] if n_anoms_hist else np.array([]),
            "Line": float(line_net),
            "xlim": np.array([-2.0, 2.0]),
        },
    }

    # ---- Fig_CondAnoms ---------------------------------------------------
    results.Fig_CondAnoms = {
        "PanelA": {"Hist": a_stats[:, 6] if n_anoms_hist else np.array([])},
        "PanelB": {"Hist": a_stats[:, 3] if n_anoms_hist else np.array([])},
        "PanelC": {"Hist": a_stats[:, 2] if n_anoms_hist else np.array([])},
    }

    # ---- Fig_Correls -----------------------------------------------------
    short_all = list(labels.get("short") or kept_names)
    lbl_short = []
    for nm in kept_names:
        if nm in short_all:
            lbl_short.append(nm)
        else:
            lbl_short.append(nm)
    # Prefer original short labels aligned to kept order
    if short_labels:
        name_to_short = {s: s for s in short_labels}
        lbl_short = [name_to_short.get(nm, nm) for nm in kept_names]
    # Panel A holds Spearman and Panel B Pearson (MATLAB order); the figure axis
    # labels and the LaTeX caption name them the same way.
    if n_anoms_hist:
        ind_s = np.isfinite(a_stats[:, 4])
        ind_p = np.isfinite(a_stats[:, 5])
        results.Fig_Correls = {
            "PanelA": {
                "x": 100.0 * a_stats[ind_s, 4],
                "lbl": [lbl_short[i] for i in range(len(lbl_short)) if ind_s[i]],
            },
            "PanelB": {
                "x": 100.0 * a_stats[ind_p, 5],
                "lbl": [lbl_short[i] for i in range(len(lbl_short)) if ind_p[i]],
            },
        }
    else:
        results.Fig_Correls = {
            "PanelA": {"x": np.array([]), "lbl": []},
            "PanelB": {"x": np.array([]), "lbl": []},
        }

    # ---- Fig_Ibbots ------------------------------------------------------
    # The figure covers the months in which the signal has returns: from its
    # first return in the sample, but not before the sample's second month
    # (MATLAB's `s+1`, as in the cluster plot), to its last. MATLAB:
    #   s = find(dates==timePeriod(1)+1); e = find(dates==timePeriod(end));
    # which is the same window for a signal with returns throughout.
    try:
        start_ts = yyyymm_to_month_end(time_period[0]) + pd.offsets.MonthEnd(1)
        start_plus = month_end_to_yyyymm(start_ts)
    except Exception:
        start_plus = time_period[0] + 1
    end_ym = time_period[1]
    ibbots_window: tuple[int, int] | None = None
    if pret_baseline is not None and len(pret_baseline):
        ibbots_window = _first_last(
            ls_ym, ls_has & (ls_ym >= start_plus) & (ls_ym <= end_ym)
        )
    if ibbots_window is not None:
        start_plus, end_ym = ibbots_window
    s_mask = yyyymm == start_plus
    e_mask = yyyymm == end_ym
    if s_mask.any() and e_mask.any():
        s_i = int(np.flatnonzero(s_mask)[0])
        e_i = int(np.flatnonzero(e_mask)[0])
    else:
        # fall back to full available baseline series window
        s_i, e_i = 0, len(dates) - 1
    date_slice = dates[s_i : e_i + 1]
    n_t = len(date_slice)

    pret_g_test = (
        pret_baseline.reindex(date_slice).to_numpy(dtype=float)
        if pret_baseline is not None
        else np.full(n_t, np.nan)
    )
    net_base = r0.netpret if r0.netpret is not None else r0.long_short_net
    pret_n_test = (
        pd.Series(net_base).reindex(date_slice).to_numpy(dtype=float)
        if net_base is not None
        else np.full(n_t, np.nan)
    )

    # anomaly columns: all labels.short length (MATLAB nAnoms = length(resAnoms))
    anom_names_all = short_labels or list(anom_map.keys())
    n_anoms_all = len(anom_names_all)
    pret_g_anoms = np.full((n_t, n_anoms_all), np.nan)
    pret_n_anoms = np.full((n_t, n_anoms_all), np.nan)
    for j, nm in enumerate(anom_names_all):
        sr = anom_map.get(nm)
        ls = _ls_return_series(sr)
        if ls is not None:
            pret_g_anoms[:, j] = ls.reindex(date_slice).to_numpy(dtype=float)
        if sr is not None:
            np_series = sr.netpret if sr.netpret is not None else sr.long_short_net
            if np_series is not None:
                pret_n_anoms[:, j] = (
                    pd.Series(np_series).reindex(date_slice).to_numpy(dtype=float)
                )
    # An anomaly gets the signal's return in each month of the window in which
    # it has none of its own (before it starts, after it ends, in a gap), and
    # only there. MATLAB replaces the column up to its *last* missing
    # month:
    #   rNan = find(isnan(pretGrossAnoms(:,i)), 1, 'last');
    #   pretGrossAnoms(1:rNan, i) = pretGrossTestSignal(1:rNan);
    # so an anomaly that ends before the window does became a copy of the
    # signal. Each panel is filled by its own missing months.
    miss_g = ~np.isfinite(pret_g_anoms)
    miss_n = ~np.isfinite(pret_n_anoms)
    pret_g_anoms = np.where(miss_g, pret_g_test[:, None], pret_g_anoms)
    pret_n_anoms = np.where(miss_n, pret_n_test[:, None], pret_n_anoms)

    results.Fig_Ibbots = {
        "pretGrossTestSignal": pret_g_test,
        "pretNetTestSignal": pret_n_test,
        "pretGrossAnoms": pret_g_anoms,
        "pretNetAnoms": pret_n_anoms,
        "dates": yyyymm[s_i : e_i + 1],
        # Months per anomaly in which it carries the signal's gross return.
        "nSignalMonths": miss_g.sum(axis=0).astype(int),
    }

    # ---- Fig_AlphaPrctl --------------------------------------------------
    # MATLAB sets every NaN net generalized alpha to zero before taking
    # percentiles (makeResToPrint.m:327, :340). Here only a genuine zero (the
    # anomaly is not held in the net MVE portfolio) counts as zero; an
    # unavailable or failed calculation stays NaN, is left out of the
    # distribution, and each panel reports how many values it rests on.
    n_models = len(models)
    alpha_gross = np.full((n_anoms_all, n_models), np.nan)
    alpha_net = np.full((n_anoms_all, n_models), np.nan)
    net_outcomes: dict[tuple[str, int], GenAlphaOutcome] = {}
    gross_issues: list[dict[str, Any]] = []
    if compute_alpha_prctl and n_anoms_all > 0:
        for i, nm in enumerate(anom_names_all):
            sr = anom_map.get(nm)
            anom_ret = _ls_return_series(sr) if sr is not None else None
            if anom_ret is None:
                for f in models:
                    net_outcomes[(nm, f)] = GenAlphaOutcome(
                        "unavailable", reason="anomaly has no long-short series"
                    )
                continue
            tcost_ts = _anom_tcosts_ts(sr, anom_ret.index)
            if tcost_ts is None:
                tcost_ts = pd.Series(0.0, index=anom_ret.index)
            else:
                tcost_ts = tcost_ts.reindex(anom_ret.index).astype(float).fillna(0.0)
            both = anom_ret.astype(float) + tcost_ts.astype(float)
            finite_idx = both.index[np.isfinite(both.to_numpy())]
            if finite_idx.empty:
                for f in models:
                    net_outcomes[(nm, f)] = GenAlphaOutcome(
                        "unavailable", n_obs=0, reason="no finite long-short returns"
                    )
                continue
            s_dt, e_dt = finite_idx[0], finite_idx[-1]
            y_slice = anom_ret.loc[s_dt:e_dt]
            tc_slice = tcost_ts.reindex(y_slice.index).fillna(0.0)
            # convention="capital": the anomaly held short has its own cost.
            tc_short = getattr(sr, "tcosts_ts_short", None)
            tc_short_slice = (
                None
                if tc_short is None
                else pd.Series(tc_short).astype(float).reindex(y_slice.index).fillna(0.0)
            )
            for j, f in enumerate(models):
                try:
                    f_df, tc_df = factor_matrix_for_gen_alpha(
                        f,
                        y_slice.index,
                        factors=factors,
                        factor_tcosts=factor_tcosts,
                    )
                except Exception as exc:  # noqa: BLE001 -- recorded, stays NaN
                    oc = GenAlphaOutcome.failed(exc)
                    net_outcomes[(nm, f)] = oc
                    gross_issues.append({"key": (nm, f), "reason": oc.reason})
                    LOGGER.warning("alpha prctl failed %s model %s: %s", nm, f, oc.reason)
                    continue
                try:
                    # Gross α via nanols on factors
                    X_g = np.column_stack(
                        [np.ones(len(y_slice)), f_df.to_numpy(dtype=float)]
                    )
                    # Scale L/S decimals ×100 so intercept matches basic-sort α
                    # (%/mo) used as ``dy`` and gold Fig_AlphaPrctl percentiles.
                    ols_g = nanols(100.0 * y_slice.to_numpy(dtype=float), X_g)
                    alpha_gross[i, j] = float(ols_g.beta[0])
                except Exception as exc:  # noqa: BLE001 -- recorded, stays NaN
                    reason = f"{type(exc).__name__}: {exc}"
                    gross_issues.append({"key": (nm, f), "reason": reason})
                    LOGGER.warning("alpha prctl gross failed %s model %s: %s", nm, f, reason)
                f_short = factor_short_tcosts_for_gen_alpha(f, y_slice.index, factor_tcosts)
                # Short-position costs are passed only when there are some.
                short_kw = {}
                if tc_short_slice is not None:
                    short_kw["anom_tcosts_short"] = tc_short_slice.to_numpy(dtype=float)
                if f_short is not None:
                    short_kw["factor_tcosts_short"] = f_short.to_numpy(dtype=float)
                oc, _, _, _ = estimate_gen_alpha(
                    y_slice.to_numpy(dtype=float),
                    tc_slice.to_numpy(dtype=float),
                    f_df.to_numpy(dtype=float),
                    tc_df.to_numpy(dtype=float),
                    **short_kw,
                )
                if oc.status == "failed":
                    LOGGER.warning("alpha prctl net failed %s model %s: %s", nm, f, oc.reason)
                net_outcomes[(nm, f)] = oc
                alpha_net[i, j] = oc.value

        # prctile 0:99 along anomalies for each model (non-finite dropped)
        alpha_gross_prct = np.full((100, n_models), np.nan)
        alpha_net_prct = np.full((100, n_models), np.nan)
        for j in range(n_models):
            col_g = alpha_gross[:, j]
            col_n = alpha_net[:, j]
            if np.isfinite(col_g).any():
                alpha_gross_prct[:, j] = _matlab_prctile(col_g, np.arange(0, 100))
            if np.isfinite(col_n).any():
                alpha_net_prct[:, j] = _matlab_prctile(col_n, np.arange(0, 100))

        test_g = np.full(n_models, np.nan)
        test_n = np.full(n_models, np.nan)
        test_outcomes: dict[int, GenAlphaOutcome] = {}
        for j, f in enumerate(models):
            sr = basic.basic.get((row0, f))
            if sr is not None:
                test_g[j] = _last(sr.alpha)
            test_outcomes[f] = _gen_alpha_outcome(basic, row0, f)
            test_n[j] = test_outcomes[f].value

        test_g_prct = np.full(n_models, np.nan)
        test_n_prct = np.full(n_models, np.nan)
        for j in range(min(5, n_models)):
            test_g_prct[j] = float(invprctile(alpha_gross[:, j], test_g[j])[0])
            test_n_prct[j] = float(invprctile(alpha_net[:, j], test_n[j])[0])

        n_valid_g = np.isfinite(alpha_gross).sum(axis=0).astype(int)
        n_valid_n = np.isfinite(alpha_net).sum(axis=0).astype(int)
        results.Fig_AlphaPrctl = {
            "PanelA": {
                "y": alpha_gross_prct,
                "x": np.arange(0, 100, dtype=float),
                "dx": test_g_prct,
                "dy": test_g,
                "n_valid": n_valid_g,
            },
            "PanelB": {
                "y": alpha_net_prct,
                "x": np.arange(0, 100, dtype=float),
                "dx": test_n_prct,
                "dy": test_n,
                "n_valid": n_valid_n,
            },
        }
        net_summary = summarize_gen_alpha_outcomes(net_outcomes)
        net_summary["n_valid_by_model"] = dict(zip(models, n_valid_n.tolist()))
        results.metadata["alpha_prctl"] = {
            "n_anoms": int(n_anoms_all),
            "anoms": list(anom_names_all),
            "models": tuple(models),
            # Per-anomaly inputs to the percentiles (rows = anoms, cols = models).
            "alpha_gross": alpha_gross.copy(),
            "alpha_net": alpha_net.copy(),
            "gross": {
                "n_valid_by_model": dict(zip(models, n_valid_g.tolist())),
                "issues": gross_issues,
            },
            "net": net_summary,
            "test_signal_net": {f: oc.to_dict() for f, oc in test_outcomes.items()},
        }
        n_missing = net_summary["n_total"] - net_summary["n_valid"]
        if n_missing:
            LOGGER.warning(
                "Net generalized alpha missing for %d of %d anomaly-model cells "
                "(%d failed, %d unavailable); excluded from the percentiles.",
                n_missing,
                net_summary["n_total"],
                net_summary["counts"]["failed"],
                net_summary["counts"]["unavailable"],
            )
    else:
        results.Fig_AlphaPrctl = {
            "PanelA": {
                "y": np.full((100, n_models), np.nan),
                "x": np.arange(0, 100, dtype=float),
                "dx": np.full(n_models, np.nan),
                "dy": np.full(n_models, np.nan),
                "n_valid": np.zeros(n_models, dtype=int),
            },
            "PanelB": {
                "y": np.full((100, n_models), np.nan),
                "x": np.arange(0, 100, dtype=float),
                "dx": np.full(n_models, np.nan),
                "dy": np.full(n_models, np.nan),
                "n_valid": np.zeros(n_models, dtype=int),
            },
        }

    # ---- Fig_Dendrogram --------------------------------------------------
    results.Fig_Dendrogram = {
        "Z": np.asarray(rs.get("Z"), dtype=float) if rs.get("Z") is not None else None,
        "dendrogramLabels": list(rs.get("dendrogramLabels") or rs.get("dendrogram_labels") or []),
        "cutoff": rs.get("cutoff"),
    }
    # The clustering window and the anomaly counts, when the run
    # recorded them; the report's sentences on the plot state them.
    dinfo = rs.get("dendrogramInfo") or rs.get("dendrogram_info")
    if dinfo:
        results.Fig_Dendrogram["window"] = [int(m) for m in dinfo["window"]]
        results.Fig_Dendrogram["nMonths"] = int(dinfo["n_months"])
        results.Fig_Dendrogram["nAnomsIn"] = int(dinfo["n_anoms_in"])
        results.Fig_Dendrogram["nAnomsKept"] = int(dinfo["n_anoms_kept"])

    # ---- Tab_CloseFMB / Tab_CloseSpan ------------------------------------
    n_close = len(close_long)
    res_close_fmb = list(rs.get("resCloseFMB") or rs.get("res_close_fmb") or [])
    res_close_span = list(rs.get("resCloseSpan") or rs.get("res_close_span") or [])
    if n_close > 0 and res_close_fmb:
        # Layout: column 0 the signal alone, columns 1..n_close the
        # bivariate regressions, the last the joint one. The last two rows
        # (no t-stat) are the number of monthly cross-sections and
        # the mean cross-sectional adjusted R² in percent.
        h_fmb = ["Intercept", signal_label] + [f"Anomaly {i}" for i in range(1, n_close + 1)]
        h_fmb = h_fmb + [r"\# months", r"$\bar{R}^2$ (\%)"]
        n_coef = n_close + 2
        a_fmb = np.full((n_close + 4, n_close + 2), np.nan)
        t_fmb = np.full((n_close + 4, n_close + 2), np.nan)

        def _fmb_r2(reg: Any) -> float:
            r2 = getattr(reg, "mean_r2", np.nan)
            try:
                return 100.0 * float(r2)
            except (TypeError, ValueError):
                return np.nan

        def _fmb_months(reg: Any) -> float:
            # Results saved by an earlier version do not record the count: blank cell.
            meta = getattr(reg, "metadata", None) or {}
            try:
                return float(meta["n_months"])
            except (KeyError, TypeError, ValueError):
                return np.nan

        bhat_0 = getattr(res_close_fmb[0], "bhat", None)
        first_labels = list(bhat_0.index) if isinstance(bhat_0, pd.Series) else []
        if first_labels == ["Const", "test_signal"]:
            fmb_solo = res_close_fmb[0]
            res_biv = res_close_fmb[1:]
            bhat = _as_1d(getattr(fmb_solo, "bhat", None))[:2]
            tt = _as_1d(getattr(fmb_solo, "t", None))[:2]
            a_fmb[: bhat.size, 0] = bhat
            t_fmb[: tt.size, 0] = tt
            a_fmb[-2, 0] = _fmb_months(fmb_solo)
            a_fmb[-1, 0] = _fmb_r2(fmb_solo)
        else:
            # Results saved by an earlier version have no signal-only regression.
            LOGGER.warning(
                "Close-anomaly FMB results have no signal-only regression (they were "
                "saved by an earlier version of the package); column 0 of "
                "Tab_CloseFMB is left blank. "
                "Re-run the protocol to fill it."
            )
            results.metadata["close_fmb_layout"] = "legacy"
            res_biv = res_close_fmb
        for i in range(n_close):
            if i >= len(res_biv):
                break
            fmb = res_biv[i]
            bhat = _as_1d(getattr(fmb, "bhat", None))
            tt = _as_1d(getattr(fmb, "t", None))
            if bhat.size >= 2:
                a_fmb[0:2, i + 1] = bhat[:2]
            if tt.size >= 2:
                t_fmb[0:2, i + 1] = tt[:2]
            if bhat.size >= 3:
                a_fmb[i + 2, i + 1] = bhat[2]
            if tt.size >= 3:
                t_fmb[i + 2, i + 1] = tt[2]
            a_fmb[-2, i + 1] = _fmb_months(fmb)
            a_fmb[-1, i + 1] = _fmb_r2(fmb)
        if len(res_biv) > n_close:
            fmb_j = res_biv[n_close]
            bhat_j = _as_1d(getattr(fmb_j, "bhat", []))[:n_coef]
            tt_j = _as_1d(getattr(fmb_j, "t", []))[:n_coef]
            a_fmb[: bhat_j.size, -1] = bhat_j
            t_fmb[: tt_j.size, -1] = tt_j
            a_fmb[-2, -1] = _fmb_months(fmb_j)
            a_fmb[-1, -1] = _fmb_r2(fmb_j)
        results.Tab_CloseFMB = {"a": a_fmb, "tA": t_fmb, "h": h_fmb}
    else:
        results.Tab_CloseFMB = {
            "a": np.zeros((0, 0)),
            "tA": np.zeros((0, 0)),
            "h": [],
        }

    if n_close > 0 and res_close_span:
        h_sp = ["Intercept"] + [f"Anomaly {i}" for i in range(1, n_close + 1)]
        h_sp = h_sp + ["mkt", "smb", "hml", "rmw", "cma", "umd"]
        # Last two rows (no t-stat): the number of months in each spanning
        # regression and its adjusted R². The R² is stored
        # as a fraction here and scaled to percent below; the months row is
        # not scaled.
        h_sp = h_sp + [r"\# months", r"$\bar{R}^2$ (\%)"]
        n_coef = n_close + 7
        a_sp = np.full((n_close + 9, n_close + 1), np.nan)
        t_sp = np.full((n_close + 9, n_close + 1), np.nan)

        def _span_r2(sp: Any) -> float:
            try:
                return float(getattr(sp, "r2_adj", np.nan))
            except (TypeError, ValueError):
                return np.nan

        def _span_months(sp: Any) -> float:
            try:
                n = int(getattr(sp, "n_obs", 0) or 0)
            except (TypeError, ValueError):
                return np.nan
            return float(n) if n > 0 else np.nan

        for i in range(n_close):
            if i >= len(res_close_span):
                break
            sp = res_close_span[i]
            beta = _as_1d(getattr(sp, "beta", None))
            tstat = _as_1d(
                getattr(sp, "tstats", None)
                if getattr(sp, "tstats", None) is not None
                else getattr(sp, "tstat", None)
            )
            if beta.size >= 1:
                a_sp[0, i] = beta[0]
            if tstat.size >= 1:
                t_sp[0, i] = tstat[0]
            if beta.size >= 2:
                a_sp[i + 1, i] = beta[1]
            if tstat.size >= 2:
                t_sp[i + 1, i] = tstat[1]
            if beta.size > 2:
                b_ff = beta[2 : 2 + (n_coef - (n_close + 1))]
                a_sp[n_close + 1 : n_close + 1 + b_ff.size, i] = b_ff
            if tstat.size > 2:
                t_ff = tstat[2 : 2 + (n_coef - (n_close + 1))]
                t_sp[n_close + 1 : n_close + 1 + t_ff.size, i] = t_ff
            a_sp[-2, i] = _span_months(sp)
            a_sp[-1, i] = _span_r2(sp)
        if len(res_close_span) > n_close:
            sp_j = res_close_span[n_close]
            beta_j = _as_1d(getattr(sp_j, "beta", None))[:n_coef]
            tstat_j = _as_1d(
                getattr(sp_j, "tstats", None)
                if getattr(sp_j, "tstats", None) is not None
                else getattr(sp_j, "tstat", None)
            )[:n_coef]
            a_sp[: beta_j.size, -1] = beta_j
            t_sp[: tstat_j.size, -1] = tstat_j
            a_sp[-2, -1] = _span_months(sp_j)
            a_sp[-1, -1] = _span_r2(sp_j)
        # The regressions run on decimal returns. Only the intercept (alpha)
        # becomes percent per month; the slopes on the anomaly and factor
        # returns are unit-free and print as estimated.
        a_sp[0] *= 100.0
        a_sp[-1] *= 100.0
        results.Tab_CloseSpan = {"a": a_sp, "tA": t_sp, "h": h_sp}
    else:
        results.Tab_CloseSpan = {
            "a": np.zeros((0, 0)),
            "tA": np.zeros((0, 0)),
            "h": [],
        }

    # ---- Fig_CombStrat ---------------------------------------------------
    comb = rs.get("combStrats") if rs.get("combStrats") is not None else rs.get("comb_strats")
    y_without = np.zeros((0, 0))
    y_with = np.zeros((0, 0))
    ttl: list[str] = []
    explanation: list[str] = []
    comb_x = np.array([])
    comb_first: list[int | None] = []
    comb_last: list[int | None] = []
    comb_signal_start: list[Any] = []
    comb_signal_window: int | None = None
    comb_ipca_skipped: dict[str, int] | None = None
    if compute_comb_sorts and comb is not None and returns is not None and mcap is not None:
        strats_list: list[Any] = []
        if isinstance(comb, CombStratsResults):
            strats_list = list(comb.strats.values())
        elif isinstance(comb, Mapping):
            strats_list = list(comb.values())
        elif isinstance(comb, (list, tuple)):
            strats_list = list(comb)

        def lab_of(st: Any) -> str:
            return str(
                getattr(st, "display_label", None)
                or getattr(st, "label", None)
                or ""
            )

        keep_strats = []
        for st in strats_list:
            lab = lab_of(st)
            if "N/A" in lab:
                continue
            keep_strats.append(st)
        n_keep = len(keep_strats)
        # The count of IPCA months skipped is kept whether or not IPCA has a
        # panel.
        for st in strats_list:
            info = getattr(st, "info", None) or {}
            if "ipca_skipped" in info:
                comb_ipca_skipped = {
                    leg: len(months) for leg, months in info["ipca_skipped"].items()
                }
        # MATLAB: s = find(dates==timePeriod(1)); e = find(dates==timePeriod(end));
        # use returned sort dates window after first sort
        if n_keep > 0:
            # One (without, with) pair per method; None where the method never
            # uses the signal, so there is no strategy to form.
            pairs: list[tuple[pd.Series, pd.Series] | None] = []
            for st in keep_strats:
                eret = getattr(st, "eret", None)
                eret_enh = getattr(st, "eret_enh", None)
                if eret is None or eret_enh is None:
                    continue
                try:
                    if not (eret.notna().any() and eret_enh.notna().any()):
                        info = getattr(st, "info", None) or {}
                        if "signal_rule" not in info or getattr(st, "signal_start", None) is not None:
                            # The method itself produced no forecast (a sample
                            # shorter than its window): no panel, as before.
                            LOGGER.warning("comb strat `%s` has no forecast; skipped", lab_of(st))
                            continue
                        # The method never uses the signal: an empty panel
                        # that the report explains.
                        pair = None
                    else:
                        legs = []
                        for sig in (eret, eret_enh):
                            res = run_univariate_sort(
                                returns,
                                sig.astype(float),
                                mcap,
                                n_bins=10,
                                breaks="name",
                                weighting="v",
                                time_period=time_period,
                                factor_model=None,
                                print_results=False,
                                plot_results=False,
                                convention=convention,
                            )
                            legs.append(_ls_return_series(res))
                        if legs[0] is None or legs[1] is None:
                            continue
                        pair = (legs[0], legs[1])
                    pairs.append(pair)
                    ttl.append(
                        str(
                            getattr(st, "display_label", None)
                            or getattr(st, "label", "")
                        )
                    )
                    explanation.append(str(getattr(st, "explanation", "") or ""))
                    comb_signal_start.append(getattr(st, "signal_start", None))
                    info = getattr(st, "info", None) or {}
                    if info.get("signal_window") is not None:
                        comb_signal_window = int(info["signal_window"])
                except Exception as exc:
                    LOGGER.warning("comb strat sort failed: %s", exc)
            formed = [pr for pr in pairs if pr is not None]
            if formed:
                # align all series to first index
                idx0 = formed[0][0].index
                nan_col = np.full(len(idx0), np.nan)
                y_without = np.column_stack([
                    nan_col if pr is None else pr[0].reindex(idx0).to_numpy(dtype=float)
                    for pr in pairs
                ])
                y_with = np.column_stack([
                    nan_col if pr is None else pr[1].reindex(idx0).to_numpy(dtype=float)
                    for pr in pairs
                ])
                # The two strategies of a panel are compared over the months in
                # which both have a return, and nowhere else.
                both = np.isfinite(y_without) & np.isfinite(y_with)
                y_without = np.where(both, y_without, np.nan)
                y_with = np.where(both, y_with, np.nan)
                comb_x = np.array([month_end_to_yyyymm(d) for d in idx0])
                # The x-axis starts in the first month in which any method has
                # a return: the signal's first month, for the average rank.
                rows = np.flatnonzero(both.any(axis=1))
                if rows.size:
                    y_without = y_without[rows[0]:]
                    y_with = y_with[rows[0]:]
                    comb_x = comb_x[rows[0]:]
                    both = both[rows[0]:]
                for j in range(both.shape[1]):
                    r = np.flatnonzero(both[:, j])
                    comb_first.append(int(comb_x[r[0]]) if r.size else None)
                    comb_last.append(int(comb_x[r[-1]]) if r.size else None)
            else:
                ttl, explanation, comb_signal_start = [], [], []

    results.Fig_CombStrat = {
        "x": comb_x,
        "yWithout": y_without,
        "yWith": y_with,
        "ttl": ttl,
        "explanation": explanation,
        # Per method: first and last month (YYYYMM) in which both strategies
        # have a return (None: the method never uses the signal).
        "first": comb_first,
        "last": comb_last,
        # Per method: first month (YYYYMM) whose forecast uses the signal.
        "signalStart": [
            None if d is None else int(month_end_to_yyyymm(d)) for d in comb_signal_start
        ],
        # Months of data the signal needs for the methods other than the
        # average rank; None for a results file of an earlier version.
        "signalWindow": comb_signal_window,
        "ipcaSkipped": comb_ipca_skipped,
    }

    # ---- Text scalars ----------------------------------------------------
    if tcosts_type is None:
        try:
            tcosts_type = str(load_config().tcosts_type)
        except Exception:
            tcosts_type = "full"
    close_str = ""
    if close_long:
        close_str = str(close_long[0])
        for i in range(1, len(close_long)):
            close_str = f"{close_str}, {close_long[i]}"
    results.Text = PrintText(
        timePeriod=np.asarray(time_period, dtype=int),
        nAnoms=str(n_anoms_hist),
        signalChar=signal_label.upper(),
        sharpeChar=f"{line_gross:1.2f}" if np.isfinite(line_gross) else "nan",
        netSharpeChar=f"{line_net:1.2f}" if np.isfinite(line_net) else "nan",
        nCloseAnoms=len(close_long),
        closeAnoms=close_str,
        closeAnomLabels=list(close_long),
        tcostsType=str(tcosts_type),
        valuePeriod=_period_or_none(value_period),
        sortPeriod=_period_or_none(sort_period),
        returnPeriod=_period_or_none(return_period),
    )

    if verbose:
        LOGGER.info(
            "Preparation of results for printing ended at %s.",
            datetime.now().isoformat(timespec="seconds"),
        )
        print(
            f"Preparation of results for printing ended at "
            f"{datetime.now():%Y-%m-%d %H:%M:%S}.\n",
            flush=True,
        )

    return results
