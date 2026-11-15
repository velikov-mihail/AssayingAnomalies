"""
Figure PDF emitters for the assay protocol paper.

Python port of ``Functions/Assay functions/prt/print*Figure.m`` (PDF half only;
LaTeX ``\\includegraphics`` lives in ``latex.py``). Basenames match MATLAB gold:

``{Signal}_figureSignalDescription.pdf``, ``â€¦SharpeDist``, ``â€¦Ibbots``,
``â€¦AlphaPrctl``, ``â€¦Correl``, ``â€¦Dendrogram``, ``â€¦CondStrats``, ``â€¦CombStrats``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

LOGGER = logging.getLogger("assayinganomalies.reporting.figures")

__all__ = [
    "FIGURE_SUFFIXES",
    "emit_all_figures",
    "emit_signal_description_figure",
    "emit_sharpe_dist_figure",
    "emit_ibbots_figure",
    "emit_alpha_prctl_figure",
    "emit_correl_figure",
    "emit_dendrogram_figure",
    "emit_cond_strats_figure",
    "emit_comb_strats_figure",
    "plot_name_histogram",
    "ibbots_cumret",
]

# Ordered (logical key, basename suffix without signal prefix)
FIGURE_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("signal_description", "figureSignalDescription"),
    ("sharpe_dist", "figureSharpeDist"),
    ("ibbots", "figureIbbots"),
    ("alpha_prctl", "figureAlphaPrctl"),
    ("correl", "figureCorrel"),
    ("dendrogram", "figureDendrogram"),
    ("cond_strats", "figureCondStrats"),
    ("comb_strats", "figureCombStrats"),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _text(results: Any) -> Any:
    t = getattr(results, "Text", None)
    if t is None and isinstance(results, Mapping):
        t = results.get("Text")
    return t


def _signal_char(results: Any, override: str | None = None) -> str:
    if override:
        return str(override)
    text = _text(results)
    if text is not None:
        sc = _get(text, "signalChar")
        if sc is not None and str(sc):
            return str(sc)
    return "SIGNAL"


def _pdf_path(out_dir: Path, signal_char: str, suffix: str) -> Path:
    return out_dir / f"{signal_char}_{suffix}.pdf"


def _as_1d(x: Any) -> np.ndarray:
    if x is None:
        return np.array([], dtype=float)
    return np.asarray(x, dtype=float).ravel()


def _as_2d(x: Any) -> np.ndarray:
    if x is None:
        return np.zeros((0, 0), dtype=float)
    a = np.asarray(x, dtype=float)
    if a.ndim == 1:
        return a.reshape(-1, 1)
    return a


def _month_pdate(dates: np.ndarray) -> np.ndarray:
    """MATLAB monthly ``ibbots`` x-axis: floor(d/100) + mod(d,100)/12."""
    d = np.asarray(dates, dtype=float).ravel()
    if d.size == 0:
        return d
    # Already plot-fraction dates?
    if float(np.nanmax(np.abs(d))) < 1e5:
        return d
    return np.floor(d / 100.0) + np.mod(d, 100.0) / 12.0


def ibbots_cumret(
    rets: np.ndarray,
    dates: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Cumulative $1 paths matching MATLAB ``ibbots`` (no plotting).

    Parameters
    ----------
    rets
        Month Ã— series decimal returns (NaN â†’ 0).
    dates
        YYYYMM (or YYYYMMDD) vector, or plot-fraction dates; optional.

    Returns
    -------
    x, y
        ``x`` length T+1 plot dates; ``y`` shape (T+1, n_series) with y0 = 1.
    """
    r = _as_2d(rets)
    r = np.nan_to_num(r, nan=0.0)
    t, k = r.shape
    y = np.cumprod(np.vstack([np.zeros((1, k)), r]) + 1.0, axis=0)
    if dates is None or np.asarray(dates).size == 0:
        x = np.arange(t + 1, dtype=float)
    else:
        xd = _month_pdate(np.asarray(dates, dtype=float).ravel())
        if xd.size != t:
            # align to min length
            n = min(xd.size, t)
            xd = xd[:n]
            r = r[:n]
            y = np.cumprod(np.vstack([np.zeros((1, k)), r]) + 1.0, axis=0)
            t = n
        if t == 0:
            x = xd[:1] if xd.size else np.array([0.0])
        elif t == 1:
            x = np.array([xd[0] - 1.0 / 12.0, xd[0]])
        else:
            x0 = 2.0 * xd[0] - xd[1]
            x = np.concatenate([[x0], xd])
    return x, y


def _ensure_matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _savefig(fig, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fig.tight_layout()
    except Exception:
        pass
    fig.savefig(path, format="pdf", bbox_inches="tight", transparent=True)
    plt = _ensure_matplotlib()
    plt.close(fig)
    LOGGER.info("Wrote figure %s", path)
    return path.resolve()


def _safe(name: str, fn, *args, **kwargs) -> Path | None:
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # pragma: no cover - defensive for incomplete leaves
        LOGGER.warning("Figure %s skipped: %s", name, exc)
        return None


# ---------------------------------------------------------------------------
# Individual emitters
# ---------------------------------------------------------------------------
def _legend_below(ax, labels: Sequence[str]) -> None:
    """Legend in one row below the panel, outside the plotting area.

    Inside the axes a legend covers whatever line ends in its corner; below
    the tick labels it covers nothing, whatever the data.
    """
    ax.legend(
        list(labels),
        loc="upper center",
        bbox_to_anchor=(0.5, -0.12),
        ncol=max(len(labels), 1),
        frameon=False,
    )


def emit_signal_description_figure(
    results: Any,
    out_dir: str | Path,
    *,
    signal_char: str | None = None,
) -> Path | None:
    """``{sc}_figureSignalDescription.pdf`` from ``Fig_Cov``."""
    sc = _signal_char(results, signal_char)
    fig_cov = _get(results, "Fig_Cov") or {}
    pan_a = _get(fig_cov, "PanelA") or {}
    pan_b = _get(fig_cov, "PanelB") or {}
    x_a = _as_1d(_get(pan_a, "x"))
    y_a = _as_2d(_get(pan_a, "y"))
    x_b = _as_1d(_get(pan_b, "x"))
    y_b = _as_2d(_get(pan_b, "y"))
    if x_a.size == 0 or y_a.size == 0:
        LOGGER.warning("Fig_Cov empty; skip signal description figure")
        return None

    # Both panels are drawn at the signal's own frequency: only the months in
    # which the signal has values are plotted, joined by lines. A signal with
    # values each June (one built from annual Compustat columns) is one point
    # a year; drawn month by month, Panel A would be isolated points that a
    # line plot does not show and Panel B a comb that returns to zero in
    # eleven months of twelve. For a signal with values every month nothing
    # changes. The stored Fig_Cov keeps every month.
    has_a = np.isfinite(y_a).any(axis=1)
    if has_a.any() and x_a.size == y_a.shape[0]:
        x_a, y_a = x_a[has_a], y_a[has_a]
    if x_b.size and y_b.size and x_b.size == y_b.shape[0]:
        has_b = np.isfinite(y_b[:, 0]) & (y_b[:, 0] > 0)
        if has_b.any():
            x_b, y_b = x_b[has_b], y_b[has_b]

    plt = _ensure_matplotlib()
    fig, axes = plt.subplots(2, 1, figsize=(8.0, 6.5))
    ax = axes[0]
    ax.plot(x_a, y_a)
    _legend_below(ax, ["25th", "Median", "75th", "Mean"])
    ax.set_title(f"Panel A: {sc} percentiles")
    xlim_a = _get(pan_a, "xlim")
    if xlim_a is not None and np.asarray(xlim_a).size >= 2:
        ax.set_xlim(float(np.asarray(xlim_a).ravel()[0]), float(np.asarray(xlim_a).ravel()[-1]))
    ax = axes[1]
    if x_b.size and y_b.size:
        # Fig_Cov stores coverage as fractions, but both the legend here and the prose in
        # printSignalDescriptionSection.m call them percentages -- MATLAB scales only the
        # prose, leaving Panel B labelled "%" over a 0..1 axis. Scale the plot instead of
        # the leaf, so the stored Fig_Cov stays byte-identical to MATLAB's.
        ax.plot(x_b, 100.0 * y_b)
    _legend_below(ax, ["% of names", "% of market cap"])
    ax.set_title(f"Panel B: {sc} coverage")
    xlim_b = _get(pan_b, "xlim")
    if xlim_b is not None and np.asarray(xlim_b).size >= 2:
        ax.set_xlim(float(np.asarray(xlim_b).ravel()[0]), float(np.asarray(xlim_b).ravel()[-1]))
    return _savefig(fig, _pdf_path(Path(out_dir), sc, "figureSignalDescription"))


def _plot_sharpe_panel(
    ax, pan, hist, xlab: str, *, sc: str, show_legend: bool, title: str | None = None
) -> None:
    """One Fig_SharpeDist panel: anomaly histogram + the test signal's vertical line.

    MATLAB (``printSharpeDistFigure.m``) calls ``legend('', signalChar)`` on Panel A only,
    and its legend silently drops the empty entry -- one row, the red line labelled ``sc``.
    matplotlib collects unlabelled handles lines-before-patches, so the same bare label list
    puts ``sc`` on the histogram instead; legend from the red handle explicitly.
    """
    if hist.size:
        ax.hist(hist[~np.isnan(hist)], bins="auto", edgecolor="none")
    line = _get(pan, "Line")
    if line is not None and np.isfinite(float(np.asarray(line).ravel()[0])):
        lv = float(np.asarray(line).ravel()[0])
        ymin, ymax = ax.get_ylim()
        if ymax <= ymin:
            ymax = ymin + 1.0
        (red,) = ax.plot([lv, lv], [ymin, ymax], color="r", linewidth=2.0)
        ax.set_ylim(ymin, ymax)
        if show_legend:
            ax.legend(handles=[red], labels=[sc], loc="upper right")
    ax.set_xlabel(xlab)
    if title:
        ax.set_title(title)
    xl = _get(pan, "xlim")
    if xl is not None and np.asarray(xl).size >= 2:
        ax.set_xlim(float(np.asarray(xl).ravel()[0]), float(np.asarray(xl).ravel()[-1]))


def emit_sharpe_dist_figure(
    results: Any,
    out_dir: str | Path,
    *,
    signal_char: str | None = None,
) -> Path | None:
    """``{sc}_figureSharpeDist.pdf`` from ``Fig_SharpeDist``."""
    sc = _signal_char(results, signal_char)
    dist = _get(results, "Fig_SharpeDist") or {}
    pan_a = _get(dist, "PanelA") or {}
    pan_b = _get(dist, "PanelB") or {}
    hist_a = _as_1d(_get(pan_a, "Hist"))
    hist_b = _as_1d(_get(pan_b, "Hist"))
    if hist_a.size == 0 and hist_b.size == 0:
        LOGGER.warning("Fig_SharpeDist empty; skip")
        return None

    plt = _ensure_matplotlib()
    fig, axes = plt.subplots(2, 1, figsize=(8.0, 6.5))
    # Legend on Panel A only, as in MATLAB.
    _plot_sharpe_panel(
        axes[0], pan_a, hist_a, "Anomaly Sharpe ratios", sc=sc, show_legend=True,
        title="Panel A: Gross Sharpe ratios",
    )
    _plot_sharpe_panel(
        axes[1], pan_b, hist_b, "Anomaly Net Sharpe ratios", sc=sc, show_legend=False,
        title="Panel B: Net Sharpe ratios",
    )
    return _savefig(fig, _pdf_path(Path(out_dir), sc, "figureSharpeDist"))


def dollar_range(*paths: np.ndarray | None) -> tuple[float, float] | None:
    """Tight (min, max) over the finite, positive values of one or more $1 paths."""
    chunks = [np.asarray(p).ravel() for p in paths if p is not None and np.size(p)]
    if not chunks:
        return None
    all_y = np.concatenate(chunks)
    all_y = all_y[np.isfinite(all_y) & (all_y > 0)]
    if all_y.size == 0:
        return None
    return float(np.min(all_y)), float(np.max(all_y))


def _apply_dollar_log_axis(ax, ylim: tuple[float, float] | None) -> None:
    """Decade ticks ``$1 .. $100,000,000`` on a log y-axis, then the limits.

    Order matters: on a log axis matplotlib's ``set_yticks`` widens the view interval to
    span the tick range, so setting the limits first would leave every axis stretched to
    $100,000,000 no matter how small the data. MATLAB's ``set(gca,'YTick',...)``
    (``ibbots.m:94``) has no such side effect. Ticks outside the limits are simply not
    drawn, which is what MATLAB does too.

    MATLAB gives nine tick positions but only eight labels, so its list recycles and the
    ``$100,000,000`` label lands on ``10**7``; both are generated here.
    """
    decades = np.arange(9)
    ax.set_yticks(10.0**decades)
    ax.set_yticklabels([f"${10 ** int(e):,d}" for e in decades])
    if ylim is not None:
        ax.set_ylim(*ylim)


def _plot_ibbots_panel(ax, pret_anoms, pret_test, dates, *, title: str, sc: str) -> None:
    anoms = _as_2d(pret_anoms)
    test = _as_1d(pret_test)
    n_anoms = anoms.shape[1] if anoms.size else 0
    if n_anoms == 0 and test.size == 0:
        ax.set_title(title)
        return
    # Align lengths
    d = _as_1d(dates) if dates is not None else np.array([])
    if anoms.size and test.size and anoms.shape[0] != test.size:
        n = min(anoms.shape[0], test.size)
        anoms = anoms[:n]
        test = test[:n]
        if d.size:
            d = d[:n]
    if d.size and anoms.size and d.size != anoms.shape[0]:
        n = min(d.size, anoms.shape[0])
        anoms = anoms[:n]
        test = test[:n] if test.size else test
        d = d[:n]

    x_a, y_a = ibbots_cumret(anoms, d if d.size else None) if anoms.size else (None, None)
    x_t, y_t = (
        ibbots_cumret(test.reshape(-1, 1), d if d.size else None)
        if test.size
        else (None, None)
    )
    gray = (0.8, 0.8, 0.8)
    h_gray = None  # first anomaly line, stands in for all of them in the legend
    h_test = None
    if y_a is not None:
        for j in range(y_a.shape[1]):
            (h,) = ax.semilogy(x_a, y_a[:, j], color=gray, linewidth=1.0)
            if h_gray is None:
                h_gray = h
    if y_t is not None:
        (h_test,) = ax.semilogy(x_t, y_t[:, 0], color="r", linewidth=2.0)
    # MATLAB passes nAnoms-1 empty labels and its legend drops them; matplotlib would draw
    # all nAnoms+1 rows, which grows the tight-bbox page to several thousand points. Legend
    # from the two representative handles instead.
    if "Gross" in title:
        handles = [h for h in (h_gray, h_test) if h is not None]
        labels = [lb for h, lb in ((h_gray, "Anomalies"), (h_test, sc)) if h is not None]
        if handles:
            ax.legend(handles=handles, labels=labels, loc="upper left")
    ax.set_title(title)
    chunks = [c for c in (y_a, y_t) if c is not None]
    _apply_dollar_log_axis(ax, dollar_range(*chunks) if chunks else None)


def emit_ibbots_figure(
    results: Any,
    out_dir: str | Path,
    *,
    signal_char: str | None = None,
) -> Path | None:
    """``{sc}_figureIbbots.pdf`` from ``Fig_Ibbots``."""
    sc = _signal_char(results, signal_char)
    ib = _get(results, "Fig_Ibbots") or {}
    pret_g = _as_2d(_get(ib, "pretGrossAnoms"))
    pret_s = _as_1d(_get(ib, "pretGrossTestSignal"))
    if pret_g.size == 0 and pret_s.size == 0:
        LOGGER.warning("Fig_Ibbots empty; skip")
        return None
    # Orientation: months Ã— anoms. If transposed (n_anoms, n_months) with n_anoms << months, flip
    dates = _as_1d(_get(ib, "dates"))
    if pret_g.ndim == 2 and pret_g.shape[0] < pret_g.shape[1] and pret_s.size == pret_g.shape[1]:
        pret_g = pret_g.T
    pret_n = _as_2d(_get(ib, "pretNetAnoms"))
    pret_ns = _as_1d(_get(ib, "pretNetTestSignal"))
    if pret_n.ndim == 2 and pret_n.shape[0] < pret_n.shape[1] and pret_ns.size == pret_n.shape[1]:
        pret_n = pret_n.T

    plt = _ensure_matplotlib()
    fig, axes = plt.subplots(2, 1, figsize=(8.0, 7.0))
    _plot_ibbots_panel(
        axes[0], pret_g, pret_s, dates, title="Panel A: Gross returns", sc=sc
    )
    _plot_ibbots_panel(
        axes[1], pret_n, pret_ns, dates, title="Panel B: Net returns", sc=sc
    )
    return _savefig(fig, _pdf_path(Path(out_dir), sc, "figureIbbots"))


def emit_alpha_prctl_figure(
    results: Any,
    out_dir: str | Path,
    *,
    signal_char: str | None = None,
) -> Path | None:
    """``{sc}_figureAlphaPrctl.pdf`` from ``Fig_AlphaPrctl``."""
    sc = _signal_char(results, signal_char)
    ap = _get(results, "Fig_AlphaPrctl") or {}
    pan_a = _get(ap, "PanelA") or {}
    pan_b = _get(ap, "PanelB") or {}
    y_a = _as_2d(_get(pan_a, "y"))
    x_a = _as_1d(_get(pan_a, "x"))
    if y_a.size == 0:
        LOGGER.warning("Fig_AlphaPrctl empty; skip")
        return None
    # Expect rows = percentiles, cols = models
    if y_a.shape[0] < y_a.shape[1] and y_a.shape[1] >= 50:
        y_a = y_a.T
    y_b = _as_2d(_get(pan_b, "y"))
    if y_b.size and y_b.shape[0] < y_b.shape[1] and y_b.shape[1] >= 50:
        y_b = y_b.T
    x_b = _as_1d(_get(pan_b, "x"))
    if x_a.size == 0:
        x_a = np.arange(y_a.shape[0], dtype=float)
    if x_b.size == 0 and y_b.size:
        x_b = np.arange(y_b.shape[0], dtype=float)

    plt = _ensure_matplotlib()
    # 14 by 6: at 6.5 the figure and its caption were taller than the
    # landscape page.
    fig, axes = plt.subplots(1, 2, figsize=(14.0, 6.0))
    for ax, pan, x, y, ylab, title in (
        (
            axes[0],
            pan_a,
            x_a,
            y_a,
            "Gross Alpha (%/month)",
            "Panel A: Gross alpha percentiles",
        ),
        (
            axes[1],
            pan_b,
            x_b,
            y_b,
            "Novy-Marx and Velikov  (RFS, 2016)\nNet Generalized Alpha (%/month)",
            "Panel B: Net alpha percentiles",
        ),
    ):
        if y is None or y.size == 0:
            continue
        n_models = y.shape[1]
        model_handles = []
        for i in range(n_models):
            gray = 1.0 - 0.05 * (i + 1)
            gray = float(np.clip(gray, 0.0, 1.0))
            (h,) = ax.plot(x[: y.shape[0]], y[:, i], linewidth=2.5, color=(gray, gray, gray))
            model_handles.append(h)
        dx = _as_1d(_get(pan, "dx"))
        dy = _as_1d(_get(pan, "dy"))
        n_sc = min(5, dx.size, dy.size)
        h_sc = None
        if n_sc:
            h_sc = ax.scatter(
                dx[:n_sc],
                dy[:n_sc],
                marker="D",
                s=40,
                c="k",
                zorder=5,
            )
        lbls = ["CAPM", "FF3", "FF4", "FF5", "FF6"]
        if pan is pan_a:
            # Explicit handles: a bare label list would rely on matplotlib collecting the
            # model lines before the scatter's PathCollection.
            handles = list(model_handles)
            labels = lbls[:n_models] + [f"Model {i + 1}" for i in range(len(lbls), n_models)]
            if h_sc is not None:
                handles.append(h_sc)
                labels.append(sc)
            ax.legend(handles=handles, labels=labels, loc="upper left", frameon=False)
        ax.set_ylabel(ylab)
        ax.set_xlabel("Anomaly percentile rank")
        ax.set_title(title)
        ax.tick_params(labelsize=11)
    return _savefig(fig, _pdf_path(Path(out_dir), sc, "figureAlphaPrctl"))


def plot_name_histogram(
    x: np.ndarray,
    labels: Sequence[str],
    ax: Any | None = None,
) -> Any:
    """Port of ``plotNameHistogram.m`` onto an Axes."""
    plt = _ensure_matplotlib()
    x = _as_1d(x)
    labels = [str(lbl) for lbl in labels]
    if len(labels) != x.size:
        # pad / trim
        if len(labels) < x.size:
            labels = list(labels) + [""] * (x.size - len(labels))
        else:
            labels = list(labels)[: x.size]
    if x.size == 0:
        ax = ax or plt.gca()
        return ax

    # Remove underscores & limit length (MATLAB strLim=10)
    cleaned = []
    for lab in labels:
        lab = lab.replace("_", "")
        cleaned.append(lab[:10])
    labels = cleaned

    abs_max = float(np.nanmax(np.abs(x))) if x.size else 0.0
    x_lims = int(np.ceil(abs_max / 20.0) * 20) if abs_max > 0 else 20
    bins = np.arange(-x_lims, x_lims + 20, 20, dtype=float)
    n_bins = len(bins)
    n_counts, _ = np.histogram(x, bins=bins)

    ax = ax or plt.gca()
    for i in range(n_bins - 1):
        if n_counts[i] <= 0:
            continue
        in_bin = (x >= bins[i]) & (x < bins[i + 1])
        srtd = sorted(lab for lab, m in zip(labels, in_bin) if m)
        # Tick k (1-based) is labelled bins[k-1], so bin i spans ticks i+1 and
        # i+2. MATLAB left-aligns each name at tick i+1 so it runs into the
        # bin; centring it on the bin midpoint keeps the same meaning and
        # stops the names sitting on top of the tick labels.
        for j, lab in enumerate(srtd, start=1):
            ax.text(
                i + 1.5,
                j,
                lab,
                color="black",
                fontsize=7,
                ha="center",
                va="bottom",
            )
    ymax = int(np.ceil(max(n_counts.max() if n_counts.size else 1, 1) / 10.0) * 10)
    ax.set_ylim(0, max(ymax, 10))
    # MATLAB: xlim([0.8 nBins+.2]); nBins = length(bins); xticks 1:nBins with labels bins
    ax.set_xlim(0.8, n_bins + 0.2)
    ax.set_xticks(list(range(1, n_bins + 1)))
    ax.set_xticklabels([str(int(b)) for b in bins])
    return ax


def emit_correl_figure(
    results: Any,
    out_dir: str | Path,
    *,
    signal_char: str | None = None,
) -> Path | None:
    """``{sc}_figureCorrel.pdf`` from ``Fig_Correls``."""
    sc = _signal_char(results, signal_char)
    corr = _get(results, "Fig_Correls") or {}
    pan_a = _get(corr, "PanelA") or {}
    pan_b = _get(corr, "PanelB") or {}
    x_a = _as_1d(_get(pan_a, "x"))
    x_b = _as_1d(_get(pan_b, "x"))
    if x_a.size == 0 and x_b.size == 0:
        LOGGER.warning("Fig_Correls empty; skip")
        return None
    lbl_a = list(_get(pan_a, "lbl") or [])
    lbl_b = list(_get(pan_b, "lbl") or [])

    plt = _ensure_matplotlib()
    fig, axes = plt.subplots(2, 1, figsize=(7.0, 12.0))
    plot_name_histogram(x_a, lbl_a, ax=axes[0])
    axes[0].set_xlabel("Panel A: Spearman")
    plot_name_histogram(x_b, lbl_b, ax=axes[1])
    axes[1].set_xlabel("Panel B: Pearson")
    return _savefig(fig, _pdf_path(Path(out_dir), sc, "figureCorrel"))


def _matlab_linkage_to_scipy(Z: np.ndarray) -> np.ndarray:
    """Convert MATLAB linkage ((n-1)Ã—3, 1-based) to SciPy ((n-1)Ã—4, 0-based)."""
    Z = np.asarray(Z, dtype=float)
    if Z.ndim != 2:
        raise ValueError(f"Z must be 2-D, got shape {Z.shape}")
    if Z.shape[1] == 4:
        # Heuristic: if indices look 1-based (min >= 1 and integers), convert
        if np.nanmin(Z[:, :2]) >= 1.0 and np.allclose(Z[:, :2], np.round(Z[:, :2])):
            n_leaf = Z.shape[0] + 1
            # if max cluster id exceeds scipy expectation, likely already 0-based
            if np.nanmax(Z[:, :2]) >= n_leaf:  # merged cluster ids
                Z = Z.copy()
                Z[:, 0] -= 1.0
                Z[:, 1] -= 1.0
        return Z
    if Z.shape[1] != 3:
        # maybe transposed
        if Z.shape[0] == 3:
            Z = Z.T
        elif Z.shape[0] == 4:
            return _matlab_linkage_to_scipy(Z.T)
        else:
            raise ValueError(f"unexpected Z shape {Z.shape}")
    n = Z.shape[0] + 1
    left = Z[:, 0].astype(int) - 1
    right = Z[:, 1].astype(int) - 1
    dist = Z[:, 2]
    counts = np.zeros(Z.shape[0], dtype=float)
    for i in range(Z.shape[0]):
        cl = 1.0 if left[i] < n else counts[left[i] - n]
        cr = 1.0 if right[i] < n else counts[right[i] - n]
        counts[i] = cl + cr
    return np.column_stack([left.astype(float), right.astype(float), dist, counts])


def _strip_dendro_label(lab: str) -> tuple[str, str | None]:
    """Return (display_label, color) from MATLAB ``\\color{red}{X}`` wrappers."""
    s = str(lab)
    m = re.search(r"\\color\{(\w+)\}\{([^}]*)\}", s)
    if m:
        return m.group(2), m.group(1)
    # also handle plain /color{} without backslash leftovers
    return s, None


def emit_dendrogram_figure(
    results: Any,
    out_dir: str | Path,
    *,
    signal_char: str | None = None,
) -> Path | None:
    """``{sc}_figureDendrogram.pdf`` from ``Fig_Dendrogram``."""
    sc = _signal_char(results, signal_char)
    dg = _get(results, "Fig_Dendrogram") or {}
    Z_raw = _get(dg, "Z")
    labels_raw = list(_get(dg, "dendrogramLabels") or [])
    cutoff = _get(dg, "cutoff")
    if Z_raw is None:
        LOGGER.warning("Fig_Dendrogram.Z missing; skip")
        return None
    Z = np.asarray(Z_raw, dtype=float)
    if Z.size == 0 or not np.any(Z):
        LOGGER.warning("Fig_Dendrogram.Z empty/zero; skip")
        return None
    if Z.ndim == 2 and Z.shape[0] in (3, 4) and Z.shape[1] > Z.shape[0]:
        Z = Z.T
    Z_sp = _matlab_linkage_to_scipy(Z)
    n_leaves = Z_sp.shape[0] + 1
    if not labels_raw:
        labels_raw = [str(i) for i in range(n_leaves)]
    display_labels = []
    leaf_colors: dict[str, str] = {}
    for lab in labels_raw:
        d, c = _strip_dendro_label(lab)
        display_labels.append(d)
        if c:
            leaf_colors[d] = c
    # pad / trim to n_leaves
    if len(display_labels) < n_leaves:
        display_labels += [""] * (n_leaves - len(display_labels))
    else:
        display_labels = display_labels[:n_leaves]

    from scipy.cluster.hierarchy import dendrogram  # type: ignore

    plt = _ensure_matplotlib()
    fig, ax = plt.subplots(figsize=(14.0, 6.0))
    color_threshold = float(np.asarray(cutoff).ravel()[0]) if cutoff is not None else None
    dendrogram(
        Z_sp,
        ax=ax,
        labels=display_labels,
        color_threshold=color_threshold,
        leaf_rotation=90,
        leaf_font_size=8,
    )
    # Color the test-signal leaf red when marked
    for tick in ax.get_xticklabels():
        if tick.get_text() in leaf_colors:
            tick.set_color(leaf_colors[tick.get_text()])
    return _savefig(fig, _pdf_path(Path(out_dir), sc, "figureDendrogram"))


def emit_cond_strats_figure(
    results: Any,
    out_dir: str | Path,
    *,
    signal_char: str | None = None,
) -> Path | None:
    """``{sc}_figureCondStrats.pdf`` from ``Fig_CondAnoms``."""
    sc = _signal_char(results, signal_char)
    cond = _get(results, "Fig_CondAnoms") or {}
    hists = [
        _as_1d(_get(_get(cond, p) or {}, "Hist"))
        for p in ("PanelA", "PanelB", "PanelC")
    ]
    if all(h.size == 0 for h in hists):
        LOGGER.warning("Fig_CondAnoms empty; skip")
        return None
    labels = [
        "Panel A: T-stats from Fama-MacBeths",
        "Panel B: T-stats from spanning tests",
        "Panel C: T-stats from conditional sorts",
    ]
    plt = _ensure_matplotlib()
    fig, axes = plt.subplots(3, 1, figsize=(8.0, 8.0))
    for ax, h, xlab in zip(axes, hists, labels):
        if h.size:
            ax.hist(h[~np.isnan(h)], bins="auto", edgecolor="none")
        ax.set_xlabel(xlab)
    return _savefig(fig, _pdf_path(Path(out_dir), sc, "figureCondStrats"))


def emit_comb_strats_figure(
    results: Any,
    out_dir: str | Path,
    *,
    signal_char: str | None = None,
) -> Path | None:
    """``{sc}_figureCombStrats.pdf`` from ``Fig_CombStrat``."""
    sc = _signal_char(results, signal_char)
    comb = _get(results, "Fig_CombStrat") or {}
    y_wo = _as_2d(_get(comb, "yWithout"))
    y_w = _as_2d(_get(comb, "yWith"))
    x = _as_1d(_get(comb, "x"))
    ttl = list(_get(comb, "ttl") or [])
    if y_wo.size == 0 and y_w.size == 0:
        LOGGER.warning("Fig_CombStrat empty; skip")
        return None
    # Orient months Ã— methods
    if y_wo.ndim == 2 and y_w.ndim == 2:
        if y_wo.shape[0] < y_wo.shape[1] and x.size == y_wo.shape[1]:
            y_wo = y_wo.T
            y_w = y_w.T
        elif y_wo.shape[1] != y_w.shape[1] and y_wo.shape[0] == y_w.shape[0]:
            pass
    n_methods = max(y_wo.shape[1] if y_wo.size else 0, y_w.shape[1] if y_w.size else 0, len(ttl))
    if n_methods == 0:
        return None
    if not ttl:
        ttl = [f"Method {i + 1}" for i in range(n_methods)]

    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    plt = _ensure_matplotlib()
    n_row, n_col = 3, 2
    # 12 by 9: at 12 by 10 the caption ran into the page number.
    fig, axes = plt.subplots(n_row, n_col, figsize=(12.0, 9.0))
    axes_flat = np.asarray(axes).ravel()
    # Cumulate every panel first, so all of them can share one y-axis: a method is only
    # comparable with its neighbours if $10 is the same height in all six panels.
    paths = []
    for i in range(n_methods):
        col_wo = y_wo[:, i] if y_wo.size and i < y_wo.shape[1] else np.array([])
        col_w = y_w[:, i] if y_w.size and i < y_w.shape[1] else np.array([])
        cols = [c for c in (col_wo, col_w) if c.size]
        if not cols:
            paths.append((None, None))
            continue
        paths.append(ibbots_cumret(np.column_stack(cols), x if x.size else None))
    ylim = dollar_range(*(yy for _, yy in paths))

    for i in range(n_methods):
        ax = axes_flat[i] if i < len(axes_flat) else None
        if ax is None:
            break
        xx, yy = paths[i]
        h_wo = h_w = None
        if yy is not None:
            colors = ("C0", "r")
            handles = []
            for j in range(yy.shape[1]):
                (h,) = ax.semilogy(xx, yy[:, j], color=colors[j % 2], linewidth=2.0)
                handles.append(h)
            h_wo, h_w = (handles + [None, None])[:2]
        if i == 0 and h_wo is not None:
            pairs = [(h_wo, "Without new signal"), (h_w, "With new signal")]
            pairs = [(h, lb) for h, lb in pairs if h is not None]
            ax.legend(
                handles=[h for h, _ in pairs],
                labels=[lb for _, lb in pairs],
                loc="upper left",
            )
        # MATLAB gets these from ibbots(); the Python port cumulates inline, so the
        # dollar ticks have to be applied here too.
        _apply_dollar_log_axis(ax, ylim)
        title = ttl[i] if i < len(ttl) else f"Method {i + 1}"
        ax.set_title(f"Panel {alphabet[i]}: {title}")
        ax.tick_params(labelsize=10)
    # hide unused axes
    for j in range(n_methods, len(axes_flat)):
        axes_flat[j].set_visible(False)
    return _savefig(fig, _pdf_path(Path(out_dir), sc, "figureCombStrats"))


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------
def emit_all_figures(
    results: Any,
    out_dir: str | Path,
    *,
    signal_char: str | None = None,
) -> dict[str, Path]:
    """Emit all 8 assay figure PDFs into ``out_dir``.

    Returns a dict mapping basename suffix â†’ written path (missing keys if skipped).
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sc = _signal_char(results, signal_char)
    emitters = (
        ("figureSignalDescription", emit_signal_description_figure),
        ("figureSharpeDist", emit_sharpe_dist_figure),
        ("figureIbbots", emit_ibbots_figure),
        ("figureAlphaPrctl", emit_alpha_prctl_figure),
        ("figureCorrel", emit_correl_figure),
        ("figureDendrogram", emit_dendrogram_figure),
        ("figureCondStrats", emit_cond_strats_figure),
        ("figureCombStrats", emit_comb_strats_figure),
    )
    written: dict[str, Path] = {}
    for suffix, fn in emitters:
        path = _safe(suffix, fn, results, out_dir, signal_char=sc)
        if path is not None:
            written[suffix] = path
    LOGGER.info(
        "Emitted %d/%d figure PDFs for %s under %s",
        len(written),
        len(emitters),
        sc,
        out_dir,
    )
    return written
