"""
Public entry points for the Assaying Anomalies Python toolkit.
"""

from __future__ import annotations

from importlib import metadata as _metadata
from pathlib import Path
from typing import Iterable, Mapping

# The installed distribution's version (pyproject.toml is the one place it is
# written). "unknown" when the package is imported from a source tree that was
# never installed; run manifests record the same string (run_manifest.UNKNOWN).
try:
    __version__ = _metadata.version("assayinganomalies")
except _metadata.PackageNotFoundError:  # pragma: no cover - uninstalled source tree
    __version__ = "unknown"

# First, and on purpose: importing .plotting pins matplotlib to Agg before
# anything below can pull in pyplot. Nothing here wants an
# interactive window, and choosing a GUI backend on a headless node is at best
# a warning. MPLBACKEND remains the escape hatch.
from .plotting import maybe_show, use_headless_backend
from .client import AssayClient
from .config import (
    AssayConfig,
    load_config,
    save_config,
    set_params,
    set_project_dir,
    resolve_project_dir,
    resolve_protocol_n_jobs,
    default_protocol_n_jobs,
)
from .data_access import (
    AnnualLayoutError,
    load,
    load_cz_anomalies,
    load_nmv_anomalies,
    list_cz_signals,
    get_cz_signal_info,
    describe_cz_signal,
)
from .analytics import (
    calc_held_ptfs,
    calc_ptf_rets,
    calc_tcosts,
    est_factor_regs,
    fill_months,
    held_legs,
    held_long_short,
    held_composite_long_short,
    ibbots,
    load_factors,
    make_ff_tcosts,
    moving,
    nanols,
    plot_anomaly_decay,
    prt,
    run_anomaly_decay,
    run_bivariate_sort,
    run_fama_macbeth,
    run_univariate_sort,
)
from .ingest import load_ff25
from .transforms import (
    CCM_LINK_COLUMNS,
    check_fill_anomalies,
    clean_ccm_link,
    fill_var,
    merge_on_link,
)
from .ops import log
from .pipeline import setup_database
from .compustat_extras import add_compustat_vars
from .session_cache import cache_info, clear_session_cache
from .analytics.protocol import FactorCostsError, ProtocolResult, run_test_signal, test_signal
from .analytics.res_to_print import PrintResults, make_res_to_print
from .signal_io import (
    default_mpe_signal_info,
    get_anomaly_signals,
    get_signal_info,
    load_signal_csv,
)
from .signal_tester import SignalInfo, SignalTester
from .reporting import print_tex_file, semantic_tex_diff

__all__ = [
    "__version__",
    "maybe_show",
    "use_headless_backend",
    "AssayClient",
    "AssayConfig",
    "SignalTester",
    "SignalInfo",
    "ProtocolResult",
    "PrintResults",
    "run_test_signal",
    "test_signal",
    "make_res_to_print",
    "print_tex_file",
    "semantic_tex_diff",
    "get_anomaly_signals",
    "load_signal_csv",
    "get_signal_info",
    "default_mpe_signal_info",
    "log",
    "AnnualLayoutError",
    "FactorCostsError",
    "load",
    "load_cz_anomalies",
    "load_nmv_anomalies",
    "list_cz_signals",
    "get_cz_signal_info",
    "describe_cz_signal",
    "load_config",
    "save_config",
    "set_params",
    "set_project_dir",
    "resolve_project_dir",
    "resolve_protocol_n_jobs",
    "default_protocol_n_jobs",
    "setup_database",
    "add_compustat_vars",
    "clear_session_cache",
    "cache_info",
    "run_univariate_sort",
    "run_bivariate_sort",
    "run_fama_macbeth",
    "load_factors",
    "calc_ptf_rets",
    "calc_held_ptfs",
    "fill_months",
    "held_legs",
    "held_long_short",
    "held_composite_long_short",
    "est_factor_regs",
    "calc_tcosts",
    "make_ff_tcosts",
    "nanols",
    "prt",
    "ibbots",
    "moving",
    "fill_var",
    "check_fill_anomalies",
    "CCM_LINK_COLUMNS",
    "clean_ccm_link",
    "merge_on_link",
    "load_ff25",
    "run_anomaly_decay",
    "plot_anomaly_decay",
]


def set_params_cli(**kwargs: object) -> AssayConfig:
    """
    Convenience wrapper used by the CLI to update parameters.
    """
    return set_params(**kwargs)


def load_fields(
    fields: Iterable[str] | Mapping[str, str],
    *,
    path: str | Path | None = None,
    **kwargs: object,
):
    """
    Thin wrapper around :func:`load` for parity with MATLAB-style scripts.
    """
    return load(path=path, fields=fields, **kwargs)

