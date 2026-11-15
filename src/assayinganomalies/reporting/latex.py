"""
LaTeX document assembler for the assay protocol paper.

Python port of ``Functions/Assay functions/prt/printTexFile.m`` and the
section / figure-include / bibliography writers it calls.

Emits multi-section ``.tex`` from a ``PrintResults`` object with table bodies
and ``\\includegraphics`` basenames. When ``emit_figures=True`` (default),
also writes the eight ``{Signal}_figure*.pdf`` files via ``reporting.figures``.
"""

from __future__ import annotations

import calendar
import io
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping, Sequence, TextIO

import numpy as np

from ..config import scratch_dir
from ..provenance import DEMO_LABEL
from .figures import emit_all_figures
from .tables import (
    add_comma,
    close_anom_selection_sentence,
    mat_to_tex,  # noqa: F401  re-export convenience
    num_to_words,
    print_basic_sort_table,
    _tex_escape,
    print_close_anoms_fmb_table,
    print_close_anoms_span_table,
    print_cond_size_sort_table,
    print_robustness_to_sorting_table,
    print_sub_sample_table,
    tcost_wording,
)

LOGGER = logging.getLogger("assayinganomalies.reporting.latex")

__all__ = [
    "print_tex_file",
    "compile_pdf",
    "latexmk_available",
    "print_document_header",
    "print_title_page",
    "print_intro_section",
    "print_signal_description_section",
    "print_return_prediction_section",
    "print_other_anomalies_section",
    "print_close_anoms_section",
    "print_comb_strats_section",
    "print_end_of_paper_text",
    "print_bibliography_file",
    "num_to_words",
    "add_comma",
    "semantic_tex_diff",
    "strip_date_today",
]


# ---------------------------------------------------------------------------
# Access helpers
# ---------------------------------------------------------------------------
def _text(results: Any) -> Any:
    t = getattr(results, "Text", None)
    if t is None and isinstance(results, Mapping):
        t = results.get("Text")
    if t is None:
        raise ValueError("Results.Text is required")
    return t


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _signal_period(text: Any, *keys: str) -> np.ndarray:
    """The first of ``Text.<key>`` that the results have, else ``Text.timePeriod``.

    The keys are ``valuePeriod``, ``sortPeriod`` and ``returnPeriod``; results
    saved by an earlier version have none of them.
    """
    for key in (*keys, "timePeriod"):
        val = _get(text, key)
        if val is not None and np.asarray(val).size >= 2:
            return np.asarray(val, dtype=int).ravel()
    raise ValueError("Results.Text.timePeriod is required")


def _is_demo(results: Any) -> bool:
    """
    Whether this report's numbers came from a demo (synthetic) database.

    The flag rides on ``printResults.metadata``, stamped by the protocol run.
    Absent metadata means an older or hand-built results object, which reads
    as production: the banner is a guard against the accidental demo run, and
    printing it on a real report would be its own kind of wrong.
    """
    return bool(_get(_get(results, "metadata"), "demo_data", False))


def _zoo_source_footnote(results: Any, signal_char: str) -> str:
    """
    The zoo section's footnote: which C-Z release, and how many anomalies, before the filter.

    Both ride on ``printResults.metadata``, stamped by the protocol run from
    the database (``cz_release``, e.g. ``"2026.10"``) and the zoo it loaded
    (``n_zoo_loaded``). MATLAB hard-codes "March, 2022" and 207. When the
    database does not record the release (built before it was recorded, or
    from a pinned or hand-placed file) the footnote says so instead of naming
    one; a results object without the count leaves the number out.
    """
    meta = _get(results, "metadata")
    label = str(_get(meta, "cz_release", "") or "")
    m = re.fullmatch(r"(\d{4})\.(\d{2})", label)
    if m and 1 <= int(m.group(2)) <= 12:
        source = (
            f"The anomalies come from the {calendar.month_name[int(m.group(2))]} "
            f"{m.group(1)} release of the \\citet{{ChenZimmermann2022}} open source "
            "asset pricing dataset."
        )
    else:
        source = (
            "The anomalies come from the \\citet{ChenZimmermann2022} open source asset "
            "pricing dataset (the database does not record which release)."
        )
    n_loaded = _get(meta, "n_zoo_loaded", None)
    their = f"their {int(n_loaded)} anomalies" if n_loaded else "their anomalies"
    return (
        f"{source} We filter {their} and require for each anomaly more than ten years "
        "of data and, in the average month, a signal for more than 40\\% of the stocks "
        "with market capitalization on CRSP in the sample period of this report."
    )


def _arr(obj: Any, *path: str) -> np.ndarray:
    cur = obj
    for p in path:
        cur = _get(cur, p)
        if cur is None:
            raise KeyError(".".join(path))
    return np.asarray(cur, dtype=float)


def _signal_info(results: Any) -> Mapping[str, Any]:
    info = getattr(results, "signalInfo", None)
    if info is None and isinstance(results, Mapping):
        info = results.get("signalInfo") or results.get("signal_info")
    if not info:
        return {}
    if hasattr(info, "to_dict"):
        return info.to_dict()  # type: ignore[no-any-return]
    if isinstance(info, Mapping):
        return info
    # dataclass-like
    out: dict[str, Any] = {}
    for k in (
        "Authors",
        "authors",
        "PaperTitle",
        "paper_title",
        "SignalName",
        "signal_name",
        "SignalAcronym",
        "signal_acronym",
        "email",
        "fileLink",
        "file_link",
    ):
        if hasattr(info, k):
            out[k] = getattr(info, k)
    # normalize keys to MATLAB names
    return {
        "Authors": out.get("Authors") or out.get("authors") or "",
        "PaperTitle": out.get("PaperTitle") or out.get("paper_title") or "",
        "SignalName": out.get("SignalName") or out.get("signal_name") or "",
        "SignalAcronym": out.get("SignalAcronym") or out.get("signal_acronym") or "",
        "email": out.get("email") or "",
        "fileLink": out.get("fileLink") or out.get("file_link") or "",
    }


_UNESCAPED_DOLLAR = re.compile(r"(?<!\\)\$")
_TEXT_NEGATIVE = re.compile(r"(?<![\w\-.,$^_{}\\])-(\d[\d,]*(?:\.\d+)?)")


def _minus_signs(tex: str) -> str:
    """Set the negative numbers of running text in math: ``-0.17`` -> ``$-0.17$``.

    In text mode a hyphen before a digit prints as a hyphen, not a minus
    sign. Only text outside ``$...$`` is touched, and only a hyphen that
    starts a number: one after a letter, a digit or another hyphen (a range
    of months, ``C-V``, ``long-short``) stays. For sentences and captions;
    table bodies are not passed through here.
    """
    pieces = _UNESCAPED_DOLLAR.split(tex)
    for i in range(0, len(pieces), 2):          # even pieces are outside math
        pieces[i] = _TEXT_NEGATIVE.sub(r"$-\1$", pieces[i])
    return "$".join(pieces)


def _ordinal(n: Any) -> str:
    """``85`` -> ``"85th"``; ``1st``, ``2nd``, ``3rd``, ``11th``, ``21st``."""
    k = int(round(float(n)))
    if 10 <= abs(k) % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(abs(k) % 10, "th")
    return f"{k}{suffix}"


def _count_of(n: int, total: int) -> str:
    """``"all three"`` / ``"two of the three"`` / ``"none of the three"``."""
    if n >= total:
        return f"all {num_to_words(total)}"
    if n <= 0:
        return f"none of the {num_to_words(total)}"
    return f"{num_to_words(n)} of the {num_to_words(total)}"


def _re_between(s: str, left: str, right: str) -> str:
    """``extractBetween``-like helper."""
    i = s.find(left)
    if i < 0:
        return s
    i += len(left)
    j = s.find(right, i)
    if j < 0:
        return s[i:]
    return s[i:j]


def _write(fid: TextIO | None, s: str, buf: io.StringIO | None = None) -> None:
    if fid is not None:
        fid.write(s)
    if buf is not None:
        buf.write(s)


# ---------------------------------------------------------------------------
# Header / title
# ---------------------------------------------------------------------------
def print_document_header(fid: TextIO | None = None) -> str:
    parts = [
        "\\documentclass[12pt]{article}\n",
        "\\usepackage{amsfonts,amsmath,amssymb,amsthm,setspace,enumerate,graphicx,"
        "threeparttable,multirow,fullpage,comment,booktabs,array,tabularx,lscape,"
        "verbatim,titling,pdfpages,natbib,rotating,pdflscape,subcaption} \n",
        "\\usepackage[labelsep=colon,labelfont=bf,justification=justified,"
        "singlelinecheck=false]{caption}  \n",
        "\\usepackage[top=1in,bottom=1in]{geometry} \n",
        "\\usepackage[title]{appendix} \n",
        "\\usepackage[]{hyperref} \n",
        "\\usepackage{xcolor} \n",
        "\\hypersetup{colorlinks,linkcolor={blue!50!black},citecolor={blue!50!black},"
        "urlcolor={blue!80!black}} \n",
    ]
    out = "".join(parts)
    if fid is not None:
        fid.write(out)
    return out


# The report's title names the signal, not the paper that uses it.
# SignalInfo.PaperTitle is kept but no longer printed.
_REPORT_TITLE_LINES = (
    "Assaying Anomalies Performance Report\\\\\n"
    "for Cross-Sectional Return Predictor\\\\\n"
)


def print_title_page(results: Any, fid: TextIO | None = None) -> str:
    info = _signal_info(results)
    text = _text(results)
    author_names = str(info.get("Authors") or "").split(" and ")
    author_text = r"\author{\vspace{\baselineskip}{" + author_names[0].strip() + "}"
    for a in author_names[1:]:
        author_text += r"\and {" + a.strip() + "}"
    author_text += "}"

    robust_a = _arr(results, "Tab_RobustSort", "PanelA", "a")
    robust_t = _arr(results, "Tab_RobustSort", "PanelA", "tA")
    robust_b = _arr(results, "Tab_RobustSort", "PanelB", "a")
    robust_bt = _arr(results, "Tab_RobustSort", "PanelB", "tA")
    # MATLAB (1,6) = row0, col5 of 5-sorts × 6 stats  (or last col)
    c_ff6 = min(5, robust_a.shape[1] - 1)
    gross_ff6 = f"{100 * robust_a[0, c_ff6]:.0f}"
    net_ff6 = f"{100 * robust_b[0, c_ff6]:.0f}"
    gross_t = f"{robust_t[0, c_ff6]:.2f}"
    net_t = f"{robust_bt[0, c_ff6]:.2f}"

    span_a = _arr(results, "Tab_CloseSpan", "a")
    span_t = _arr(results, "Tab_CloseSpan", "tA")
    alpha_close = f"{100 * span_a[0, -1]:.0f}"
    tstat_close = f"{span_t[0, -1]:.2f}"

    n_close = int(_get(text, "nCloseAnoms", 0))
    n_close_char = num_to_words(n_close)
    close_anoms = _tex_escape(str(_get(text, "closeAnoms", "")))  # names may hold & or %
    signal_char = str(_get(text, "signalChar", info.get("SignalAcronym", "SIGNAL")))
    sharpe = str(_get(text, "sharpeChar", ""))
    net_sharpe = str(_get(text, "netSharpeChar", ""))

    abstract = (
        f"This report studies the asset pricing implications of {info.get('SignalName', '')} "
        f"({info.get('SignalAcronym', '')}), and its robustness in predicting returns in the "
        "cross-section of equities "
        "using the protocol proposed by \\citet{Novy-MarxVelikov2026}. "
        f"A value-weighted long/short trading strategy based on {signal_char} "
        f"achieves an annualized gross (net) Sharpe ratio of {sharpe} "
        f"({net_sharpe}), and monthly average abnormal gross (net) "
        "return relative to the \\citet{FamaFrench2015} five-factor model plus a momentum "
        f"factor of {gross_ff6} ({net_ff6}) bps/month with a t-statistic of "
        f"{gross_t} ({net_t}), respectively. Its gross monthly alpha "
        f"relative to these six factors plus the {n_close_char} most closely related strategies from "
        f"the factor zoo ({close_anoms}) is {alpha_close} bps/month with a "
        f"t-statistic of {tstat_close}. \n"
    )
    abstract = _minus_signs(abstract)

    # A report built on a demo database says so in its own title and first
    # line of abstract, not only in a log nobody keeps. The .tex is the
    # artifact that travels.
    if _is_demo(results):
        title_line = (
            f"\\textcolor{{red}}{{[{_tex_escape(DEMO_LABEL)}]}}\\\\\n"
            + _REPORT_TITLE_LINES
        )
        abstract = (
            f"\\textbf{{\\textcolor{{red}}{{{_tex_escape(DEMO_LABEL)}.}}}} "
            "Every number in this report was computed from synthetic "
            "stand-in data, not from CRSP, COMPUSTAT or the "
            "Chen-Zimmerman anomaly zoo. It demonstrates the protocol's "
            "output format and nothing else. "
        ) + abstract
    else:
        title_line = _REPORT_TITLE_LINES

    out = (
        f"\\title{{{title_line}"
        f"{info.get('SignalName', '')}}}\n"
        f"{author_text}"
        "\\date{\\today}\n"
        "\\begin{document}\n\n"
        "\\maketitle\n"
        "\\begin{abstract}\n\n"
        f"{abstract}"
        "\\end{abstract}\n\n"
    )
    if fid is not None:
        fid.write(out)
    return out


def _package_version_phrase() -> str:
    """``"version 0.9.0"`` from the installed package, for the intro footnote."""
    from importlib import metadata

    try:
        return f"version {metadata.version('assayinganomalies')}"
    except metadata.PackageNotFoundError:
        return "an unreleased version"


def print_intro_section(results: Any, fid: TextIO | None = None) -> str:
    info = _signal_info(results)
    out = (
        "\\doublespacing\n\n"
        "\\newpage\n"
        "\\clearpage\n\n"
        "\\section{Introduction}\n"
        f"The following automatically generated report tests the asset pricing implications of "
        f"{info.get('SignalName', '')} ({info.get('SignalAcronym', '')}), and its robustness in "
        "predicting returns in the cross-section of equities. "
        "It is produced using the methodology of \\citet{Novy-MarxVelikov2026}, from input data "
        "consisting of firm-month observations for the proposed predictor.\\footnote{It used "
        f"{_package_version_phrase()} of the publicly available code repository at "
        "\\href{https://github.com/velikov-mihail/AssayingAnomalies}"
        "{https://github.com/velikov-mihail/AssayingAnomalies}. See more details at "
        "\\href{https://AssayingAnomalies.com}"
        "{https://AssayingAnomalies.com}.}\n\n\n"
    )
    if fid is not None:
        fid.write(out)
    return out


# ---------------------------------------------------------------------------
# Section prose writers
# ---------------------------------------------------------------------------
def print_signal_description_section(results: Any, fid: TextIO | None = None) -> str:
    text = _text(results)
    signal_char = str(_get(text, "signalChar", "SIGNAL"))
    tp = np.asarray(_get(text, "timePeriod"), dtype=int).ravel()
    y_a = _arr(results, "Fig_Cov", "PanelA", "y")
    y_b = _arr(results, "Fig_Cov", "PanelB", "y")
    pan_a = _get(_get(results, "Fig_Cov"), "PanelA")
    x = np.asarray(_get(pan_a, "x"), dtype=float)
    # Prefer masking by YYYYMM timePeriod via pdate conversion
    s_p = float(tp[0] // 100) + (tp[0] % 100 - 1) / 12.0
    e_p = float(tp[-1] // 100) + (tp[-1] % 100 - 1) / 12.0
    # Also try direct index if Fig_Cov was built on library dates matching YYYYMM
    mask = (x >= s_p - 1e-9) & (x <= e_p + 1e-9)
    if not np.any(mask):
        mask = np.ones(y_a.shape[0], dtype=bool)

    signal_mean = f"{np.nanmean(y_a[mask, -1]):.2f}"
    signal_median = f"{np.nanmean(y_a[mask, 1]):.2f}"
    signal_iqr_lb = f"{np.nanmin(y_a[mask, 0]):.2f}"
    signal_iqr_ub = f"{np.nanmax(y_a[mask, 2]):.2f}"
    # The years of the months in which the signal has values, not of
    # the run's window, which may start before the signal does.
    vp = _signal_period(text, "valuePeriod")
    sample_start = str(int(vp[0] // 100))
    sample_end = str(int(vp[-1] // 100))
    # Coverage is averaged over the months in which the signal has values. A
    # signal built from annual Compustat columns has values in June only
    # (Ch 13, "When a sort trades"); its other months have coverage 0 by
    # construction, and averaging over them would understate it twelvefold.
    # For a signal with values every month this is the average over all months.
    has_signal = mask & np.isfinite(y_b[:, 0]) & (y_b[:, 0] > 0)
    cov_mask = has_signal if np.any(has_signal) else mask
    avg_names = f"{100 * np.nanmean(y_b[cov_mask, 0]):.2f}"
    avg_mcap = f"{100 * np.nanmean(y_b[cov_mask, 1]):.2f}"

    body = (
        f"Figure~\\ref{{fig:descriptiveStats}}  plots descriptive statistics for the "
        f"{signal_char} signal. Panel A plots the time-series of the mean, median, and "
        f"interquartile range for {signal_char}. "
        f"On average, the cross-sectional mean (median) {signal_char} is {signal_mean} "
        f"({signal_median})  over the {sample_start} to {sample_end} sample, where the "
        f"starting date is determined by the availability of the input {signal_char} data. "
        f"The signal's interquartile range spans {signal_iqr_lb} to {signal_iqr_ub}. "
        f"Panel B of Figure~\\ref{{fig:descriptiveStats}} plots the time-series of the "
        f"coverage of the {signal_char} signal for the CRSP universe. On average over the "
        f"months in which it has values, the {signal_char} signal is available for "
        f"{avg_names}\\% of CRSP names,  which on "
        f"average make up {avg_mcap}\\% of total market capitalization.\n\n\n"
    )
    body = _minus_signs(body)
    out = (
        "\\section{Signal diagnostics} \n"
        "\\label{sec:signalDescription}\n\n\n"
        + body
    )
    if fid is not None:
        fid.write(out)
    return out


def print_return_prediction_section(results: Any, fid: TextIO | None = None) -> str:
    text = _text(results)
    signal_char = str(_get(text, "signalChar", "SIGNAL"))
    sharpe_char = str(_get(text, "sharpeChar", ""))
    tcosts_type = str(_get(text, "tcostsType", "full"))
    # The first mention of trading costs defines the estimator.
    tc_words = tcost_wording(tcosts_type)

    pa = _get(_get(results, "Tab_BasicSort"), "PanelA")
    pb = _get(_get(results, "Tab_BasicSort"), "PanelB")
    pc = _get(_get(results, "Tab_BasicSort"), "PanelC")
    a_a = np.asarray(pa["a"], dtype=float)
    t_a = np.asarray(pa["tA"], dtype=float)
    h_a = list(pa["h"])
    a_b = np.asarray(pb["a"], dtype=float)
    t_b = np.asarray(pb["tA"], dtype=float)
    h_b = list(pb["h"])
    a_c = np.asarray(pc["a"], dtype=float)

    average_ret = f"{a_a[0, -1]:.2f}"
    average_t = f"{t_a[0, -1]:.2f}"
    alphas = a_a[1:, -1]
    t_alphas = t_a[1:, -1]
    alpha_min_i = int(np.nanargmin(alphas))
    alpha_min = f"{np.nanmin(alphas):.2f}"
    alpha_max = f"{np.nanmax(alphas):.2f}"
    talpha_min = f"{np.nanmin(t_alphas):.2f}"
    alpha_min_fm = _re_between(str(h_a[alpha_min_i + 1]), "{", "}")

    out_parts: list[str] = [
        f"\\section{{Does {signal_char} predict returns?}} \n",
        "\\label{sec:returnPrediction}\n\n\n",
        (
            f"Table~\\ref{{tab:tsRegs}} reports the performance of portfolios constructed "
            f"using a value-weighted, quintile sort on  {signal_char} using NYSE breaks. "
            "The first two lines of Panel A report monthly average excess returns "
            f"for each of the five portfolios and for the long/short portfolio that buys "
            f"the high {signal_char} portfolio and sells the low {signal_char} portfolio. "
            "The rest of Panel A reports the portfolios' "
            "monthly abnormal returns relative to the five most common factor models: the "
            "CAPM, the \\citet{FamaFrench1993} three-factor model (FF3) and its variation "
            "that adds momentum (FF4), the \\citet{FamaFrench2015} five-factor model (FF5), "
            "and its variation that adds the momentum factor, used in \\citet{FamaFrench2018} "
            f"(FF6). The table shows that the long/short {signal_char} strategy earns an "
            f"average return of {average_ret}\\% per month with a t-statistic of "
            f"{average_t}. The annualized Sharpe ratio of the strategy is {sharpe_char}. "
            f"The alphas range from {alpha_min}\\% to {alpha_max}\\% per month and have "
            f"t-statistics of at least {talpha_min}. The lowest alpha is with "
            f"respect to the {alpha_min_fm} factor model.\n\n\n"
        ),
    ]

    tbetas = t_b[:, -1]
    max_i = int(np.nanargmax(np.abs(tbetas)))
    max_beta = f"{a_b[max_i, -1]:.2f}"
    max_t = f"{tbetas[max_i]:.2f}"
    max_lab = _re_between(str(h_b[max_i]), r"\text{", "}")
    n_stocks = a_c[0, :]
    min_n_i = int(np.nanargmin(n_stocks))
    min_n = add_comma(n_stocks[min_n_i])
    m_caps = a_c[1, :]
    min_m_i = int(np.nanargmin(m_caps))
    min_m = add_comma(m_caps[min_m_i])
    out_parts.append(
        "Panel B reports the six portfolios' loadings on the factors in the "
        "\\citet{FamaFrench2018} six-factor model.  "
        f"The long/short strategy's most significant loading is {max_beta}, with a "
        f"t-statistic of {max_t} on the {max_lab} factor. Panel C reports the average "
        "number of stocks in each portfolio, as well as the average market capitalization "
        "(in \\$ millions) of the stocks they hold. In an average month, "
        f"the five portfolios have at least {min_n} stocks and an average market "
        f"capitalization of at least \\${min_m} million.\n\n\n"
    )

    # Table 2 Panel A
    ra = _get(_get(results, "Tab_RobustSort"), "PanelA")
    rets = np.asarray(ra["a"][:, 0], dtype=float)
    h = list(ra["h"])
    min_i = int(np.nanargmin(rets))
    min_ret = f"{100 * rets[min_i]:.0f}"
    min_tret = f"{np.asarray(ra['tA'], dtype=float)[min_i, 0]:.2f}"
    parts_lbl = [p.strip().lower() for p in str(h[min_i]).split("&")]
    while len(parts_lbl) < 3:
        parts_lbl.append("")
    w_lbl = "value-weighted" if parts_lbl[2] == "vw" else "equal-weighted"
    br_lbl = "NYSE" if parts_lbl[1] == "nyse" else parts_lbl[1]
    t_alphas_r = np.asarray(ra["tA"][:, 1:], dtype=float)
    # "all twenty-five" / "seventeen" / "none" of the alphas of the panel.
    def _of_the_alphas(n: int) -> str:
        if n >= t_alphas_r.size:
            return f"all {num_to_words(t_alphas_r.size)}"
        return "none" if n <= 0 else num_to_words(n)

    n_gt2 = _of_the_alphas(int(np.nansum(t_alphas_r > 2)))
    n_gt3 = _of_the_alphas(int(np.nansum(t_alphas_r > 3)))
    out_parts.append(
        "Table~\\ref{tab:robustnessToSorting} reports robustness results for alternative "
        "sorting methodologies, and accounting for trading costs. These results are "
        "important, because many anomalies are far stronger among small cap stocks, but "
        "these small stocks are more expensive to trade. Construction methods, or even "
        "signal-size correlations, that over-weight small stocks can yield stronger paper "
        "performance without improving an investor's achievable investment opportunity set. "
        f"{tc_words['definition']}"
        "Panel A reports gross returns and alphas for the long/short strategies made using "
        "various different portfolio constructions. The first row reports the average "
        "returns and the alphas for the long/short strategy from Table~\\ref{tab:tsRegs}, "
        "which is constructed from a quintile sort using NYSE breakpoints and value-weighted "
        "portfolios. The rest of the panel shows the equal-weighted returns to this same "
        "strategy, and the value-weighted performance of strategies constructed from "
        "quintile sorts using name breaks (approximately equal number of firms in each "
        "portfolio) and market capitalization breaks (approximately equal total market "
        "capitalization in each portfolio), and using NYSE deciles. The average return is "
        f"lowest for the {parts_lbl[0]} sort using {br_lbl} breakpoints and {w_lbl} "
        f"portfolios, and equals {min_ret} bps/month with a t-statistic of {min_tret}. "
        f"Out of the {num_to_words(t_alphas_r.size)} alphas reported in Panel A, the "
        f"t-statistics for {n_gt2} "
        f"exceed two, and for {n_gt3} exceed three.\n\n\n"
    )

    # Panel B net
    rb = _get(_get(results, "Tab_RobustSort"), "PanelB")
    rets_n = np.asarray(rb["a"][:, 0], dtype=float)
    h_n = list(rb["h"])
    min_i = int(np.nanargmin(rets_n))
    max_i = int(np.nanargmax(rets_n))
    min_ret = f"{100 * rets_n[min_i]:.0f}"
    max_ret = f"{100 * rets_n[max_i]:.0f}"
    min_tret = f"{np.asarray(rb['tA'], dtype=float)[min_i, 0]:.2f}"
    parts_lbl = [p.strip().lower() for p in str(h_n[min_i]).split("&")]
    while len(parts_lbl) < 3:
        parts_lbl.append("")
    w_lbl = "value-weighted" if parts_lbl[2] == "vw" else "equal-weighted"
    br_lbl = "NYSE" if parts_lbl[1] == "nyse" else parts_lbl[1]
    net_a = np.asarray(rb["a"][:, 1:], dtype=float)
    net_t = np.asarray(rb["tA"][:, 1:], dtype=float)
    # Only a positive generalized alpha improves the frontier. A
    # blank cell is either not defined (the strategy gets zero weight in the
    # net MVE portfolio) or not estimated; the status counts stamped by
    # make_res_to_print tell them apart, and without them every blank cell
    # reads as not estimated.
    num_fin = num_to_words(int(np.sum(np.isfinite(net_a) & (net_a > 0))))
    num_sig = num_to_words(int(np.nansum(net_t >= 1.96)))
    n_net_blank = int(np.sum(~np.isfinite(net_a)))
    ga_counts = _get(_get(_get(results, "metadata"), "gen_alpha_table"), "counts") or {}
    n_net_zero = min(int(ga_counts.get("zero", 0)), n_net_blank)
    n_net_missing = n_net_blank - n_net_zero
    net_missing_txt = ""
    if n_net_zero:
        net_missing_txt += (
            f" The generalized alpha is not defined for {num_to_words(n_net_zero)} of "
            "these pairs, in which the strategy receives zero weight in the net "
            "mean-variance efficient portfolio."
        )
    if n_net_missing:
        net_missing_txt += (
            f" Generalized alphas could not be estimated for {num_to_words(n_net_missing)} "
            "of these pairs."
        )
    # Results without the key predate held legs (toolkit before 2026-11).
    convention = str(_get(_get(results, "metadata"), "convention", "") or "")
    if convention in ("capital", "dollar"):
        resized = (
            "both legs are set to the strategy's capital"
            if convention == "capital"
            else "each leg is set back to one dollar"
        )
        tcosts_desc = (
            "Each portfolio is bought in a month in which the signal is available and "
            "held, without rebalancing, until the next such month, when "
            f"{resized}. Net returns are "
            "gross returns less the cost of the trades made in those months, "
            f"charged at the {tc_words['short']}; the cost of the initial purchase is "
            "not charged. "
            "The factors' trading costs are those of the 2$\\times$3 portfolios held "
            "between trades, each side brought back to equal shares every month, "
            "under the same convention. "
        )
    else:
        tcosts_desc = (
            "Net returns are gross returns less the cost of each month's rebalancing "
            f"trades, charged at the {tc_words['short']}. "
        )
    out_parts.append(
        "Panel B reports for these same strategies the average monthly net returns and the "
        "generalized net alphas of \\citet{Novy-MarxVelikov2016}. These generalized alphas "
        "measure the extent to which a test asset improves the ex-post mean-variance "
        "efficient portfolio, accounting for the costs of trading both the asset and the "
        f"explanatory factors. {tcosts_desc}"
        f"The net average returns reported in the first column range from {min_ret} to "
        f"{max_ret} bps/month. The lowest return, {min_ret} bps/month, is achieved by the "
        f"{parts_lbl[0]} sort using {br_lbl} breakpoints and {w_lbl} portfolios, and has an "
        f"associated t-statistic of {min_tret}. Out of the twenty-five "
        "construction-methodology-factor-model pairs reported in Panel B, the "
        f"{signal_char} trading strategy improves the achievable mean-variance efficient "
        f"frontier spanned by the factor models in {num_fin} cases, and significantly "
        f"expands the achievable frontier in {num_sig} cases.{net_missing_txt}\n\n\n"
    )

    # Subsample table (Python-only); absent from older results.
    sub = _get(results, "Tab_SubSample") or {}
    sub_a = np.atleast_2d(np.asarray(_get(sub, "a", np.zeros((0, 0))), dtype=float))
    sub_t = np.atleast_2d(np.asarray(_get(sub, "tA", np.zeros((0, 0))), dtype=float))
    sub_h = list(_get(sub, "h", []) or [])
    sub_cols = list(_get(sub, "cols", []) or [])
    if sub_a.shape[0] > 1 and sub_a.shape[1] > 1 and len(sub_h) == sub_a.shape[0]:
        n_sub = sub_a.shape[0] - 1
        re_sub = sub_a[1:, 0]
        t_re_sub = sub_t[1:, 0]
        periods = sub_h[1:]
        n_pos = int(np.sum(np.isfinite(re_sub) & (re_sub > 0)))
        sub_txt = (
            "Table~\\ref{tab:subSample} examines the stability of the strategy's "
            "performance over time. It reports the average return and alphas of the "
            f"long/short {signal_char} strategy from Table~\\ref{{tab:tsRegs}} over the "
            f"full sample and splits the sample into {num_to_words(n_sub)} subsamples "
            "of roughly equal length."
        )
        if np.isfinite(re_sub).any():
            lo_i = int(np.nanargmin(re_sub))
            hi_i = int(np.nanargmax(re_sub))
            sub_txt += (
                f" The strategy's average return is positive in {_count_of(n_pos, n_sub)} "
                "subsamples, ranging from "
                f"{re_sub[lo_i]:.2f}\\% per month (t-statistic of {t_re_sub[lo_i]:.2f}, "
                f"{periods[lo_i]}) to {re_sub[hi_i]:.2f}\\% per month (t-statistic of "
                f"{t_re_sub[hi_i]:.2f}, {periods[hi_i]})."
            )
        last_alpha = sub_a[1:, -1]
        last_t = sub_t[1:, -1]
        if np.isfinite(last_alpha).any():
            model = _re_between(str(sub_cols[-1]), r"\text{", "}") if sub_cols else ""
            model_txt = f"the {model} factor model" if model else "the last factor model"
            sub_txt += (
                f" Its alpha relative to {model_txt} ranges from "
                f"{np.nanmin(last_alpha):.2f}\\% to {np.nanmax(last_alpha):.2f}\\% per "
                f"month across the subsamples, with t-statistics between "
                f"{np.nanmin(last_t):.2f} and {np.nanmax(last_t):.2f}."
            )
        out_parts.append(sub_txt + "\n\n\n")

    # Table 3
    ca = _get(_get(results, "Tab_CondSizeSort"), "PanelA")
    a_cs = np.asarray(ca["a"], dtype=float)
    t_cs = np.asarray(ca["tA"], dtype=float)
    # last row = largest size quintile; col index 7 → re L/S (0-based: n_me + 1)
    n_me = 5
    re_col = n_me + 1
    alphas_row = a_cs[-1, re_col + 1 :]
    t_alphas_row = t_cs[-1, re_col + 1 :]
    large_ret = f"{100 * a_cs[-1, re_col]:.0f}"
    large_t = f"{t_cs[-1, re_col]:.2f}"
    i_min = int(np.nanargmin(alphas_row))
    i_max = int(np.nanargmax(alphas_row))
    out_parts.append(
        "Table~\\ref{tab:doubleSortSize} provides direct tests for the role size plays in "
        f"the {signal_char} strategy performance. Panel A reports the average returns for "
        f"the twenty-five portfolios constructed from a conditional double sort on size and "
        f"{signal_char}, as well as average returns and alphas for long/short "
        f"{signal_char} trading strategies within each size quintile. Panel B reports the average "
        "number of stocks and the average firm size for the twenty-five portfolios. Among "
        "the largest stocks (those with market capitalization greater than the 80$^\\text{th}$ "
        f"NYSE percentile), the {signal_char} strategy achieves an average return of "
        f"{large_ret} bps/month with a t-statistic of {large_t}. Among these large cap "
        f"stocks, the alphas for the {signal_char} strategy relative to the five most common "
        f"factor models range from {100 * alphas_row[i_min]:.0f} to "
        f"{100 * alphas_row[i_max]:.0f} bps/month with t-statistics between "
        f"{t_alphas_row[i_min]:.2f} and {t_alphas_row[i_max]:.2f}.\n\n\n"
    )

    out = _minus_signs("".join(out_parts))
    if fid is not None:
        fid.write(out)
    return out


# Which months an alpha uses, for the anomalies and for the signal.
_ALPHA_MONTHS_SENTENCE = (
    "Each strategy's alphas are estimated over all months in which the strategy "
    "and the model's factors have returns."
)


def _ibbots_window(results: Any) -> tuple[str, str] | None:
    """First and last month (YYYYMM) of the dollar-invested figure, if stored."""
    dates = _get(_get(results, "Fig_Ibbots"), "dates")
    if dates is None:
        return None
    d = np.asarray(dates).ravel()
    if d.size == 0:
        return None
    return str(int(d[0])), str(int(d[-1]))


def _ibbots_window_sentence(results: Any, signal_char: str, *, caption: bool = False) -> str:
    """The window of the dollar-invested figure and its rule for missing months.

    Written only for results that record it (``Fig_Ibbots`` has
    ``nSignalMonths``): in earlier versions the figure covered the run's window and
    spliced differently, and the sentence would be false.
    """
    ib = _get(results, "Fig_Ibbots")
    win = _ibbots_window(results)
    if win is None or _get(ib, "nSignalMonths") is None:
        return ""
    start, end = win
    if caption:
        return (
            f"The figure covers {start} to {end}, the months in which the {signal_char} "
            "strategy has returns; every strategy starts at \\$1. In a month in which an "
            f"anomaly strategy has no return it is given the return of the {signal_char} "
            "strategy. "
        )
    return (
        f"The figure covers {start} to {end}, the months in which the {signal_char} "
        "strategy has returns. In a month of this period in which an anomaly strategy "
        f"has no return, it is given the return of the {signal_char} strategy. "
    )


def print_other_anomalies_section(results: Any, fid: TextIO | None = None) -> str:
    text = _text(results)
    n_anoms = str(_get(text, "nAnoms", ""))
    signal_char = str(_get(text, "signalChar", "SIGNAL"))
    sharpe_char = str(_get(text, "sharpeChar", ""))
    net_sharpe_char = str(_get(text, "netSharpeChar", ""))

    g_a = _get(_get(results, "Fig_SharpeDist"), "PanelA")
    g_b = _get(_get(results, "Fig_SharpeDist"), "PanelB")
    gross_line = float(g_a["Line"])
    gross_hist = np.asarray(g_a["Hist"], dtype=float).ravel()
    net_line = float(g_b["Line"])
    net_hist = np.asarray(g_b["Hist"], dtype=float).ravel()
    gross_rank = f"{100 * np.sum(gross_line > gross_hist) / max(len(gross_hist), 1):.0f}"
    net_rank = f"{100 * np.sum(net_line > net_hist) / max(len(net_hist), 1):.0f}"

    sp = _signal_period(text, "sortPeriod", "returnPeriod")
    sharpe_start, sharpe_end = str(int(sp[0])), str(int(sp[-1]))

    parts = [
        f"\\section{{How does {signal_char} perform relative to the zoo?}}  \n",
        "\\label{sec:otherAnoms}\n\n\n",
        (
            f"Figure~\\ref{{fig:distributionSharpeRatios}} puts the performance of "
            f"{signal_char} in context, showing the long/short strategy performance relative "
            "to other strategies in the ``factor zoo.'' It shows Sharpe ratio histograms, "
            f"both for gross and net returns (Panels A and B, respectively), for {n_anoms} "
            "documented anomalies in the zoo."
            f"\\footnote{{{_zoo_source_footnote(results, signal_char)}}} "
            f"The vertical red line shows where the Sharpe ratio for the {signal_char} "
            f"strategy falls in the distribution. The {signal_char} strategy's gross (net) "
            f"Sharpe ratio of {sharpe_char} ({net_sharpe_char}) is greater than "
            f"{gross_rank}\\% ({net_rank}\\%) of anomaly Sharpe ratios, respectively. "
            "Each anomaly's Sharpe ratio is calculated over all months in which the "
            f"anomaly strategy has returns, and that of {signal_char} over "
            f"{sharpe_start} to {sharpe_end}. \n\n\n"
        ),
    ]

    ib = _get(results, "Fig_Ibbots")
    pret_g_a = np.asarray(ib["pretGrossAnoms"], dtype=float)
    pret_g_s = np.asarray(ib["pretGrossTestSignal"], dtype=float).ravel()
    pret_n_a = np.asarray(ib["pretNetAnoms"], dtype=float)
    pret_n_s = np.asarray(ib["pretNetTestSignal"], dtype=float).ravel()
    # match MATLAB: treat as returns, cumprod; NaNs → leave (MATLAB doesn't nan→0 here)
    with np.errstate(invalid="ignore"):
        cg_a = np.cumprod(1.0 + np.nan_to_num(pret_g_a, nan=0.0), axis=0) - 1.0
        cg_s = np.cumprod(1.0 + np.nan_to_num(pret_g_s, nan=0.0)) - 1.0
        cn_a = np.cumprod(1.0 + np.nan_to_num(pret_n_a, nan=0.0), axis=0) - 1.0
        cn_s = np.cumprod(1.0 + np.nan_to_num(pret_n_s, nan=0.0)) - 1.0
    # The sentence prints the end value of the figure's line (\$1 compounded,
    # `ibbots_cumret`), not the cumulative return: the product, not the
    # product minus one. The ranks compare the same numbers either
    # way.
    cum_g = f"{1.0 + cg_s[-1]:.2f}"
    cum_g_rank = f"{100 * np.sum(cg_a[-1, :] > cg_s[-1]) / max(cg_a.shape[1], 1):.0f}"
    cum_n = f"{1.0 + cn_s[-1]:.2f}"
    cum_n_rank = f"{100 * np.sum(cn_a[-1, :] > cn_s[-1]) / max(cn_a.shape[1], 1):.0f}"
    parts.append(
        f"Figure~\\ref{{fig:dollarInvested}} plots the growth of \\$1 invested in these "
        f"same {n_anoms} anomaly trading strategies (gray lines), and compares those with "
        f"the growth of \\$1 invested in the {signal_char} strategy (red line)."
        "\\footnote{The figure assumes an initial investment of \\$1 in T-bills and \\$1 "
        "long/short in the two sides of the strategy. Returns are compounded each month, "
        "assuming, as in \\citet*{DetzelNovy-MarxVelikov2022}, that a capital cost is "
        "charged against the strategy's returns at the risk-free rate. This excess return "
        "corresponds more closely to the strategy's economic profitability.}     "
        f"{_ibbots_window_sentence(results, signal_char)}"
        f"Ignoring trading costs, \\$1 invested in the {signal_char} strategy grew to "
        f"\\${cum_g}, which ranks the {signal_char} strategy in the top "
        f"{cum_g_rank}\\% across the {n_anoms} anomalies. Accounting for trading costs, "
        f"\\$1 invested in the {signal_char} strategy grew to \\${cum_n}, which "
        f"ranks the {signal_char} strategy in the top {cum_n_rank}\\% across the "
        f"{n_anoms} anomalies.\n\n\n"
    )

    ap = _get(results, "Fig_AlphaPrctl")
    pa = _get(ap, "PanelA")
    pb = _get(ap, "PanelB")
    dx_a = np.asarray(pa["dx"], dtype=float).ravel()
    dx_b = np.asarray(pb["dx"], dtype=float).ravel()
    y_b = np.asarray(pb["y"], dtype=float)
    min_g = _ordinal(np.nanmin(dx_a))
    max_g = _ordinal(np.nanmax(dx_a))
    # first index where FF3 (col1) / FF6 (col4) net alphapath goes positive
    col_ff3 = min(1, y_b.shape[1] - 1)
    col_ff6 = min(4, y_b.shape[1] - 1)
    z3 = np.where(y_b[:, col_ff3] > 0)[0]
    z6 = np.where(y_b[:, col_ff6] > 0)[0]
    frac_ff3 = str(int(z3[0]) if z3.size else 0)
    frac_ff6 = str(int(z6[0]) if z6.size else 0)
    # The net percentiles rest only on anomalies with an available generalized
    # alpha; say so when that is fewer than all of them.
    frac_base = f"the {n_anoms} anomalies"
    n_valid_b = _get(pb, "n_valid")
    if n_valid_b is not None:
        nv = np.asarray(n_valid_b, dtype=int).ravel()
        nv3 = int(nv[col_ff3]) if nv.size > col_ff3 else None
        nv6 = int(nv[col_ff6]) if nv.size > col_ff6 else None
        if nv3 is not None and nv6 is not None and str(n_anoms).isdigit():
            if nv3 < int(n_anoms) or nv6 < int(n_anoms):
                both = f"{nv3}" if nv3 == nv6 else f"{nv3} ({nv6})"
                frac_base = (
                    f"the {both} of {n_anoms} anomalies with an available net "
                    "generalized alpha"
                )
    rb = _get(_get(results, "Tab_RobustSort"), "PanelB")
    net_row0 = np.asarray(rb["a"][0, 1:], dtype=float)
    # Zero means the strategy is not held in the net MVE portfolio; missing
    # means no estimate. Neither is a positive generalized alpha.
    ind_pos = np.isfinite(net_row0) & (net_row0 > 0)
    n_pos_models = int(np.sum(ind_pos))
    dx_pos = dx_b[ind_pos] if ind_pos.size and dx_b.size >= ind_pos.size else dx_b
    # Where the signal ranks among the models for which its net generalized
    # alpha is positive; with none there is no such sentence.
    rank_sentence = ""
    if n_pos_models > 0 and dx_pos.size and np.isfinite(dx_pos).any():
        rank_sentence = (
            f" In these cases {signal_char} ranks between the {_ordinal(np.nanmin(dx_pos))} "
            f"and {_ordinal(np.nanmax(dx_pos))} percentiles in terms of how much it could "
            "have expanded the achievable investment frontier."
        )
    parts.append(
        f"Figure~\\ref{{fig:factorModelAlphas}} plots percentile ranks for the {n_anoms} "
        "anomaly trading strategies in terms of gross and \\citet{Novy-MarxVelikov2016} net "
        "generalized alphas with respect to the CAPM, and the Fama-French three-, four-, "
        f"five-, and six-factor models from Table~\\ref{{tab:tsRegs}}, and indicates the "
        f"ranking of {signal_char} relative to those. Panel A shows that the "
        f"{signal_char} strategy gross alphas fall between the {min_g} and {max_g} "
        "percentiles across the five factor models. Panel B shows that, accounting for "
        "trading costs, a large fraction of anomalies have not improved the investment "
        "opportunity set of an investor with access to the factor models. "
        f"For example, {frac_ff3}\\% ({frac_ff6}"
        f"\\%) of {frac_base} would not have improved the investment opportunity "
        "set for an investor having access to the Fama-French three-factor (six-factor) "
        f"model. {_ALPHA_MONTHS_SENTENCE} "
        f"The {signal_char} strategy has a positive net generalized alpha for "
        f"{_count_of(n_pos_models, int(net_row0.size))} factor models.{rank_sentence}\n\n\n"
    )

    out = _minus_signs("".join(parts))
    if fid is not None:
        fid.write(out)
    return out


def print_close_anoms_section(results: Any, fid: TextIO | None = None) -> str:
    text = _text(results)
    n_anoms = str(_get(text, "nAnoms", ""))
    signal_char = str(_get(text, "signalChar", "SIGNAL"))
    n_close = int(_get(text, "nCloseAnoms", 0))
    n_close_char = num_to_words(n_close)
    close_labels = [_tex_escape(str(s)) for s in (_get(text, "closeAnomLabels", []) or [])]

    fmb = _get(results, "Tab_CloseFMB")
    a_fmb = np.asarray(fmb["a"], dtype=float)
    t_fmb = np.asarray(fmb["tA"], dtype=float)
    # row index 1 = signal coeff t-stats. Columns: 0 the signal
    # alone, 1..n_close bivariate, last joint; the last two rows the months
    # and the adjusted R² (%).
    row = min(1, t_fmb.shape[0] - 1)
    solo_t = t_fmb[row, 0]
    t_row = t_fmb[row, 1:-1]
    if t_row.size == 0:
        t_row = t_fmb[row, :-1]
    min_i = int(np.nanargmin(t_row))
    min_t = f"{t_row[min_i]:.2f}"
    min_lab = close_labels[min_i] if min_i < len(close_labels) else f"Anomaly {min_i + 1}"
    all_t = f"{t_fmb[row, -1]:.2f}"
    solo_sentence = (
        f"On its own, {signal_char} has a t-statistic of {solo_t:.2f}. "
        if np.isfinite(solo_t)
        else ""
    )
    r2_solo, r2_all = a_fmb[-1, 0], a_fmb[-1, -1]
    if np.isfinite(r2_solo) and np.isfinite(r2_all):
        r2_sentence = (
            " The average cross-sectional adjusted $R^2$ "
            f"{'rises' if r2_all >= r2_solo else 'falls'} from "
            f"{r2_solo:.2f}\\% with {signal_char} alone to "
            f"{r2_all:.2f}\\% in the joint regression."
        )
    else:
        r2_sentence = ""

    span = _get(results, "Tab_CloseSpan")
    a_sp = np.asarray(span["a"], dtype=float)
    t_sp = np.asarray(span["tA"], dtype=float)
    a0 = a_sp[0, :-1]
    t0 = t_sp[0, :-1]
    min_a = f"{100 * np.nanmin(a0):.0f}"
    max_a = f"{100 * np.nanmax(a0):.0f}"
    min_ai = int(np.nanargmin(t0))
    min_at = f"{t0[min_ai]:.2f}"
    min_alab = close_labels[min_ai] if min_ai < len(close_labels) else f"Anomaly {min_ai + 1}"
    all_a = f"{100 * a_sp[0, -1]:.0f}"
    all_st = f"{t_sp[0, -1]:.2f}"
    # Last row of Tab_CloseSpan: adjusted R² in percent.
    span_r2 = a_sp[-1, -1] if a_sp.shape[0] > 1 else np.nan
    span_r2_sentence = (
        f" The adjusted $R^2$ of this joint spanning regression is {span_r2:.0f}\\%."
        if np.isfinite(span_r2)
        else ""
    )

    out = (
        f"\\section{{Does {signal_char} add relative to related anomalies?}} \n"
        "\\label{sec:closeAnoms}\n\n\n"
        "With so many anomalies, it is possible that any proposed, new cross-sectional "
        "predictor is just capturing some combination of known predictors. It is consequently "
        "natural to investigate to what extent the proposed predictor adds additional "
        "predictive power beyond the most closely related anomalies. \n"
        "Closely related anomalies are more likely to be formed on the basis of signals "
        "with higher absolute correlations. Figure~\\ref{fig:distributionCorrelations} plots "
        f"a name histogram of the correlations of {signal_char} with the {n_anoms} anomaly "
        "signals. Figure~\\ref{fig:hierarchicalClusterPlot} also shows an agglomerative "
        "hierarchical cluster plot of the long/short strategy returns, built with Ward's "
        "minimum-variance linkage; links below the 75th percentile of the linkage distances "
        "are colored by cluster." + _dendrogram_window_sentence(results, signal_char) + "  \n\n\n"
        f"A closely related anomaly is also more likely to price {signal_char} or at least "
        f"to weaken the power {signal_char} has predicting the cross-section of returns. "
        f"Figure~\\ref{{fig:conditionalStrategies}} plots histograms of t-statistics for "
        f"predictability tests of {signal_char} conditioning on each of the {n_anoms} "
        f"anomaly signals one at a time. Panel A reports t-statistics on $\\beta_{{{signal_char}}}$"
        f" from Fama-MacBeth regressions of the form $r_{{i,t}} = \\alpha + "
        f"\\beta_{{{signal_char}}}{signal_char}_{{i,t-1}} + \\beta_X X_{{i,t-1}}+\\epsilon_{{i,t}}$, "
        f"where $X$ stands for one of the {n_anoms} anomaly signals at a time. "
        f"Panel B plots t-statistics on $\\alpha$ from spanning tests of the form: "
        f"$r_{{{signal_char}, t}} = \\alpha + \\beta r_{{X, t}}+\\epsilon_t$, "
        f"where $r_{{X,t}}$ stands for the returns to one of the {n_anoms} anomaly trading "
        "strategies at a time. The strategies employed in the spanning tests are constructed "
        "using quintile sorts, value-weighting, and NYSE breakpoints. "
        "Panel C plots t-statistics on the average returns to strategies constructed by "
        f"conditional double sorts. In each month in which both signals are available, "
        f"we sort stocks into quintiles based on one of "
        f"the {n_anoms} anomaly signals. Then, within each quintile, we sort stocks into "
        f"quintiles based on {signal_char}. Stocks are finally grouped into five "
        f"{signal_char} portfolios by combining stocks within each anomaly sorting portfolio. "
        "The portfolios are value-weighted, with weights reset every month. "
        f"The panel plots the t-statistics on the average returns of these conditional "
        f"double-sorted {signal_char} trading strategies conditioned on each of the "
        f"{n_anoms} anomalies.\n\n\n"
        "Table~\\ref{tab:closeAnomFMB} reports Fama-MacBeth cross-sectional regressions "
        f"of returns on {signal_char} and the {n_close_char} anomalies most closely related "
        f"to it. The {n_close_char} most closely related anomalies are "
        f"{close_anom_selection_sentence()} {solo_sentence}"
        f"Controlling for these signals one at a time, the t-statistics on the "
        f"{signal_char} signal in these Fama-MacBeth regressions are at least {min_t}, with the "
        f"minimum t-statistic occurring when controlling for {min_lab}. Controlling "
        f"for all {n_close_char} closely related anomalies, the t-statistic on "
        f"{signal_char} is {all_t}.{r2_sentence}\n\n\n"
        "Similarly, Table~\\ref{tab:closeAnomSpan} reports results from spanning tests "
        f"that regress returns to the {signal_char} strategy onto the returns of "
        f"the {n_close_char} most closely related anomalies and the six Fama-French factors. "
        f"Controlling for the {n_close_char} most closely related anomalies individually, "
        f"the {signal_char} strategy earns alphas that range from {min_a} to {max_a} bps/month. "
        f"The minimum t-statistic on these alphas controlling for one anomaly at a time is "
        f"{min_at}, which is achieved when controlling for {min_alab}. Controlling for "
        f"all {n_close_char} closely related anomalies and the six Fama-French factors "
        f"simultaneously, the {signal_char} trading strategy achieves an alpha of "
        f"{all_a} bps/month with a t-statistic of {all_st}.{span_r2_sentence}\n\n\n"
    )
    out = _minus_signs(out)
    if fid is not None:
        fid.write(out)
    return out


def _month_words(yyyymm: Any) -> str | None:
    """``199807`` -> ``"July 1998"``; None for a missing month."""
    if yyyymm is None:
        return None
    try:
        m = int(yyyymm)
    except (TypeError, ValueError):
        return None
    if not 1 <= m % 100 <= 12:
        return None
    return f"{calendar.month_name[m % 100]} {m // 100}"


def _comb_signal_window(comb: Any) -> int | None:
    """Months of data the signal needs outside the average rank.

    None for results written before the rule was recorded.
    """
    w = _get(comb, "signalWindow")
    try:
        return None if w is None else int(w)
    except (TypeError, ValueError):
        return None


def _comb_window_words(window: int) -> str:
    if window % 12 == 0:
        years = window // 12
        return f"{num_to_words(years)} year{'s' if years != 1 else ''}"
    return f"{window} months"


def print_comb_strats_section(results: Any, fid: TextIO | None = None) -> str:
    text = _text(results)
    n_anoms = str(_get(text, "nAnoms", ""))
    signal_char = str(_get(text, "signalChar", "SIGNAL"))
    comb = _get(results, "Fig_CombStrat") or {}
    ttl = list(_get(comb, "ttl", []) or [])
    expl = list(_get(comb, "explanation", []) or [])
    n_methods = len(ttl)
    n_char = num_to_words(n_methods)
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    y_wo = np.asarray(_get(comb, "yWithout", np.zeros((1, max(n_methods, 1)))), dtype=float)
    y_w = np.asarray(_get(comb, "yWith", np.zeros_like(y_wo)), dtype=float)
    y_wo = np.nan_to_num(y_wo, nan=0.0)
    y_w = np.nan_to_num(y_w, nan=0.0)
    cum_wo = np.cumprod(1.0 + y_wo, axis=0)
    cum_w = np.cumprod(1.0 + y_w, axis=0)

    parts = [
        f"\\section{{Does {signal_char} add relative to the whole zoo?}} \n",
        "\\label{sec:combStrat}\n\n\n",
        (
            f"Finally, we can ask how much adding {signal_char} to the entire factor zoo could "
            "improve investment performance. Figure~\\ref{fig:combStrat} plots the growth of "
            "\\$1 invested in trading strategies that combine multiple anomalies following "
            f"\\citet{{ChenVelikov2022}}. The combinations use either the {n_anoms} anomalies "
            f"from the zoo that satisfy our inclusion criteria  (blue lines) or these "
            f"{n_anoms} anomalies augmented with the {signal_char} signal. We consider "
            f"{n_char} different methods for combining signals.\n\n"
        ),
    ]
    # When each method uses the signal, and the period each panel's
    # two strategies are compared over. A results file without the record
    # reads as before.
    window = _comb_signal_window(comb)
    first = list(_get(comb, "first", []) or [])
    last = list(_get(comb, "last", []) or [])
    if window is not None:
        parts.append(
            f"The average rank uses {signal_char} from the first month in which it has "
            f"data, and the other methods once it has {_comb_window_words(window)} of data, "
            "so that their estimation windows contain it throughout. In each panel the two "
            "strategies start in the same month, the first in which the method uses "
            f"{signal_char}, and the figure starts in {signal_char}'s first month.\n\n"
        )
    for i in range(n_methods):
        end_wo = f"{cum_wo[-1, i]:,.2f}"
        end_w = f"{cum_w[-1, i]:,.2f}"
        exp_i = expl[i] if i < len(expl) else ""
        lead = f"Panel {alphabet[i]} shows results using ``{ttl[i]}'' as the combination method. "
        start_i = _month_words(first[i]) if i < len(first) else None
        end_i = _month_words(last[i]) if i < len(last) else None
        if window is not None and (start_i is None or end_i is None):
            parts.append(
                f"{lead}{exp_i} For this method the two strategies are not formed, because "
                f"{signal_char} does not have {_comb_window_words(window)} of data.\n\n"
            )
            continue
        period = (
            f"From {start_i} to {end_i}, " if window is not None else "For this method, "
        )
        parts.append(
            f"{lead}{exp_i} {period}\\$1 investment in the {n_anoms}-anomaly combination "
            f"strategy grows to \\${end_wo}, while \\$1 investment in the combination "
            f"strategy that includes {signal_char} grows to \\${end_w}.\n\n"
        )
    parts.append("\n\n\n")
    out = "".join(parts)
    if fid is not None:
        fid.write(out)
    return out


# ---------------------------------------------------------------------------
# Figure includes (PDF emission via ``emit_all_figures`` in ``print_tex_file``)
# ---------------------------------------------------------------------------
def _fig_includegraphics(
    signal_char: str,
    stem_suffix: str,
    *,
    width: str = "1.015\\linewidth",
) -> str:
    return (
        f"\\hspace{{-4mm}} \\includegraphics[width={width},keepaspectratio]"
        f"{{{signal_char}_{stem_suffix}}}\n"
    )


def print_signal_description_figure(results: Any, fid: TextIO | None = None) -> str:
    sc = str(_get(_text(results), "signalChar", "SIGNAL"))
    out = (
        "\\newpage\n\\clearpage\n\n"
        "\\begin{figure}[!htbp]\n"
        "\\begin{center}\n"
        f"\\hspace{{-4mm}} \\includegraphics[width=1.015\\textwidth,keepaspectratio]"
        f"{{{sc}_figureSignalDescription}}\n"
        "\\end{center}\n"
        f"\\caption{{Time series of {sc} percentiles and coverage. \\\\\n"
        f"This figure plots descriptive statistics for {sc}. "
        f"Panel A shows cross-sectional percentiles of {sc} over the sample. "
        f"Panel B plots the coverage of {sc} relative to the universe of CRSP "
        "stocks with available market capitalizations. Both panels show the months "
        "in which the signal has values.\n"
        "\\label{fig:descriptiveStats}}\n"
        "\\end{figure}\n\n\n"
    )
    if fid is not None:
        fid.write(out)
    return out


def print_sharpe_dist_figure(results: Any, fid: TextIO | None = None) -> str:
    text = _text(results)
    sc = str(_get(text, "signalChar", "SIGNAL"))
    n = str(_get(text, "nAnoms", ""))
    sp = _signal_period(text, "sortPeriod", "returnPeriod")
    sp_start, sp_end = str(int(sp[0])), str(int(sp[-1]))
    out = (
        "\\begin{figure}[!htbp]\n\\begin{center}\n"
        + _fig_includegraphics(sc, "figureSharpeDist")
        + "\\end{center}\n"
        "\\caption{Distribution of Sharpe ratios. \\\\\n"
        f"This figure plots a histogram of Sharpe ratios for {n} anomalies, and compares "
        f"the Sharpe ratio of {sc} with them (red vertical line). Panel A plots results "
        "for gross Sharpe ratios. Panel B plots results for Sharpe ratios net of "
        f"{tcost_wording(_get(text, 'tcostsType', 'full'))['caption']}. "
        "Each anomaly's Sharpe ratio is calculated over all months in which the "
        f"anomaly strategy has returns; that of {sc} over {sp_start} to {sp_end}.\n"
        "\\label{fig:distributionSharpeRatios}}\n"
        "\\end{figure}\n\n\n"
    )
    if fid is not None:
        fid.write(out)
    return out


def print_ibbots_plots_figure(results: Any, fid: TextIO | None = None) -> str:
    text = _text(results)
    sc = str(_get(text, "signalChar", "SIGNAL"))
    n = str(_get(text, "nAnoms", ""))
    out = (
        "\\begin{figure}[!htbp]\n\\begin{center}\n"
        + _fig_includegraphics(sc, "figureIbbots")
        + "\\end{center}\n"
        "\\caption{Dollar invested. \\\\\n"
        f"This figure plots the growth of \\$1 invested in {n} anomaly trading strategies "
        f"(gray lines), and compares those with the {sc} trading strategy (red line). "
        "The strategies are constructed using value-weighted quintile sorts using NYSE "
        "breakpoints. Panel A plots results for gross strategy returns. "
        "Panel B plots results for strategy returns net of "
        f"{tcost_wording(_get(text, 'tcostsType', 'full'))['caption']}. "
        f"{_ibbots_window_sentence(results, sc, caption=True).rstrip()}\n"
        "\\label{fig:dollarInvested}}\n"
        "\\end{figure}\n\n\n"
    )
    if fid is not None:
        fid.write(out)
    return out


def print_alpha_prctl_figure(results: Any, fid: TextIO | None = None) -> str:
    text = _text(results)
    sc = str(_get(text, "signalChar", "SIGNAL"))
    n = str(_get(text, "nAnoms", ""))
    out = (
        "\\begin{landscape}\n"
        "\\begin{figure}[!htbp]\n\\begin{center}\n"
        f"\\hspace{{-4mm}} \\includegraphics[width=\\linewidth,keepaspectratio]"
        f"{{{sc}_figureAlphaPrctl}}\n"
        "\\end{center}\n"
        "\\caption{Gross and generalized net alpha percentiles of anomalies relative to "
        "factor models \\\\\n"
        f"\\small{{This figure plots the percentile ranks for {n} anomaly trading strategies "
        f"in terms of alphas (solid lines), and compares those with the {sc} trading strategy "
        "alphas (diamonds). The strategies are constructed using value-weighted quintile "
        "sorts using NYSE breakpoints. The alphas include those with respect to the CAPM,  "
        "\\citet{FamaFrench1993} three-factor model, \\citet{FamaFrench1993} three-factor "
        "model augmented with the \\citet{Carhart1997} momentum factor, "
        "\\citet{FamaFrench2015} five-factor model, and the \\citet{FamaFrench2015} "
        "five-factor model augmented with the \\citet{Carhart1997} momentum factor "
        "following \\citet{FamaFrench2018}. Panel A plots alphas with no adjustment "
        "for trading costs. Panel B plots \\citet{Novy-MarxVelikov2016} "
        "generalized alphas net of "
        f"{tcost_wording(_get(text, 'tcostsType', 'full'))['caption']}. "
        f"{_ALPHA_MONTHS_SENTENCE}}}\n"
        "\\label{fig:factorModelAlphas}}\n"
        "\\end{figure}\n\n\n"
        "\\end{landscape}\n"
    )
    if fid is not None:
        fid.write(out)
    return out


def print_correl_figure(results: Any, fid: TextIO | None = None) -> str:
    text = _text(results)
    sc = str(_get(text, "signalChar", "SIGNAL"))
    n = str(_get(text, "nAnoms", ""))
    out = (
        "\\begin{figure}[!htbp]\n\\begin{center}\n"
        f"\\hspace{{-4mm}} \\includegraphics[height=0.85\\textheight,keepaspectratio]"
        f"{{{sc}_figureCorrel}}\n"
        "\\end{center}\n"
        "\\caption{Distribution of correlations. \\\\\n"
        f"This figure plots a name histogram of correlations of {n} anomaly signals with "
        f"{sc}. The correlations are pooled. Panel A plots Spearman rank correlations, "
        "while Panel B plots Pearson correlations.\n"
        "\\label{fig:distributionCorrelations}}\n"
        "\\end{figure}\n\n\n"
    )
    if fid is not None:
        fid.write(out)
    return out


def _dendrogram_window(results: Any) -> tuple[str, str, int, int] | None:
    """Window (as "July 1964", "December 2025") and anomaly counts of the plot.

    None for results written before the window was recorded.
    """
    dg = _get(results, "Fig_Dendrogram") or {}
    window = _get(dg, "window")
    kept = _get(dg, "nAnomsKept")
    n_in = _get(dg, "nAnomsIn")
    if window is None or kept is None or n_in is None:
        return None
    w = [int(m) for m in np.asarray(window).ravel()[:2]]
    months = [f"{calendar.month_name[m % 100]} {m // 100}" for m in w]
    return months[0], months[1], int(kept), int(n_in)


def _dendrogram_window_sentence(results: Any, signal_char: str) -> str:
    win = _dendrogram_window(results)
    if win is None:
        return ""
    start, end, kept, n_in = win
    return (
        f" The plot uses the months from {start} to {end}, in which {signal_char} "
        f"has a return, and the {kept} of the {n_in} anomalies with a return in "
        "every one of those months."
    )


def _dendrogram_caption_series(results: Any, signal_char: str) -> str:
    win = _dendrogram_window(results)
    if win is None:
        return "the anomaly strategies and the test signal"
    start, end, kept, _ = win
    return (
        f"{signal_char} and the {kept} anomaly strategies with a return in every "
        f"month from {start} to {end}"
    )


def print_dendrogram_figure(results: Any, fid: TextIO | None = None) -> str:
    sc = str(_get(_text(results), "signalChar", "SIGNAL"))
    out = (
        "\\begin{landscape}\n"
        "\\begin{figure}[!htbp]\n\\begin{center}\n"
        + _fig_includegraphics(sc, "figureDendrogram")
        + "\\end{center}\n"
        "\\caption{Agglomerative hierarchical cluster plot\\\\\n"
        "This figure plots an agglomerative hierarchical cluster plot of the monthly "
        "long/short returns of " + _dendrogram_caption_series(results, sc) + ", using Ward's "
        "minimum-variance linkage on Euclidean distances. Links below the 75th percentile "
        "of the linkage distances are colored by cluster. \n"
        "\\label{fig:hierarchicalClusterPlot}}\n"
        "\\end{figure}\n"
        "\\end{landscape}\n\n\n"
    )
    if fid is not None:
        fid.write(out)
    return out


def print_cond_strats_figure(results: Any, fid: TextIO | None = None) -> str:
    text = _text(results)
    sc = str(_get(text, "signalChar", "SIGNAL"))
    n = str(_get(text, "nAnoms", ""))
    # MATLAB hardcodes 157 once at the end of the long caption — use nAnoms for both
    out = (
        "\\begin{figure}[!htbp]\n\\begin{center}\n"
        + _fig_includegraphics(sc, "figureCondStrats")
        + "\\end{center}\n"
        "\\caption{Distribution of t-stats on conditioning strategies\\\\\n"
        f"\\small{{This figure plots histograms of t-statistics for predictability tests of "
        f"{sc} conditioning on each of the {n} anomaly signals one at a time. "
        f"Panel A reports t-statistics on $\\beta_{{{sc}}}$ from Fama-MacBeth regressions "
        f"of the form $r_{{i,t}} = \\alpha + \\beta_{{{sc}}}{sc}_{{i,t-1}} + "
        f"\\beta_X X_{{i,t-1}}+\\epsilon_{{i,t}}$, where $X$ stands for one of the {n} "
        f"anomaly signals at a time. Panel B plots t-statistics on $\\alpha$ from spanning "
        f"tests of the form: $r_{{{sc}, t}} = \\alpha + \\beta r_{{X, t}}+\\epsilon_t$, "
        f"where $r_{{X,t}}$ stands for the returns to one of the {n} anomaly trading "
        "strategies at a time. The strategies employed in the spanning tests are constructed "
        "using quintile sorts, value-weighting, and NYSE breakpoints. Panel C plots "
        "t-statistics on the average returns to strategies constructed by conditional double "
        f"sorts. In each month in which both signals are available, we sort stocks into "
        f"quintiles based on one of the {n} anomaly "
        f"signals at a time. Then, within each quintile, we sort stocks into quintiles based "
        f"on {sc}. Stocks are finally grouped into five {sc} portfolios by combining stocks "
        f"within each anomaly sorting portfolio. The portfolios are value-weighted, with "
        f"weights reset every month. The panel plots the t-statistics on the "
        f"average returns of these conditional double-sorted {sc} trading strategies "
        f"conditioned on each of the {n} anomalies. }}\n"
        "\\label{fig:conditionalStrategies}}\n"
        "\\end{figure}\n\n\n"
    )
    if fid is not None:
        fid.write(out)
    return out


def print_comb_strats_figure(results: Any, fid: TextIO | None = None) -> str:
    text = _text(results)
    sc = str(_get(text, "signalChar", "SIGNAL"))
    n = str(_get(text, "nAnoms", ""))
    comb = _get(results, "Fig_CombStrat") or {}
    ttl = list(_get(comb, "ttl", []) or [])
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    caption = (
        "This figure plots the growth of \\$1 invested in trading strategies that combine "
        "multiple anomalies following \\citet{ChenVelikov2022}. In all panels, the blue solid "
        f"lines indicate combination trading strategies that utilize {n} anomalies. The red "
        f"solid lines indicate combination trading strategies that utilize the {n} anomalies "
        f"as well as {sc}. "
    )
    for i, title in enumerate(ttl):
        caption += f"Panel {alphabet[i]} shows results using ``{title}'' as the combination method. "
    window = _comb_signal_window(comb)
    if window is not None:
        caption += (
            f"The figure starts in the first month in which {sc} has data. In each panel "
            f"both strategies start in the first month in which the method uses {sc}: that "
            f"month for the average rank, and {_comb_window_words(window)} later for the "
            "other methods. "
        )
    caption += "See Section~\\ref{sec:combStrat} for details on the combination methods. "
    out = (
        "\\begin{figure}[!htbp]\n\\begin{center}\n"
        + _fig_includegraphics(sc, "figureCombStrats")
        + "\\end{center}\n"
        "\\caption{Combination strategy performance\\\\\n"
        f"{caption}"
        "\\label{fig:combStrat}}\n"
        "\\end{figure}\n"
    )
    if fid is not None:
        fid.write(out)
    return out


def print_end_of_paper_text(fid: TextIO | None = None) -> str:
    out = (
        "\\newpage\n"
        "\\clearpage\n\n"
        "\\bibliographystyle{apalike}\n"
        "\\bibliography{newSignalTestBib}\n"
        "\\end{document}\n"
    )
    if fid is not None:
        fid.write(out)
    return out


def print_bibliography_file(file_path: str | Path) -> Path:
    """Copy / emit ``newSignalTestBib.bib`` next to the ``.tex`` file."""
    out_dir = Path(file_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / "newSignalTestBib.bib"
    # Prefer the MATLAB gold bib if present; else package resource; else minimal stub.
    candidates = [
        Path(__file__).resolve().parents[3]
        / "AssayingAnomalies-MATLAB"
        / "Scratch"
        / "Assay"
        / "tex"
        / "newSignalTestBib.bib",
        Path(__file__).resolve().parent / "bib" / "newSignalTestBib.bib",
    ]
    for src in candidates:
        if src.is_file():
            shutil.copyfile(src, dest)
            return dest
    dest.write_text(_MINIMAL_BIB, encoding="utf-8")
    return dest


_MINIMAL_BIB = """@article{Novy-MarxVelikov2026,
title={Assaying Anomalies},
author={Novy-Marx, Robert and Velikov, Mihail},
year={2026},
journal={Working paper}}
"""


# ---------------------------------------------------------------------------
# Assembler
# ---------------------------------------------------------------------------
LATEXMK = "latexmk"


def latexmk_available() -> str | None:
    """Absolute path to ``latexmk``, or None when no TeX distribution is here."""
    return shutil.which(LATEXMK)


def compile_pdf(tex_path: str | Path, *, timeout: float = 600.0) -> Path | None:
    """
    Compile ``tex_path`` to PDF with ``latexmk``; return the PDF, or None.

    A cluster node usually has no TeX distribution, and that must not fail a
    protocol run whose real deliverable is the ``.tex`` (plus the figure PDFs).
    So a missing ``latexmk``, a non-zero exit, or a timeout each log a warning
    and return None, leaving the ``.tex`` on disk to be compiled elsewhere.
    """
    tex_path = Path(tex_path)
    exe = latexmk_available()
    if exe is None:
        LOGGER.warning(
            "%s not found on PATH; leaving %s uncompiled. "
            "Install a TeX distribution, or compile the .tex on another machine.",
            LATEXMK,
            tex_path.name,
        )
        return None

    cmd = [exe, "-pdf", "-interaction=nonstopmode", "-halt-on-error", tex_path.name]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(tex_path.parent),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        LOGGER.warning("%s failed to run on %s (%s); .tex kept", LATEXMK, tex_path.name, exc)
        return None

    pdf_path = tex_path.with_suffix(".pdf")
    if proc.returncode != 0 or not pdf_path.exists():
        LOGGER.warning(
            "%s exited %s on %s; .tex kept. Tail of the log:\n%s",
            LATEXMK,
            proc.returncode,
            tex_path.name,
            "\n".join((proc.stdout or "").splitlines()[-20:]),
        )
        return pdf_path if pdf_path.exists() else None

    LOGGER.info("Compiled %s", pdf_path)
    return pdf_path


def print_tex_file(
    results: Any,
    out_dir: str | Path | None = None,
    *,
    signal_acronym: str | None = None,
    emit_figures: bool = True,
    compile_tex: bool = False,
) -> Path:
    """Port of MATLAB ``printTexFile``.

    Writes ``{signal}.tex`` under ``out_dir`` (default ``Scratch/Assay/tex`` in
    the project folder) plus ``newSignalTestBib.bib``. When ``emit_figures`` is True (default;
    MATLAB always emits), also writes the eight ``{signal}_figure*.pdf`` files
    from ``Fig_*`` leaves. ``\\includegraphics`` basenames are always written.

    With ``compile_tex=True`` the ``.tex`` is additionally run through
    ``latexmk`` when one is on PATH; a missing or failing ``latexmk`` only logs
    a warning (see :func:`compile_pdf`). The return value is the ``.tex`` either
    way.

    Returns
    -------
    Path
        Absolute path to the written ``.tex`` file.
    """
    text = _text(results)
    sc = signal_acronym or str(_get(text, "signalChar", "SIGNAL"))
    if out_dir is None:
        out_dir = scratch_dir() / "tex"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tex_path = out_dir / f"{sc}.tex"
    LOGGER.info("Writing assay TeX to %s", tex_path)

    if emit_figures:
        written = emit_all_figures(results, out_dir, signal_char=sc)
        LOGGER.info("Figure PDFs written: %s", sorted(written.keys()))

    with tex_path.open("w", encoding="utf-8", newline="\n") as fid:
        print_document_header(fid)
        print_title_page(results, fid)
        print_intro_section(results, fid)
        print_signal_description_section(results, fid)
        print_return_prediction_section(results, fid)
        print_other_anomalies_section(results, fid)
        print_close_anoms_section(results, fid)
        print_comb_strats_section(results, fid)

        print_signal_description_figure(results, fid)
        print_basic_sort_table(results, fid=fid)
        print_robustness_to_sorting_table(results, fid=fid)
        print_sub_sample_table(results, fid=fid)
        print_cond_size_sort_table(results, fid=fid)
        print_sharpe_dist_figure(results, fid)
        print_ibbots_plots_figure(results, fid)
        print_alpha_prctl_figure(results, fid)
        print_correl_figure(results, fid)
        print_dendrogram_figure(results, fid)
        print_cond_strats_figure(results, fid)
        print_close_anoms_fmb_table(results, fid=fid)
        print_close_anoms_span_table(results, fid=fid)
        print_comb_strats_figure(results, fid)
        print_end_of_paper_text(fid)

    print_bibliography_file(out_dir)
    if compile_tex:
        compile_pdf(tex_path)
    return tex_path.resolve()


# ---------------------------------------------------------------------------
# Semantic diff helpers
# ---------------------------------------------------------------------------
def strip_date_today(tex: str) -> str:
    """Remove ``\\date{\\today}`` for cross-file comparison."""
    return re.sub(r"\\date\{\\today\}", r"\\date{}", tex)


def semantic_tex_diff(
    produced: str,
    gold: str,
    *,
    keys: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Compare abstract / table numeric cells / includegraphics basenames.

    Returns a dict with ``ok`` (bool), per-section notes, and extracted
    headline numbers.
    """
    prod = strip_date_today(produced)
    gld = strip_date_today(gold)

    def _abstract(s: str) -> str:
        m = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", s, re.S)
        return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""

    def _figs(s: str) -> list[str]:
        return re.findall(r"\\includegraphics\[[^\]]*\]\{([^}]+)\}", s)

    def _table_body(s: str, label: str) -> str:
        m = re.search(
            rf"\\label\{{{re.escape(label)}\}}(.*?)\\end\{{table\}}",
            s,
            re.S,
        )
        if not m:
            return ""
        # keep digits and structure; collapse whitespace
        body = re.sub(r"\s+", " ", m.group(1))
        return body

    def _nums(s: str) -> list[float]:
        return [float(x) for x in re.findall(r"-?\d+\.\d+|-?\d+", s)]

    abs_p, abs_g = _abstract(prod), _abstract(gld)
    figs_p, figs_g = _figs(prod), _figs(gld)

    table_labels = keys or [
        "tab:tsRegs",
        "tab:robustnessToSorting",
        "tab:doubleSortSize",
        "tab:closeAnomFMB",
        "tab:closeAnomSpan",
    ]
    table_reports: dict[str, Any] = {}
    tables_ok = True
    for lab in table_labels:
        bp, bg = _table_body(prod, lab), _table_body(gld, lab)
        np_p, np_g = np.asarray(_nums(bp), dtype=float), np.asarray(_nums(bg), dtype=float)
        # Compare common prefix of numeric sequences with a magnitude-aware
        # tolerance: a cell matches if it is close in absolute terms (0.02,
        # i.e. the 2-decimal print resolution of small cells) OR in relative
        # terms (1e-3, so a large-magnitude cell like a coefficient of ~401
        # is not held to more precision than the print carries).
        n = min(np_p.size, np_g.size)
        if n == 0:
            match = bp == bg
            max_abs = None
            max_rel = None
        else:
            diff = np.abs(np_p[:n] - np_g[:n])
            max_abs = float(np.nanmax(diff))
            scale = np.maximum(np.abs(np_p[:n]), np.abs(np_g[:n]))
            rel = np.divide(diff, scale, out=np.zeros_like(diff), where=scale > 0)
            max_rel = float(np.nanmax(rel))
            cells_ok = bool(np.all((diff <= 0.02) | (rel <= 1e-3)))
            match = cells_ok and abs(np_p.size - np_g.size) <= 5
        table_reports[lab] = {
            "n_prod": int(np_p.size),
            "n_gold": int(np_g.size),
            "max_abs_prefix": max_abs,
            "max_rel_prefix": max_rel,
            "match": match,
        }
        tables_ok = tables_ok and bool(match)

    # Headline abstract anchors
    def _pull_sharpes(ab: str) -> tuple[str | None, str | None]:
        m = re.search(
            r"Sharpe ratio of ([0-9.]+) \(([0-9.]+)\)",
            ab,
        )
        return (m.group(1), m.group(2)) if m else (None, None)

    sh_p = _pull_sharpes(abs_p)
    sh_g = _pull_sharpes(abs_g)

    abstract_ok = sh_p == sh_g and sh_p[0] is not None
    # Also compare bps snippets
    def _bps(ab: str) -> list[str]:
        return re.findall(r"(\d+) \((\d+)\) bps/month", ab) + re.findall(
            r"is (\d+) bps/month", ab
        )

    figs_ok = figs_p == figs_g

    return {
        "ok": bool(abstract_ok and figs_ok and tables_ok),
        "abstract_ok": abstract_ok,
        "sharpe_prod": sh_p,
        "sharpe_gold": sh_g,
        "bps_prod": _bps(abs_p),
        "bps_gold": _bps(abs_g),
        "figures_ok": figs_ok,
        "figures_prod": figs_p,
        "figures_gold": figs_g,
        "tables": table_reports,
        "abstract_prod": abs_p[:400],
        "abstract_gold": abs_g[:400],
    }
