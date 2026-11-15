"""
LaTeX table emitters for the Novy-Marx / Velikov (2026) assaying-anomalies
protocol. Python port of the MATLAB ``prt/print*Table.m`` helpers.

Unlike the MATLAB originals (which fprintf to an open file handle) these
functions return a LaTeX string. Callers may pass an open text-mode file
handle via ``fid`` to mirror the MATLAB API (the function then writes and
also returns the string).
"""

from __future__ import annotations

import io
import math
from typing import Any, Mapping, Sequence, TextIO

import numpy as np

# Characters that are special in a pdflatex source file. Report text built from
# data (Chen-Zimmermann anomaly names such as "Operating profitability R&D
# adjusted") goes through _tex_escape; latex.py imports it from here.
_TEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "—": "---",
}


def _tex_escape(s: str) -> str:
    """Make a plain string safe for a pdflatex source file."""
    return "".join(_TEX_ESCAPES.get(ch, ch) for ch in s)


__all__ = [
    "mat_to_tex",
    "tcost_wording",
    "add_comma",
    "num_to_words",
    "print_basic_sort_table",
    "print_robustness_to_sorting_table",
    "print_sub_sample_table",
    "print_cond_size_sort_table",
    "print_close_anoms_fmb_table",
    "print_close_anoms_span_table",
    "close_anom_selection_sentence",
    "build_basic_sort_panels",
]

_ONES = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)
_TENS = (
    "",
    "",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
)


def num_to_words(num: int | float) -> str:
    """Minimal English integer spell-out covering paper uses (0–99, 100).

    Full MATLAB ``num2words`` is far larger; assay prose only needs small
    cardinals (``six``, ``twenty-five``, …).
    """
    n = int(round(float(num)))
    if n < 0:
        return "negative " + num_to_words(-n)
    if n < 20:
        return _ONES[n]
    if n < 100:
        t, o = divmod(n, 10)
        return _TENS[t] if o == 0 else f"{_TENS[t]}-{_ONES[o]}"
    if n == 100:
        return "one hundred"
    # Fallback for larger counts that occasionally appear in ranks
    return str(n)

# Default column headers used for the quintile-sort panels (Panels A and B).
_QUINTILE_HEADER_ROW = "& (L) & (2) & (3) & (4) & (H) & (H-L)\\\\[2pt]\n"

# Factor-model codes -> alpha row labels used by Panel A of the basic-sort
# table. Order matches the MATLAB columns for ``resBasicSorts(1, :)``:
# the 5-element layout used in the original paper is xret + (1, 3, 4, 5, 6).
_PANEL_A_ROW_HEADERS: tuple[str, ...] = (
    r"$r^e$",
    r"$\alpha_{CAPM}$",
    r"$\alpha_{FF3}$",
    r"$\alpha_{FF4}$",
    r"$\alpha_{FF5}$",
    r"$\alpha_{FF6}$",
)

_PANEL_C_ROW_HEADERS: tuple[str, ...] = (r"$n$", r"me $(\$10^6)$")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def add_comma(num: float | int) -> str:
    """Port of MATLAB ``addComma.m``: integer-style thousands separators."""
    if not np.isfinite(num):
        return ""
    return f"{int(round(float(num))):,}"


def _time_period_pair(time_period: Any) -> tuple[str, str]:
    arr = np.asarray(time_period).ravel()
    if arr.size < 2:
        raise ValueError("time_period must have at least two entries")
    return str(int(arr[0])), str(int(arr[-1]))


def _as_panel_map(obj: Any, *keys: str) -> Mapping[str, Any]:
    """Normalize PrintResults / nested dict panel containers."""
    cur: Any = obj
    for k in keys:
        if cur is None:
            raise KeyError(f"missing path element {k!r}")
        if isinstance(cur, Mapping):
            cur = cur[k]
        else:
            cur = getattr(cur, k)
    if not isinstance(cur, Mapping):
        raise TypeError(f"expected mapping at path {keys!r}, got {type(cur)}")
    return cur


def _write_or_return(buf: io.StringIO, fid: TextIO | None) -> str:
    output = buf.getvalue()
    if fid is not None:
        fid.write(output)
    return output


def _fmt_sig(x: float, n: int) -> str:
    """Format ``x`` with ``n`` significant digits, never in scientific notation.

    0.0073 -> "0.0073", 0.11 -> "0.11", 1.23 -> "1.2", 12.3 -> "12" (n=2).
    """
    if x == 0:
        return "0"
    e = int(math.floor(math.log10(abs(x))))
    d = max(0, n - 1 - e)
    # 0.0996 rounds up to 0.100: one decade more, one decimal fewer.
    x_r = round(x, d)
    if x_r != 0 and int(math.floor(math.log10(abs(x_r)))) > e:
        d = max(0, d - 1)
    return f"{x:.{d}f}"


# ---------------------------------------------------------------------------
# mat2Tex port
# ---------------------------------------------------------------------------
def mat_to_tex(
    coeffs: np.ndarray,
    sigstats: np.ndarray | None = None,
    row_headers: Sequence[str] | None = None,
    decimals: int = 2,
    brackets_type: str = "[",
    col_format_spec: Sequence[str] | None = None,
    sig_digits: int | None = None,
) -> str:
    """Port of MATLAB ``mat2Tex``.

    Returns the LaTeX body (rows of ampersand-separated cells) for a matrix
    of coefficients, optionally interleaved with significance statistics
    (e.g. t-stats) wrapped in brackets on a second line per coefficient row.

    ``sig_digits`` (not in MATLAB) prints the coefficient cells with that many
    significant digits instead of ``decimals`` decimals; the sigstats cells
    keep ``decimals``. ``col_format_spec``, when given, wins over both.
    """
    if brackets_type not in {"[", "(", "{"}:
        raise ValueError(f"Invalid brackets_type: {brackets_type!r}")

    coeffs = np.asarray(coeffs, dtype=float)
    if coeffs.ndim == 1:
        coeffs = coeffs.reshape(1, -1)

    if sigstats is None:
        sigstats = coeffs
        ind_sig_stats = False
    else:
        sigstats = np.asarray(sigstats, dtype=float)
        if sigstats.ndim == 1:
            sigstats = sigstats.reshape(1, -1)
        if sigstats.shape != coeffs.shape:
            raise ValueError(
                f"sigstats shape {sigstats.shape} must match coeffs shape {coeffs.shape}"
            )
        # MATLAB: indSigStats = (nansum(nansum(coeffs - sigstats)) ~= 0).
        diff = np.where(
            np.isnan(coeffs) | np.isnan(sigstats),
            0.0,
            coeffs - sigstats,
        )
        ind_sig_stats = bool(np.nansum(diff) != 0)

    n_rows, n_cols = coeffs.shape

    open_b, close_b = {"[": ("[", "]"), "(": ("(", ")"), "{": ("{", "}")}[brackets_type]

    def _fmt(x: float, j: int, *, coeff: bool = False) -> str:
        if col_format_spec is not None:
            spec = col_format_spec[j]
            return spec % x
        if coeff and sig_digits is not None:
            return _fmt_sig(x, sig_digits)
        return f"%.{decimals}f" % x

    lines: list[str] = ["", ""]  # MATLAB leads with `\n\n`.

    for i in range(n_rows):
        parts: list[str] = []
        if row_headers is not None and len(row_headers) > 0:
            parts.append(str(row_headers[i]))
        for j in range(n_cols):
            val = coeffs[i, j]
            if np.isnan(val):
                parts.append(" & ")
            else:
                parts.append(" & " + _fmt(val, j, coeff=True))

        coeff_line = "".join(parts) + (r"\\[-1pt]" if ind_sig_stats else r"\\[2pt]")
        lines.append(coeff_line)

        if ind_sig_stats:
            stat_parts: list[str] = []
            for j in range(n_cols):
                val = sigstats[i, j]
                if np.isnan(val):
                    stat_parts.append(" & ")
                else:
                    stat_parts.append(" & " + open_b + _fmt(val, j) + close_b)
            lines.append("".join(stat_parts) + r"\\[2pt]")

    lines.append("")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Panel-assembly helper (stand-in for part of makeResToPrint.m)
# ---------------------------------------------------------------------------
def build_basic_sort_panels(
    basic_sorts_res: Any,
    row_label: str = "vw_nyse_5",
) -> dict[str, dict[str, Any]]:
    """Assemble Panels A/B/C of the basic-sort table from a
    ``BasicSortsResults`` instance, mirroring ``makeResToPrint.m`` lines
    89-113.
    """
    alpha_factors = (1, 3, 4, 5, 6)

    def _get(f):
        try:
            return basic_sorts_res.basic[(row_label, f)]
        except (AttributeError, KeyError) as exc:
            raise KeyError(
                f"basic_sorts_res.basic[({row_label!r}, {f})] not found; "
                f"cannot build Panel A"
            ) from exc

    r0 = _get(1)
    xret = np.asarray(r0.xret, dtype=float).reshape(-1)
    txret = np.asarray(r0.txret, dtype=float).reshape(-1)

    alpha_rows = [xret]
    talpha_rows = [txret]
    for f in alpha_factors:
        rf = _get(f)
        alpha_rows.append(np.asarray(rf.alpha, dtype=float).reshape(-1))
        talpha_rows.append(np.asarray(rf.talpha, dtype=float).reshape(-1))

    panel_a = {
        "a": np.vstack(alpha_rows),
        "tA": np.vstack(talpha_rows),
        "h": list(_PANEL_A_ROW_HEADERS),
    }

    # Prefer 6-factor loadings (MATLAB column 5 = models[4]) when available.
    try:
        rff = _get(6)
    except KeyError:
        rff = _get(5)
    fl = getattr(rff, "factor_loadings", None)
    if fl is None:
        raise AttributeError("basic_sorts_res row is missing factor_loadings")
    b = np.asarray(_fl_attr(fl, "b"), dtype=float)
    t = np.asarray(_fl_attr(fl, "t"), dtype=float)
    panel_b_a = b.T if b.ndim == 2 else b.reshape(-1, 1).T
    panel_b_tA = t.T if t.ndim == 2 else t.reshape(-1, 1).T

    labels = _fl_attr(fl, "label")
    labels_upper = [str(lbl).upper() for lbl in labels]
    panel_b_h = [rf"$\beta_{{\text{{{lbl}}}}}$" for lbl in labels_upper]

    panel_b = {"a": panel_b_a, "tA": panel_b_tA, "h": panel_b_h}

    ptf_num_stocks = np.asarray(r0.ptf_num_stocks, dtype=float)
    ptf_market_cap = np.asarray(r0.ptf_market_cap, dtype=float)
    n_row = np.nanmean(ptf_num_stocks[:, :5], axis=0)
    # Average firm size in $10^6 (MATLAB printed the total in $10^9).
    from ..analytics.sorts import average_firm_size

    me_row = average_firm_size(ptf_market_cap, ptf_num_stocks[:, :5])
    panel_c_a = np.vstack([n_row, me_row])

    panel_c = {
        "a": panel_c_a,
        "tA": panel_c_a,
        "h": list(_PANEL_C_ROW_HEADERS),
    }

    return {"PanelA": panel_a, "PanelB": panel_b, "PanelC": panel_c}


def _fl_attr(fl: Any, name: str) -> Any:
    if isinstance(fl, Mapping):
        if name in fl:
            return fl[name]
        raise KeyError(f"factor_loadings missing key {name!r}")
    return getattr(fl, name)


def _resolve_basic_panels(
    panels: Mapping[str, Mapping[str, Any]] | Any,
    *,
    row_label: str = "vw_nyse_5",
) -> Mapping[str, Mapping[str, Any]]:
    """Accept Tab_BasicSort, PrintResults, or BasicSortsResults."""
    # PrintResults
    if hasattr(panels, "Tab_BasicSort"):
        tab = getattr(panels, "Tab_BasicSort")
        if isinstance(tab, Mapping) and "PanelA" in tab:
            return tab
    if isinstance(panels, Mapping):
        if "Tab_BasicSort" in panels and isinstance(panels["Tab_BasicSort"], Mapping):
            return panels["Tab_BasicSort"]  # type: ignore[return-value]
        if "PanelA" in panels:
            return panels  # type: ignore[return-value]
    # BasicSortsResults fall-through
    return build_basic_sort_panels(panels, row_label=row_label)


def _text_period(text: Any, period: str) -> Any:
    """``Text.<period>`` if the results have it, else ``Text.timePeriod``.

    ``period`` is ``"sortPeriod"`` (the months in which the signal's sorts
    have returns) or ``"returnPeriod"`` (those of them inside the run's
    window). Results saved by an earlier version have neither and fall back to the
    run's window, which is what their captions said.
    """
    def get(key: str) -> Any:
        return text.get(key) if isinstance(text, Mapping) else getattr(text, key, None)

    chain = {"sortPeriod": ("sortPeriod", "returnPeriod"), "returnPeriod": ("returnPeriod",)}
    for key in (*chain.get(period, ()), "timePeriod"):
        val = get(key)
        if val is not None and np.asarray(val).size >= 2:
            return val
    return None


def _resolve_text_fields(
    results: Any,
    signal_char: str | None,
    time_period: Any | None,
    *,
    period: str = "sortPeriod",
) -> tuple[str, tuple[str, str]]:
    """Signal label and the caption's sample period, as two YYYYMM strings.

    The period is the months the table's numbers use, see
    :func:`_text_period`; an explicit ``time_period`` overrides it.
    """
    text: Any = None
    if hasattr(results, "Text") and results.Text is not None:
        text = results.Text
    elif isinstance(results, Mapping) and "Text" in results and results["Text"] is not None:
        text = results["Text"]

    if text is None:
        sc = signal_char if signal_char is not None else "SIGNAL"
        tp = time_period
    else:
        if signal_char is not None:
            sc = signal_char
        elif isinstance(text, Mapping):
            sc = str(text.get("signalChar", "SIGNAL"))
        else:
            sc = str(getattr(text, "signalChar", "SIGNAL"))
        tp = time_period if time_period is not None else _text_period(text, period)

    if tp is None:
        raise ValueError("time_period required (or Results.Text.timePeriod)")
    return sc, _time_period_pair(tp)


def _gen_alpha_period_clause(results: Any, start: str, end: str) -> str:
    """Caption clause for generalized alphas estimated on other months than the sorts.

    The sorts ignore the run's window and the generalized alphas are cut to
    it, so the two differ when the signal has returns outside the window.
    Empty when they are the same months.
    """
    try:
        _, (r0, r1) = _resolve_text_fields(results, None, None, period="returnPeriod")
    except ValueError:
        return ""
    if (r0, r1) == (start, end):
        return ""
    return f" The generalized alphas use {r0} to {r1}."


# ---------------------------------------------------------------------------
# printBasicSortTable port
# ---------------------------------------------------------------------------
def print_basic_sort_table(
    panels: Mapping[str, Mapping[str, Any]] | Any,
    signal_char: str | None = None,
    time_period: tuple[int | str, int | str] | Sequence[int | str] | None = None,
    *,
    fid: TextIO | None = None,
    row_label: str = "vw_nyse_5",
) -> str:
    """Port of MATLAB ``printBasicSortTable(fid, Results)``.

    ``panels`` may be:

    - ``PrintResults`` (preferred; uses ``Tab_BasicSort`` + ``Text``),
    - a ``Tab_BasicSort`` dict with ``PanelA/B/C``,
    - a ``BasicSortsResults`` instance (legacy assembly via
      :func:`build_basic_sort_panels`).
    """
    # When first arg is PrintResults, Text supplies defaults.
    if hasattr(panels, "Tab_BasicSort") or (
        isinstance(panels, Mapping) and "Tab_BasicSort" in panels
    ):
        sc, (start, end) = _resolve_text_fields(panels, signal_char, time_period)
        tab = _resolve_basic_panels(panels, row_label=row_label)
    else:
        if signal_char is None or time_period is None:
            # may still be BasicSortsResults without text
            sc = signal_char if signal_char is not None else "SIGNAL"
            if time_period is None:
                raise ValueError(
                    "signal_char and time_period required when panels is not PrintResults"
                )
            start, end = _time_period_pair(time_period)
        else:
            sc = signal_char
            start, end = _time_period_pair(time_period)
        tab = _resolve_basic_panels(panels, row_label=row_label)

    pa = tab["PanelA"]
    pb = tab["PanelB"]
    pc = tab["PanelC"]

    buf = io.StringIO()
    w = buf.write

    w("\\begin{table}[!htbp]\n")
    w("\\small\n")
    caption = (
        "\\caption{Basic sort: VW, quintile, NYSE-breaks\\\\\n"
        "\\small{This table reports average excess returns and alphas for "
        f"portfolios sorted on {sc}. "
        "In each month in which the signal is available, we sort stocks into five "
        "portfolios based on their signal using NYSE breakpoints. "
        "The portfolios are held, without rebalancing, until the next such month. "
        "Panel A reports average value-weighted quintile portfolio (L,2,3,4,H) "
        "returns in excess of the risk-free rate, "
        "the long-short extreme quintile portfolio (H-L) return, and alphas "
        "with respect to the CAPM, "
        "\\citet{FamaFrench1993} three-factor model, \\citet{FamaFrench1993} "
        "three-factor model augmented with the "
        "\\citet{Carhart1997} momentum factor, \\citet{FamaFrench2015} "
        "five-factor model, and "
        "the \\citet{FamaFrench2015} five-factor model augmented with the "
        "\\citet{Carhart1997} momentum factor "
        "following \\citet{FamaFrench2018}. "
        "Panel B reports the factor loadings for the quintile portfolios and "
        "long-short extreme quintile portfolio in the "
        "\\citet{FamaFrench2015} five-factor model augmented with the "
        "\\citet{Carhart1997} momentum factor. "
        "Panel C reports the average number of stocks and market capitalization "
        "of each portfolio. "
        f"T-statistics are in brackets. The sample period is {start} to {end}.}}}}\n"
    )
    w(caption)
    w("\\label{tab:tsRegs}\n")
    w("\\begin{tabularx}{\\linewidth}{l*6{>{\\centering\\arraybackslash}X}}\\hline\n")

    w(
        "\\multicolumn{7}{l}{Panel A: Excess returns and alphas on "
        f"{sc}-sorted portfolios}}\\\\[2pt]\n"
    )
    w(_QUINTILE_HEADER_ROW)
    w(mat_to_tex(pa["a"], sigstats=pa["tA"], row_headers=pa["h"], decimals=2))
    w("\\hline\n")

    w(
        "\\multicolumn{7}{l}{Panel B: \\citet{FamaFrench2018} 6-factor model "
        f"loadings for {sc}-sorted portfolios}}\\\\[2pt]\n"
    )
    w(mat_to_tex(pb["a"], sigstats=pb["tA"], row_headers=pb["h"], decimals=2))
    w("\\hline\n")

    w(
        "\\multicolumn{7}{l}{Panel C: Average number of firms ($n$) and "
        "market capitalization ($me$)}\\\\[2pt]\n"
    )
    w(mat_to_tex(pc["a"], sigstats=pc["a"], row_headers=pc["h"], decimals=0))
    w("\\hline\n")

    w("\\end{tabularx}\n")
    w("\\end{table}\n\n\n")

    return _write_or_return(buf, fid)


# ---------------------------------------------------------------------------
# printRobustnessToSortingTable
# ---------------------------------------------------------------------------
def print_robustness_to_sorting_table(
    results: Any,
    *,
    fid: TextIO | None = None,
) -> str:
    """Port of MATLAB ``printRobustnessToSortingTable``."""
    sc, (start, end) = _resolve_text_fields(results, None, None)
    tab = _as_panel_map(results, "Tab_RobustSort")
    pa, pb = tab["PanelA"], tab["PanelB"]

    buf = io.StringIO()
    w = buf.write

    w("\\begin{table}[!htbp]\n")
    w("\\small\n")
    w(
        "\\caption{Robustness to sorting methodology \\& trading costs\\\\\n"
        "\\small{This table evaluates the robustness of the choices made in the "
        f"{sc} strategy construction methodology. "
        "In each panel, the first row shows results from a quintile, value-weighted "
        "sort using NYSE break points as employed in Table~\\ref{tab:tsRegs}. "
        "Each of the subsequent rows deviates in one of the three choices at a time, "
        "and the choices are specified in the first three columns. "
        "For each strategy construction methodology, the table reports average excess "
        "returns and alphas with respect to the CAPM,  "
        "\\citet{FamaFrench1993} three-factor model, \\citet{FamaFrench1993} "
        "three-factor model augmented with the "
        "\\citet{Carhart1997} momentum factor, \\citet{FamaFrench2015} "
        "five-factor model, and "
        "the \\citet{FamaFrench2015} five-factor model augmented with the "
        "\\citet{Carhart1997} momentum factor "
        "following \\citet{FamaFrench2018}. "
        "Panel A reports average returns and alphas with no adjustment for trading costs. "
        "Panel B reports net average returns and \\citet{Novy-MarxVelikov2016} "
        "generalized alphas as "
        "prescribed by \\citet*{DetzelNovy-MarxVelikov2022}, net of "
        f"{tcost_wording(_tcosts_type_of(results))['caption']}. "
        f"T-statistics are in brackets. The sample period is {start} to {end}."
        f"{_gen_alpha_period_clause(results, start, end)}}}}}\n"
    )
    w("\\label{tab:robustnessToSorting}\n")
    w("\\begin{tabularx}{\\linewidth}{l*9{>{\\centering\\arraybackslash}X}}\\hline\n")

    w("\\multicolumn{9}{l}{Panel A: Gross Returns and Alphas}\\\\[2pt]\n")
    w(
        "Portfolios & Breaks & Weights & $r^e$ & $\\alpha_{\\text{CAPM}}$  "
        "& $\\alpha_{\\text{FF3}}$ & $\\alpha_{\\text{FF4}}$  "
        "& $\\alpha_{\\text{FF5}}$  & $\\alpha_{\\text{FF6}}$\\\\[2pt]\n"
    )
    body = mat_to_tex(pa["a"], sigstats=pa["tA"], row_headers=pa["h"], decimals=2)
    # MATLAB: pad t-stat rows under the three construction-method columns
    body = body.replace("[-1pt]", "[-1pt] & &")
    w(body)
    w("\\hline\n")

    w(
        "\\multicolumn{9}{l}{Panel B: Net Returns and "
        "\\citet{Novy-MarxVelikov2016} generalized alphas}\\\\[2pt]\n"
    )
    w(
        "Portfolios & Breaks & Weights & $r^e_{net}$ & $\\alpha^*_{\\text{CAPM}}$  "
        "& $\\alpha^*_{\\text{FF3}}$ & $\\alpha^*_{\\text{FF4}}$  "
        "& $\\alpha^*_{\\text{FF5}}$  & $\\alpha^*_{\\text{FF6}}$\\\\[2pt]\n"
    )
    body = mat_to_tex(pb["a"], sigstats=pb["tA"], row_headers=pb["h"], decimals=2)
    body = body.replace("[-1pt]", "[-1pt] & &")
    w(body)
    w("\\hline\n")

    w("\\end{tabularx}\n")
    w("\\end{table}\n\n\n")
    return _write_or_return(buf, fid)


# ---------------------------------------------------------------------------
# Subsample table (Python-only)
# ---------------------------------------------------------------------------
def print_sub_sample_table(
    results: Any,
    *,
    fid: TextIO | None = None,
) -> str:
    """Write ``tab:subSample``: the Table 1 strategy over the full sample and subperiods.

    No MATLAB counterpart. Returns ``""`` when ``Tab_SubSample`` is
    missing or empty, so results saved by an earlier version still print.
    """
    try:
        tab = _as_panel_map(results, "Tab_SubSample")
        a = np.atleast_2d(np.asarray(tab["a"], dtype=float))
        t_a = np.atleast_2d(np.asarray(tab["tA"], dtype=float))
        h = list(tab["h"])
    except (KeyError, TypeError, AttributeError):
        return ""
    if a.size == 0 or not h:
        return ""
    sc, (start, end) = _resolve_text_fields(results, None, None, period="returnPeriod")
    n_sub = int(tab.get("n_sub") or len(h) - 1)
    cols = list(tab.get("cols") or [])
    if len(cols) != a.shape[1]:
        cols = ["$r^e$"] + [f"({k})" for k in range(1, a.shape[1])]

    buf = io.StringIO()
    w = buf.write

    w("\\begin{table}[!htbp]\n")
    w("\\small\n")
    w(
        "\\caption{Performance across subsamples\\\\\n"
        "\\small{This table reports the performance of the long/short "
        f"{sc} strategy from Table~\\ref{{tab:tsRegs}}, which is constructed from a "
        "quintile sort using NYSE breakpoints and value-weighted portfolios, in "
        "different parts of the sample. "
        "The first row reports results for the full sample. "
        f"The following rows split the sample into {num_to_words(n_sub)} contiguous "
        "subsamples of approximately equal length, labelled by their first and last "
        "month. "
        "For each sample, the table reports the average excess return and alphas with "
        "respect to the CAPM, \\citet{FamaFrench1993} three-factor model, "
        "\\citet{FamaFrench1993} three-factor model augmented with the "
        "\\citet{Carhart1997} momentum factor, \\citet{FamaFrench2015} five-factor "
        "model, and the \\citet{FamaFrench2015} five-factor model augmented with the "
        "\\citet{Carhart1997} momentum factor following \\citet{FamaFrench2018}, "
        "all in percent per month. "
        f"T-statistics are in brackets. The sample period is {start} to {end}.}}}}\n"
    )
    w("\\label{tab:subSample}\n")
    w(
        f"\\begin{{tabularx}}{{\\linewidth}}{{l*{{{a.shape[1]}}}"
        "{>{\\centering\\arraybackslash}X}}\\hline\n"
    )
    w("Sample & " + " & ".join(cols) + "\\\\[2pt]\n")
    w(mat_to_tex(a, sigstats=t_a, row_headers=h, decimals=2))
    w("\\hline\n")
    w("\\end{tabularx}\n")
    w("\\end{table}\n\n\n")
    return _write_or_return(buf, fid)


# ---------------------------------------------------------------------------
# printCondSizeSortTable
# ---------------------------------------------------------------------------
def print_cond_size_sort_table(
    results: Any,
    *,
    fid: TextIO | None = None,
) -> str:
    """Port of MATLAB ``printCondSizeSortTable``."""
    sc, (start, end) = _resolve_text_fields(results, None, None)
    tab = _as_panel_map(results, "Tab_CondSizeSort")
    pa, pb = tab["PanelA"], tab["PanelB"]

    buf = io.StringIO()
    w = buf.write

    # Match MATLAB (gold may omit landscape around this table).
    w("\\begin{landscape}\n")
    w("\\begin{table}[!htbp]\n")
    w("\\small\n")
    w(
        f"\\caption{{Conditional sort on size and {sc}\\\\"
        f"\\small{{This table presents results for conditional double sorts on size "
        f"and {sc}. "
        "In each month in which the signal is available, stocks are first sorted "
        "into quintiles based on size using NYSE breakpoints. "
        f"Then, within each size quintile, stocks are further sorted based on {sc}. "
        "Finally, they are grouped into twenty-five portfolios based on the "
        "intersection of the two sorts. "
        "The portfolios are value-weighted, with weights reset every month. "
        f"Panel A presents the average returns to the 25 portfolios, as well as "
        f"strategies that go long stocks with high {sc} and short stocks with low "
        f"{sc}. Panel B documents the average number of firms "
        "and the average firm size for each portfolio. "
        f"The sample period is {start} to {end}.}}}}\n"
    )
    w("\\label{tab:doubleSortSize}\n")
    w(
        "\\begin{tabularx}{\\linewidth}"
        "{l*7{>{\\centering\\arraybackslash}X}*7{>{\\centering\\arraybackslash}X}}"
        "\\hline\n"
    )

    w(
        "\\multicolumn{13}{l}{Panel A: portfolio average returns and "
        "time-series regression results}\\\\[2pt]\n"
    )
    w(
        f"& & \\multicolumn{{5}}{{c}}{{{sc} Quintiles}} & & "
        f"\\multicolumn{{6}}{{c}}{{{sc} Strategies}} \\\\[2pt]\n"
    )
    w(
        "& & (L) & (2) & (3) & (4) & (H) & & $r^e$ & $\\alpha_{CAPM}$ & "
        "$\\alpha_{FF3}$ & $\\alpha_{FF4}$  & $\\alpha_{FF5}$ &$\\alpha_{FF6}$"
        "\\\\\\cline{3-7}\\cline{9-14}\n"
    )
    w(
        "\\parbox[t]{2mm}{\\multirow{10}{*}{\\rotatebox[origin=c]{90}"
        "{Size quintiles }}} \n"
    )
    body_a = mat_to_tex(pa["a"], sigstats=pa["tA"], row_headers=pa["h"], decimals=2)
    # Align t-stat rows under the size label / (i) header columns.
    body_a = _pad_cond_size_panel_a(body_a)
    w(body_a)
    w("\\hline\n")

    w(
        "\\multicolumn{13}{l}{Panel B: Portfolio average number of firms and "
        "market capitalization}\\\\[2pt]\n"
    )
    w(
        f"& & \\multicolumn{{5}}{{c}}{{{sc} Quintiles}} & & "
        f"\\multicolumn{{5}}{{c}}{{{sc} Quintiles}} \\\\[2pt]\n"
    )
    w(
        "& & \\multicolumn{5}{c}{Average $n$} & & "
        "\\multicolumn{5}{c}{Average market capitalization ($\\$10^6$)} \\\\[2pt]\n"
    )
    w(
        "& & (L) & (2) & (3) & (4) & (H) & &(L) & (2) & (3) & (4) & (H) "
        "\\\\\\cline{3-7}\\cline{9-13}\n"
    )
    w(
        "\\parbox[t]{2mm}{\\multirow{5}{*}{\\rotatebox[origin=c]{90}"
        "{Size quintiles }}} \n"
    )
    w(mat_to_tex(pb["a"], sigstats=pb["a"], row_headers=pb["h"], decimals=0))
    w("\\hline\n")

    w("\\end{tabularx}\n")
    w("\\end{table}\n")
    w("\\end{landscape}\n\n\n")
    return _write_or_return(buf, fid)


def _pad_cond_size_panel_a(body: str) -> str:
    """Approximate MATLAB's character-index ``&`` inserts on Panel A body.

    Ensures t-stat lines start with ``&&`` so the multirow size label column
    lines up with gold output.
    """
    out_lines: list[str] = []
    for line in body.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("& [") or stripped.startswith("& ["):
            # already a t-stat line from mat_to_tex; add one leading &
            if not stripped.startswith("&&"):
                out_lines.append("&" + line if line.startswith(" &") else "&&" + stripped)
            else:
                out_lines.append(line)
        elif stripped.startswith("& [") is False and "[" in line and line.strip().startswith("&"):
            # t-stat cells mid-line style
            if line.startswith(" & ["):
                out_lines.append("&" + line)
            else:
                out_lines.append(line)
        else:
            out_lines.append(line)
    # Simpler second pass matching gold majority: t-stat rows start with ' &'
    final: list[str] = []
    for line in out_lines:
        if "\\[2pt]" in line and "[" in line and "\\[-1pt]" not in line:
            s = line.lstrip("\n")
            if s.startswith(" & [") and not s.startswith(" &&"):
                final.append("&" + s)
            elif s.startswith("& [") and not s.startswith("&&"):
                final.append("&" + s)
            else:
                final.append(line)
        else:
            final.append(line)
    return "\n".join(final)


# ---------------------------------------------------------------------------
# Trading-cost wording
# ---------------------------------------------------------------------------
_LF_ESTIMATORS = (
    "the Gibbs sampler of \\citet{Hasbrouck2009} and the estimators of "
    "\\citet{CorwinSchultz2012}, \\citet{AbdiRanaldo2017}, and "
    "\\citet{KyleObizhaeva2016}"
)
_IMPUTED = (
    "for stock-months with none of these, from stocks matched on size and "
    "idiosyncratic volatility"
)


def tcost_wording(tcosts_type: str | None) -> dict[str, str]:
    """Report wording for the trading-cost estimator behind ``tcosts_type``.

    The report calls costs "trading costs" but names the estimator once in
    the text, in a defining sentence (``"definition"``), now and then in the
    text by a short name (``"short"``), and in every caption that shows net
    numbers (``"caption"``, a phrase following "net of"), so that a reader
    never sees an unqualified cost. ``tcosts_type`` is the
    value stored in ``Text.tcostsType``: ``'full'``, ``'lf_combo'`` or
    ``'gibbs'`` (see ``transforms.tcosts.make_trading_costs``). Any other
    value gets wording that names no estimator.
    """
    t = str(tcosts_type or "").strip().lower()
    if t == "full":
        return {
            "definition": (
                "Trading costs throughout this report are the Chen--Velikov (C-V) "
                "effective-spread costs of \\citet{ChenVelikov2022}. A stock's cost "
                "is its effective bid-ask half-spread, taken from high-frequency "
                "TAQ and ISSM trade and quote data where these are available; "
                f"otherwise from the average of four low-frequency estimators "
                f"({_LF_ESTIMATORS}); and, {_IMPUTED}. "
            ),
            "short": "C-V effective spreads",
            "caption": (
                "trading costs, measured as Chen--Velikov (C-V) effective "
                "spreads \\citep{ChenVelikov2022}"
            ),
        }
    if t == "lf_combo":
        return {
            "definition": (
                "Trading costs throughout this report are the Chen--Velikov (C-V) "
                "low-frequency effective-spread costs of \\citet{ChenVelikov2022}. "
                "A stock's cost is its effective bid-ask half-spread, estimated as "
                f"the average of four low-frequency estimators ({_LF_ESTIMATORS}); "
                f"and, {_IMPUTED}. "
            ),
            "short": "C-V low-frequency effective spreads",
            "caption": (
                "trading costs, measured as Chen--Velikov (C-V) low-frequency "
                "effective spreads \\citep{ChenVelikov2022}"
            ),
        }
    if t == "gibbs":
        return {
            "definition": (
                "Trading costs throughout this report are Gibbs effective-spread "
                "costs. A stock's cost is its effective bid-ask half-spread, "
                "estimated with the Gibbs sampler of \\citet{Hasbrouck2009}; or, "
                "for stock-months without that estimate, from stocks matched on "
                "size and idiosyncratic volatility. "
            ),
            "short": "Gibbs effective spreads",
            "caption": (
                "trading costs, measured as Gibbs effective spreads "
                "\\citep{Hasbrouck2009}"
            ),
        }
    return {
        "definition": (
            "Trading costs throughout this report are effective bid-ask "
            "half-spreads. "
        ),
        "short": "effective spreads",
        "caption": "trading costs, measured as effective bid-ask half-spreads",
    }


def _tcosts_type_of(results: Any) -> str:
    text = getattr(results, "Text", None)
    if text is None and isinstance(results, Mapping):
        text = results.get("Text")
    if isinstance(text, Mapping):
        return str(text.get("tcostsType", "full"))
    return str(getattr(text, "tcostsType", "full"))


# ---------------------------------------------------------------------------
# Close-anomaly tables
# ---------------------------------------------------------------------------
def close_anom_selection_sentence() -> str:
    """How the closely related anomalies were picked.

    One builder for the body text (``print_close_anoms_section``) and the
    captions of Tables tab:closeAnomFMB and tab:closeAnomSpan, so the three
    cannot drift apart. It mirrors ``make_close_anom_results``: the combined
    rank of the absolute Spearman correlation and the adjusted R² of
    the signal's long/short return on the anomaly's (no factors).
    The caller supplies the subject ("These anomalies were ").
    """
    return (
        "picked as those with the highest combined rank where the ranks are based "
        "on the absolute value of the Spearman rank correlations in Panel A of "
        "Figure~\\ref{fig:distributionCorrelations} and the adjusted $R^{2}$ from "
        "regressions of the signal's long/short returns on each anomaly's long/short "
        "returns, the regressions behind Figure~\\ref{fig:conditionalStrategies}, Panel B."
    )


def _numbered_header(n_cols: int) -> str:
    """Header row of column numbers only: ``& (1) & ... & (n)``."""
    return "".join(f"& ({k}) " for k in range(1, n_cols + 1)).rstrip() + "\\\\[2pt]\n"


def scale_small_slope_rows(
    coeffs: np.ndarray,
    row_headers: Sequence[str],
    *,
    keep: Sequence[str] = ("Intercept",),
) -> tuple[np.ndarray, list[str], list[tuple[str, int]]]:
    """Scale the coefficient rows that would print as zeros at two decimals.

    A row whose largest absolute coefficient is positive and below 0.01 is
    multiplied by ``10^k``, ``k`` the smallest integer that brings the largest
    to at least 0.1, and its header gets `` $\\times 10^{k}$``. Rows named in
    ``keep`` (the intercept) are left alone. Returns the scaled copy, the
    headers and the ``(header, k)`` of each scaled row, for the caption.
    T-statistics are not touched by the caller.
    """
    out = np.array(coeffs, dtype=float, copy=True)
    headers = [str(x) for x in row_headers]
    scaled: list[tuple[str, int]] = []
    for i in range(min(out.shape[0], len(headers))):
        if headers[i] in keep:
            continue
        row = np.abs(out[i])
        if not np.isfinite(row).any():
            continue
        top = float(np.nanmax(row))
        if not (0.0 < top < 0.01):
            continue
        k = max(int(math.ceil(-1.0 - math.log10(top))), 1)
        while top * 10.0**k < 0.1:
            k += 1
        while k > 1 and top * 10.0 ** (k - 1) >= 0.1:
            k -= 1
        out[i] = out[i] * 10.0**k
        scaled.append((headers[i], k))
        headers[i] = f"{headers[i]} $\\times 10^{{{k}}}$"
    return out, headers, scaled


def print_close_anoms_fmb_table(
    results: Any,
    *,
    fid: TextIO | None = None,
) -> str:
    """Port of MATLAB ``printCloseAnomsFMBTable``."""
    sc, (start, end) = _resolve_text_fields(results, None, None, period="returnPeriod")
    text = getattr(results, "Text", None) or (
        results.get("Text") if isinstance(results, Mapping) else None
    )
    if text is None:
        raise ValueError("Results.Text required")
    n_close = int(
        getattr(text, "nCloseAnoms", None)
        or (text.get("nCloseAnoms") if isinstance(text, Mapping) else 0)
    )
    close_anoms = _tex_escape(str(getattr(text, "closeAnoms", None) or (
        text.get("closeAnoms") if isinstance(text, Mapping) else ""
    ) or ""))
    n_close_char = num_to_words(n_close)
    tab = _as_panel_map(results, "Tab_CloseFMB")
    # Layout: signal alone, one anomaly each, all of them; then the
    # months row and the R² row, without t-stats. A slope row that
    # would print as zeros is scaled by a power of ten and says so.
    a = np.atleast_2d(np.asarray(tab["a"], dtype=float))
    t_a = np.atleast_2d(np.asarray(tab["tA"], dtype=float))
    h = list(tab["h"])
    n_cols = a.shape[1]
    coef, coef_h, scaled = scale_small_slope_rows(a[:-2], h[:-2])
    scaled_sentence = "".join(
        f"The slopes on {label} are multiplied by $10^{{{k}}}$. " for label, k in scaled
    )

    buf = io.StringIO()
    w = buf.write
    w("\\begin{table}[!htbp]\n")
    w("\\small\n")
    w(
        "\\caption{Fama-MacBeth regressions controlling for the most closely related "
        "anomalies\\\\\n"
        f"\\small{{This table presents Fama-MacBeth results of returns on {sc} "
        f"and the {n_close_char} most closely related anomalies. The regressions "
        f"take the following form: "
        f"$r_{{i,t}}=\\alpha+\\beta_{{{sc}}} {sc}"
        f"_{{i,t-1}}+\\sum_{{k=1}}^{{{n_close}}} \\beta_{{X_k}} X_{{i,t-1}}^k"
        f"+\\epsilon_{{i,t}}$, with returns in percent per month. "
        f"The {n_close_char} most closely related anomalies, $X$, are {close_anoms}. "
        f"These anomalies were {close_anom_selection_sentence()} "
        f"The first column reports the regression on {sc} alone, the last "
        "column the regression on all of them jointly. "
        + scaled_sentence
        + "The row \\# months reports the number of monthly cross-sections and "
        "the last row the average cross-sectional adjusted $R^2$ in percent. "
        f"The sample period is {start} to {end}; each regression uses the months "
        "in which all of its variables are available.}}\n"
    )
    w("\\label{tab:closeAnomFMB}\n")
    w(
        f"\\begin{{tabularx}}{{\\linewidth}}{{l*{{{max(n_cols, 1)}}}"
        "{>{\\centering\\arraybackslash}X}}\\hline\n"
    )
    if n_cols >= 2:
        w(_numbered_header(n_cols))
    w(mat_to_tex(coef, sigstats=t_a[:-2], row_headers=coef_h, decimals=2))
    w(mat_to_tex(a[-2:-1], row_headers=h[-2:-1], decimals=0))
    w(mat_to_tex(a[-1:], row_headers=h[-1:], decimals=2))
    w("\\hline\n")
    w("\\end{tabularx}\n")
    w("\\end{table}\n")
    return _write_or_return(buf, fid)


def print_close_anoms_span_table(
    results: Any,
    *,
    fid: TextIO | None = None,
) -> str:
    """Port of MATLAB ``printCloseAnomsSpanTable``."""
    sc, (start, end) = _resolve_text_fields(results, None, None, period="returnPeriod")
    text = getattr(results, "Text", None) or (
        results.get("Text") if isinstance(results, Mapping) else None
    )
    if text is None:
        raise ValueError("Results.Text required")
    n_close = int(
        getattr(text, "nCloseAnoms", None)
        or (text.get("nCloseAnoms") if isinstance(text, Mapping) else 0)
    )
    close_anoms = _tex_escape(str(getattr(text, "closeAnoms", None) or (
        text.get("closeAnoms") if isinstance(text, Mapping) else ""
    ) or ""))
    n_close_char = num_to_words(n_close)
    tab = _as_panel_map(results, "Tab_CloseSpan")

    buf = io.StringIO()
    w = buf.write
    w("\\begin{table}[!htbp]\n")
    w("\\small\n")
    w(
        "\\caption{Spanning tests controlling for the most closely related anomalies\\\\\n"
        f"\\small{{This table presents spanning-test results of regressing returns "
        f"to the {sc} trading strategy on trading strategies exploiting "
        f"the {n_close_char} most closely related anomalies. The regressions take "
        f"the following form: "
        f"$r_{{t}}^{{{sc}}}=\\alpha+ \\sum_{{k=1}}^{{{n_close}}} "
        f"\\beta_{{X_k}} r_{{t}}^{{X_k}}+\\sum_{{j=1}}^6 "
        f"\\beta_{{f_j}} r_t^{{f_j}}+\\epsilon_t$, where $X_k$ indicates each of the "
        f"{n_close_char} most closely related anomalies "
        "and $f_j$ indicates the six factors from "
        "the \\citet{FamaFrench2015} five-factor model augmented with the "
        "\\citet{Carhart1997} momentum factor. "
        f"The {n_close_char} most closely related anomalies, $X$, are {close_anoms}. "
        f"These anomalies were {close_anom_selection_sentence()} "
        "The last column reports the regression on all of them jointly. "
        "The row \\# months reports the number of months in each regression and "
        "the last row the adjusted $R^2$ in percent. "
        f"The sample period is {start} to {end}; each regression uses the months "
        "in which all of its strategies have returns.}}\n"
    )
    w("\\label{tab:closeAnomSpan}\n")
    # Coefficient rows as in MATLAB; then the months row and the
    # adjusted R² in integer percent, without t-stat lines. The
    # columns are numbered: one anomaly each, the last all of them.
    a = np.atleast_2d(np.asarray(tab["a"], dtype=float))
    t_a = np.atleast_2d(np.asarray(tab["tA"], dtype=float))
    h = list(tab["h"])
    n_cols = a.shape[1]
    w(
        f"\\begin{{tabularx}}{{\\linewidth}}{{l*{{{max(n_cols, 1)}}}"
        "{>{\\centering\\arraybackslash}X}}\\hline\n"
    )
    if n_cols >= 1:
        w(_numbered_header(n_cols))
    w(mat_to_tex(a[:-2], sigstats=t_a[:-2], row_headers=h[:-2], decimals=2))
    w(mat_to_tex(a[-2:-1], row_headers=h[-2:-1], decimals=0))
    w(mat_to_tex(a[-1:], row_headers=h[-1:], decimals=0))
    w("\\hline\n")
    w("\\end{tabularx}\n")
    w("\\end{table}\n")
    return _write_or_return(buf, fid)
