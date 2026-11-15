"""
LaTeX / text reporting helpers for the Assaying Anomalies toolkit.

This subpackage hosts Python ports of the MATLAB ``Functions/Assay functions/prt``
helpers, which emit the LaTeX assay paper one table/figure at a time.
"""

from .tables import (
    add_comma,
    build_basic_sort_panels,
    mat_to_tex,
    num_to_words,
    print_basic_sort_table,
    print_close_anoms_fmb_table,
    print_close_anoms_span_table,
    print_cond_size_sort_table,
    print_robustness_to_sorting_table,
)
from .figures import (
    FIGURE_SUFFIXES,
    emit_all_figures,
    emit_signal_description_figure,
    emit_sharpe_dist_figure,
    emit_ibbots_figure,
    emit_alpha_prctl_figure,
    emit_correl_figure,
    emit_dendrogram_figure,
    emit_cond_strats_figure,
    emit_comb_strats_figure,
)
from .latex import print_tex_file, semantic_tex_diff, strip_date_today

__all__ = [
    "mat_to_tex",
    "add_comma",
    "num_to_words",
    "print_basic_sort_table",
    "print_robustness_to_sorting_table",
    "print_cond_size_sort_table",
    "print_close_anoms_fmb_table",
    "print_close_anoms_span_table",
    "build_basic_sort_panels",
    "print_tex_file",
    "semantic_tex_diff",
    "strip_date_today",
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
]
