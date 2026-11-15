"""
Results orchestration for the Novy-Marx / Velikov (2026) protocol.

MATLAB equivalents:
  - Functions/Assay functions/makeBasicSortsResults.m
  - Functions/Assay functions/makeAnomBenchmarkResults.m

`make_basic_sorts_results` produces the univariate-sort tables (Tables 1-3):
  1. 5 univariate-sort variants x 5 factor models
     - row 1: VW quintile sort, NYSE breakpoints
     - row 2: EW quintile sort, NYSE breakpoints
     - row 3: VW quintile sort, name breakpoints
     - row 4: VW quintile sort, cap (portfolio-mass) breakpoints
     - row 5: VW decile  sort, NYSE breakpoints
  2. Conditional-on-size sorts (5 ME quintiles x 5 factor models).

`make_anom_benchmark_results` compares the candidate test signal against a
panel of benchmark anomaly signals via:
  - Pearson / Spearman panel correlations
  - 5x5 conditional double sort (collapsed to a hedged 2-leg portfolio)
  - Bivariate Fama-MacBeth regressions (testSignal, anom_i)
"""
from __future__ import annotations

import gc
import logging
import os
import pickle
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import get_context
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..config import pool_worker_count
from ..tiebreak import anomaly_noise_rng
from .regressions import RegressionResult, _calendar_lag_panel, run_fama_macbeth
from .sorts import SortResult, check_convention, run_univariate_sort

LOGGER = logging.getLogger("assayinganomalies.analytics.results")


# Factor-model codes mirrored from runUnivSort.m / makeBasicSortsResults.m.
FACTOR_MODELS: tuple[int, ...] = (1, 3, 4, 5, 6)

# Labels for the 5 basic-sort rows (matches MATLAB resBasicSorts(i,:) row index).
BASIC_SORT_LABELS: tuple[str, ...] = (
    "vw_nyse_5",  # row 1: VW quintiles, NYSE breaks
    "ew_nyse_5",  # row 2: EW quintiles, NYSE breaks
    "vw_name_5",  # row 3: VW quintiles, name breaks
    "vw_cap_5",   # row 4: VW quintiles, cap (portfolio-mass) breaks
    "vw_nyse_10", # row 5: VW deciles,   NYSE breaks
)


@dataclass
class BasicSortsResults:
    """Container mirroring MATLAB's [resBasicSorts, resCondSorts] tuple.

    Attributes
    ----------
    basic : dict[tuple[str, int], SortResult]
        Keyed by (row_label, factor_model). `row_label` is one of
        `BASIC_SORT_LABELS`, `factor_model` one of `FACTOR_MODELS`.
    conditional : dict[tuple[int, int], SortResult]
        Keyed by (me_quintile, factor_model). me_quintile in 1..5.
    gen_alpha : dict[tuple[str, int], dict]
        Generalized (net) alpha per basic-sort cell. Key matches ``basic``.
        Each value has ``alpha_res`` (OlsRes), ``w_x_y``, ``w_x``, the
        aligned input series used for the calculation, and ``outcome``
        (``GenAlphaOutcome.to_dict()``: ``status`` is ``success``, ``zero``,
        ``unavailable`` or ``failed``, with ``value``, ``tstat``, ``n_obs``,
        ``reason`` and ``w_anom``, the strategy's net-MVE weight). Both MVEs
        are estimated on the strategy's own complete months.
    metadata : dict
        Time-period used and any other orchestration context. With gen-α on,
        ``gen_alpha_diagnostics`` holds status counts, the valid count, a
        record for every cell that did not succeed, and ``w_anom`` per cell.
    """

    basic: dict[tuple[str, int], SortResult] = field(default_factory=dict)
    conditional: dict[tuple[int, int], SortResult] = field(default_factory=dict)
    gen_alpha: dict[tuple[str, int], dict] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


def _slice_time_period(
    test_signal: pd.Series,
    time_period: tuple[pd.Timestamp | int, pd.Timestamp | int] | None,
) -> tuple[pd.Timestamp | int, pd.Timestamp | int] | None:
    """Pass-through; `run_univariate_sort` already parses YYYYMM or Timestamps."""
    if time_period is None:
        return None
    return time_period


def reweighted_sort(
    returns: pd.Series,
    signal: pd.Series,
    mcap: pd.Series,
    *,
    factor_models: Any,
    factors: pd.DataFrame | None = None,
    n_bins: int = 5,
) -> dict[int, SortResult]:
    """Quintile sort on ``signal`` whose portfolios are reweighted every month.

    The conditional size sort of the protocol (the report's double-sort
    table) calls this once per size quintile, with the signal masked outside
    the quintile. Membership is that of the other sorts: portfolios are
    formed, on name breakpoints, in the months in which the signal has
    values, and carried to the next such month. The weights are not: every
    month each portfolio is weighted by its stocks' market capitalization at
    the end of the previous month (``calc_ptf_rets``), where the held legs of
    ``run_univariate_sort`` let the weights of the purchase drift. Gross
    returns only, so there are no trades to price.

    Returns one ``SortResult`` per factor model, all on the same portfolio
    returns; ``ptf_num_stocks`` and ``ptf_market_cap`` are the stocks with a
    return and a lagged market capitalization and the sum of the latter.
    """
    from .sorts import (
        _bin_by_cross_section,
        _matlab_style_sort_outputs,
        _resolve_factor_model,
        _run_factor_regs,
        calc_ptf_rets,
    )

    df = pd.concat({"ret": returns, "signal": signal, "mcap": mcap}, axis=1)
    bins = _bin_by_cross_section(df["signal"], n_bins, breaks="name", nyse_flag=None, mcap=mcap)
    ind = bins.reindex(df.index).fillna(0)
    if int(pd.to_numeric(ind, errors="coerce").max() or 0) <= 0:
        raise ValueError("No data available after filtering/NaN removal.")

    leg_ts, ptf_counts, ptf_mcap = calc_ptf_rets(
        df["ret"], ind, df["mcap"], holding_period=1, weighting="v"
    )
    cols = range(1, n_bins + 1)
    leg_ts = leg_ts.reindex(columns=cols)
    ptf_counts = ptf_counts.reindex(columns=cols)
    ptf_mcap = ptf_mcap.reindex(columns=cols)
    long_short = leg_ts[n_bins] - leg_ts[1]
    pret_all = leg_ts.copy()
    pret_all["long_short"] = long_short

    out: dict[int, SortResult] = {}
    for f in factor_models:
        factor_df = _resolve_factor_model(pret_all.index, f, factors=factors)
        alphas, tstats, loadings, loading_tstats, r2 = _run_factor_regs(
            leg_ts, long_short, factor_df, robust=False
        )
        stats = _matlab_style_sort_outputs(
            pret_all, factors=factor_df, robust_se=False, input_is_excess=False
        )
        out[f] = SortResult(
            leg_returns=leg_ts,
            long_short=long_short,
            metadata={
                "n_bins": n_bins,
                "breaks": "name",
                "weighting": "v",
                "holding_period": 1,
                "add_long_short": True,
                "factor_model": f,
                "tcosts": None,
                "weights": "reset monthly",
            },
            xret=stats["xret"],
            txret=stats["txret"],
            alpha=stats["alpha"],
            talpha=stats["talpha"],
            sharpe=stats["sharpe"],
            info=stats["info"],
            resid=stats["resid"],
            alphas=alphas,
            tstats=tstats,
            factor_loadings=loadings,
            factor_loading_tstats=loading_tstats,
            r2=r2,
            r2_adj=stats["r2_adj"],
            ptf_num_stocks=ptf_counts,
            ptf_market_cap=ptf_mcap,
        )
    return out


def make_basic_sorts_results(
    test_signal: pd.Series,
    returns: pd.Series,
    mcap: pd.Series,
    *,
    nyse_flag: pd.Series | None = None,
    tcosts: pd.Series | None = None,
    factor_tcosts: pd.DataFrame | None = None,
    factors: pd.DataFrame | None = None,
    time_period: tuple[pd.Timestamp | int, pd.Timestamp | int] | None = None,
    factor_models: tuple[int, ...] = FACTOR_MODELS,
    me_for_conditional: pd.Series | None = None,
    n_me_ptfs: int = 5,
    compute_gen_alpha: bool = True,
    verbose: bool = True,
    convention: str = "dollar",
) -> BasicSortsResults:
    """
    Run the basic-sorts panel of the Novy-Marx / Velikov (2026) protocol.

    Parameters
    ----------
    test_signal : pd.Series
        Candidate anomaly signal, MultiIndex (date, permno).
    returns : pd.Series
        Stock returns, MultiIndex (date, permno).
    mcap : pd.Series
        Market cap (me), MultiIndex (date, permno). Used for VW weighting,
        cap breakpoints and (by default) the conditional-size sort.
    nyse_flag : pd.Series, optional
        NYSE indicator, MultiIndex (date, permno). Required for NYSE breaks.
    tcosts : pd.Series, optional
        Stock-level trading costs as decimal effective half-spreads,
        MultiIndex (date, permno). Priced on the legs' trades (see
        ``run_univariate_sort``) and subtracted from the long-short when
        provided.
    factor_tcosts : pd.DataFrame, optional
        Factor-leg trading costs, indexed by date, with columns per factor
        (mkt_tc, smb_tc, hml_tc, rmw_tc, cma_tc, umd_tc, as applicable).
        Used by ``calc_gen_alpha``. Missing columns are treated as zeros
        (matches ``mkt_tc = 0`` for the market).
    factors : pd.DataFrame, optional
        Factor returns and ``rf`` (date index): the explicit factor bundle.
        When supplied, every ordinary sort, conditional sort and gen-α cell
        selects its model's columns from this frame by name and nothing is
        loaded from a database. Ordinary models 5/6 use the five-factor
        ``smb2``; gen-α uses plain ``smb`` for all model codes (MATLAB
        ``ff.mat``). The two are never substituted for each other. When
        omitted, integer models load factors from the configured library DB
        (interactive use).
    time_period : tuple, optional
        (start, end) as YYYYMM ints or Timestamps. Windows the generalized-alpha
        inputs only: MATLAB's ``makeBasicSortsResults`` passes no ``timePeriod``
        to ``runUnivSort``, so every sort (and every stat derived from it) spans
        the full sample and only ``calcGenAlpha`` sees ``pret(s:e)``.
    factor_models : tuple[int, ...]
        Factor models to evaluate. MATLAB default is (1,3,4,5,6).
    me_for_conditional : pd.Series, optional
        Series used to form ME quintiles for the conditional-on-size sort.
        Defaults to `mcap` (matches MATLAB: `indME = makeUnivSortInd(me, 5, NYSE)`).
    n_me_ptfs : int
        Number of ME quintiles for conditional sort. Default 5.
    compute_gen_alpha : bool
        If True (default), fill ``gen_alpha`` via ``calc_gen_alpha`` for each
        basic-sort cell (Novy-Marx / Velikov 2016). Set False to skip the
        combinatorial net-MVE search (faster smoke tests).
    verbose : bool
        If True, log progress per factor model / me-quintile.
    convention : str
        ``"dollar"`` (default) or ``"capital"``: the size of the two legs
        after a trade, passed to every ``run_univariate_sort`` call here.

    Returns
    -------
    BasicSortsResults
        ``metadata["capital_restarts"]`` maps a sort's label to the number of
        trades at which the strategy's capital was zero or negative
        (``"capital"`` only; only sorts where that happened are listed).

    Notes
    -----
    - Matches MATLAB ordering: the conditional sort uses *name* breakpoints
      (no NYSE flag passed to the inner makeUnivSortInd call), with NaN
      masking applied outside each ME quintile.
    - ``gen_alpha[(label, f)]['alpha_res']`` is the MATLAB
      ``resBasicSorts(j,c).gen_alpha_res`` OLS struct (beta in percent units).
    """
    me_cond = mcap if me_for_conditional is None else me_for_conditional
    convention = check_convention(convention)

    res = BasicSortsResults(
        metadata={
            "convention": convention,
            "time_period": time_period,
            "factor_models": tuple(factor_models),
            "n_me_ptfs": int(n_me_ptfs),
            "has_factor_tcosts": factor_tcosts is not None,
            "compute_gen_alpha": bool(compute_gen_alpha),
        }
    )

    if verbose:
        LOGGER.info(
            "Starting basic-sort results at %s", datetime.now().isoformat(timespec="seconds")
        )

    # Generalized-alpha outcome per (row_label, factor_model); summarized into
    # metadata["gen_alpha_diagnostics"] after the loop.
    ga_outcomes: dict[tuple[str, int], Any] = {}

    # -------- 5 sort variants x len(factor_models) factor models --------
    for f in factor_models:
        # Row 1: VW, NYSE breakpoints, 5 bins
        res.basic[("vw_nyse_5", f)] = run_univariate_sort(
            returns, test_signal, mcap,
            n_bins=5,
            breaks="nyse",
            nyse_flag=nyse_flag,
            weighting="v",
            factor_model=f,
            factors=factors,
            tcosts=tcosts,
            print_results=False,
            plot_results=False,
            convention=convention,
        )

        # Row 2: EW, NYSE breakpoints, 5 bins
        res.basic[("ew_nyse_5", f)] = run_univariate_sort(
            returns, test_signal, mcap,
            n_bins=5,
            breaks="nyse",
            nyse_flag=nyse_flag,
            weighting="e",
            factor_model=f,
            factors=factors,
            tcosts=tcosts,
            print_results=False,
            plot_results=False,
            convention=convention,
        )

        # Row 3: VW, name breakpoints, 5 bins
        res.basic[("vw_name_5", f)] = run_univariate_sort(
            returns, test_signal, mcap,
            n_bins=5,
            breaks="name",
            weighting="v",
            factor_model=f,
            factors=factors,
            tcosts=tcosts,
            print_results=False,
            plot_results=False,
            convention=convention,
        )

        # Row 4: VW, cap (portfolio-mass) breakpoints, 5 bins.
        # MATLAB: makeUnivSortInd(testSignal, 5, 'portfolioMassInd', me)
        res.basic[("vw_cap_5", f)] = run_univariate_sort(
            returns, test_signal, mcap,
            n_bins=5,
            breaks="cap",
            portfolio_mass=mcap,
            weighting="v",
            factor_model=f,
            factors=factors,
            tcosts=tcosts,
            print_results=False,
            plot_results=False,
            convention=convention,
        )

        # Row 5: VW, NYSE breakpoints, 10 bins (deciles)
        res.basic[("vw_nyse_10", f)] = run_univariate_sort(
            returns, test_signal, mcap,
            n_bins=10,
            breaks="nyse",
            nyse_flag=nyse_flag,
            weighting="v",
            factor_model=f,
            factors=factors,
            tcosts=tcosts,
            print_results=False,
            plot_results=False,
            convention=convention,
        )

        # Generalized alpha (Novy-Marx / Velikov 2016): MATLAB
        #   anomRet = pret(s:e, end); anomTcosts = tcostsTS(s:e);
        #   gen_alpha_res = calcGenAlpha(... factorRet(s:e,:), factorTcosts(s:e,:), 0)
        if compute_gen_alpha:
            from .gen_alpha import (
                GenAlphaOutcome,
                estimate_gen_alpha,
                factor_matrix_for_gen_alpha,
                factor_short_tcosts_for_gen_alpha,
            )

            for label in BASIC_SORT_LABELS:
                sr = res.basic[(label, f)]
                anom_ret = sr.long_short
                if anom_ret is None:
                    ga_outcomes[(label, f)] = GenAlphaOutcome(
                        "unavailable", reason="sort has no long-short series"
                    )
                    continue
                # Portfolio-level long+short leg costs (SortResult.tcosts_ts)
                if sr.tcosts_ts is not None:
                    anom_tc = sr.tcosts_ts.reindex(anom_ret.index).astype(float)
                else:
                    anom_tc = pd.Series(0.0, index=anom_ret.index)
                # The sorts run on the full sample (MATLAB passes no
                # 'timePeriod' to runUnivSort); only gen-alpha is windowed.
                # convention="capital": the strategy held short has its own
                # cost (None under "dollar", where it is anom_tc).
                anom_tc_short = None
                if sr.tcosts_ts_short is not None:
                    anom_tc_short = sr.tcosts_ts_short.reindex(anom_ret.index).astype(float)
                anom_ret = _slice_panel_by_time(anom_ret, time_period)
                anom_tc = _slice_panel_by_time(anom_tc, time_period)
                if anom_tc_short is not None:
                    anom_tc_short = _slice_panel_by_time(anom_tc_short, time_period)
                tc_short_df = None
                try:
                    f_df, tc_df = factor_matrix_for_gen_alpha(
                        f,
                        anom_ret.index,
                        factors=factors,
                        factor_tcosts=factor_tcosts,
                    )
                except Exception as exc:  # noqa: BLE001 -- recorded as failed
                    outcome = GenAlphaOutcome.failed(exc)
                    alpha_res, w_x_y, w_x = None, None, None
                    f_df, tc_df = None, factor_tcosts
                else:
                    tc_short_df = factor_short_tcosts_for_gen_alpha(
                        f, anom_ret.index, factor_tcosts
                    )
                    # Short-position costs are passed only when there are some.
                    short_kw = {}
                    if anom_tc_short is not None:
                        short_kw["anom_tcosts_short"] = anom_tc_short.to_numpy()
                    if tc_short_df is not None:
                        short_kw["factor_tcosts_short"] = tc_short_df.to_numpy()
                    outcome, alpha_res, w_x_y, w_x = estimate_gen_alpha(
                        anom_ret.to_numpy(),
                        anom_tc.to_numpy(),
                        f_df.to_numpy(),
                        tc_df.to_numpy(),
                        **short_kw,
                    )
                if outcome.status == "failed":
                    LOGGER.warning(
                        "calc_gen_alpha failed for %s model %s: %s",
                        label, f, outcome.reason,
                    )
                ga_outcomes[(label, f)] = outcome
                res.gen_alpha[(label, f)] = {
                    "outcome": outcome.to_dict(),
                    "anom_ret": anom_ret,
                    "anom_tcosts": anom_tc,
                    "factor_rets": f_df,
                    "factor_tcosts": tc_df,
                    # None unless the run prices short positions separately
                    # (convention="capital").
                    "anom_tcosts_short": anom_tc_short,
                    "factor_tcosts_short": tc_short_df,
                    "alpha_res": alpha_res,
                    "w_x_y": w_x_y,
                    "w_x": w_x,
                }

        if verbose:
            LOGGER.info(
                "Done with univariate sort controlling for %d-factor model @ %s",
                f,
                datetime.now().isoformat(timespec="seconds"),
            )

    # -------- Conditional-on-size sorts: 5 ME quintiles x factor_models --------
    # MATLAB: indME = makeUnivSortInd(me, nMePtfs, NYSE); then loop:
    #   tempSignal(indME ~= i) = nan;  ind = makeUnivSortInd(tempSignal, 5);
    # i.e. *name* breaks inside each ME quintile (no NYSE flag on inner sort).
    me_quintile_sort = run_univariate_sort(
        returns, me_cond, mcap,
        n_bins=n_me_ptfs,
        breaks="nyse" if nyse_flag is not None else "name",
        nyse_flag=nyse_flag,
        weighting="v",
        factor_model=None,
        add_long_short=False,
        print_results=False,
        plot_results=False,
        convention=convention,
    )
    # Rebuild per-stock ME bin assignments: mirror MATLAB `makeUnivSortInd(me,5,NYSE)`.
    # `run_univariate_sort` lags the signal internally by 1 month, but MATLAB's
    # `makeUnivSortInd` does not lag. Recompute the per-(date, permno) bin on
    # the raw me signal using the same helpers.
    from .sorts import _bin_by_cross_section  # local import to avoid cycle

    me_bins = _bin_by_cross_section(
        me_cond,
        n_me_ptfs,
        breaks="nyse" if nyse_flag is not None else "name",
        nyse_flag=nyse_flag,
        mcap=me_cond,
    )
    # `me_quintile_sort` is captured only to keep a reference to the ME
    # quintile boundaries for downstream reporting; not used directly.
    del me_quintile_sort

    for i in range(1, n_me_ptfs + 1):
        # Mask the test signal outside ME quintile i, matching
        # `tempSignal(indME ~= i) = nan` in MATLAB.
        mask = me_bins.eq(i)
        masked_signal = test_signal.where(mask.reindex(test_signal.index).fillna(False))

        res.conditional.update(
            {
                (i, f): sr
                for f, sr in reweighted_sort(
                    returns, masked_signal, mcap,
                    factor_models=factor_models,
                    factors=factors,
                ).items()
            }
        )
        if verbose:
            LOGGER.info(
                "Done with conditional-on-size sort for ME quintile %d @ %s",
                i,
                datetime.now().isoformat(timespec="seconds"),
            )

    restarts: dict[str, int] = {}
    for (label, _f), sr in res.basic.items():
        n_restarts = int((sr.metadata or {}).get("capital_restarts", 0) or 0)
        if n_restarts and label not in restarts:
            restarts[label] = n_restarts
            LOGGER.warning(
                "basic sort %s: the strategy's capital was zero or negative at %d "
                "trade(s); it restarted there with $1 in each leg",
                label, n_restarts,
            )
    res.metadata["capital_restarts"] = restarts
    # The cost of each sort's first purchase (decimal), which is not in its
    # cost series; one entry per label (the factor model does not change it).
    res.metadata["entry_cost"] = {
        label: float(sr.entry_cost)
        for (label, _f), sr in res.basic.items()
        if sr.entry_cost is not None
    }

    if compute_gen_alpha:
        from .gen_alpha import summarize_gen_alpha_outcomes

        res.metadata["gen_alpha_diagnostics"] = summarize_gen_alpha_outcomes(ga_outcomes)

    if verbose:
        LOGGER.info(
            "Done with basic-sort results at %s", datetime.now().isoformat(timespec="seconds")
        )
    return res


# ---------------------------------------------------------------------------
# makeAnomBenchmarkResults.m port
# ---------------------------------------------------------------------------
# Deterministic noise seed for the "add small jitter" step that MATLAB uses
# to break ties in the conditional bivariate sort. MATLAB uses `randn(...)*1e-12`
# with the default (non-seeded) RNG; for reproducibility we fix a seed here.
_ANOM_NOISE_SEED: int = 20231201
_ANOM_NOISE_SCALE: float = 1e-12


def _sort_anoms_by_stock_month(
    anoms: pd.DataFrame | dict[str, pd.Series] | np.ndarray,
) -> pd.DataFrame | dict[str, pd.Series] | np.ndarray:
    """Sort the zoo by its ``(date, permno)`` index so the jitter is keyed to the row.

    The tie-breaking draw is attached by position, so without this a stock-month's
    noise would depend on the physical row order of the input -- for the protocol,
    DuckDB's scan order of ``cz_anomalies``. Already-sorted input is
    returned as is, without a copy. The 3-D ndarray form needs nothing:
    :func:`_coerce_anoms_to_dict` builds it on a sorted product index.
    """
    if isinstance(anoms, pd.DataFrame):
        return anoms if anoms.index.is_monotonic_increasing else anoms.sort_index()
    if isinstance(anoms, dict):
        return {
            k: v if v.index.is_monotonic_increasing else v.sort_index()
            for k, v in anoms.items()
        }
    return anoms


def _anom_jitters(
    anoms_dict: dict[str, pd.Series], noise_seed: int | None
) -> dict[str, np.ndarray | None]:
    """Tie-breaking noise, one independent stream per anomaly.

    Each anomaly draws from the stream of its **name**
    (:func:`assayinganomalies.tiebreak.anomaly_noise_rng`), so its noise depends
    neither on the other anomalies passed in nor on its place among them: an
    anomaly has the same strategy in every zoo. The draw is attached to the
    ``(date, permno)``-sorted index, so a stock-month keeps its draw whatever the
    input row order and however many months follow it. ``noise_seed=None`` means
    no jitter.
    """
    if noise_seed is None:
        return {name: None for name in anoms_dict}
    return {
        name: anomaly_noise_rng(noise_seed, name).standard_normal(len(anom))
        * _ANOM_NOISE_SCALE
        for name, anom in anoms_dict.items()
    }


@dataclass
class AnomBenchmarkResults:
    """Container mirroring MATLAB's [resCorrels, resCondSort, resFMBs] tuple.

    Attributes
    ----------
    correls : pd.DataFrame
        Rows = anomaly names, columns = ``{"spearman", "pearson"}``. Matches
        MATLAB `resCorrels` (nAnoms x 2, order is [rhoS, rhoP]).
    cond_sort : dict[str, SortResult]
        Keyed by anomaly name. Each `SortResult` is a 2-leg VW sort: leg 1 =
        stocks in the lowest testSignal quintile conditional on each anomaly
        quintile, leg 2 = highest testSignal quintile. Long-short = leg 2 - 1.
    fmbs : dict[str, RegressionResult]
        Keyed by anomaly name. Bivariate Fama-MacBeth of 100*ret on
        [testSignal, anom_i] with a constant.
    metadata : dict
        Orchestration context (time_period, anomaly names, noise seed).
    """

    correls: pd.DataFrame = field(default_factory=pd.DataFrame)
    cond_sort: dict[str, SortResult] = field(default_factory=dict)
    fmbs: dict[str, RegressionResult] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


def _panel_correls(var1: pd.Series, var2: pd.Series) -> tuple[float, float]:
    """Pearson + Spearman panel correlations (MATLAB `calcPanelCorrels.m`).

    Flattens the two panels, drops NaNs pairwise, and returns
    ``(rho_spearman, rho_pearson)`` to match MATLAB's output tuple order.

    Each coefficient uses every observation it can. MATLAB drops NaN rows and
    keeps ``±Inf``, which the rank correlation handles exactly -- an infinite
    signal value is simply the extreme rank, the same way `prctile` treats it
    when placing sort breakpoints. Pearson cannot use those cells at all
    (``Inf - mean`` is undefined), and a single one turns the whole coefficient
    into NaN, so it is computed on the finite subsample instead. 21 of the 212
    CZ zoo signals carry ``±Inf`` from divide-by-zero cells in their
    construction; leaving Pearson NaN for them made it useless as a ranking key.
    """
    df = pd.concat({"v1": var1, "v2": var2}, axis=1, join="inner").dropna()
    if df.empty or df["v1"].nunique() < 2 or df["v2"].nunique() < 2:
        return (np.nan, np.nan)
    v1 = df["v1"].astype(float)
    v2 = df["v2"].astype(float)

    rho_s = v1.corr(v2, method="spearman")

    finite = np.isfinite(v1) & np.isfinite(v2)
    v1f, v2f = v1[finite], v2[finite]
    if len(v1f) < 2 or v1f.nunique() < 2 or v2f.nunique() < 2:
        rho_p = np.nan
    else:
        rho_p = v1f.corr(v2f, method="pearson")

    return (float(rho_s), float(rho_p))


def _slice_panel_by_time(
    s: pd.Series | pd.DataFrame,
    time_period: tuple[pd.Timestamp | int, pd.Timestamp | int] | None,
) -> pd.Series | pd.DataFrame:
    """Subset a (date, permno)-indexed panel to ``[start, end]``.

    ``time_period`` supports YYYYMM ints (MATLAB convention) or Timestamps.
    """
    if time_period is None:
        return s
    start, end = time_period
    if isinstance(start, int):
        start = pd.Timestamp(year=start // 100, month=start % 100, day=1) + pd.offsets.MonthEnd(0)
    if isinstance(end, int):
        end = pd.Timestamp(year=end // 100, month=end % 100, day=1) + pd.offsets.MonthEnd(0)
    dates = s.index.get_level_values(0)
    mask = (dates >= start) & (dates <= end)
    return s[mask]


def _coerce_anoms_to_dict(
    anoms: pd.DataFrame | dict[str, pd.Series] | np.ndarray,
    *,
    signal_index: pd.MultiIndex,
    labels: list[str] | None,
) -> dict[str, pd.Series]:
    """Normalize the anomaly-signals input into ``{name: Series(date, permno)}``.

    Accepted forms:
      - DataFrame indexed by (date, permno), one column per anomaly.
      - dict[name -> Series], each Series indexed by (date, permno).
      - 3-D numpy array (nMonths x nStocks x nAnoms) -- mirrors MATLAB shape.
        Requires ``signal_index`` (used to recover date/permno labels) and
        ``labels``.
    """
    if isinstance(anoms, pd.DataFrame):
        return {str(c): anoms[c] for c in anoms.columns}
    if isinstance(anoms, dict):
        return {str(k): v for k, v in anoms.items()}
    if isinstance(anoms, np.ndarray):
        if anoms.ndim != 3:
            raise ValueError("anoms ndarray must be 3-D (nMonths, nStocks, nAnoms)")
        if labels is None or len(labels) != anoms.shape[2]:
            raise ValueError("must supply `anom_labels` matching 3-D anoms panel depth")
        # Reshape each anomaly slice into a Series aligned with `signal_index`.
        # Assume signal_index is sorted rectangularly as (date, permno).
        # This path is primarily for MATLAB-bridge callers; production code
        # should prefer the DataFrame form.
        # Rebuild panel by stacking the 2-D (nMonths x nStocks) slice into
        # a 1-D Series over the flattened index.
        dates = signal_index.get_level_values(0).unique().sort_values()
        permnos = signal_index.get_level_values(1).unique().sort_values()
        if (len(dates), len(permnos)) != anoms.shape[:2]:
            raise ValueError(
                "anoms panel shape %s does not match testSignal (%d dates, %d permnos)"
                % (anoms.shape[:2], len(dates), len(permnos))
            )
        full_idx = pd.MultiIndex.from_product([dates, permnos], names=["date", "permno"])
        out: dict[str, pd.Series] = {}
        for k, lab in enumerate(labels):
            arr = anoms[:, :, k].reshape(-1)
            out[str(lab)] = pd.Series(arr, index=full_idx)
        return out
    raise TypeError("anoms must be DataFrame, dict[str, Series], or 3-D ndarray")


# ---------------------------------------------------------------------------
# Per-anomaly process-pool helpers
# ---------------------------------------------------------------------------
# Shared read-only state for worker processes. The parent writes numeric
# panels once (memmap when large) so spawn-based platforms do not pickle a
# multi-GB copy of the zoo into every worker.
_POOL_SHARED: dict[str, Any] = {}
_MEMMAP_BYTES_THRESHOLD: int = 32 * 1024 * 1024


def _align_dates_index(index: pd.Index) -> pd.Index:
    """Unique month-end dates of a (date, permno) panel, for factor alignment."""
    if isinstance(index, pd.MultiIndex):
        return pd.Index(index.get_level_values(0).unique()).sort_values()
    return pd.Index(index.unique()).sort_values()


def _prepare_factor_frame(
    factor_model: int | pd.DataFrame,
    align_index: pd.Index,
    factors: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Resolve a factor-model code or frame once, aligned to ``align_index``.

    When ``factors`` is supplied it is used as the store (no DuckDB hit) but
    still subset to the columns of ``factor_model`` so passing the full FF
    panel does not silently turn a CAPM sort into a six-factor regression.
    The frame is resolved on the parent, so pool workers receive it rather
    than reloading factors themselves.
    """
    from .sorts import _resolve_factor_model

    if not isinstance(factor_model, pd.DataFrame):
        factor_model = int(factor_model)
    return _resolve_factor_model(align_index, factor_model, factors=factors)


def _series_from_values(values: np.ndarray, index: pd.Index, name: str) -> pd.Series:
    return pd.Series(np.asarray(values, dtype=np.float64), index=index, name=name)


def _maybe_memmap_array(tmpdir: str | None, name: str, arr: np.ndarray) -> Any:
    """Inline ndarray, or a ``('memmap', path, shape, dtype)`` descriptor."""
    arr = np.ascontiguousarray(arr)
    if tmpdir is None or arr.nbytes < _MEMMAP_BYTES_THRESHOLD:
        return arr
    path = os.path.join(tmpdir, f"{name}.npy")
    np.save(path, arr)
    return ("memmap", path, arr.shape, arr.dtype.str)


def _load_packed_array(packed: Any) -> np.ndarray:
    if isinstance(packed, tuple) and packed and packed[0] == "memmap":
        _, path, shape, dtype = packed
        return np.load(path, mmap_mode="r")
    return packed


def _unpack_index(payload: dict[str, Any]) -> pd.MultiIndex:
    dates = pd.to_datetime(_load_packed_array(payload["dates"]))
    permnos = _load_packed_array(payload["permnos"])
    return pd.MultiIndex.from_arrays([dates, permnos], names=["date", "permno"])


def _pack_series(s: pd.Series | None, tmpdir: str | None, name: str) -> dict[str, Any] | None:
    if s is None:
        return None
    idx = s.index
    if not isinstance(idx, pd.MultiIndex):
        raise TypeError(f"{name} must be MultiIndex (date, permno)")
    return {
        "index": _pack_shared_index(idx, tmpdir, prefix=name),
        "values": _maybe_memmap_array(
            tmpdir, name, pd.to_numeric(s, errors="coerce").to_numpy(dtype=np.float64)
        ),
        "name": s.name,
    }


def _unpack_series(payload: dict[str, Any] | None) -> pd.Series | None:
    if payload is None:
        return None
    return pd.Series(
        _load_packed_array(payload["values"]),
        index=_unpack_index(payload["index"]),
        name=payload.get("name"),
    )


def spawn_context():
    """
    The ``spawn`` multiprocessing context, used for every process pool here.

    Windows has no ``fork`` and macOS' ``fork`` is unsafe once Accelerate or any
    other threaded BLAS has been touched, so pinning ``spawn`` everywhere makes
    Linux behave the same as the other two instead of being the odd one out.
    Workers therefore inherit nothing: every pool must ship its state through a
    picklable ``initializer``/``initargs`` pair (see :func:`_init_pool_worker`),
    and every worker callable must be importable at module top level.
    """
    return get_context("spawn")


def _init_pool_worker(shared: dict[str, Any]) -> None:
    global _POOL_SHARED
    loaded: dict[str, Any] = {
        "factor_df": shared["factor_df"],
        "factor_model": shared["factor_model"],
        "outer_breaks": shared.get("outer_breaks", "name"),
        "anom_index": _unpack_index(shared["anom_index"]),
        "anom_mat": _load_packed_array(shared["anom_mat"]),
        "jitter_mat": (
            None if shared.get("jitter_mat") is None else _load_packed_array(shared["jitter_mat"])
        ),
        "ts": _unpack_series(shared.get("ts")),
        "ret": _unpack_series(shared.get("ret")),
        "ret100": _unpack_series(shared.get("ret100")),
        "mcap": _unpack_series(shared.get("mcap")),
        "nyse": _unpack_series(shared.get("nyse")),
        "tc": _unpack_series(shared.get("tc")),
        "convention": shared.get("convention", "dollar"),
    }
    _POOL_SHARED = loaded


def _empty_cond_sort(name: str) -> SortResult:
    return SortResult(
        leg_returns=pd.DataFrame(),
        long_short=None,
        metadata={"anom": name},
    )


def _cond_sort_ind(bins_anom: pd.Series, bins_ts: pd.Series) -> pd.Series:
    """Collapse the 5x5 conditional sort to 2 legs on ``bins_ts``'s index.

    Leg 1 = test-signal quintile 1, leg 2 = quintile 5, among rows with a
    finite anomaly bin; every other row is 0. ``bins_anom`` may sit on a
    different index than ``bins_ts``: it is reindexed explicitly (a row
    missing from it has no anomaly bin), and a missing test-signal bin is
    never a leg.
    """
    anom_ok = bins_anom.notna().reindex(bins_ts.index, fill_value=False)
    is_lo = (bins_ts == 1).fillna(False).astype(bool)
    is_hi = (bins_ts == 5).fillna(False).astype(bool)
    ind = pd.Series(0, index=bins_ts.index, dtype="Int64")
    ind = ind.mask(anom_ok & is_lo, 1)
    ind = ind.mask(anom_ok & is_hi, 2)
    return ind


def _run_one_benchmark(
    name: str,
    anom_sliced: pd.Series,
    *,
    ts_sliced: pd.Series,
    ret_sliced: pd.Series,
    ret100: pd.Series,
    mcap_sliced: pd.Series,
    nyse_sliced: pd.Series | None,
    jitter: np.ndarray | None,
    factor_df: pd.DataFrame,
    factor_model: int,
    outer_breaks: str,
) -> tuple[float, float, SortResult, RegressionResult]:
    """Correlations + collapsed 5x5 sort + bivariate FMB for one anomaly.

    Inputs are already time-sliced. ``factor_df`` is the resolved factor
    frame (loaded once on the parent, not from DuckDB per anomaly).
    """
    from .sorts import (
        _bin_by_cross_section,
        _conditional_bin_by_cross_section,
        _matlab_style_sort_outputs,
        _resolve_factor_model,
        _run_factor_regs,
        calc_ptf_rets,
    )

    rho_s, rho_p = _panel_correls(anom_sliced, ts_sliced)

    if jitter is not None:
        anom_signal = anom_sliced + pd.Series(
            np.asarray(jitter, dtype=np.float64), index=anom_sliced.index
        )
    else:
        anom_signal = anom_sliced

    bins_anom = _bin_by_cross_section(
        anom_signal,
        5,
        breaks=outer_breaks,
        nyse_flag=nyse_sliced,
        mcap=mcap_sliced,
    )
    bins_ts = _conditional_bin_by_cross_section(
        ts_sliced,
        bins_anom,
        n_bins2=5,
        breaks="name",
        nyse_flag=None,
        mcap=mcap_sliced,
    )
    ind = _cond_sort_ind(bins_anom, bins_ts)

    # ``ret`` / ``mcap`` are already aligned; do not rebuild a concat panel
    # per anomaly. ``calc_ptf_rets`` still concatenates internally.
    ind_aligned = ind.reindex(ret_sliced.index).fillna(0)

    if int(pd.to_numeric(ind_aligned, errors="coerce").max() or 0) <= 0:
        LOGGER.warning("No data for conditional sort on anomaly %s; skipping.", name)
        cond_sort = _empty_cond_sort(name)
    else:
        leg_ts, ptf_counts, ptf_mcap = calc_ptf_rets(
            ret_sliced, ind_aligned, mcap_sliced, holding_period=1, weighting="v"
        )
        long_short = None
        alphas = tstats = loadings = loading_tstats = r2 = None
        xret = txret = alpha = talpha = sharpe = info = resid = r2_adj = None
        if leg_ts.shape[1] >= 2:
            long_short = leg_ts[2] - leg_ts[1]
            aligned_factors = _resolve_factor_model(long_short.index, factor_df)
            alphas, tstats, loadings, loading_tstats, r2 = _run_factor_regs(
                leg_ts, long_short, aligned_factors, robust=False
            )
            pret_for_stats = leg_ts.copy()
            pret_for_stats["long_short"] = long_short
            stats = _matlab_style_sort_outputs(
                pret_for_stats,
                factors=aligned_factors,
                robust_se=False,
                input_is_excess=False,
            )
            xret = stats["xret"]
            txret = stats["txret"]
            alpha = stats["alpha"]
            talpha = stats["talpha"]
            sharpe = stats["sharpe"]
            info = stats["info"]
            resid = stats["resid"]
            r2_adj = stats["r2_adj"]

        cond_sort = SortResult(
            leg_returns=leg_ts,
            long_short=long_short,
            metadata={
                "anom": name,
                "n_bins": 2,
                "breaks": outer_breaks,
                "weighting": "v",
                "holding_period": 1,
                "factor_model": factor_model,
                "collapse": "5x5->2leg (hedged testSignal L-S)",
            },
            xret=xret,
            txret=txret,
            alpha=alpha,
            talpha=talpha,
            sharpe=sharpe,
            info=info,
            resid=resid,
            alphas=alphas,
            tstats=tstats,
            factor_loadings=loadings,
            factor_loading_tstats=loading_tstats,
            r2=r2,
            r2_adj=r2_adj,
            ptf_num_stocks=ptf_counts,
            ptf_market_cap=ptf_mcap,
        )

    rhs = pd.concat({"test_signal": ts_sliced, name: anom_sliced}, axis=1)
    fmb = run_fama_macbeth(
        ret100,
        rhs,
        time_period=None,
        print_results=False,
        labels=["Const", "test_signal", name],
    )
    return float(rho_s), float(rho_p), cond_sort, fmb


def _bench_pool_task(item: tuple[str, int]) -> tuple[str, float, float, SortResult, RegressionResult]:
    """Worker entry: ``(name, column_index)`` against :data:`_POOL_SHARED`."""
    name, col = item
    shared = _POOL_SHARED
    anom = _series_from_values(shared["anom_mat"][:, col], shared["anom_index"], name)
    jitter_mat = shared.get("jitter_mat")
    jitter = None if jitter_mat is None else np.asarray(jitter_mat[:, col])
    rho_s, rho_p, sr, fmb = _run_one_benchmark(
        name,
        anom,
        ts_sliced=shared["ts"],
        ret_sliced=shared["ret"],
        ret100=shared["ret100"],
        mcap_sliced=shared["mcap"],
        nyse_sliced=shared.get("nyse"),
        jitter=jitter,
        factor_df=shared["factor_df"],
        factor_model=shared["factor_model"],
        outer_breaks=shared["outer_breaks"],
    )
    return name, rho_s, rho_p, sr, fmb


def _run_one_strat(
    name: str,
    anom: pd.Series,
    *,
    ret_sliced: pd.Series,
    mcap_sliced: pd.Series,
    nyse_sliced: pd.Series | None,
    tc_sliced: pd.Series | None,
    jitter: np.ndarray | None,
    factor_df: pd.DataFrame,
    factor_model: int,
    convention: str = "dollar",
) -> SortResult:
    """One zoo-strategy quintile VW sort (extreme legs only).

    The two legs are bought in the months the anomaly has values and held in
    between (``calc_held_ptfs``); ``convention`` is their size after a trade.
    """
    from .sorts import (
        _bin_by_cross_section,
        calc_held_ptfs,
        _matlab_style_sort_outputs,
        _resolve_factor_model,
        _run_factor_regs,
    )

    if jitter is not None:
        anom_signal = anom + pd.Series(
            np.asarray(jitter, dtype=np.float64), index=anom.index
        )
    else:
        anom_signal = anom

    bins = _bin_by_cross_section(
        anom_signal,
        5,
        breaks="nyse" if nyse_sliced is not None else "name",
        nyse_flag=nyse_sliced,
        mcap=mcap_sliced,
    )
    ind = pd.Series(0, index=bins.index, dtype="Int64")
    ind = ind.mask((bins == 1).fillna(False), 1)
    ind = ind.mask((bins == 5).fillna(False), 2)
    ind_aligned = ind.reindex(ret_sliced.index).fillna(0)

    if int(pd.to_numeric(ind_aligned, errors="coerce").max() or 0) <= 0:
        LOGGER.warning("No data for anomaly strategy %s; skipping.", name)
        return SortResult(
            leg_returns=pd.DataFrame(),
            long_short=None,
            metadata={"anom": name},
        )

    held = calc_held_ptfs(
        ret_sliced, ind_aligned, mcap_sliced, tc_sliced,
        weighting="v", convention=convention, label=name,
    )
    leg_ts, ptf_counts, ptf_mcap = held.leg_returns, held.num_stocks, held.market_cap
    long_short = None
    if leg_ts.shape[1] >= 2 and 1 in leg_ts.columns and 2 in leg_ts.columns:
        long_short = leg_ts[2] - leg_ts[1]

    long_short_net = None
    tcosts_ts = None
    netpret = None
    netxret = tnetxret = tcosts_avg = None
    capital_restarts = 0
    if long_short is not None and held.costs is not None:
        from .ols import nanols

        tcosts_ts = held.costs["cost"].rename(None)
        netpret = long_short - tcosts_ts
        long_short_net = netpret
        nr = nanols(100.0 * netpret.to_numpy(dtype=float), np.ones(len(netpret)))
        netxret = float(nr.beta[0])
        tnetxret = float(nr.tstat[0])
        # Average over the months the strategy has a return, as in
        # run_univariate_sort.
        live = long_short.notna().to_numpy()
        tcosts_avg = (
            float(tcosts_ts.to_numpy()[live].mean()) if live.any() else float("nan")
        )
        capital_restarts = held.restarts

    alphas = tstats = loadings = loading_tstats = r2 = None
    xret = txret = alpha = talpha = sharpe = info = resid = r2_adj = None
    if long_short is not None and factor_model is not None:
        aligned_factors = _resolve_factor_model(long_short.index, factor_df)
        alphas, tstats, loadings, loading_tstats, r2 = _run_factor_regs(
            leg_ts, long_short, aligned_factors, robust=False
        )
        pret_for_stats = leg_ts.copy()
        pret_for_stats["long_short"] = long_short
        stats = _matlab_style_sort_outputs(
            pret_for_stats,
            factors=aligned_factors,
            robust_se=False,
            input_is_excess=False,
        )
        xret = stats["xret"]
        txret = stats["txret"]
        alpha = stats["alpha"]
        talpha = stats["talpha"]
        sharpe = stats["sharpe"]
        info = stats["info"]
        resid = stats["resid"]
        r2_adj = stats["r2_adj"]

    return SortResult(
        leg_returns=leg_ts,
        long_short=long_short,
        long_short_net=long_short_net,
        metadata={
            "anom": name,
            "n_bins": 2,
            "breaks": "nyse" if nyse_sliced is not None else "name",
            "weighting": "v",
            "factor_model": factor_model,
            "convention": convention,
            "capital_restarts": capital_restarts,
        },
        alphas=alphas,
        tstats=tstats,
        factor_loadings=loadings,
        factor_loading_tstats=loading_tstats,
        r2=r2,
        xret=xret,
        txret=txret,
        alpha=alpha,
        talpha=talpha,
        sharpe=sharpe,
        info=info,
        resid=resid,
        r2_adj=r2_adj,
        ptf_num_stocks=ptf_counts,
        ptf_market_cap=ptf_mcap,
        tcosts_ts=tcosts_ts,
        netpret=netpret,
        netxret=netxret,
        tnetxret=tnetxret,
        tcosts=tcosts_avg,
        entry_cost=held.entry_cost,
        ptf_entry_costs=held.entry_costs,
        tcosts_ts_short=(
            held.costs["cost_exchanged"].rename(None)
            if convention == "capital" and held.costs is not None and long_short is not None
            else None
        ),
    )


def _strat_pool_task(item: tuple[str, int]) -> tuple[str, SortResult]:
    name, col = item
    shared = _POOL_SHARED
    anom = _series_from_values(shared["anom_mat"][:, col], shared["anom_index"], name)
    jitter_mat = shared.get("jitter_mat")
    jitter = None if jitter_mat is None else np.asarray(jitter_mat[:, col])
    sr = _run_one_strat(
        name,
        anom,
        ret_sliced=shared["ret"],
        mcap_sliced=shared["mcap"],
        nyse_sliced=shared.get("nyse"),
        tc_sliced=shared.get("tc"),
        jitter=jitter,
        factor_df=shared["factor_df"],
        factor_model=shared["factor_model"],
        convention=shared.get("convention", "dollar"),
    )
    return name, sr


def _pack_shared_index(
    index: pd.MultiIndex, tmpdir: str | None, prefix: str = "idx"
) -> dict[str, Any]:
    dates = index.get_level_values(0).to_numpy(dtype="datetime64[ns]")
    permnos = index.get_level_values(1).to_numpy()
    return {
        "dates": _maybe_memmap_array(tmpdir, f"{prefix}_dates", dates.view("int64")),
        "permnos": _maybe_memmap_array(tmpdir, f"{prefix}_permnos", np.asarray(permnos)),
    }


def _stack_aligned(
    anoms_dict: dict[str, pd.Series],
) -> tuple[pd.Index, np.ndarray] | None:
    """``(index, n x k float64)`` if every series shares one index, else None."""
    if not anoms_dict:
        return None
    names = list(anoms_dict.keys())
    first = anoms_dict[names[0]]
    idx = first.index
    if not all(anoms_dict[n].index.equals(idx) for n in names[1:]):
        return None
    mat = np.column_stack(
        [
            pd.to_numeric(anoms_dict[n], errors="coerce").to_numpy(dtype=np.float64)
            for n in names
        ]
    )
    return idx, mat


def _map_anomalies(
    names: list[str],
    worker,
    shared: dict[str, Any],
    n_jobs: int,
    *,
    verbose: bool,
    label: str,
) -> list[Any]:
    """Run ``worker((name, col))`` serially or in a process pool; preserve order.

    The pool size is re-checked against the memory budget here, once the
    caller has packed its inputs (see :func:`~assayinganomalies.config.pool_worker_count`).
    """
    n_anoms = len(names)
    tasks = [(name, i) for i, name in enumerate(names)]
    n_jobs = pool_worker_count(n_jobs, what=label)
    # Popped before either branch: the cap can turn a planned pool serial, and
    # the memmapped inputs must be removed then too.
    tmpdir = shared.pop("_tmpdir", None)
    if n_jobs <= 1 or n_anoms <= 1:
        _init_pool_worker(shared)
        try:
            out = []
            for i, task in enumerate(tasks, start=1):
                out.append(worker(task))
                if verbose and i % 10 == 0:
                    LOGGER.info(
                        "Done with %d/%d anomalies @ %s.",
                        i,
                        n_anoms,
                        datetime.now().isoformat(timespec="seconds"),
                    )
            return out
        finally:
            _POOL_SHARED.clear()
            if tmpdir is not None:
                import shutil

                shutil.rmtree(tmpdir, ignore_errors=True)

    results_by_name: dict[str, Any] = {}
    try:
        with ProcessPoolExecutor(
            max_workers=min(n_jobs, n_anoms),
            mp_context=spawn_context(),
            initializer=_init_pool_worker,
            initargs=(shared,),
        ) as pool:
            futures = {pool.submit(worker, task): task[0] for task in tasks}
            done = 0
            for fut in as_completed(futures):
                payload = fut.result()
                results_by_name[payload[0]] = payload
                done += 1
                if verbose and done % 10 == 0:
                    LOGGER.info(
                        "Done with %d/%d anomalies (%s) @ %s.",
                        done,
                        n_anoms,
                        label,
                        datetime.now().isoformat(timespec="seconds"),
                    )
    finally:
        if tmpdir is not None:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)
    return [results_by_name[n] for n in names]


def make_anom_benchmark_results(
    anoms: pd.DataFrame | dict[str, pd.Series] | np.ndarray,
    test_signal: pd.Series,
    returns: pd.Series,
    mcap: pd.Series,
    *,
    nyse_flag: pd.Series | None = None,
    time_period: tuple[pd.Timestamp | int, pd.Timestamp | int] | None = None,
    anom_labels: list[str] | None = None,
    factor_model: int = 1,
    noise_seed: int | None = _ANOM_NOISE_SEED,
    verbose: bool = True,
    n_jobs: int | None = 1,
    factors: pd.DataFrame | None = None,
) -> AnomBenchmarkResults:
    """
    Benchmark a test signal against a set of anomaly signals.

    MATLAB equivalent: ``makeAnomBenchmarkResults.m`` (Novy-Marx / Velikov 2026).

    For each anomaly ``i`` in ``anoms``, compute:

      1. Pearson + Spearman panel correlations with ``test_signal``.
      2. A 5x5 **conditional** double sort (anom on the outside, testSignal on
         the inside), collapsed into a 2-leg portfolio:
           - leg 1 = stocks in lowest testSignal-within-anom-quintile
           - leg 2 = stocks in highest testSignal-within-anom-quintile
         The long-short of this sort isolates the testSignal effect after
         hedging out the anomaly.
      3. Fama-MacBeth cross-sectional regression of ``100*returns`` on
         ``[testSignal, anom_i]`` (plus a constant).

    Parameters
    ----------
    anoms : DataFrame or dict or 3-D ndarray
        Benchmark anomaly signals. DataFrame: (date, permno) index, one
        column per anomaly. dict: ``{name: Series}`` each with (date, permno).
        ndarray: MATLAB-style 3-D (nMonths x nStocks x nAnoms); requires
        ``anom_labels`` and is interpreted relative to ``test_signal``'s panel.
    test_signal : pd.Series
        Candidate anomaly signal, MultiIndex (date, permno).
    returns : pd.Series
        Stock returns (decimals), MultiIndex (date, permno).
    mcap : pd.Series
        Market cap, MultiIndex (date, permno). Used for VW portfolio returns.
    nyse_flag : pd.Series, optional
        NYSE indicator, MultiIndex (date, permno). If provided, used for the
        NYSE breakpoint filter in the outer anom sort (matches MATLAB default
        behavior for anomaly benchmarking).
    time_period : tuple, optional
        ``(start, end)`` as YYYYMM ints or Timestamps. Applied to all inputs.
    anom_labels : list[str], optional
        Required when ``anoms`` is a 3-D ndarray; ignored otherwise.
    factor_model : int
        Factor model to use for the 2-leg conditional sort. MATLAB default
        is CAPM (``factorModel=1``).
    noise_seed : int or None
        Seed for the tie-breaking jitter added to each anomaly signal. Set
        to ``None`` to skip the jitter step entirely. MATLAB adds
        ``randn(...)*1e-12``; we fix a seed for reproducibility.
    verbose : bool
        If True, log progress every 10 anomalies.
    n_jobs : int, optional
        Process-pool size. ``1`` (the library default) runs serially.
        ``None`` is treated as 1 here; :func:`run_test_signal` resolves the
        config default (cores-1) before calling. Jitter is generated on the
        parent, one stream per anomaly, so worker count does not move numbers.
    factors : DataFrame, optional
        Pre-loaded factor returns. When omitted, the factor-model code is
        resolved from DuckDB **once** (not once per anomaly).

    Returns
    -------
    AnomBenchmarkResults

    Notes
    -----
    - The collapsed 2-leg sort is constructed by remapping a 5x5 conditional
      sort (MATLAB indices 1..25, row-major: ``ind = (bin1-1)*5 + bin2``).
      Leg 1 = ``ind in {1, 6, 11, 16, 21}`` (bin2==1), leg 2 = ``ind in
      {5, 10, 15, 20, 25}`` (bin2==5). All other portfolios are excluded.
    - The Fama-MacBeth regression scales returns by 100 so coefficients are
      interpretable as % per month (matching MATLAB).
    """
    n_workers = 1 if n_jobs is None else max(1, int(n_jobs))
    anoms = _sort_anoms_by_stock_month(anoms)

    # Slice a DataFrame of anomalies once rather than column-by-column.
    if isinstance(anoms, pd.DataFrame):
        anoms_sliced = _slice_panel_by_time(anoms, time_period)
        anoms_dict = {str(c): anoms_sliced[c] for c in anoms_sliced.columns}
    else:
        raw = _coerce_anoms_to_dict(
            anoms, signal_index=test_signal.index, labels=anom_labels
        )
        anoms_dict = {
            name: _slice_panel_by_time(s, time_period) for name, s in raw.items()
        }
    n_anoms = len(anoms_dict)
    names = list(anoms_dict.keys())

    if verbose:
        LOGGER.info(
            "Now working on getting the related anomalies results. Run started at %s.",
            datetime.now().isoformat(timespec="seconds"),
        )

    ts_sliced = _slice_panel_by_time(test_signal, time_period)
    ret_sliced = _slice_panel_by_time(returns, time_period)
    mcap_sliced = _slice_panel_by_time(mcap, time_period)
    nyse_sliced = (
        _slice_panel_by_time(nyse_flag, time_period) if nyse_flag is not None else None
    )
    ret100 = 100.0 * ret_sliced
    outer_breaks = "nyse" if nyse_sliced is not None else "name"
    factor_df = _prepare_factor_frame(
        factor_model, _align_dates_index(ret_sliced.index), factors
    )

    jitters = _anom_jitters(anoms_dict, noise_seed)

    stacked = _stack_aligned(anoms_dict)
    correls = pd.DataFrame(
        index=names, columns=["spearman", "pearson"], dtype="float64"
    )
    cond_sort: dict[str, SortResult] = {}
    fmbs: dict[str, RegressionResult] = {}

    use_pool = n_workers > 1 and n_anoms > 1 and stacked is not None
    if use_pool:
        common_index, anom_mat = stacked
        jitter_mat = None
        if noise_seed is not None:
            jitter_mat = np.column_stack([jitters[n] for n in names])
        tmpdir = tempfile.mkdtemp(prefix="aa_bench_")
        shared = {
            "anom_index": _pack_shared_index(common_index, tmpdir, prefix="anom"),
            "anom_mat": _maybe_memmap_array(tmpdir, "anom_mat", anom_mat),
            "jitter_mat": (
                None if jitter_mat is None else _maybe_memmap_array(tmpdir, "jitter_mat", jitter_mat)
            ),
            "ts": _pack_series(ts_sliced, tmpdir, "ts"),
            "ret": _pack_series(ret_sliced, tmpdir, "ret"),
            "ret100": _pack_series(ret100, tmpdir, "ret100"),
            "mcap": _pack_series(mcap_sliced, tmpdir, "mcap"),
            "nyse": _pack_series(nyse_sliced, tmpdir, "nyse") if nyse_sliced is not None else None,
            "factor_df": factor_df,
            "factor_model": int(factor_model) if not isinstance(factor_model, pd.DataFrame) else 1,
            "outer_breaks": outer_breaks,
            "_tmpdir": tmpdir,
        }
        # The stacks are on disk now; workers mmap them. Drop this process's
        # copies (two n x k float64 arrays plus the per-anomaly jitter draws,
        # ~17 GB at full sample) before the workers start.
        del stacked, anom_mat, jitter_mat, jitters
        gc.collect()
        payloads = _map_anomalies(
            names, _bench_pool_task, shared, n_workers, verbose=verbose, label="benchmarks"
        )
        for name, rho_s, rho_p, sr, fmb in payloads:
            correls.loc[name, "spearman"] = rho_s
            correls.loc[name, "pearson"] = rho_p
            cond_sort[name] = sr
            fmbs[name] = fmb
    else:
        for i, (name, anom) in enumerate(anoms_dict.items(), start=1):
            rho_s, rho_p, sr, fmb = _run_one_benchmark(
                name,
                anom,
                ts_sliced=ts_sliced,
                ret_sliced=ret_sliced,
                ret100=ret100,
                mcap_sliced=mcap_sliced,
                nyse_sliced=nyse_sliced,
                jitter=jitters[name],
                factor_df=factor_df,
                factor_model=int(factor_model) if not isinstance(factor_model, pd.DataFrame) else 1,
                outer_breaks=outer_breaks,
            )
            correls.loc[name, "spearman"] = rho_s
            correls.loc[name, "pearson"] = rho_p
            cond_sort[name] = sr
            fmbs[name] = fmb
            if verbose and i % 10 == 0:
                LOGGER.info(
                    "Done with %d/%d anomalies @ %s.",
                    i,
                    n_anoms,
                    datetime.now().isoformat(timespec="seconds"),
                )

    if verbose:
        LOGGER.info(
            "Done with getting the related anomalies results at %s.",
            datetime.now().isoformat(timespec="seconds"),
        )

    return AnomBenchmarkResults(
        correls=correls,
        cond_sort=cond_sort,
        fmbs=fmbs,
        metadata={
            "time_period": time_period,
            "n_anoms": n_anoms,
            "anom_names": names,
            "factor_model": factor_model,
            "noise_seed": noise_seed,
            "noise_scale": _ANOM_NOISE_SCALE,
            "n_jobs": n_workers,
        },
    )


# ---------------------------------------------------------------------------
# makeAnomStratResults.m port
# ---------------------------------------------------------------------------


@dataclass
class AnomStratResults:
    """Container for per-anomaly univariate strategy sorts.

    MATLAB equivalent: output of ``makeAnomStratResults.m`` (``resAnoms``).

    Attributes
    ----------
    results : dict[str, SortResult]
        Keyed by anomaly name. Each entry is a 2-leg (low/high quintile) VW
        NYSE-breakpoint sort with optional net-of-tcost long-short.
    metadata : dict
        Orchestration context (n_anoms, factor_model, etc.).
    """

    results: dict[str, SortResult] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


def make_anom_strat_results(
    anoms: pd.DataFrame | dict[str, pd.Series] | np.ndarray,
    returns: pd.Series,
    mcap: pd.Series,
    *,
    tcosts: pd.Series | None = None,
    nyse_flag: pd.Series | None = None,
    time_period: tuple[pd.Timestamp | int, pd.Timestamp | int] | None = None,
    anom_labels: list[str] | None = None,
    factor_model: int = 1,
    noise_seed: int | None = _ANOM_NOISE_SEED,
    verbose: bool = True,
    n_jobs: int | None = 1,
    factors: pd.DataFrame | None = None,
    convention: str = "dollar",
) -> AnomStratResults:
    """
    Run per-anomaly quintile VW NYSE-breakpoint sorts (extreme legs only).

    MATLAB equivalent: ``makeAnomStratResults.m``.

    For each anomaly: add tiny jitter, form NYSE quintiles, keep legs 1 and 5
    (remapped to 1=short / 2=long), compute VW portfolio returns, CAPM alphas,
    and — when ``tcosts`` is supplied — the trading costs of the two legs,
    subtracted from the L/S.

    Notes
    -----
    - The legs are bought in the months in which the anomaly has values and
      left alone in between, and costs are those of the held legs' trades
      (``analytics/held.py``). An anomaly with values every month trades every
      month; one with values each June trades each June. ``convention`` is
      the size of the two legs after a trade: $1 (``"dollar"``, the
      default) or the strategy's capital (``"capital"``).
    - ``metadata["capital_restarts"]`` maps an anomaly's name to the number of
      trades at which its capital was zero or negative (``"capital"`` only;
      only anomalies where that happened are listed). Each is also logged as a
      warning, from this process, so it reaches the run log when the sorts
      ran in workers.
    - Bins are formed on *contemporaneous* signals; returns start the month
      after (formation at t, returns at t+1), and assignments carry through
      months with no new assignment (annual signals trade annually).
    - ``time_period`` is accepted for signature compatibility but deliberately
      ignored: the sorts span the full sample, as in MATLAB.
    - ``n_jobs`` and ``factors`` match :func:`make_anom_benchmark_results`:
      library default is serial (``n_jobs=1``); the protocol resolves the
      config worker count and passes the already-loaded factor frame.
    """
    n_workers = 1 if n_jobs is None else max(1, int(n_jobs))
    convention = check_convention(convention)
    anoms_dict = _coerce_anoms_to_dict(
        _sort_anoms_by_stock_month(anoms), signal_index=returns.index, labels=anom_labels
    )
    n_anoms = len(anoms_dict)
    names = list(anoms_dict.keys())

    if verbose:
        LOGGER.info(
            "Now working on getting the anomaly strategy results. Run started at %s.",
            datetime.now().isoformat(timespec="seconds"),
        )

    ret_sliced = returns
    mcap_sliced = mcap
    nyse_sliced = nyse_flag
    tc_sliced = tcosts
    factor_df = _prepare_factor_frame(
        factor_model, _align_dates_index(ret_sliced.index), factors
    )

    jitters = _anom_jitters(anoms_dict, noise_seed)

    stacked = _stack_aligned(anoms_dict)
    out: dict[str, SortResult] = {}
    use_pool = n_workers > 1 and n_anoms > 1 and stacked is not None
    if use_pool:
        common_index, anom_mat = stacked
        jitter_mat = None
        if noise_seed is not None:
            jitter_mat = np.column_stack([jitters[n] for n in names])
        tmpdir = tempfile.mkdtemp(prefix="aa_strat_")
        shared = {
            "anom_index": _pack_shared_index(common_index, tmpdir, prefix="anom"),
            "anom_mat": _maybe_memmap_array(tmpdir, "anom_mat", anom_mat),
            "jitter_mat": (
                None if jitter_mat is None else _maybe_memmap_array(tmpdir, "jitter_mat", jitter_mat)
            ),
            "ret": _pack_series(ret_sliced, tmpdir, "ret"),
            "mcap": _pack_series(mcap_sliced, tmpdir, "mcap"),
            "nyse": _pack_series(nyse_sliced, tmpdir, "nyse") if nyse_sliced is not None else None,
            "tc": _pack_series(tc_sliced, tmpdir, "tc") if tc_sliced is not None else None,
            "factor_df": factor_df,
            "factor_model": int(factor_model) if not isinstance(factor_model, pd.DataFrame) else 1,
            "convention": convention,
            "_tmpdir": tmpdir,
        }
        # As in make_anom_benchmark_results: the stacks are on disk now.
        del stacked, anom_mat, jitter_mat, jitters
        gc.collect()
        payloads = _map_anomalies(
            names, _strat_pool_task, shared, n_workers, verbose=verbose, label="strats"
        )
        for name, sr in payloads:
            out[name] = sr
    else:
        for i, (name, anom) in enumerate(anoms_dict.items(), start=1):
            out[name] = _run_one_strat(
                name,
                anom,
                ret_sliced=ret_sliced,
                mcap_sliced=mcap_sliced,
                nyse_sliced=nyse_sliced,
                tc_sliced=tc_sliced,
                jitter=jitters[name],
                factor_df=factor_df,
                factor_model=int(factor_model) if not isinstance(factor_model, pd.DataFrame) else 1,
                convention=convention,
            )
            if verbose and i % 10 == 0:
                LOGGER.info(
                    "Done with %d/%d anomalies @ %s.",
                    i,
                    n_anoms,
                    datetime.now().isoformat(timespec="seconds"),
                )

    if verbose:
        LOGGER.info(
            "Done with getting the anomaly strategy results at %s.",
            datetime.now().isoformat(timespec="seconds"),
        )

    restarts = {
        name: int((sr.metadata or {}).get("capital_restarts", 0) or 0) for name, sr in out.items()
    }
    restarts = {name: k for name, k in restarts.items() if k}
    for name, k in restarts.items():
        LOGGER.warning(
            "anomaly strategy %s: the strategy's capital was zero or negative at %d "
            "trade(s); it restarted there with $1 in each leg",
            name, k,
        )

    return AnomStratResults(
        results=out,
        metadata={
            "convention": convention,
            "capital_restarts": restarts,
            "entry_cost": {
                name: float(sr.entry_cost) for name, sr in out.items() if sr.entry_cost is not None
            },
            "n_anoms": n_anoms,
            "factor_model": factor_model,
            "time_period": time_period,
            "noise_scale": _ANOM_NOISE_SCALE,
            "n_jobs": n_workers,
        },
    )


# ---------------------------------------------------------------------------
# makeFMBRes.m port
# ---------------------------------------------------------------------------
# Rolling window (months) over which per-month Fama-MacBeth slopes are averaged
# to form the combined forecast. MATLAB hard-codes T=120.
_FMB_ROLL_WINDOW: int = 120
# Pairwise correlation threshold above which the earlier of a colinear pair of
# anomaly columns is dropped in the monthly cross-sectional regression
# (MATLAB: 0.90).
_FMB_CORR_THRESHOLD: float = 0.90
# Winsorization percentile (each anomaly, cross-sectionally, per month).
_FMB_WINSOR_PCT: float = 1.0


@dataclass
class FMBRes:
    """Container for the Fama-MacBeth forecast-return combination signal.

    MATLAB equivalent: output of ``makeFMBRes.m`` (the ``eret`` matrix).

    Attributes
    ----------
    eret : pd.Series
        Forecast returns, MultiIndex (date, permno). NaN outside the rolling
        window or where no signal is available; aligned to the original panel.
    betas : pd.DataFrame
        Per-month cross-sectional slopes (index = date, columns = anomaly
        names). Each row holds the slopes from one FM regression (sans the
        intercept). NaN for anomalies that were dropped that month (all-zero,
        all-NaN, or colinear).
    metadata : dict
        Orchestration context: time period, rolling window, correlation
        threshold, winsor pct, and anomaly names.
    """

    eret: pd.Series = field(default_factory=pd.Series)
    betas: pd.DataFrame = field(default_factory=pd.DataFrame)
    metadata: dict[str, Any] = field(default_factory=dict)


def _winsorize_xs_1pct(x: pd.DataFrame, pct: float = _FMB_WINSOR_PCT) -> pd.DataFrame:
    """Winsorize each column of ``x`` at ``pct`` / ``100-pct`` percentiles.

    Mirrors MATLAB ``winsorize(x, 1)`` applied to a (stocks x anoms) matrix
    after the transpose-trick: each anomaly is winsorized independently over
    the stocks observed this month. Returns a *copy*; ``x`` is not modified.
    """
    if x.empty:
        return x
    from .sorts import _matlab_prctile

    out = x.astype(float).copy()
    for col in out.columns:
        s = out[col]
        if s.notna().sum() == 0:
            continue
        lo, hi = _matlab_prctile(s.to_numpy(dtype=float), [pct, 100.0 - pct])
        out[col] = s.clip(lower=lo, upper=hi)
    return out


def _drop_highly_correlated(x: pd.DataFrame, threshold: float) -> list[str]:
    """Return columns of ``x`` to drop due to |pairwise corr| > threshold.

    Mirrors MATLAB:
        corrs = tril(corrcoef(x(sum(isnan(x),2)==0, :)));
        corrs(eye) = 0;
        indToRemove = any(abs(corrs) > 0.90);
    i.e. on the complete-case rows, compute the lower-triangular correlation
    matrix, zero its diagonal, and mark columns where any |entry| in that
    column of the lower triangle exceeds the threshold. Because the triangle
    is strictly lower, the only non-zero entries in column ``k`` sit in rows
    ``> k``, so a flagged ``k`` is the *earlier* partner of a highly-correlated
    pair: MATLAB keeps the later column and drops the earlier one.
    """
    if x.shape[1] < 2:
        return []
    x_cc = x.dropna(how="any")
    if x_cc.shape[0] < 2:
        return []
    # drop columns that are constant in the complete-case sample — corrcoef
    # on them is NaN in MATLAB (any(NaN>0.9)==false) so they should be kept.
    # We handle by filling pairwise correlations involving such columns with 0.
    corr = x_cc.corr().abs()
    # Keep only strictly lower triangle (MATLAB `tril` includes the diagonal
    # but the next line zeros it out — equivalent to strictly lower).
    lower = np.tril(corr.to_numpy(), k=-1)
    lower = np.nan_to_num(lower, nan=0.0)
    # MATLAB `any(... > 0.90)` operates column-wise. A column k is flagged if
    # *any* row of the lower triangle in that column exceeds the threshold —
    # and rows below the diagonal in column k are the later columns i > k, so
    # this drops k whenever some *later* column i had |corr(i, k)| > threshold.
    mask = (lower > threshold).any(axis=0)
    return [c for c, drop in zip(x.columns, mask) if drop]


def make_fmb_res(
    filled_anoms: pd.DataFrame | dict[str, pd.Series] | np.ndarray,
    returns: pd.Series,
    *,
    time_period: tuple[pd.Timestamp | int, pd.Timestamp | int] | None = None,
    anom_labels: list[str] | None = None,
    roll_window: int = _FMB_ROLL_WINDOW,
    corr_threshold: float = _FMB_CORR_THRESHOLD,
    winsor_pct: float = _FMB_WINSOR_PCT,
    verbose: bool = True,
) -> FMBRes:
    """
    Build the Fama-MacBeth forecast-return combination signal.

    MATLAB equivalent: ``makeFMBRes.m`` (Novy-Marx / Velikov 2026). For each
    month ``t``:

      1. Take last-month signals ``X_{t-1}`` across ``nAnoms`` columns.
      2. Drop anomaly columns with no variation this month (all-NaN or all-0).
      3. Winsorize each surviving anomaly at ``winsor_pct`` / ``100-winsor_pct``
         cross-sectionally.
      4. Drop the earlier member of any pair with ``|corr| > corr_threshold``
         (MATLAB's rule; see ``_drop_highly_correlated``).
      5. Run plain OLS of ``ret_t`` on ``[1, X_{t-1}]``; store slopes in
         ``betas[t]`` (NaN for dropped anoms).
      6. Once ``t >= roll_window``, average ``betas`` over the trailing
         ``roll_window`` months per anomaly; form the fitted value
         ``eret_t = X_t @ bmean`` using only anoms with non-NaN ``bmean``.

    Parameters
    ----------
    filled_anoms : DataFrame or dict or 3-D ndarray
        Filled anomaly signals (no NaN from missing-data gaps). DataFrame:
        MultiIndex (date, permno) x anomaly columns. dict: ``{name: Series}``
        each MultiIndex (date, permno). 3-D ndarray: MATLAB-style
        ``(nMonths, nStocks, nAnoms)`` — requires ``anom_labels`` and is
        interpreted relative to ``returns``'s panel.
    returns : pd.Series
        Stock returns (decimals), MultiIndex (date, permno). Used both as the
        dependent variable and to fix the output panel.
    time_period : tuple, optional
        ``(start, end)`` as YYYYMM ints or Timestamps. Subset applied before
        running the monthly regressions. Matches MATLAB ``timePeriod``.
    anom_labels : list[str], optional
        Required when ``filled_anoms`` is a 3-D ndarray; ignored otherwise.
    roll_window : int
        Months over which to average the monthly betas. Default 120 (MATLAB).
    corr_threshold : float
        Drop later partner of any anomaly pair with ``|corr| > threshold``
        (same-month complete-case correlation). Default 0.90 (MATLAB).
    winsor_pct : float
        Per-anomaly, per-month winsorization percentile. Default 1.0 (MATLAB).
    verbose : bool
        If True, log progress every ``roll_window`` months (MATLAB cadence).

    Returns
    -------
    FMBRes

    Notes
    -----
    - Output ``eret`` is re-indexed to the *original* (pre-slice) ``returns``
      index so pipeline-downstream callers can align without gaps. Values
      outside ``time_period`` (or inside the first ``roll_window - 1`` months
      of the window) are NaN.
    - The "drop anoms with no variation" step uses MATLAB's exact predicate:
      ``sum(isfinite(lagX) & lagX~=0) > 0``, i.e. keep anoms with at least
      one finite non-zero value *this month*. This is intentionally lenient
      (1 obs is enough) because the later winsorize + OLS steps tolerate it.
    - The OLS uses only rows with no NaN across ``[ret, constant, X]`` —
      matching MATLAB's ``regress`` behavior.
    """
    # ---------------- Normalize inputs -------------------------------------
    anoms_dict = _coerce_anoms_to_dict(
        filled_anoms, signal_index=returns.index, labels=anom_labels
    )
    anom_names = list(anoms_dict.keys())
    n_anoms = len(anom_names)
    if n_anoms == 0:
        raise ValueError("filled_anoms must contain at least one anomaly signal")

    if verbose:
        LOGGER.info(
            "Now working on Fama-MacBeth with %d anomalies. Run started at %s.",
            n_anoms,
            datetime.now().isoformat(timespec="seconds"),
        )

    # Stack anomaly Series into a DataFrame over the union of (date, permno).
    # We will align to `returns` below so the panel rectangle matches MATLAB.
    anoms_df_full = pd.concat(anoms_dict, axis=1)
    anoms_df_full.columns = anom_names  # flatten MultiIndex columns if any

    # ---------------- Time-period subset -----------------------------------
    ret_sliced = _slice_panel_by_time(returns, time_period)
    ret_sliced = pd.to_numeric(ret_sliced, errors="coerce")
    anoms_sliced = _slice_panel_by_time(anoms_df_full, time_period)

    # Align anomaly panel to the sliced return index (outer-join then reindex).
    # This yields a rectangular (date x permno) view per column, matching the
    # MATLAB `filledAnoms(s:e, :, :)` slice.
    anoms_sliced = anoms_sliced.reindex(ret_sliced.index)

    # Dates in the evaluation window (month-ends).
    eval_dates = ret_sliced.index.get_level_values(0).unique().sort_values()

    # ---------------- Monthly loop ----------------------------------------
    betas = pd.DataFrame(index=eval_dates, columns=anom_names, dtype="float64")
    # Per-month forecasts; we'll assemble them into a Series at the end.
    temp_eret: dict[pd.Timestamp, pd.Series] = {}

    # Pre-shift anoms by 1 month so that, when we select rows at date t, we are
    # reading X_{t-1} — mirroring MATLAB's `lagX = filledAnoms(i-1, :, :)`,
    # which is a row of the rectangular grid (a stock absent at t-1 is NaN, not
    # its last observed value).
    anoms_lagged = _calendar_lag_panel(anoms_sliced, 1)

    # Convenience: per-date views.
    ret_by_date = ret_sliced.groupby(level="date")

    for i, d in enumerate(eval_dates, start=1):
        # i==1 in MATLAB's 1-indexed loop is skipped (`for i = 2:nMonths`);
        # we skip the first eval date in the same way.
        if i == 1:
            continue

        if verbose and (i % roll_window == 0):
            LOGGER.info(
                "Done until %s @ %s.",
                d.strftime("%Y-%m"),
                datetime.now().isoformat(timespec="seconds"),
            )

        # ---- RHS: lagged anoms at date d (rows: permnos present at d) -----
        try:
            lagX = anoms_lagged.xs(d, level="date", drop_level=False)
        except KeyError:
            continue
        # Align to the permnos that have a return this month.
        try:
            y_ser = ret_by_date.get_group(d)
        except KeyError:
            continue
        # Inner-join on the shared permno index at this date.
        lagX = lagX.reindex(y_ser.index)

        # ---- Pick anoms with at least one finite non-zero obs this month --
        is_signal = np.isfinite(lagX.to_numpy()) & (lagX.to_numpy() != 0)
        nobs_per_anom = is_signal.sum(axis=0)
        anoms_to_use = [a for a, n in zip(anom_names, nobs_per_anom) if n > 0]
        if not anoms_to_use:
            continue

        # ---- Winsorize each surviving anom cross-sectionally --------------
        x_w = _winsorize_xs_1pct(lagX[anoms_to_use], pct=winsor_pct)

        # ---- Drop earlier partner of any highly-correlated pair -----------
        drop_cols = _drop_highly_correlated(x_w, threshold=corr_threshold)
        if drop_cols:
            anoms_to_use = [a for a in anoms_to_use if a not in drop_cols]
            if not anoms_to_use:
                continue
            # Re-winsorize on the reduced set. MATLAB re-winsorizes too:
            #   x = [const winsorize(lagX(:, anomsToUse)', 1)'];
            x_w = _winsorize_xs_1pct(lagX[anoms_to_use], pct=winsor_pct)

        # ---- Regress: y on [1, x_w] via complete-case OLS -----------------
        y_vec = y_ser.to_numpy(dtype=float)
        X_mat = np.column_stack([np.ones(len(y_vec)), x_w.to_numpy(dtype=float)])
        ok = np.isfinite(y_vec) & np.isfinite(X_mat).all(axis=1)
        if ok.sum() <= X_mat.shape[1]:
            # Not enough degrees of freedom; leave betas as NaN.
            continue
        bhat, _, _, _ = np.linalg.lstsq(X_mat[ok], y_vec[ok], rcond=None)
        # Slopes (excluding intercept) mapped back to the anomaly columns.
        slopes = bhat[1:]
        for a, b in zip(anoms_to_use, slopes):
            betas.loc[d, a] = b

        # ---- Fitted values once we have a full rolling window -------------
        if i >= roll_window:
            # Trailing `roll_window` rows up to and including row i (inclusive).
            window_dates = eval_dates[i - roll_window : i]
            bmean = betas.loc[window_dates].mean(axis=0, skipna=True)
            anoms_with_bmean = bmean.dropna().index.tolist()
            if not anoms_with_bmean:
                continue
            # `anoms_sliced` (unshifted) at date d is X_t — MATLAB:
            #   thisMonthX = permute(filledAnoms(i, :, indToUse), [2 3 1]);
            try:
                x_t = anoms_sliced.xs(d, level="date", drop_level=False)
            except KeyError:
                continue
            x_t = x_t.reindex(y_ser.index)
            # Compute fitted value per stock; missing anom -> row NaN (match
            # MATLAB matrix multiply semantics).
            x_t_used = x_t[anoms_with_bmean].to_numpy(dtype=float)
            b_used = bmean.loc[anoms_with_bmean].to_numpy(dtype=float)
            fitted = x_t_used @ b_used
            temp_eret[d] = pd.Series(fitted, index=y_ser.index)

    # ---------------- Assemble output panel -------------------------------
    if temp_eret:
        eret_sliced = pd.concat(temp_eret.values()).sort_index()
    else:
        eret_sliced = pd.Series(dtype="float64")

    # Re-index back to the original returns panel (matches MATLAB:
    # `eret = nan(length(dates), nStocks); eret(s:e,:) = temp_eret`).
    eret = pd.Series(np.nan, index=returns.index, dtype="float64", name="eret")
    if not eret_sliced.empty:
        eret.loc[eret_sliced.index] = eret_sliced.to_numpy()

    if verbose:
        LOGGER.info(
            "Done with Fama-MacBeth at %s.",
            datetime.now().isoformat(timespec="seconds"),
        )

    return FMBRes(
        eret=eret,
        betas=betas,
        metadata={
            "time_period": time_period,
            "roll_window": int(roll_window),
            "corr_threshold": float(corr_threshold),
            "winsor_pct": float(winsor_pct),
            "n_anoms": n_anoms,
            "anom_names": anom_names,
        },
    )


# ---------------------------------------------------------------------------
# makeCloseAnomResults.m port
# ---------------------------------------------------------------------------
# Number of closely-related anomalies to include in the spanning / FM regressions.
# MATLAB hard-codes this to 6.
_CLOSE_N_ANOMS: int = 6
# Factor model used for the spanning-test RHS. MATLAB uses `ff6(s:e, 2:end)`
# (all 6 FF factors ex-rf), so the default here is 6.
_CLOSE_SPAN_FACTOR_MODEL: int = 6


@dataclass
class CloseAnomResult:
    """Container for one spanning / FM regression in the close-anom panel.

    Each MATLAB `resCloseSpan(i,1)` (from `nanols`) carries beta + tstats + rbar;
    `resCloseFMB(i,1)` carries the full Fama-MacBeth result. Python stores them
    as a pair of typed sub-structures for clarity.
    """

    beta: pd.Series = field(default_factory=pd.Series)
    tstats: pd.Series = field(default_factory=pd.Series)
    r2: float = float("nan")
    r2_adj: float = float("nan")
    n_obs: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CloseAnomResults:
    """Container mirroring MATLAB's [resCloseFMB, resCloseSpan, closeLabels].

    Attributes
    ----------
    fmb : list[RegressionResult]
        Length ``n_close + 2`` (empty when no anomaly is selected). Entry 0 is
        the FM regression of returns on the testSignal alone (labels
        ``["Const", "test_signal"]``; not in MATLAB). Entry ``i``
        (1..n_close) regresses returns on ``[testSignal,
        closely_related_anom_i]``. The last entry controls for *all*
        ``n_close`` anomalies jointly. ``metadata["fmb_layout"]`` names the
        entries in order. Results saved by an earlier version have no entry 0.
        The regressions run on percent returns (``100 * ret``;
        ``metadata["fmb_returns"] == "percent"``) and each entry's
        ``metadata["n_months"]`` counts the monthly cross-sections
        averaged; older pickles used decimal returns and lack both keys.
    span : list[CloseAnomResult]
        Length ``n_close + 1``. Entry ``i`` is the OLS spanning regression of
        the testSignal L/S leg on ``[1, close_anom_i_LS, FF6_ex_rf]``. The
        last entry controls for all ``n_close`` anomaly L/S legs jointly.
    close_labels : dict[str, list[str]]
        ``{"short": [...], "long": [...]}``. Short + long labels for the
        selected closely-related anomalies (length ``n_close``).
    close_indices : list[int]
        The positions (0-indexed) within the input anomaly ordering that were
        picked as "closely related". Length ``n_close``, or fewer when fewer
        anomalies have a finite combined rank: a missing rank (no spanning
        rbar2 or no correlation) sorts last and is never selected.
        ``metadata`` records ``n_close_requested``, ``combined_rank`` and
        ``rank_missing``.
    span_r2 : pd.Series
        Per-anomaly spanning-regression rbar2 from the pre-selection step.
        NaN for anomalies skipped (no L/S portfolio).
    anom_corr : pd.Series
        Per-anomaly signal correlation used in the combined rank: the pooled
        Spearman rank correlation by default, or Pearson when
        ``rank_correlation="pearson"`` (``metadata["rank_correlation"]``
        says which). NaN where unavailable.
    metadata : dict
        Orchestration context: time period, n_close, factor model, etc.
    """

    fmb: list[RegressionResult] = field(default_factory=list)
    span: list[CloseAnomResult] = field(default_factory=list)
    close_labels: dict[str, list[str]] = field(default_factory=dict)
    close_indices: list[int] = field(default_factory=list)
    span_r2: pd.Series = field(default_factory=pd.Series)
    anom_corr: pd.Series = field(default_factory=pd.Series)
    metadata: dict[str, Any] = field(default_factory=dict)


def _nanols_span(y: pd.Series, X: pd.DataFrame) -> CloseAnomResult:
    """Classical OLS with NaN-row dropping (mirrors MATLAB `nanols`).

    ``X`` must already include the constant column. Returns a
    ``CloseAnomResult`` with beta, tstats, R^2, adjusted R^2, and n.
    """
    # Local import avoids a top-level cycle with sorts.py.
    from .sorts import _ols

    df = pd.concat([y.rename("_y"), X], axis=1).dropna()
    n = len(df)
    k = X.shape[1]
    if n <= k:
        return CloseAnomResult(
            beta=pd.Series(np.nan, index=X.columns),
            tstats=pd.Series(np.nan, index=X.columns),
            r2=np.nan,
            r2_adj=np.nan,
            n_obs=int(n),
        )
    y_arr = df["_y"].to_numpy(dtype=float)
    X_arr = df[X.columns].to_numpy(dtype=float)
    beta, tstats, r2 = _ols(y_arr, X_arr, robust=False)
    if pd.notna(r2) and n > k:
        r2_adj = 1.0 - (1.0 - r2) * (n - 1) / (n - k)
    else:
        r2_adj = np.nan
    return CloseAnomResult(
        beta=pd.Series(beta, index=X.columns),
        tstats=pd.Series(tstats, index=X.columns),
        r2=float(r2) if pd.notna(r2) else np.nan,
        r2_adj=float(r2_adj) if pd.notna(r2_adj) else np.nan,
        n_obs=int(n),
    )


def _tiedrank(x: pd.Series) -> pd.Series:
    """MATLAB `tiedrank`: average rank, NaNs kept as NaN.

    Python equivalent of MATLAB `tiedrank(x)` — ascending average rank with
    NaN preserved. Pandas `rank(method='average')` already averages ties; by
    default NaNs are kept (``na_option='keep'``), which mirrors MATLAB.
    """
    return x.rank(method="average", na_option="keep")


def make_close_anom_results(
    res_correls: pd.DataFrame,
    res_anoms: dict[str, SortResult] | "AnomBenchmarkResults",
    anoms: pd.DataFrame | dict[str, pd.Series] | np.ndarray,
    labels: dict[str, list[str]],
    test_signal: pd.Series,
    res_basic_sorts: BasicSortsResults,
    *,
    returns: pd.Series,
    mcap: pd.Series | None = None,
    time_period: tuple[pd.Timestamp | int, pd.Timestamp | int] | None = None,
    n_close: int = _CLOSE_N_ANOMS,
    span_factor_model: int = _CLOSE_SPAN_FACTOR_MODEL,
    basic_sort_row: str = BASIC_SORT_LABELS[0],
    basic_sort_factor_model: int | None = None,
    anom_labels: list[str] | None = None,
    verbose: bool = True,
    factors: pd.DataFrame | None = None,
    rank_correlation: str = "spearman",
) -> CloseAnomResults:
    """
    Build the closely-related anomaly FM + spanning results.

    MATLAB equivalent: ``makeCloseAnomResults.m`` (Novy-Marx / Velikov 2026).
    Given a panel of benchmark anomalies, pick the ``n_close`` most
    closely-related (by combined rank of spanning ``rbar`` and the absolute
    pooled signal correlation, Spearman by default) and run:

      (a) For each close anom ``i``: a bivariate Fama-MacBeth of returns on
          ``[testSignal, anom_i]``.
      (b) For each close anom ``i``: an OLS spanning regression of the
          testSignal L/S leg on ``[1, anom_i_LS, FF6_ex_rf]``.
      (c) A joint FM with ``testSignal`` and *all* close anom signals.
      (d) A joint spanning regression with all close anom L/S legs + FF6.

    Parameters
    ----------
    res_correls : pd.DataFrame
        Output of ``make_anom_benchmark_results().correls`` -- rows = anomaly
        names, columns = ``{"spearman", "pearson"}``. The column named by
        ``rank_correlation`` (default ``"spearman"``) enters the combined rank.
    res_anoms : dict[str, SortResult] or AnomBenchmarkResults
        Per-anomaly ``SortResult`` (the 2-leg hedged L/S from the conditional
        sort). Accepts the ``.cond_sort`` dict directly or the full
        ``AnomBenchmarkResults`` object.
    anoms : DataFrame or dict or 3-D ndarray
        Raw anomaly signals. Same conventions as ``make_anom_benchmark_results``.
    labels : dict[str, list[str]]
        ``{"short": [...], "long": [...]}`` -- one entry per anomaly, in the
        same order as the anomaly columns in ``anoms``.
    test_signal : pd.Series
        Candidate anomaly signal, MultiIndex (date, permno).
    res_basic_sorts : BasicSortsResults
        Output of ``make_basic_sorts_results``. The testSignal L/S leg used for
        the spanning LHS is taken from
        ``res_basic_sorts.basic[(basic_sort_row, basic_sort_factor_model)].long_short``.
    returns : pd.Series
        Stock returns (decimals), MultiIndex (date, permno). Required for the
        FM regressions.
    mcap : pd.Series, optional
        Unused directly (FM regressions don't need it here), kept for parity
        with the other ``make_*`` signatures.
    time_period : tuple, optional
        ``(start, end)`` as YYYYMM ints or Timestamps. Applied to both the FM
        sample and the spanning sample.
    n_close : int
        Number of closely-related anomalies to pick. Default 6 (MATLAB).
    span_factor_model : int
        Factor model appended to the RHS of the spanning regressions. Default
        6 (MATLAB: ``ff6(s:e, 2:end)`` -- all 6 FF factors ex-rf).
    basic_sort_row : str
        Row of ``res_basic_sorts.basic`` whose L/S leg is the spanning LHS.
        MATLAB uses the first row (``vw_nyse_5``).
    basic_sort_factor_model : int, optional
        Factor model key paired with ``basic_sort_row``. Defaults to the first
        factor model in ``res_basic_sorts.metadata["factor_models"]``, or 1.
    anom_labels : list[str], optional
        Required when ``anoms`` is a 3-D ndarray; ignored otherwise. Order
        must match ``labels["short"]`` / ``labels["long"]`` / ``res_correls``
        row index.
    verbose : bool
        If True, log start / end timestamps.
    factors : pd.DataFrame, optional
        Explicit factor bundle (date index). The spanning factors for
        ``span_factor_model`` are selected from it by name, with no database
        access. When omitted they are loaded from the configured library DB.
    rank_correlation : {"spearman", "pearson"}
        Which pooled signal correlation enters the combined rank. Default
        ``"spearman"``: the rank correlation is invariant to each
        signal's scale and outliers. ``"pearson"`` restores the earlier
        choice; on raw, unwinsorized signals it is dominated by outliers and
        close to zero for most anomalies. Without named columns the first
        column is Spearman and the second Pearson (MATLAB's order).

    Returns
    -------
    CloseAnomResults

    Notes
    -----
    - The MATLAB indexing ``ff6(s:e, 2:end)`` drops the first column, which in
      the MATLAB ``ff6`` matrix is the risk-free rate (``rf``). Here we call
      ``_resolve_factor_model(..., span_factor_model)`` and drop ``rf``
      explicitly so the RHS contains the 6 pricing factors (mkt, smb, hml,
      rmw, cma, mom).
    - MATLAB skips anomalies with empty ``xret`` in the pre-selection loop
      (``if ~isempty(resAnoms(i).xret)``). Our equivalent is
      ``SortResult.long_short is None`` *or* ``SortResult.xret is None``.
    - MATLAB uses ``resBasicSorts(1,1).res.pret(:, end)`` as the testSignal
      L/S (last column of the portfolio return matrix, i.e. the L/S leg). In
      Python we use ``SortResult.long_short`` directly, which stores the same
      quantity.
    - The tie-breaking behavior of MATLAB ``sort`` on ``tiedrank``+``tiedrank``
      is not perfectly deterministic if the combined rank has exact ties; we
      break by original position ascending (pandas default for stable sort),
      which matches MATLAB most of the time for realistic rank sums.
    """
    # ---- Normalize inputs -------------------------------------------------
    # Per-anomaly SortResult dict.
    if isinstance(res_anoms, AnomBenchmarkResults):
        anom_sorts: dict[str, SortResult] = res_anoms.cond_sort
    elif isinstance(res_anoms, dict):
        anom_sorts = res_anoms
    else:
        raise TypeError(
            "res_anoms must be AnomBenchmarkResults or dict[str, SortResult]"
        )

    # Raw anomaly signals as a dict[name -> Series(date, permno)].
    anoms_dict = _coerce_anoms_to_dict(
        anoms, signal_index=test_signal.index, labels=anom_labels
    )
    anom_names = list(anoms_dict.keys())
    n_anoms = len(anom_names)
    if n_anoms == 0:
        raise ValueError("anoms must contain at least one anomaly signal")
    if n_close <= 0 or n_close > n_anoms:
        raise ValueError(
            f"n_close ({n_close}) must be in [1, n_anoms={n_anoms}]"
        )

    # Validate labels shape.
    for key in ("short", "long"):
        if key not in labels:
            raise ValueError(f"labels must contain '{key}' key")
        if len(labels[key]) != n_anoms:
            raise ValueError(
                f"labels['{key}'] length {len(labels[key])} != n_anoms={n_anoms}"
            )

    # Ranking correlation: the pooled Spearman rank correlation by
    # default. An earlier version had switched to Pearson, which MATLAB's
    # `makeCloseAnomResults` reads `resCorrels(i, 2)` believing it to hold
    # (MATLAB in fact ranked on Spearman: `calcPanelCorrels` was called with
    # one output, so rhoS filled both columns). On raw, unwinsorized signals
    # the pooled Pearson coefficient is driven by outliers and is near zero
    # for most anomalies, so the R2 rank alone decided the selection.
    rank_correlation = str(rank_correlation).lower()
    if rank_correlation not in ("spearman", "pearson"):
        raise ValueError(
            f"rank_correlation must be 'spearman' or 'pearson', got {rank_correlation!r}"
        )
    if not isinstance(res_correls, pd.DataFrame):
        raise ValueError("res_correls must be a DataFrame")
    if rank_correlation in res_correls.columns:
        corr_series = res_correls[rank_correlation]
    elif res_correls.shape[1] >= 2:
        # Positional fallback: MATLAB's order is [rhoS, rhoP].
        corr_series = res_correls.iloc[:, 0 if rank_correlation == "spearman" else 1]
    elif res_correls.shape[1] == 1:
        corr_series = res_correls.iloc[:, 0]
    else:
        raise ValueError(
            "res_correls must have a 'spearman' or 'pearson' column (or at least 1 column)"
        )
    # Align the correlation series to anom_names order.
    corr_aligned = pd.Series(
        [
            float(corr_series.get(nm, np.nan)) if nm in corr_series.index else np.nan
            for nm in anom_names
        ],
        index=anom_names,
    )

    # Basic-sort row -> testSignal L/S leg for the spanning LHS.
    if basic_sort_factor_model is None:
        fm_list = res_basic_sorts.metadata.get("factor_models", FACTOR_MODELS)
        basic_sort_factor_model = int(fm_list[0]) if len(fm_list) else 1
    try:
        basic_sort_res = res_basic_sorts.basic[(basic_sort_row, basic_sort_factor_model)]
    except KeyError as exc:
        raise KeyError(
            f"res_basic_sorts.basic is missing ({basic_sort_row!r}, "
            f"{basic_sort_factor_model!r})"
        ) from exc
    if basic_sort_res.long_short is None:
        raise ValueError(
            f"basic sort ({basic_sort_row}, fm={basic_sort_factor_model}) has "
            "no long-short leg"
        )

    if verbose:
        LOGGER.info(
            "Now working on getting the closely-related anomaly results. "
            "Run started at %s.",
            datetime.now().isoformat(timespec="seconds"),
        )

    # ---- Slice y (testSignal L/S) to time_period --------------------------
    # MATLAB: y = resBasicSorts(1,1).res.pret(s:e, end);
    y_full = basic_sort_res.long_short
    # The L/S series is date-indexed (single index). Slice by time_period.
    if time_period is not None:
        start, end = time_period
        if isinstance(start, int):
            start = pd.Timestamp(year=start // 100, month=start % 100, day=1) + pd.offsets.MonthEnd(0)
        if isinstance(end, int):
            end = pd.Timestamp(year=end // 100, month=end % 100, day=1) + pd.offsets.MonthEnd(0)
        y = y_full.loc[(y_full.index >= start) & (y_full.index <= end)]
    else:
        y = y_full

    # ---- Pre-select the closely-related anomalies -------------------------
    # MATLAB:
    #   for i=1:nAnoms:
    #       if ~isempty(resAnoms(i).xret):
    #           y_i = resBasicSorts(1,1).res.pret(s:e, end)
    #           X_i = [ones ... resAnoms(i).pret(s:e, end)]
    #           res = nanols(y_i, X_i)
    #           spanR2[i] = res.rbar
    #           anomCorr[i] = resCorrels[i, 2]
    #   combinedRank = tiedrank(spanR2) + tiedrank(|anomCorr|)
    #   [~, I] = sort(combinedRank, 'descend')
    span_r2 = pd.Series(np.nan, index=anom_names, dtype="float64")
    anom_corr = pd.Series(np.nan, index=anom_names, dtype="float64")

    # L/S leg per anomaly, sliced once.
    anom_ls_sliced: dict[str, pd.Series] = {}
    for name in anom_names:
        sr = anom_sorts.get(name)
        if sr is None or sr.long_short is None or sr.xret is None:
            continue
        ls = sr.long_short
        if time_period is not None:
            ls_sliced = ls.loc[(ls.index >= y.index.min()) & (ls.index <= y.index.max())]
        else:
            ls_sliced = ls
        anom_ls_sliced[name] = ls_sliced

        # Align L/S to y for the pre-selection regression.
        df = pd.concat({"y": y, "x": ls_sliced}, axis=1).dropna()
        if df.empty or len(df) < 3:
            continue
        X = pd.DataFrame(
            {"const": 1.0, "anom_ls": df["x"].to_numpy()},
            index=df.index,
        )
        span_i = _nanols_span(df["y"], X)
        span_r2.loc[name] = span_i.r2_adj
        anom_corr.loc[name] = corr_aligned.loc[name]

    # Combined rank: descending on (tiedrank(rbar) + tiedrank(|corr|)).
    combined = _tiedrank(span_r2) + _tiedrank(anom_corr.abs())
    # Stable sort, descending; ties -> earlier anomaly first (matches MATLAB
    # behavior for non-tied sums). MATLAB's sort(...,'descend') puts NaN
    # *first*, so an anomaly with no spanning rbar2 or no correlation led the
    # ranking as if it were the closest relative. A missing rank means there
    # is no overlap measurement at all: it sorts last and is never selected.
    order = combined.sort_values(ascending=False, kind="mergesort", na_position="last")
    finite_order = order[np.isfinite(order.to_numpy(dtype=float))]
    rank_missing = [nm for nm in order.index if nm not in finite_order.index]
    if finite_order.empty:
        raise ValueError(
            "No anomaly has a finite combined rank (spanning rbar2 and signal "
            f"correlation); cannot select closely related anomalies from {n_anoms}."
        )
    close_names: list[str] = list(finite_order.index[:n_close])
    if len(close_names) < n_close:
        LOGGER.warning(
            "Only %d of %d anomalies have a finite combined rank; selecting %d "
            "closely related anomalies instead of %d. Missing ranks: %s",
            len(finite_order), n_anoms, len(close_names), n_close, rank_missing,
        )
    close_indices: list[int] = [anom_names.index(nm) for nm in close_names]

    # ---- FF-ex-rf factor matrix for the spanning regressions --------------
    from .sorts import _resolve_factor_model

    ff_df = _resolve_factor_model(y.index, span_factor_model, factors=factors)
    ff_ex_rf = ff_df.drop(columns=["rf"], errors="ignore")

    # ---- Loop over close anomalies: FM + spanning ------------------------
    fmb_results: list[RegressionResult] = []
    span_results: list[CloseAnomResult] = []
    # Accumulators for the joint-all regression.
    fmb_X_joint: dict[str, pd.Series] = {}
    span_X_joint: dict[str, pd.Series] = {}

    # Slice inputs once for the FM regressions.
    # The FMBs run on percent returns, like the per-anomaly FMBs, so the
    # coefficients print with fixed decimals. t-stats and R2 are
    # unchanged by the scaling.
    ret_sliced = 100.0 * _slice_panel_by_time(returns, time_period)
    ts_sliced = _slice_panel_by_time(test_signal, time_period)

    # (0) Signal-only FM: returns ~ [testSignal]. Not in MATLAB;
    # it is column 0 of the close-anomaly FMB table, so a reader sees the
    # signal's own slope and R² next to the controlled ones.
    if close_names:
        fmb_results.append(
            run_fama_macbeth(
                ret_sliced,
                ts_sliced.to_frame("test_signal"),
                time_period=time_period if isinstance(time_period, tuple) else None,
                print_results=False,
                labels=["Const", "test_signal"],
            )
        )

    for rank_i, name in enumerate(close_names, start=1):
        anom_signal = anoms_dict[name]
        anom_sliced = _slice_panel_by_time(anom_signal, time_period)

        # (a) Bivariate FM: returns ~ [testSignal, anom_i]
        rhs = pd.concat(
            {"test_signal": ts_sliced, name: anom_sliced}, axis=1
        )
        fmb_i = run_fama_macbeth(
            ret_sliced,
            rhs,
            time_period=time_period if isinstance(time_period, tuple) else None,
            print_results=False,
            labels=["Const", "test_signal", name],
        )
        fmb_results.append(fmb_i)
        fmb_X_joint[name] = anom_sliced

        # (b) Spanning: y ~ [1, anom_i_LS, FF6_ex_rf]
        anom_ls = anom_ls_sliced.get(name)
        if anom_ls is None:
            # We only selected anomalies with a valid L/S earlier, so this
            # should not happen, but guard anyway.
            span_results.append(
                CloseAnomResult(metadata={"anom": name, "status": "no_ls_leg"})
            )
        else:
            X_span = pd.concat(
                [
                    pd.Series(1.0, index=y.index, name="const"),
                    anom_ls.rename("anom_ls"),
                    ff_ex_rf,
                ],
                axis=1,
            )
            span_i = _nanols_span(y, X_span)
            span_i.metadata = {
                "anom": name,
                "rank": rank_i,
                "factor_model": span_factor_model,
            }
            span_results.append(span_i)
            span_X_joint[name] = anom_ls

    # ---- Joint regressions (all close anomalies together) -----------------
    # (c) Joint FM: returns ~ [testSignal, anom_1, ..., anom_k]
    if fmb_X_joint:
        rhs_joint = pd.concat(
            {"test_signal": ts_sliced, **fmb_X_joint}, axis=1
        )
        fm_labels = ["Const", "test_signal"] + list(fmb_X_joint.keys())
        fmb_joint = run_fama_macbeth(
            ret_sliced,
            rhs_joint,
            time_period=time_period if isinstance(time_period, tuple) else None,
            print_results=False,
            labels=fm_labels,
        )
        fmb_results.append(fmb_joint)

    # (d) Joint spanning: y ~ [1, anom_1_LS, ..., anom_k_LS, FF6_ex_rf]
    if span_X_joint:
        span_cols = {name: ls for name, ls in span_X_joint.items()}
        X_joint = pd.concat(
            [
                pd.Series(1.0, index=y.index, name="const"),
                pd.DataFrame(span_cols),
                ff_ex_rf,
            ],
            axis=1,
        )
        span_joint = _nanols_span(y, X_joint)
        span_joint.metadata = {
            "anom": "all_close",
            "factor_model": span_factor_model,
            "n_close": len(close_names),
        }
        span_results.append(span_joint)

    # ---- Close labels ----------------------------------------------------
    close_labels = {
        "short": [labels["short"][i] for i in close_indices],
        "long": [labels["long"][i] for i in close_indices],
    }

    if verbose:
        LOGGER.info(
            "Done with closely-related anomaly results at %s.",
            datetime.now().isoformat(timespec="seconds"),
        )

    return CloseAnomResults(
        fmb=fmb_results,
        span=span_results,
        close_labels=close_labels,
        close_indices=close_indices,
        span_r2=span_r2,
        anom_corr=anom_corr,
        metadata={
            "time_period": time_period,
            "n_close": len(close_names),
            "n_close_requested": int(n_close),
            "n_anoms": int(n_anoms),
            "combined_rank": combined,
            "rank_missing": rank_missing,
            "span_factor_model": int(span_factor_model),
            "basic_sort_row": basic_sort_row,
            "basic_sort_factor_model": int(basic_sort_factor_model),
            "anom_names": anom_names,
            "close_names": close_names,
            "fmb_layout": ["signal_only", *close_names, "joint"] if close_names else [],
            "fmb_returns": "percent",
            "rank_correlation": rank_correlation,
        },
    )


# ---------------------------------------------------------------------------
# Dendrogram results (MATLAB: makeDendrogramResults.m)
# ---------------------------------------------------------------------------
# MATLAB clusters anomaly L/S return time series using Ward's minimum-variance
# method via `linkage(rets', 'ward')`. In Python we use
# `scipy.cluster.hierarchy.linkage` with the same method.

# Factor model appended via makeDendrogramResults: none (it only clusters
# anomaly L/S returns). We just pull the last column of each portfolio return
# matrix (MATLAB `pret(s:e, end)`), which for us is `SortResult.long_short`.


@dataclass
class DendrogramResults:
    """Container mirroring MATLAB ``[Z, dendrogramLabels, cutoff]``.

    Attributes
    ----------
    Z : np.ndarray
        ``(n-1) x 4`` linkage matrix encoding the agglomerative cluster tree
        (see ``scipy.cluster.hierarchy.linkage``). Columns are
        ``[cluster_a, cluster_b, distance, n_in_cluster]``.
    labels : list[str]
        Leaf labels for the dendrogram. The test-signal leaf is wrapped in a
        MATLAB-style ``\\color{red}{...}`` tag for parity; Python plotters can
        strip or re-style that marker.
    cutoff : float
        Color-threshold cutoff (75th percentile of linkage distances), used by
        ``scipy.cluster.hierarchy.dendrogram(color_threshold=...)``.
    metadata : dict
        Orchestration context -- time period, included anomaly indices, and
        counts of dropped / kept series.
    """

    Z: np.ndarray
    labels: list[str]
    cutoff: float
    metadata: dict[str, Any] = field(default_factory=dict)


def _to_month_end(x: pd.Timestamp | int) -> pd.Timestamp:
    """Coerce a YYYYMM int or Timestamp to a month-end Timestamp."""
    if isinstance(x, int):
        return pd.Timestamp(year=x // 100, month=x % 100, day=1) + pd.offsets.MonthEnd(0)
    ts = pd.Timestamp(x)
    # Snap to month-end for consistent slicing.
    return ts + pd.offsets.MonthEnd(0) if ts.is_month_start or ts.day != ts.days_in_month else ts


class AnomalyScreenError(ValueError):
    """No anomaly passes the coverage screen of ``check_fill_anomalies``.

    Raised by ``run_protocol`` when the screen keeps none of the anomalies it
    was given (or was given none). Every zoo-based part of the report needs
    at least one anomaly, and anomalies that fail the screen are not the ones
    the report describes, so the run stops instead of going on with them.
    """


class DendrogramSignalError(ValueError):
    """The test signal cannot be placed in the cluster plot.

    Raised when the signal's long/short series has no return in the sample,
    has a month without a return between its first and its last return, or
    is not among the leaves of the tree. ``run_protocol`` lets this error
    through (other failures of the dendrogram stage are only logged), because
    a cluster plot without the signal is not the plot the report describes.
    """


def _yyyymm(ts: pd.Timestamp) -> int:
    return int(ts.year) * 100 + int(ts.month)


def _basic_sort_long_short(
    res_basic_sorts: BasicSortsResults,
    basic_sort_row: str = BASIC_SORT_LABELS[0],
    basic_sort_factor_model: int | None = None,
) -> tuple[pd.Series, int]:
    """The test signal's long/short series used by the cluster plot."""
    if basic_sort_factor_model is None:
        fm_list = res_basic_sorts.metadata.get("factor_models", FACTOR_MODELS)
        basic_sort_factor_model = int(fm_list[0]) if len(fm_list) else 1
    try:
        basic_sort_res = res_basic_sorts.basic[
            (basic_sort_row, basic_sort_factor_model)
        ]
    except KeyError as exc:
        raise KeyError(
            f"res_basic_sorts.basic is missing ({basic_sort_row!r}, "
            f"{basic_sort_factor_model!r})"
        ) from exc
    if basic_sort_res.long_short is None:
        raise ValueError(
            f"basic sort ({basic_sort_row}, fm={basic_sort_factor_model}) has "
            "no long-short leg"
        )
    return basic_sort_res.long_short, int(basic_sort_factor_model)


def dendrogram_signal_window(
    signal_ls: pd.Series,
    time_period: tuple[pd.Timestamp | int, pd.Timestamp | int] | None = None,
    *,
    signal_label: str = "the test signal",
) -> pd.Series:
    """The test signal's long/short returns over the clustering window.

    The window starts in the first month in which the signal has a return, or
    in the second month of ``time_period`` if that is later (MATLAB's
    ``s+1``), and ends in the signal's last return month. A signal
    with a return in every month from the second month of the sample on gets
    MATLAB's window ``s+1:e``.

    Raises
    ------
    DendrogramSignalError
        If the signal has no return in the sample, or lacks a return in a
        month between its first and its last return. The message names the
        months.
    """
    ls = signal_ls.astype("float64")
    if time_period is not None:
        start = _to_month_end(time_period[0])
        end = _to_month_end(time_period[1])
        ls = ls.loc[(ls.index >= start) & (ls.index <= end)]
    # MATLAB indexes `s+1:e`: the first month of the sample is never used.
    ls = ls.iloc[1:]
    finite = np.isfinite(ls.to_numpy())
    if not finite.any():
        raise DendrogramSignalError(
            f"Cluster plot: the long/short strategy of {signal_label} has no "
            "return in the sample, so it cannot be placed in the tree."
        )
    pos = np.flatnonzero(finite)
    window = ls.iloc[pos[0] : pos[-1] + 1]
    gaps = window.index[~np.isfinite(window.to_numpy())]
    if len(gaps):
        shown = ", ".join(str(_yyyymm(d)) for d in gaps[:12])
        more = f" and {len(gaps) - 12} more" if len(gaps) > 12 else ""
        raise DendrogramSignalError(
            f"Cluster plot: the long/short strategy of {signal_label} has no "
            f"return in {len(gaps)} month(s) between its first return "
            f"({_yyyymm(window.index[0])}) and its last ({_yyyymm(window.index[-1])}): "
            f"{shown}{more}. The tree needs a return in every month of the "
            "window, so the signal would be dropped from it. Fill or remove "
            "the gap in the signal, or run the protocol on a sample without it."
        )
    return window


def make_dendrogram_results(
    res_anoms: dict[str, SortResult] | "AnomBenchmarkResults" | list[SortResult],
    signal_label: str,
    labels: list[str],
    res_basic_sorts: BasicSortsResults,
    time_period: tuple[pd.Timestamp | int, pd.Timestamp | int] | None = None,
    *,
    basic_sort_row: str = BASIC_SORT_LABELS[0],
    basic_sort_factor_model: int | None = None,
    linkage_method: str = "ward",
    cutoff_percentile: float = 75.0,
    verbose: bool = True,
) -> DendrogramResults:
    """Build agglomerative hierarchical cluster results on anomaly L/S returns.

    MATLAB equivalent: ``makeDendrogramResults.m`` (Novy-Marx / Velikov 2026).
    Clusters the panel of anomaly long-short return time series plus the
    candidate test-signal long-short leg using Ward's minimum-variance method,
    and returns the SciPy linkage matrix ``Z``, the leaf labels, and a
    color-threshold cutoff (75th percentile of the linkage distances) to pass
    to ``scipy.cluster.hierarchy.dendrogram``.

    Parameters
    ----------
    res_anoms : dict[str, SortResult], AnomBenchmarkResults, or list[SortResult]
        Per-anomaly univariate-sort results (L/S legs). Each anomaly
        contributes one column (``SortResult.long_short``). Anomalies with no
        L/S leg or an ``xret is None`` flag are skipped (matches the MATLAB
        ``~isempty(resAnoms(i).xret)`` guard). For ``AnomBenchmarkResults`` we
        take ``.cond_sort`` by default.
    signal_label : str
        Plain string label for the candidate test signal. Wrapped as
        ``"\\color{red}{...}"`` in the returned labels for parity with the
        MATLAB ``dendrogram`` call. The Python plotter can strip the wrapper.
    labels : list[str]
        Short labels for each anomaly in ``res_anoms`` (MATLAB passes
        ``labels.short``). Must have one entry per anomaly in the same order.
        Extra labels are truncated to the number of anomalies; too few raises.
    res_basic_sorts : BasicSortsResults
        Output of ``make_basic_sorts_results``. The test-signal L/S leg is
        taken from ``res_basic_sorts.basic[(basic_sort_row,
        basic_sort_factor_model)].long_short`` (MATLAB uses
        ``resBasicSorts(1,1).res.pret(:, end)``).
    time_period : tuple, optional
        ``(start, end)`` as YYYYMM ints or Timestamps: the sample. The
        clustering window lies inside it: from the signal's first return
        month (not before the sample's second month, MATLAB's ``s+1``) to the
        signal's last return month. See :func:`dendrogram_signal_window`.
    basic_sort_row : str
        Row of ``res_basic_sorts.basic`` whose L/S leg is the test-signal leg.
        MATLAB uses the first row (``vw_nyse_5``).
    basic_sort_factor_model : int, optional
        Factor model key paired with ``basic_sort_row``. Defaults to the first
        factor model in ``res_basic_sorts.metadata["factor_models"]``, or 1.
    linkage_method : str
        Agglomerative method for ``scipy.cluster.hierarchy.linkage``. MATLAB
        uses ``'ward'`` (Ward's minimum variance, Euclidean distance).
    cutoff_percentile : float
        Percentile of linkage distances (column 3 of ``Z``) used as the color
        threshold. MATLAB hard-codes 75.
    verbose : bool
        If True, log start / end timestamps.

    Returns
    -------
    DendrogramResults
        With ``Z`` (linkage matrix), ``labels`` (leaf labels including the
        red-colored test-signal label), ``cutoff`` (threshold), and metadata.
        ``metadata["window"]`` is the clustering window as ``(YYYYMM, YYYYMM)``,
        ``metadata["n_anoms_kept"]`` the number of anomalies in the tree, and
        ``metadata["dropped_detail"]`` the dropped anomalies with their first
        and last return month.

    Raises
    ------
    DendrogramSignalError
        If the test signal cannot be placed in the tree (no return in the
        sample, or a month without a return inside its window).

    Notes
    -----
    - MATLAB ``linkage(rets', 'ward')`` treats each anomaly as an observation
      (rows) and each month as a feature (columns). SciPy's
      ``linkage(X, method='ward')`` expects the same layout (observations as
      rows), so we pass ``rets.T`` equivalent: ``rets_obs = rets_matrix.T`` in
      pandas terms (each row = one anomaly's time series).
    - MATLAB Ward uses Euclidean distance (default); SciPy's 'ward' is also
      Euclidean. The linkage matrices should agree up to leaf ordering and
      cluster-id conventions (SciPy uses 0-based cluster ids; MATLAB 1-based).
    - The MATLAB code slices every series with ``s+1:e`` (one-month burn-in)
      and drops each series with a missing month, the test signal included.
      Here the window is the signal's own return months, so the
      signal is always a leaf; for a signal with a return in every month of
      ``s+1:e`` the window, and the tree, are MATLAB's.
    - Anomaly columns with *any* NaN inside the clustering window are dropped
      (MATLAB: ``isfinite(sum(rets, 1))``). The corresponding labels are
      dropped in the same order, and the dropped names are logged.
    """
    # ---- Normalize res_anoms -> dict[name -> SortResult] -----------------
    if isinstance(res_anoms, AnomBenchmarkResults):
        anom_sorts: dict[str, SortResult] = dict(res_anoms.cond_sort)
    elif isinstance(res_anoms, dict):
        anom_sorts = dict(res_anoms)
    elif isinstance(res_anoms, list):
        # Fall back to positional labels if a bare list is provided. Requires
        # `labels` to be aligned.
        if len(labels) < len(res_anoms):
            raise ValueError(
                f"labels length {len(labels)} < number of anomalies {len(res_anoms)}"
            )
        anom_sorts = {str(labels[i]): sr for i, sr in enumerate(res_anoms)}
    else:
        raise TypeError(
            "res_anoms must be AnomBenchmarkResults, dict[str, SortResult], "
            "or list[SortResult]"
        )

    # Preserve anomaly order. When `res_anoms` is a dict we assume the dict is
    # already in the intended order (Python 3.7+ dict preserves insertion).
    anom_names = list(anom_sorts.keys())
    n_anoms = len(anom_names)
    if n_anoms == 0:
        raise ValueError("res_anoms must contain at least one anomaly")

    # Truncate `labels` to n_anoms (MATLAB `labels` is a cell array of the
    # same length as `resAnoms`).
    if len(labels) < n_anoms:
        raise ValueError(
            f"labels length {len(labels)} < number of anomalies {n_anoms}"
        )

    # ---- Resolve the test-signal L/S leg from res_basic_sorts -------------
    signal_ls, basic_sort_factor_model = _basic_sort_long_short(
        res_basic_sorts, basic_sort_row, basic_sort_factor_model
    )

    if verbose:
        LOGGER.info(
            "Now working on making dendrogram data. Run started at %s.",
            datetime.now().isoformat(timespec="seconds"),
        )

    # ---- The clustering window ---------------------------------
    # MATLAB uses `s+1:e` for every series, the signal included, so a signal
    # whose first return comes later is dropped from its own plot. Here the
    # window is the signal's own return months: from its first return (not
    # before the second month of the sample) to its last.
    signal_ls = dendrogram_signal_window(
        signal_ls, time_period, signal_label=str(signal_label)
    )

    # Use the signal's window as the master date axis.
    dates = signal_ls.index

    # ---- Build the (dates x n_anoms+1) return matrix ---------------------
    # MATLAB:
    #   anomRets(s:e, i) = resAnoms(i).pret(s:e, end)
    #   rets = [anomRets(s+1:e, :)  signalRet(s+1:e)]
    cols: dict[str, pd.Series] = {}
    missing_xret: list[str] = []
    for name in anom_names:
        sr = anom_sorts.get(name)
        # MATLAB: `if ~isempty(resAnoms(i).xret)` -- skip anomalies whose
        # sort produced no excess-return stats. We keep the column full of
        # NaNs so the drop-step below reports it consistently.
        if sr is None or sr.long_short is None or sr.xret is None:
            missing_xret.append(name)
            cols[name] = pd.Series(np.nan, index=dates, dtype="float64")
            continue
        ls = sr.long_short.reindex(dates)
        cols[name] = ls.astype("float64")

    cols[signal_label] = signal_ls.astype("float64").reindex(dates)

    rets = pd.DataFrame(cols, index=dates)

    # ---- Drop anomalies with any non-finite value over the window --------
    # MATLAB: `anomsToKeep = isfinite(sum(rets, 1))`
    col_finite_mask = np.isfinite(rets.values).all(axis=0)
    keep_cols = [c for c, keep in zip(rets.columns, col_finite_mask) if keep]
    dropped = [c for c in rets.columns if c not in keep_cols]
    if signal_label not in keep_cols:  # cannot happen after the window check
        raise DendrogramSignalError(
            f"Cluster plot: {signal_label} is not among the leaves of the tree."
        )

    # Dropped anomalies, each with its first and last return month in the
    # sample (None when it has no return at all), for the log and the results.
    dropped_detail: list[dict[str, Any]] = []
    for name in dropped:
        sr = anom_sorts.get(name)
        first = last = None
        if sr is not None and sr.long_short is not None:
            valid = sr.long_short.dropna()
            if len(valid):
                first, last = _yyyymm(valid.index[0]), _yyyymm(valid.index[-1])
        dropped_detail.append({"name": str(name), "first": first, "last": last})
    window = (_yyyymm(dates[0]), _yyyymm(dates[-1]))
    n_kept_anoms = len(keep_cols) - 1
    LOGGER.info(
        "Cluster plot: window %d to %d (%d months, the return months of %s); "
        "%d of %d anomalies have a return in every month and are in the tree.",
        window[0], window[1], len(dates), signal_label, n_kept_anoms, n_anoms,
    )
    if dropped_detail:
        LOGGER.info(
            "Cluster plot: %d anomalies dropped (first to last return month): %s",
            len(dropped_detail),
            "; ".join(
                f"{d['name']} ({d['first']} to {d['last']})" for d in dropped_detail
            ),
        )
    rets = rets.loc[:, keep_cols]

    # Build `dendrogramLabels`, preserving MATLAB order:
    # [kept anomaly labels..., colored signal label].
    # The signal column is always last in `rets` construction above.
    dendro_labels: list[str] = []
    for c in rets.columns:
        if c == signal_label:
            dendro_labels.append(f"\\color{{red}}{{{signal_label}}}")
        else:
            # Map column name (anomaly key) back to its short label.
            # When res_anoms was a dict, column name == label.
            # When res_anoms was a list, column name == labels[i].
            dendro_labels.append(str(c))

    if rets.shape[1] < 2:
        raise ValueError(
            f"fewer than 2 series survive the finite-value filter "
            f"(kept={rets.shape[1]}); cannot build a dendrogram"
        )

    # ---- Run Ward linkage on anomalies-as-observations -------------------
    # MATLAB: Z = linkage(rets', 'ward')
    # SciPy's `linkage` expects observations as rows (n x m), so we pass
    # rets.T.values (rows = anomalies, cols = months).
    from scipy.cluster.hierarchy import linkage  # type: ignore

    obs_matrix = rets.to_numpy(dtype="float64").T  # (n_anoms_kept, n_months)
    Z = linkage(obs_matrix, method=linkage_method)

    # ---- Cutoff: percentile of linkage distances -------------------------
    # MATLAB: cutoff = prctile(Z(:,3), 75)
    from .sorts import _matlab_prctile

    cutoff = float(_matlab_prctile(Z[:, 2], [cutoff_percentile])[0])

    if verbose:
        LOGGER.info(
            "Done with making dendrogram data at %s.",
            datetime.now().isoformat(timespec="seconds"),
        )

    return DendrogramResults(
        Z=Z,
        labels=dendro_labels,
        cutoff=cutoff,
        metadata={
            "time_period": time_period,
            "linkage_method": linkage_method,
            "cutoff_percentile": float(cutoff_percentile),
            "window": window,
            "n_anoms_in": int(n_anoms),
            "n_anoms_kept": int(n_kept_anoms),
            "n_series_kept": int(rets.shape[1]),
            "n_months": int(rets.shape[0]),
            "dropped_columns": dropped,
            "dropped_detail": dropped_detail,
            "missing_xret": missing_xret,
            "signal_label": str(signal_label),
            "basic_sort_row": basic_sort_row,
            "basic_sort_factor_model": int(basic_sort_factor_model),
        },
    )


# ---------------------------------------------------------------------------
# makeCombStrats.m port
# ---------------------------------------------------------------------------
# Labels for the combination-strategy rows, matching MATLAB order:
#   1. Average rank
#   2. Weighted-Average rank
#   3. Fama-MacBeth
#   4. Partial Least Squares
#   5. IPCA
#   6. LASSO
# These are the keys under which each entry appears in ``CombStratsResults``.
COMB_STRAT_LABELS: tuple[str, ...] = (
    "avg_rank",
    "weighted_avg_rank",
    "fama_macbeth",
    "pls",
    "ipca",
    "lasso",
)

# Human-readable labels -- mirror the `combStrats(count,1).label` strings in
# MATLAB. Kept separately from `COMB_STRAT_LABELS` so downstream code can key
# by the short identifier while reporting uses the pretty label.
COMB_STRAT_DISPLAY_LABELS: dict[str, str] = {
    "avg_rank": "Average rank",
    "weighted_avg_rank": "Weighted-Average rank",
    "fama_macbeth": "Fama-MacBeth",
    "pls": "Partial Least Squares",
    "ipca": "IPCA",
    "lasso": "LASSO",
}

# Explanations (LaTeX-ready) lifted verbatim from MATLAB `makeCombStrats.m`.
COMB_STRAT_EXPLANATIONS: dict[str, str] = {
    "avg_rank": (
        "This method sorts stocks on the basis of forecast excess returns, where "
        "these are calculated on the basis of their average cross-sectional "
        "percentile rank across return predictors, and the predictors are all "
        "signed so that higher ranks are associated with higher average returns. "
    ),
    "weighted_avg_rank": (
        "This method sorts stocks on the basis of forecast excess returns, where "
        "these are calculated as their weighted-average cross-sectional "
        "percentile rank across return predictors, and the predictors are all "
        "signed so that higher ranks are associated with higher average returns and the "
        "weights are determined by the average returns over the past ten years to  the "
        "long/short strategies based on the individual signals. "
    ),
    "fama_macbeth": (
        "This method sorts stocks on the basis of forecast excess returns, where "
        "these are calculated from \\citet{FamaMacBeth1973} regressions following "
        "\\citet{HaugenBaker1996} and \\citet{Lewellen2015} using only data in the investor's "
        "information set at the time of portfolio formation, given the anomalies "
        "selected on the full sample. The estimation uses rolling "
        "ten years of data, so the actual strategies begin ten years later for this combination method.  "
    ),
    "pls": (
        "This method sorts stocks on the basis of forecast excess returns, where "
        "these are calculated from the partial least squares (PLS) filtering procedure following "
        "\\citet*{LightMaslovRytchkov2017} using only data in the investor's "
        "information set at the time of portfolio formation, given the anomalies "
        "selected on the full sample. Each month's forecasts use only "
        "that month's cross-sectional regressions, so this method needs no estimation window.  "
    ),
    "ipca": (
        "This method sorts stocks on the basis of forecast excess returns, where "
        "these are calculated from  the instrumented principal component analysis (IPCA) procedure of "
        "\\citet*{KellyPruittSu2019} using only data in the investor's "
        "information set at the time of portfolio formation, given the anomalies "
        "selected on the full sample. The estimation uses rolling "
        "ten years of data, so the actual strategies begin ten years later for this combination method.  "
    ),
    "lasso": (
        "This method sorts stocks on the basis of forecast excess returns, where "
        "these are estimated by the least absolute shrinkage and selection operator (LASSO) "
        "using only data in the investor's information set at the time of portfolio formation, "
        "given the anomalies selected on the full sample. "
        "Following \\citet*{ChenVelikov2022}, the LASSO penalty ($\\lambda$) is selected "
        "by minimizing the mean squared error (MSE) estimated by 5-fold cross validation. "
        "The estimation uses rolling ten years of data, so the actual strategies begin ten "
        "years later for this combination method.  "
    ),
}


@dataclass
class CombStratResult:
    """One row of MATLAB's ``combStrats(count, 1)`` structure.

    MATLAB equivalent: each iteration of ``makeCombStrats.m`` produces a
    ``combStrats(count, 1)`` struct with fields ``eret``, ``eret_enh``,
    ``label``, ``explanation``, and optionally ``errorObject`` when the
    helper threw. Python collects them as a list of these records.

    Attributes
    ----------
    eret : pd.Series
        Forecast returns from the baseline combination (``filledAnoms`` only),
        MultiIndex (date, permno). Full-NaN when *this* panel's helper call
        raised.
    eret_enh : pd.Series
        Forecast returns from the "enhanced" combination that appends the
        candidate test signal as an extra column (``cat(3, filledAnoms,
        filledSignal)`` in MATLAB), MultiIndex (date, permno). Full-NaN when
        *this* panel's helper call raised.
    label : str
        Short identifier (one of ``COMB_STRAT_LABELS``) used as the dict key
        in ``CombStratsResults.strats``.
    display_label : str
        Human-readable label mirroring MATLAB ``combStrats(count,1).label``;
        receives an ``" - N/A"`` suffix when either panel raised, matching
        MATLAB's fallback.
    explanation : str
        LaTeX-ready explanation of the combination method. Empty string on
        helper failure (MATLAB leaves the field unset in the catch branch).
    error : Exception or None
        ``None`` on success. On failure, the raised exception (MATLAB stores
        the whole ``ME`` object in ``combStrats(count,1).errorObject``). When
        both panels raised, the baseline exception is the one kept.
    signal_start : pd.Timestamp or None
        First month whose forecast uses the test signal; ``None`` when the
        method never uses it. ``eret`` and ``eret_enh`` are both NaN in the
        months in which the method does not use the signal, so the
        two strategies start together.
    info : dict
        ``signal_rule`` and ``signal_window`` (the rule those months follow);
        for IPCA also ``ipca_skipped``, the months its solver skipped on
        either panel.
    """

    eret: pd.Series = field(default_factory=pd.Series)
    eret_enh: pd.Series = field(default_factory=pd.Series)
    label: str = ""
    display_label: str = ""
    explanation: str = ""
    error: Exception | None = None
    # First month whose forecast uses the test signal (None: never). Both
    # forecasts are NaN in every month in which the method does not use it.
    signal_start: pd.Timestamp | None = None
    # ``signal_rule`` / ``signal_window`` (what the months above follow) and,
    # for IPCA, the months its solver skipped (``ipca_skipped``).
    info: dict[str, Any] = field(default_factory=dict)


@dataclass
class CombStratsResults:
    """Container mirroring MATLAB's ``combStrats`` (nCombMethods x 1) struct.

    Attributes
    ----------
    strats : dict[str, CombStratResult]
        Keyed by the short identifiers in ``COMB_STRAT_LABELS``. Order matches
        MATLAB row order (average rank, weighted-average rank, Fama-MacBeth,
        PLS, IPCA, LASSO) courtesy of insertion-ordered dicts.
    metadata : dict
        Orchestration context: time period, counts of successful / failed
        methods, and the set of helpers found at call time.
    """

    strats: dict[str, CombStratResult] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


# Version of the rule for the months in which a combination method uses the
# test signal. Stored with every checkpoint: one written under
# another rule is recomputed, not reused.
_COMB_SIGNAL_RULE: int = 1

# The fields of a checkpoint's identity, in the order they are compared and
# reported. A checkpoint is reused only if every one of them equals
# the running call's.
_COMB_CHECKPOINT_FIELDS: tuple[str, ...] = (
    "signal",
    "signal_sha256",
    "database_scientific_id",
    "window",
    "anomalies_sha256",
    "package_version",
    "package_sha256",
)


def _comb_checkpoint_identity(
    given: Any,
    *,
    filled_signal: pd.Series,
    time_period: Any,
    anom_names: list[str],
) -> dict[str, Any]:
    """What a combination checkpoint belongs to: signal, database, window, code.

    ``given`` is the caller's part (``run_protocol`` passes the signal's name,
    the hash of its values and the database's ``scientific_id``); what it
    leaves out is filled in from this call's own inputs. Every value is plain
    JSON (strings, integers, None), so two identities compare with ``==``.
    """
    import hashlib

    from .. import run_manifest

    def _month(x: Any) -> int | None:
        if x is None:
            return None
        if isinstance(x, (pd.Timestamp, datetime)):
            return _yyyymm(pd.Timestamp(x))
        try:
            return int(x)
        except (TypeError, ValueError):
            return _yyyymm(pd.Timestamp(x))

    window = None
    if time_period is not None:
        window = [_month(time_period[0]), _month(time_period[1])]
    code = run_manifest.protocol_code_identity()
    ident: dict[str, Any] = {
        "signal": None,
        "signal_sha256": run_manifest.signal_content_sha256(filled_signal),
        "database_scientific_id": None,
        "window": window,
        "anomalies_sha256": hashlib.sha256(
            "\n".join(str(n) for n in anom_names).encode("utf-8")
        ).hexdigest(),
        "package_version": code.get("package_version"),
        "package_sha256": code.get("package_sha256"),
    }
    for key, value in dict(given or {}).items():
        if key not in ident:
            raise ValueError(
                f"checkpoint_identity: unknown field {key!r}; the fields are "
                f"{', '.join(_COMB_CHECKPOINT_FIELDS)}"
            )
        if key == "window":
            value = None if value is None else [_month(value[0]), _month(value[1])]
        elif value is not None:
            value = str(value)
        ident[key] = value
    return ident



def _nan_eret_like(returns: pd.Series) -> pd.Series:
    """Return an all-NaN ``eret`` series aligned to the input returns panel.

    Mirrors MATLAB ``nan(size(ret))`` in the catch branches of
    ``makeCombStrats.m``. Used as the fallback for whichever of ``eret`` /
    ``eret_enh`` could not be computed (helper raised, or is not yet
    implemented).
    """
    return pd.Series(np.nan, index=returns.index, dtype="float64", name="eret")


def make_comb_strats(
    filled_anoms: pd.DataFrame | dict[str, pd.Series] | np.ndarray,
    filled_signal: pd.Series,
    keep_roll_anoms: pd.DataFrame | np.ndarray | None,
    res_anoms: dict[str, SortResult] | AnomBenchmarkResults | list[SortResult],
    res_basic_sorts: BasicSortsResults,
    returns: pd.Series,
    *,
    time_period: tuple[pd.Timestamp | int, pd.Timestamp | int] | None = None,
    anom_labels: list[str] | None = None,
    basic_sort_row: str = BASIC_SORT_LABELS[0],
    basic_sort_factor_model: int | None = None,
    avg_rank_fn: Any = None,
    weighted_avg_rank_fn: Any = None,
    fmb_fn: Any = None,
    pls_fn: Any = None,
    ipca_fn: Any = None,
    lasso_fn: Any = None,
    rf: pd.Series | None = None,
    verbose: bool = True,
    n_jobs: int | None = None,
    checkpoint_dir: str | Path | None = None,
    lasso_cv_mode: str = "shuffled",
    lasso_random_state: int = 0,
    signal_window: int = 120,
    checkpoint_identity: dict[str, Any] | None = None,
) -> CombStratsResults:
    """Build the six forecast-return combination strategies of Novy-Marx/Velikov (2026).

    MATLAB equivalent: ``makeCombStrats.m``. For each of six combination
    methods, compute two forecast-return panels -- a *baseline* one using
    only the benchmark-anomaly signals in ``filled_anoms``, and an *enhanced*
    one that appends the candidate test signal as an extra column
    (``cat(3, filledAnoms, filledSignal)`` in MATLAB). Each panel is what the
    downstream univariate-sort machinery consumes as its sort signal.

    The MATLAB implementation wraps every method in ``try/catch``: when the
    helper throws (or isn't implemented yet), the row is filled with
    ``nan(size(ret))``, the label gets an ``N/A`` suffix, and the error
    object is stashed on the struct. This port preserves that behaviour, with
    one correction: the two panels are attempted independently, so each field
    is assigned once from its own call and a failure on one panel does not
    discard the other's forecast.

    Parameters
    ----------
    filled_anoms : DataFrame, dict[str, Series], or 3-D ndarray
        Filled-in anomaly signals (no gaps from missing data). DataFrame /
        dict forms use MultiIndex (date, permno); the 3-D ndarray form
        mirrors MATLAB's ``(nMonths, nStocks, nAnoms)`` layout and requires
        ``anom_labels``.
    filled_signal : pd.Series
        Filled-in test signal, MultiIndex (date, permno). Concatenated onto
        ``filled_anoms`` (last slot) to form the "enhanced" input.
    keep_roll_anoms : DataFrame, ndarray, or None
        Rolling-flag matrix (``nMonths x nAnoms`` in MATLAB) indicating
        whether each anomaly has had > 40% of market-cap coverage in the
        trailing 10 years. Only the IPCA helper uses this. ``None`` is
        acceptable when the IPCA helper is unavailable.
    res_anoms : AnomBenchmarkResults, dict[str, SortResult], or list[SortResult]
        Per-anomaly univariate-sort results. The weighted-average-rank helper
        extracts each anomaly's long-short leg from here.
    res_basic_sorts : BasicSortsResults
        Output of ``make_basic_sorts_results``. Only the test signal's L/S
        leg (``res_basic_sorts.basic[(basic_sort_row,
        basic_sort_factor_model)].long_short``) is used, matching MATLAB
        ``resBasicSorts(1,1).res.pret(:, end)``.
    returns : pd.Series
        Stock returns (decimals), MultiIndex (date, permno). Used as the
        output panel for the NaN fallbacks and, where relevant, as LHS for
        the combination helpers.
    time_period : tuple, optional
        ``(start, end)`` as YYYYMM ints or Timestamps. Forwarded to helpers
        that accept it (FMB, PLS, IPCA).
    anom_labels : list[str], optional
        Labels for the 3-D ndarray form of ``filled_anoms``. Required when
        ``filled_anoms`` is an ndarray; ignored otherwise.
    basic_sort_row : str
        Row of ``res_basic_sorts.basic`` whose long-short leg represents the
        test signal (weighted-average-rank helper uses it as the signal's
        historical return series).
    basic_sort_factor_model : int, optional
        Factor-model key paired with ``basic_sort_row``. Defaults to the
        first factor model in ``res_basic_sorts.metadata["factor_models"]``,
        else 1.
    avg_rank_fn, weighted_avg_rank_fn, fmb_fn, pls_fn, ipca_fn, lasso_fn :
        callable, optional
        Injection hooks for the six combination helpers. When ``None``, the
        function wires a default adapter around the corresponding ``make_*``
        helper in this module: ``make_avg_rank``,
        ``make_weighted_avg_rank``, ``make_fmb_res``, ``make_pls_res``,
        ``make_ipca_res``, ``make_lasso_res``. Any method whose helper raises
        is marked ``N/A`` with a full-NaN panel, preserving the MATLAB
        fallback. Callers may still override any of the six via these
        keywords.
    rf : pd.Series, optional
        Risk-free rate (month-indexed). Forwarded to the IPCA helper only
        (MATLAB passes ``rf`` via the workspace ``load ff``). Omitting it
        makes IPCA fit on raw rather than excess returns.
    verbose : bool
        If True, log start / end timestamps and per-method progress, and
        forward that verbosity to the six helpers.
    n_jobs : int, optional
        Worker count for the two helpers that can use one (``make_ipca_res``
        and ``make_lasso_res``). Resolved through
        :func:`~assayinganomalies.config.resolve_protocol_n_jobs`, so an
        explicit value wins, then ``AA_PROTOCOL_N_JOBS``, then the persisted
        config, then ``cpu_count - 1`` — capped by the RAM budget either way.
    checkpoint_dir : path-like, optional
        Directory for per-method checkpoints. After each method finishes, its
        :class:`CombStratResult` is pickled to
        ``<checkpoint_dir>/comb_strats_<method>.pkl``; on entry, any
        checkpoint already present is loaded instead of recomputing. This is
        what makes a killed run resumable — the block is hours long and
        previously produced nothing at all until the very end.
        A checkpoint is used only if it was written for the same signal,
        database, window, anomalies and toolkit version as this call (see
        ``checkpoint_identity``) and under the same rule for the months the
        signal is used; otherwise the method is computed again and the log
        names the field that differs.
    lasso_cv_mode : {"shuffled", "month_grouped"}, default "shuffled"
    lasso_random_state : int, default 0
        Forwarded to :func:`make_lasso_res` and recorded in ``metadata`` under
        the same names, so a stored ``CombStratsResults`` says how its LASSO
        row was tuned. Ignored when an explicit ``lasso_fn`` is supplied — that
        caller owns its own settings. See :func:`make_lasso_res` for what the
        modes do.
    signal_window : int, default 120
        Months of data the test signal needs before the five methods other
        than the average rank use it; see "When the test signal is used".
    checkpoint_identity : dict, optional
        The caller's part of what a checkpoint belongs to: any of ``signal``
        (its name), ``signal_sha256`` (a hash of its values),
        ``database_scientific_id`` and ``window``. What is left out is taken
        from this call: the hash of ``filled_signal``, ``time_period``, and no
        database. The names of the anomalies, the package version and the hash
        of the installed package's files are always this call's. Used only
        with ``checkpoint_dir``.

    Returns
    -------
    CombStratsResults
        ``strats`` dict keyed by ``COMB_STRAT_LABELS``; each entry a
        ``CombStratResult``. ``metadata`` carries the time period, the count
        of successful / failed methods, the resolved helper map, the month
        each method starts to use the signal (``signal_start``) and the IPCA
        months skipped (``ipca_skipped``).

    When the test signal is used
    --------------------------------------
    A month *has data* when the filled signal has a non-zero value in it
    (``fill_var`` gives every stock the median, 0, in a month without data).
    The average rank uses the signal in every month that has data. The other
    five methods use it in a month when each of the ``signal_window`` months
    before it has data, so every estimation window is full of signal data.
    In the months in which a method does not use the signal, **both**
    forecasts are NaN: the strategy with the signal and the one without start
    together, and a report compares them over one period. For IPCA the
    signal's column of ``keep_roll_anoms`` follows the same rule instead of
    MATLAB's ``true(size(dates))``, which made every window before the signal
    exists singular.

    Notes
    -----
    - All six helpers dispatch to real implementations by default. MATLAB's
      own gold run reports ``IPCA - N/A`` and ``LASSO - N/A`` for the MPE
      signal, but both rows carry ``MATLAB:nomem`` / "Out of memory." --
      a resource failure of the dense ``(nMonths, nStocks, nAnoms)`` layout,
      not a statement that the methods do not apply. Neither Python helper
      builds that array, so both run.
    - Callers with out-of-tree helper implementations can pass them via the
      ``*_fn`` keyword arguments without editing this module.
    - The MATLAB IPCA branch appends a column of ``true(size(dates))`` to
      ``keep_roll_anoms`` for the enhanced panel (the test signal is always
      "kept"). Here the column is true in a month when the signal has data in
      that month and the ``signal_window - 1`` before it.
    """
    # ---- Timekeeping ------------------------------------------------------
    from ..config import resolve_protocol_n_jobs

    n_workers = resolve_protocol_n_jobs(n_jobs)
    ckpt_dir = Path(checkpoint_dir) if checkpoint_dir is not None else None
    if ckpt_dir is not None:
        ckpt_dir.mkdir(parents=True, exist_ok=True)

    t_block = time.perf_counter()
    if verbose:
        LOGGER.info(
            "Now working on combination strategy returns. Run started at %s. "
            "n_jobs=%d checkpoint_dir=%s",
            datetime.now().isoformat(timespec="seconds"),
            n_workers,
            ckpt_dir if ckpt_dir is not None else "(none)",
        )

    # ---- Resolve the helper-function map ---------------------------------
    # Resolve in order: explicit injection (caller-supplied `*_fn`) -> a
    # default adapter around this module's `make_*` helper. All six have a
    # real default implementation; `_run_one`'s try/except still degrades any
    # of them to an N/A row if the helper raises.
    if fmb_fn is None:
        # The FMB helper has a slightly different signature than MATLAB's
        # (takes `returns` as a positional arg, not via workspace). Wrap it
        # so the call-site below can stay uniform.
        def _fmb_adapter(
            fa, ret, *, time_period=None, anom_labels=None, **_ignored
        ):
            return make_fmb_res(
                fa,
                ret,
                time_period=time_period,
                anom_labels=anom_labels,
                verbose=verbose,
            )
        fmb_fn = _fmb_adapter

    if avg_rank_fn is None:
        # make_avg_rank(filled_anoms, me=None, ...) uses `me` only as a NaN
        # mask / index for the output panel shape (no market-cap values are
        # read). `returns` shares the same (date, permno) panel index as the
        # market-cap series in this orchestrator's caller, so it stands in
        # for `me` without requiring a new make_comb_strats parameter.
        def _avg_rank_adapter(filled_anoms, **_ignored):
            return make_avg_rank(filled_anoms, me=returns, verbose=verbose)
        avg_rank_fn = _avg_rank_adapter

    if weighted_avg_rank_fn is None:
        # make_weighted_avg_rank(filled_anoms, pret, me, ...) likewise only
        # uses `me.index` to fix the output panel shape; see above.
        def _weighted_avg_rank_adapter(
            filled_anoms, pret, *, time_period=None, **_ignored
        ):
            return make_weighted_avg_rank(
                filled_anoms, pret, returns, time_period=time_period, verbose=verbose
            )
        weighted_avg_rank_fn = _weighted_avg_rank_adapter

    if pls_fn is None:
        def _pls_adapter(
            filled_anoms, ret, *, time_period=None, anom_labels=None, **_ignored
        ):
            return make_pls_res(
                filled_anoms,
                ret,
                time_period=time_period,
                anom_labels=anom_labels,
                verbose=verbose,
            )
        pls_fn = _pls_adapter

    if ipca_fn is None:
        def _ipca_adapter(
            filled_anoms,
            keep_roll_anoms,
            ret,
            rf,
            *,
            time_period=None,
            anom_labels=None,
            **_ignored,
        ):
            return make_ipca_res(
                filled_anoms,
                keep_roll_anoms,
                ret,
                rf,
                time_period=time_period,
                anom_labels=anom_labels,
                verbose=verbose,
                n_jobs=n_workers,
            )
        ipca_fn = _ipca_adapter

    if lasso_fn is None:
        def _lasso_adapter(
            filled_anoms, ret, *, time_period=None, anom_labels=None, **_ignored
        ):
            return make_lasso_res(
                filled_anoms,
                ret,
                time_period=time_period,
                anom_labels=anom_labels,
                verbose=verbose,
                n_jobs=n_workers,
                cv_mode=lasso_cv_mode,
                random_state=lasso_random_state,
            )
        lasso_fn = _lasso_adapter

    # ---- Stitch the "enhanced" signal panel (filled_anoms + filled_signal)
    # For DataFrame / dict inputs the concat is straightforward (extend by a
    # column). For 3-D ndarray inputs we defer: each helper can accept a dict
    # via `_coerce_anoms_to_dict` at its own call site, so we normalize here
    # to a dict representation that both base and enhanced variants share.
    base_dict = _coerce_anoms_to_dict(
        filled_anoms, signal_index=filled_signal.index, labels=anom_labels
    )
    # Use a distinct, non-colliding key for the enhanced signal.
    signal_key = "__test_signal__"
    while signal_key in base_dict:
        signal_key = signal_key + "_"
    enh_dict = dict(base_dict)
    enh_dict[signal_key] = filled_signal

    base_labels = list(base_dict.keys())
    enh_labels = list(enh_dict.keys())

    # ---- What this call's checkpoints belong to ------------------
    ckpt_identity: dict[str, Any] | None = None
    if ckpt_dir is not None:
        ckpt_identity = _comb_checkpoint_identity(
            checkpoint_identity,
            filled_signal=filled_signal,
            time_period=time_period,
            anom_names=base_labels,
        )

    # ---- When each method uses the test signal -------------------
    if int(signal_window) < 1:
        raise ValueError("signal_window must be >= 1")
    signal_window = int(signal_window)
    panel_dates = (
        returns.index.get_level_values(0).unique().sort_values()
    )
    sig_num = pd.to_numeric(filled_signal, errors="coerce")
    has_data = (
        (sig_num.notna() & (sig_num != 0))
        .groupby(level=0)
        .any()
        .reindex(panel_dates, fill_value=False)
        .astype(bool)
    )
    # True in month j when months j - signal_window + 1 .. j all have data.
    full_window = (
        has_data.astype(float)
        .rolling(signal_window, min_periods=signal_window)
        .min()
        .eq(1.0)
    )
    # The average rank uses the signal in a month that has data; the other
    # methods in a month whose previous `signal_window` months all have data.
    use_avg = has_data
    use_rest = full_window.shift(1, fill_value=False).astype(bool)
    signal_first_month = has_data.index[has_data.to_numpy()].min() if has_data.any() else None

    def _use_months(key: str) -> pd.Series:
        return use_avg if key == "avg_rank" else use_rest

    if verbose:
        LOGGER.info(
            "Test signal: first month with data %s; used by the average rank "
            "from then on and by the other methods from %s (%d months of data).",
            signal_first_month.strftime("%Y-%m") if signal_first_month is not None else "none",
            (
                use_rest.index[use_rest.to_numpy()].min().strftime("%Y-%m")
                if use_rest.any() else "never"
            ),
            signal_window,
        )

    # For the IPCA branch the signal's column of keep_roll_anoms follows the
    # same rule (MATLAB: ``[keepRollAnoms true(size(dates))]``, which keeps the
    # signal in windows in which it is a column of zeros). Row j of the flag
    # matrix decides the fit for month j + 1, whose window ends in month j.
    keep_roll_enh: pd.DataFrame | np.ndarray | None
    if keep_roll_anoms is None:
        keep_roll_enh = pd.DataFrame(True, index=panel_dates, columns=list(base_dict.keys()))
        keep_roll_enh[signal_key] = full_window.to_numpy()
    elif isinstance(keep_roll_anoms, pd.DataFrame):
        keep_roll_enh = keep_roll_anoms.copy()
        keep_roll_enh[signal_key] = (
            full_window.reindex(keep_roll_enh.index, fill_value=False).to_numpy()
        )
    elif isinstance(keep_roll_anoms, np.ndarray):
        if keep_roll_anoms.ndim != 2:
            raise ValueError(
                "keep_roll_anoms ndarray must be 2-D (nMonths, nAnoms)"
            )
        if keep_roll_anoms.shape[0] != len(panel_dates):
            raise ValueError(
                "keep_roll_anoms ndarray must have one row per month of the "
                f"returns panel ({len(panel_dates)}), got {keep_roll_anoms.shape[0]}; "
                "pass a DataFrame indexed by date instead"
            )
        sig_col = full_window.to_numpy().astype(keep_roll_anoms.dtype).reshape(-1, 1)
        keep_roll_enh = np.concatenate([keep_roll_anoms, sig_col], axis=1)
    else:
        raise TypeError(
            "keep_roll_anoms must be DataFrame, 2-D ndarray, or None"
        )

    # Months the IPCA solver skipped, per panel, filled in by `_run_leg`.
    ipca_skipped: dict[str, list[tuple[Any, str]]] = {}

    def _signal_months(key: str, strat: CombStratResult) -> CombStratResult:
        """NaN both forecasts where the method does not use the signal."""
        use = _use_months(key)
        for name in ("eret", "eret_enh"):
            ser = getattr(strat, name)
            if ser is None or len(ser) == 0:
                continue
            mask = use.reindex(ser.index.get_level_values(0), fill_value=False).to_numpy()
            setattr(strat, name, ser.where(mask))
        strat.signal_start = use.index[use.to_numpy()].min() if use.any() else None
        strat.info = {"signal_rule": _COMB_SIGNAL_RULE, "signal_window": signal_window}
        if ckpt_identity is not None:
            strat.info["identity"] = dict(ckpt_identity)
        if key == "ipca":
            strat.info["ipca_skipped"] = {
                leg: list(months) for leg, months in ipca_skipped.items()
            }
        return strat

    # ---- Shared helper to run one combination method with MATLAB-style catch
    def _unwrap_eret(value: Any) -> pd.Series:
        """Pull the `eret` series out of a helper's container return type."""
        if isinstance(value, (FMBRes, LassoRes, PLSRes, IPCARes)):
            return value.eret
        return value

    def _run_leg(key: str, leg: str, kwargs: dict, fn) -> tuple[pd.Series, Exception | None]:
        """Run one panel variant, returning its forecast or a shaped NaN panel."""
        try:
            value = fn(**kwargs)
            if isinstance(value, IPCARes):
                ipca_skipped[leg] = list(value.metadata.get("skipped_months", []))
            return _unwrap_eret(value), None
        except Exception as exc:  # noqa: BLE001 -- mirror MATLAB `catch ME`.
            if verbose:
                LOGGER.warning(
                    "Combination method `%s` failed on the %s panel: %s",
                    key, leg, exc,
                )
            return _nan_eret_like(returns), exc

    def _run_one(key: str, base_kwargs: dict, enh_kwargs: dict, fn) -> CombStratResult:
        # Each field is assigned exactly once, from its own attempt. MATLAB's
        # weighted-average `catch` assigns `.eret_enh` twice and never `.eret`
        # (`makeCombStrats.m:99-100`), and running both panels under one
        # try/catch means a failure on either discards the other's result.
        eret, base_exc = _run_leg(key, "baseline", base_kwargs, fn)
        eret_enh, enh_exc = _run_leg(key, "enhanced", enh_kwargs, fn)
        exc = base_exc or enh_exc
        if exc is None:
            return CombStratResult(
                eret=eret,
                eret_enh=eret_enh,
                label=key,
                display_label=COMB_STRAT_DISPLAY_LABELS[key],
                explanation=COMB_STRAT_EXPLANATIONS[key],
                error=None,
            )
        # A method whose baseline or enhanced forecast is missing cannot be
        # compared with/without the test signal, so the row stays N/A --
        # `make_res_to_print` drops it from Fig_CombStrat on that suffix.
        return CombStratResult(
            eret=eret,
            eret_enh=eret_enh,
            label=key,
            display_label=f"{COMB_STRAT_DISPLAY_LABELS[key]} - N/A",
            explanation="",
            error=exc,
        )

    def _checkpoint_path(key: str) -> Path | None:
        return None if ckpt_dir is None else ckpt_dir / f"comb_strats_{key}.pkl"

    def _load_checkpoint(key: str) -> CombStratResult | None:
        """Return a previously computed method, or None to (re)compute it."""
        path = _checkpoint_path(key)
        if path is None or not path.is_file():
            return None
        try:
            with path.open("rb") as fh:
                payload = pickle.load(fh)
        except Exception as exc:  # noqa: BLE001 -- a bad checkpoint just recomputes
            LOGGER.warning(
                "Combination method `%s`: ignoring unreadable checkpoint %s (%s)",
                key, path, exc,
            )
            return None
        if not isinstance(payload, CombStratResult):
            LOGGER.warning(
                "Combination method `%s`: ignoring checkpoint %s (unexpected %s)",
                key, path, type(payload).__name__,
            )
            return None
        info = getattr(payload, "info", None) or {}
        if (
            info.get("signal_rule") != _COMB_SIGNAL_RULE
            or info.get("signal_window") != signal_window
        ):
            # A checkpoint of an earlier version (or of another window) holds
            # forecasts over other months; using it would mix two rules.
            LOGGER.warning(
                "Combination method `%s`: ignoring checkpoint %s (written under "
                "another rule for the months the test signal is used)",
                key, path,
            )
            return None
        saved = info.get("identity")
        if not isinstance(saved, dict):
            LOGGER.warning(
                "Combination method `%s`: ignoring checkpoint %s (it does not record "
                "the signal, database, window and toolkit version it was computed "
                "for); recomputing",
                key, path,
            )
            return None
        for name in _COMB_CHECKPOINT_FIELDS:
            if saved.get(name) != ckpt_identity.get(name):
                LOGGER.warning(
                    "Combination method `%s`: ignoring checkpoint %s (`%s` differs: "
                    "the checkpoint has %s, this run %s); recomputing",
                    key, path, name, saved.get(name), ckpt_identity.get(name),
                )
                return None
        LOGGER.info("Combination method `%s`: reusing checkpoint %s", key, path)
        return payload

    def _save_checkpoint(key: str, value: CombStratResult) -> None:
        path = _checkpoint_path(key)
        if path is None:
            return
        # Write to a sibling temp file and replace, so a kill mid-write cannot
        # leave a truncated checkpoint that the next run would trust.
        tmp = path.with_suffix(".pkl.tmp")
        try:
            with tmp.open("wb") as fh:
                pickle.dump(value, fh, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, path)
        except Exception as exc:  # noqa: BLE001 -- never fail the run over a checkpoint
            LOGGER.warning("Combination method `%s`: could not checkpoint (%s)", key, exc)
            return
        LOGGER.info("Combination method `%s`: checkpointed to %s", key, path)

    def _run_method(key: str, base_kwargs: dict, enh_kwargs: dict, fn) -> CombStratResult:
        """Checkpoint-aware, timed wrapper around :func:`_run_one`."""
        cached = _load_checkpoint(key)
        if cached is not None:
            return cached

        LOGGER.info(
            "Combination method `%s`: start at %s",
            key, datetime.now().isoformat(timespec="seconds"),
        )
        t0 = time.perf_counter()
        out = _signal_months(key, _run_one(key, base_kwargs, enh_kwargs, fn))
        LOGGER.info(
            "Combination method `%s`: done in %.1fs (%s)",
            key,
            time.perf_counter() - t0,
            "N/A" if out.error is not None else "ok",
        )
        _save_checkpoint(key, out)
        return out

    strats: dict[str, CombStratResult] = {}

    # ---- 1. Average rank -------------------------------------------------
    # MATLAB: makeAverageRank(filledAnoms, me)  /  makeAverageRank([fa fs], me)
    # Helper signature is TBD at port time; we pass base/enh anom dicts and
    # let the injected helper pull whatever it needs from the MultiIndex.
    strats["avg_rank"] = _run_method(
        "avg_rank",
        base_kwargs={"filled_anoms": base_dict},
        enh_kwargs={"filled_anoms": enh_dict},
        fn=avg_rank_fn,
    )

    # ---- 2. Weighted-average rank ---------------------------------------
    # MATLAB gathers per-anomaly portfolio returns from `resAnoms(i).pret(:,end)`
    # (i.e. the long-short leg) plus `resBasicSorts(1,1).res.pret(:,end)` for
    # the enhanced panel. Mirror that assembly here before handing off.
    #
    # Normalize res_anoms to a dict[name -> SortResult] once.
    if isinstance(res_anoms, AnomBenchmarkResults):
        anom_sorts: dict[str, SortResult] = dict(res_anoms.cond_sort)
    elif isinstance(res_anoms, dict):
        anom_sorts = dict(res_anoms)
    elif isinstance(res_anoms, list):
        # Positional list -- use `anom_labels` if provided, else the anomaly
        # names from `base_dict` (same order MATLAB uses).
        pos_labels = (
            anom_labels if anom_labels is not None else list(base_dict.keys())
        )
        if len(pos_labels) < len(res_anoms):
            raise ValueError(
                "anom_labels / filled_anoms columns shorter than res_anoms"
            )
        anom_sorts = {
            str(pos_labels[i]): sr for i, sr in enumerate(res_anoms)
        }
    else:
        anom_sorts = {}

    # Build the (dates x (nAnoms+1)) long-short-return matrix. We return a
    # DataFrame keyed by anomaly name; helper consumers can reshape as needed.
    ls_cols: dict[str, pd.Series] = {}
    for name in base_labels:
        sr = anom_sorts.get(name)
        ls_cols[name] = (
            sr.long_short if (sr is not None and sr.long_short is not None)
            else pd.Series(dtype="float64")
        )
    # Test-signal L/S leg -- match makeDendrogramResults's resolution logic.
    try:
        if basic_sort_factor_model is None:
            fm_list = res_basic_sorts.metadata.get("factor_models", FACTOR_MODELS)
            basic_sort_factor_model_resolved = (
                int(fm_list[0]) if len(fm_list) else 1
            )
        else:
            basic_sort_factor_model_resolved = int(basic_sort_factor_model)
        signal_ls = res_basic_sorts.basic[
            (basic_sort_row, basic_sort_factor_model_resolved)
        ].long_short
        if signal_ls is None:
            signal_ls = pd.Series(dtype="float64")
    except (KeyError, AttributeError):
        signal_ls = pd.Series(dtype="float64")
    pret_enh = dict(ls_cols)
    pret_enh[signal_key] = signal_ls
    pret_base = pd.DataFrame(ls_cols)
    pret_enh_df = pd.DataFrame(pret_enh)

    strats["weighted_avg_rank"] = _run_method(
        "weighted_avg_rank",
        base_kwargs={
            "filled_anoms": base_dict,
            "pret": pret_base,
            "time_period": time_period,
        },
        enh_kwargs={
            "filled_anoms": enh_dict,
            "pret": pret_enh_df,
            "time_period": time_period,
        },
        fn=weighted_avg_rank_fn,
    )

    # ---- 3. Fama-MacBeth -------------------------------------------------
    # MATLAB: makeFMBRes(filledAnoms, dates, timePeriod, ret)
    strats["fama_macbeth"] = _run_method(
        "fama_macbeth",
        base_kwargs={
            "fa": base_dict,
            "ret": returns,
            "time_period": time_period,
            "anom_labels": base_labels,
        },
        enh_kwargs={
            "fa": enh_dict,
            "ret": returns,
            "time_period": time_period,
            "anom_labels": enh_labels,
        },
        fn=fmb_fn,
    )

    # ---- 4. Partial Least Squares ---------------------------------------
    strats["pls"] = _run_method(
        "pls",
        base_kwargs={
            "filled_anoms": base_dict,
            "ret": returns,
            "time_period": time_period,
        },
        enh_kwargs={
            "filled_anoms": enh_dict,
            "ret": returns,
            "time_period": time_period,
        },
        fn=pls_fn,
    )

    # ---- 5. IPCA ---------------------------------------------------------
    # MATLAB: makeIPCARes(filledAnoms, keepRollAnoms, ret, rf, dates, timePeriod)
    strats["ipca"] = _run_method(
        "ipca",
        base_kwargs={
            "filled_anoms": base_dict,
            "keep_roll_anoms": keep_roll_anoms,
            "ret": returns,
            "rf": rf,
            "time_period": time_period,
        },
        enh_kwargs={
            "filled_anoms": enh_dict,
            "keep_roll_anoms": keep_roll_enh,
            "ret": returns,
            "rf": rf,
            "time_period": time_period,
        },
        fn=ipca_fn,
    )

    # ---- 6. LASSO --------------------------------------------------------
    strats["lasso"] = _run_method(
        "lasso",
        base_kwargs={
            "filled_anoms": base_dict,
            "ret": returns,
            "time_period": time_period,
        },
        enh_kwargs={
            "filled_anoms": enh_dict,
            "ret": returns,
            "time_period": time_period,
        },
        fn=lasso_fn,
    )

    # ---- Timekeeping -----------------------------------------------------
    if verbose:
        LOGGER.info(
            "Done with combination strategy results at %s (block took %.1fs).",
            datetime.now().isoformat(timespec="seconds"),
            time.perf_counter() - t_block,
        )

    n_success = sum(1 for cs in strats.values() if cs.error is None)
    n_failed = sum(1 for cs in strats.values() if cs.error is not None)

    return CombStratsResults(
        strats=strats,
        metadata={
            "time_period": time_period,
            "n_methods": len(strats),
            "n_success": n_success,
            "n_failed": n_failed,
            "anom_names": base_labels,
            "signal_key": signal_key,
            "basic_sort_row": basic_sort_row,
            "basic_sort_factor_model": basic_sort_factor_model,
            "n_jobs": n_workers,
            "checkpoint_dir": str(ckpt_dir) if ckpt_dir is not None else None,
            "checkpoint_identity": ckpt_identity,
            "elapsed_seconds": time.perf_counter() - t_block,
            # Which LASSO tuning produced this run. Recorded unconditionally so
            # a stored result says how it was cross-validated, not just that it
            # was. Only meaningful when `lasso_fn` is the default adapter.
            "lasso_cv_mode": lasso_cv_mode,
            "lasso_random_state": lasso_random_state,
            # When each method starts to use the test signal, and the
            # IPCA months its solver skipped (none are expected).
            "signal_window": signal_window,
            "signal_first_month": signal_first_month,
            "signal_start": {k: cs.signal_start for k, cs in strats.items()},
            "ipca_skipped": dict(
                (strats["ipca"].info or {}).get("ipca_skipped", {})
            ),
        },
    )


# ---------------------------------------------------------------------------
# makeLassoRes.m port
# ---------------------------------------------------------------------------
_LASSO_ROLL_WINDOW: int = 120


@dataclass
class LassoRes:
    """Container for the LASSO forecast-return combination signal.

    MATLAB equivalent: output of ``makeLassoRes.m`` (``eret`` / ``bhat``).

    Attributes
    ----------
    eret : pd.Series
        Forecast returns, MultiIndex (date, permno), aligned to the original
        returns panel (NaN outside the fit window).
    betas : pd.DataFrame
        Per-month LASSO coefficients (index = full returns date index,
        columns = anomaly names). NaN outside fit months / dropped anoms.
    metadata : dict
        Orchestration context.
    """

    eret: pd.Series = field(default_factory=pd.Series)
    betas: pd.DataFrame = field(default_factory=pd.DataFrame)
    metadata: dict[str, Any] = field(default_factory=dict)


# Precompute the Gram matrix (X'X) before coordinate descent. This is NOT
# optional here: a rolling window is ~600k rows x ~157 columns, and without a
# Gram matrix every descent iteration re-forms those inner products. Measured
# on the certification slice, `False` costs ~140x per fit month against
# sklearn's `"auto"` (which resolves to True whenever n_samples > n_features,
# i.e. always in this loop). It is spelled out rather than left to `"auto"` so
# nobody re-derives that the hard way.
_LASSO_PRECOMPUTE: bool = True

# Supported cross-validation fold schemes for the rolling LASSO.
#
# ``shuffled`` is the compatibility default and the only one that was ever run:
# five folds over *observations*, shuffled with a fixed seed, matching MATLAB's
# ``cvpartition(n, 'KFold', 5)``. Two stocks in the same month routinely land in
# different folds, so the validation fold is not independent of the training
# folds -- returns share a month's common shock, and the filled ranks share that
# month's cross-sectional standardization. The penalty it selects is therefore
# chosen against a correlated hold-out.
#
# ``month_grouped`` is the sensitivity mode: every observation from one
# calendar month lands in one fold, and the missing-value imputation is refitted
# inside each training fold rather than once over the whole window. It changes
# the estimator, so it is never the default; see :func:`make_lasso_res`.
_LASSO_CV_MODES: tuple[str, ...] = ("shuffled", "month_grouped")
_LASSO_N_FOLDS: int = 5

# sklearn's own LassoCV path defaults. Reproduced here because `month_grouped`
# tunes through GridSearchCV, which needs an explicit grid.
_LASSO_N_ALPHAS: int = 100
_LASSO_EPS: float = 1e-3

# State handed to a spawned LASSO worker by :func:`_init_lasso_pool_worker`.
_LASSO_POOL: dict[str, Any] = {}


def _lasso_alpha_grid(
    X: np.ndarray,
    y: np.ndarray,
    *,
    n_alphas: int = _LASSO_N_ALPHAS,
    eps: float = _LASSO_EPS,
) -> np.ndarray:
    """The descending alpha grid ``LassoCV`` would build for ``(X, y)``.

    ``LassoCV`` derives its own path and never exposes it before fitting, so
    the ``month_grouped`` mode -- which tunes through ``GridSearchCV`` in order
    to refit the imputer inside each fold -- has to build the same grid itself.

    The formula is sklearn's: with an intercept, centre both sides, take
    ``alpha_max = max|X_c' y_c| / n``, which is the smallest penalty that
    zeroes every coefficient, and lay ``n_alphas`` points log-uniformly down to
    ``eps * alpha_max``. Returned descending, so warm starts run from the
    sparsest fit, exactly as the coordinate-descent path does.
    """
    n = X.shape[0]
    Xc = X - X.mean(axis=0)
    yc = y - y.mean()
    alpha_max = float(np.abs(Xc.T @ yc).max()) / max(n, 1)
    if not np.isfinite(alpha_max) or alpha_max <= 0:
        # A design orthogonal to y: any penalty gives the null model. One point
        # keeps GridSearchCV well-formed.
        return np.array([np.finfo(float).eps])
    return np.logspace(np.log10(alpha_max), np.log10(alpha_max * eps), n_alphas)


def _init_lasso_pool_worker(shared: dict[str, Any]) -> None:
    """Open the packed panels read-only in a freshly spawned worker.

    The training panel is tens of gibibytes at full sample, so it is written
    once as ``.npy`` and opened here with ``mmap_mode="r"``: every worker maps
    the same pages and the OS page cache holds one copy, instead of pickling a
    private copy into each process.
    """
    global _LASSO_POOL
    _LASSO_POOL = {
        "x_train": np.load(shared["x_train"], mmap_mode="r"),
        "y_train": np.load(shared["y_train"], mmap_mode="r"),
        "x_now": np.load(shared["x_now"], mmap_mode="r"),
        "train_start": shared["train_start"],
        "train_end": shared["train_end"],
        "now_start": shared["now_start"],
        "now_end": shared["now_end"],
        "roll_window": int(shared["roll_window"]),
        "random_state": int(shared["random_state"]),
        "n_anoms": int(shared["n_anoms"]),
        "cv_mode": str(shared["cv_mode"]),
        "train_month": np.load(shared["train_month"], mmap_mode="r"),
    }


def _lasso_coef_shuffled(
    X: np.ndarray, y: np.ndarray, random_state: int
) -> np.ndarray:
    """Five shuffled observation folds -- the compatibility default.

    Unchanged from the original port: ``LassoCV`` over ``KFold(5,
    shuffle=True)``. Two stocks in the same month can land in different folds.
    """
    from sklearn.linear_model import LassoCV
    from sklearn.model_selection import KFold

    model = LassoCV(
        cv=KFold(n_splits=_LASSO_N_FOLDS, shuffle=True, random_state=random_state),
        random_state=random_state,
        precompute=_LASSO_PRECOMPUTE,
        n_jobs=1,  # the month pool owns the parallelism budget (D5)
    )
    model.fit(X, y)
    return model.coef_


def _lasso_coef_month_grouped(
    X: np.ndarray, y: np.ndarray, groups: np.ndarray, random_state: int
) -> np.ndarray | None:
    """Five month-grouped folds, with the imputer refitted inside each fold.

    Two departures from :func:`_lasso_coef_shuffled`, and they are the point of
    the mode:

    * **Folds respect the month.** ``GroupKFold`` on the calendar-month label
      keeps every observation from one month together, so a validation month is
      never predicted by a model that already saw its own cross-section. That
      removes the common-shock and common-standardization dependence between
      the training and validation folds, which is what makes the shuffled
      scheme's hold-out optimistic.
    * **Preprocessing is fitted inside the training folds.** The mean
      imputation runs in a ``Pipeline``, so each fold's column means come from
      that fold's training rows only. ``LassoCV`` cannot express that -- it
      takes an already-imputed matrix -- hence ``GridSearchCV`` over the grid
      :func:`_lasso_alpha_grid` reproduces.

    ``GroupKFold`` is unshuffled and deterministic; ``random_state`` is
    threaded in only so the mode has a seed on record, and it is unused here.
    Returns ``None`` when there are fewer months than folds.

    The fold loop is spelled out rather than handed to ``GridSearchCV`` because
    the grid is 100 penalties wide: ``lasso_path`` walks the whole path once per
    fold with warm starts, which is what ``LassoCV`` does internally, while
    ``GridSearchCV`` would refit from scratch 100 times per fold. With no
    missing values the two agree exactly with ``LassoCV`` given the same splits.
    """
    from sklearn.linear_model import Lasso, lasso_path
    from sklearn.model_selection import GroupKFold

    n_groups = int(np.unique(groups).size)
    if n_groups < 2:
        return None
    n_splits = min(_LASSO_N_FOLDS, n_groups)

    def impute(block: np.ndarray, means: np.ndarray) -> np.ndarray:
        bad = np.where(~np.isfinite(block))
        if not bad[0].size:
            return block
        out = block.copy()
        out[bad] = np.take(means, bad[1])
        return out

    # The grid's endpoints come from the whole window, exactly as `LassoCV`
    # derives its path from all the data before splitting. Every *fitted* model
    # below still imputes from its own training fold.
    window_means = np.nan_to_num(np.nanmean(X, axis=0), nan=0.0)
    alphas = _lasso_alpha_grid(impute(X, window_means), y)

    mse = np.zeros((n_splits, alphas.size), dtype=float)
    for k, (tr, va) in enumerate(GroupKFold(n_splits=n_splits).split(X, y, groups)):
        means = np.nan_to_num(np.nanmean(X[tr], axis=0), nan=0.0)
        X_tr, X_va = impute(X[tr], means), impute(X[va], means)
        y_tr = y[tr]

        # `lasso_path` fits no intercept, so centre as `fit_intercept=True`
        # would and rebuild it from the training fold's own centres.
        xc, yc = X_tr.mean(axis=0), y_tr.mean()
        _, coefs, _ = lasso_path(X_tr - xc, y_tr - yc, alphas=alphas)
        pred = (X_va - xc) @ coefs + yc
        mse[k] = ((pred - y[va][:, None]) ** 2).mean(axis=0)

    best = alphas[int(np.argmin(mse.mean(axis=0)))]
    final = Lasso(alpha=best, precompute=_LASSO_PRECOMPUTE, random_state=random_state)
    final.fit(impute(X, window_means), y)
    return final.coef_


def _lasso_fit_month(
    i: int,
    *,
    x_train: np.ndarray,
    y_train: np.ndarray,
    x_now: np.ndarray,
    train_start: np.ndarray,
    train_end: np.ndarray,
    now_start: np.ndarray,
    now_end: np.ndarray,
    roll_window: int,
    random_state: int,
    n_anoms: int,
    cv_mode: str = "shuffled",
    train_month: np.ndarray | None = None,
) -> tuple[int, np.ndarray | None, np.ndarray | None]:
    """Fit one rolling LASSO month.

    Returns ``(i, beta_row, eret_rows)``; either payload is None when the
    month is skipped, exactly where the original loop used ``continue``.

    Both the serial and the pooled paths call this, so the two cannot drift.

    ``cv_mode`` picks the fold scheme; see :data:`_LASSO_CV_MODES`. Row
    selection, column selection and the forecast are identical in both modes,
    so any difference between them is the tuning and nothing else.
    """
    # The training window is months i-roll_window+1 .. i, and the panel is
    # sorted by date, so it is one contiguous row range -- no `isin` scan over
    # the whole stacked panel per month.
    lo = int(train_start[i - roll_window + 1])
    hi = int(train_end[i])
    if hi <= lo:
        return i, None, None

    y = np.asarray(y_train[lo:hi], dtype=float)
    X = np.asarray(x_train[lo:hi], dtype=float)

    col_ok = []
    for j in range(n_anoms):
        col = X[:, j]
        finite = col[np.isfinite(col)]
        if finite.size > 0 and np.nansum(np.abs(finite)) != 0:
            col_ok.append(j)
    if not col_ok:
        return i, None, None
    col_ok_arr = np.asarray(col_ok, dtype=np.intp)

    X_raw = X[:, col_ok_arr]
    # Window-level mean imputation. `col_means` is fitted on the whole training
    # window, which is inside the training cutoff and so timing-safe, but it is
    # *not* inside a CV fold -- see the `month_grouped` branch below.
    col_means = np.nanmean(X_raw, axis=0)
    X_use = X_raw
    inds = np.where(~np.isfinite(X_use))
    if inds[0].size:
        X_use = X_use.copy()
        X_use[inds] = np.take(col_means, inds[1])
    row_ok = np.isfinite(y) & np.isfinite(X_use).all(axis=1)
    if row_ok.sum() < 10:
        return i, None, None
    y_fit = y[row_ok]
    X_fit = X_use[row_ok]

    try:
        if cv_mode == "shuffled":
            coef = _lasso_coef_shuffled(X_fit, y_fit, random_state)
        elif cv_mode == "month_grouped":
            if train_month is None:
                raise ValueError("month_grouped folds need `train_month`")
            groups = np.asarray(train_month[lo:hi])[row_ok]
            # Feed the *unimputed* design so the imputer refits per fold.
            X_holes = np.where(np.isfinite(X_raw[row_ok]), X_raw[row_ok], np.nan)
            coef = _lasso_coef_month_grouped(X_holes, y_fit, groups, random_state)
        else:
            raise ValueError(
                f"cv_mode must be one of {_LASSO_CV_MODES}, got {cv_mode!r}"
            )
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 -- mirror the original `continue`
        LOGGER.warning("LassoCV failed at month index %d: %s", i, exc)
        return i, None, None
    if coef is None:
        return i, None, None

    beta_row = np.full(n_anoms, np.nan, dtype=float)
    beta_row[col_ok_arr] = coef

    ns, ne = int(now_start[i]), int(now_end[i])
    if ne <= ns:
        return i, beta_row, None

    X_now_use = np.asarray(x_now[ns:ne][:, col_ok_arr], dtype=float)
    inds = np.where(~np.isfinite(X_now_use))
    if inds[0].size:
        X_now_use = X_now_use.copy()
        means_pred = np.nanmean(X_now_use, axis=0)
        bad = ~np.isfinite(means_pred)
        means_pred = np.where(bad, col_means, means_pred)
        X_now_use[inds] = np.take(means_pred, inds[1])
    return i, beta_row, X_now_use @ coef


def _lasso_pool_task(i: int) -> tuple[int, np.ndarray | None, np.ndarray | None]:
    """Worker entry: one month against :data:`_LASSO_POOL`.

    Pinned to one BLAS thread. Coordinate descent and the Gram build underneath
    it are already threaded, so N worker processes each opening a full thread
    pool would put N x n_cores threads on n_cores and spend the run in the
    scheduler. The month pool owns the parallelism budget (D5).
    """
    try:
        from threadpoolctl import threadpool_limits
    except ImportError:  # pragma: no cover - threadpoolctl ships with sklearn
        return _lasso_fit_month(i, **_LASSO_POOL)
    with threadpool_limits(limits=1):
        return _lasso_fit_month(i, **_LASSO_POOL)


def make_lasso_res(
    filled_anoms: pd.DataFrame | dict[str, pd.Series] | np.ndarray,
    returns: pd.Series,
    *,
    time_period: tuple[pd.Timestamp | int, pd.Timestamp | int] | None = None,
    anom_labels: list[str] | None = None,
    roll_window: int = _LASSO_ROLL_WINDOW,
    random_state: int = 0,
    cv_mode: str = "shuffled",
    n_jobs: int = 1,
    verbose: bool = True,
) -> LassoRes:
    """
    Build the LASSO forecast-return combination signal.

    MATLAB equivalent: ``makeLassoRes.m``. Rolling-window LASSO with 5-fold CV.

    Loop bounds match MATLAB ``for i = (s+T):e`` (0-indexed:
    ``range(roll_window, n_months)``) with training window
    ``eval_dates[i - roll_window + 1 : i + 1]`` (includes month ``i``).
    Forecast at ``i`` uses contemporaneous anomalies ``X[i] @ coef``.
    ``betas`` is reindexed to the full returns date index.

    Parameters
    ----------
    random_state : int, default 0
        Seed for the cross-validation fold assignment. MATLAB's partition is
        unseeded, but at this sample size the choice of seed is immaterial --
        see the note below. Recorded in ``metadata["random_state"]``.
    cv_mode : {"shuffled", "month_grouped"}, default "shuffled"
        Which cross-validation folds tune the penalty. Recorded in
        ``metadata["cv_mode"]``.

        ``"shuffled"`` is the documented compatibility default and the mode
        every stored result was produced under: five folds over *observations*,
        shuffled with ``random_state``, reproducing MATLAB's
        ``cvpartition(n, 'KFold', 5)``.

        ``"month_grouped"`` is a sensitivity mode. Every observation from one
        calendar month lands in the same fold, and the missing-value imputation
        is refitted inside each training fold. Shuffled observation folds put
        stocks from the same month on both sides of the split, so the hold-out
        shares that month's common return shock and its cross-sectional
        standardization with the training rows; the penalty is then chosen
        against a correlated validation set and tends to come out too weak.
        Month-grouped folds remove that dependence. The two can select
        different penalties -- that is the point of running it -- so it changes
        the estimator and is never the default.
    n_jobs : int, default 1
        Months fitted in parallel. Purely a speed knob; the fitted path does
        not depend on it.

    Notes
    -----
    MATLAB's ``lasso(x, y, 'CV', 5)`` assigns observations to folds with
    ``cvpartition(n, 'KFold', 5)``, i.e. at random. ``LassoCV(cv=5)`` would
    instead expand to an *unshuffled* ``KFold(5)``, which on a panel sorted by
    (date, permno) makes each fold a contiguous 24-month block -- a
    time-series CV, and a materially different estimator: it selects a penalty
    one to two orders of magnitude stronger (on the MPE zoo, 20 non-zero betas
    against 149 in the 2005-2015 window) and the resulting forecast
    cross-section ranks only 0.79 against the random-fold one. The folds are
    therefore shuffled here to match MATLAB. Seeding is a Python-only addition;
    with ~500k observations per window the selected penalty is
    the same to four significant figures across seeds, so MATLAB's unseeded
    partition is reproducible in practice.

    Residual differences from MATLAB's ``lasso`` that no seeding can remove:
    it standardizes ``x`` by default and back-transforms the coefficients,
    and it builds its own geometric lambda grid. Both are near-neutral here
    because filled anomaly signals are uniform ranks on a common scale.
    """
    if cv_mode not in _LASSO_CV_MODES:
        raise ValueError(
            f"cv_mode must be one of {_LASSO_CV_MODES}, got {cv_mode!r}"
        )

    # Fail here, in the parent, rather than inside every spawned worker: the
    # fitting itself imports sklearn in `_lasso_fit_month`.
    try:
        from sklearn.linear_model import LassoCV  # noqa: F401  (availability probe)
        from sklearn.model_selection import KFold  # noqa: F401  (availability probe)
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "make_lasso_res requires scikit-learn (`pip install scikit-learn`)"
        ) from exc

    anoms_dict = _coerce_anoms_to_dict(
        filled_anoms, signal_index=returns.index, labels=anom_labels
    )
    anom_names = list(anoms_dict.keys())
    n_anoms = len(anom_names)
    if n_anoms == 0:
        raise ValueError("filled_anoms must contain at least one anomaly signal")

    if verbose:
        LOGGER.info(
            "Now working on LASSO with %d anomalies. Run started at %s.",
            n_anoms,
            datetime.now().isoformat(timespec="seconds"),
        )

    anoms_df_full = pd.concat(anoms_dict, axis=1)
    anoms_df_full.columns = anom_names
    anoms_df_full = anoms_df_full.reindex(returns.index)

    # Lagged X for training (MATLAB: filledAnoms(s-1:e-1)); contemporaneous for forecast.
    anoms_lagged_full = _calendar_lag_panel(anoms_df_full, 1)

    ret_sliced = _slice_panel_by_time(returns, time_period)
    ret_sliced = pd.to_numeric(ret_sliced, errors="coerce")
    anoms_sliced = _slice_panel_by_time(anoms_df_full, time_period)
    anoms_lagged = _slice_panel_by_time(anoms_lagged_full, time_period)
    anoms_sliced = anoms_sliced.reindex(ret_sliced.index)
    anoms_lagged = anoms_lagged.reindex(ret_sliced.index)

    eval_dates = ret_sliced.index.get_level_values(0).unique().sort_values()
    n_months = len(eval_dates)

    # betas: full original returns date index (MATLAB bhat = nan(nMonths, nAnoms))
    full_dates = returns.index.get_level_values(0).unique().sort_values()
    betas = pd.DataFrame(np.nan, index=full_dates, columns=anom_names, dtype="float64")

    # ---- Pack the panels onto contiguous, date-sorted arrays -------------
    # The old loop rebuilt `index.get_level_values(0)` and ran `.isin` over the
    # whole stacked panel once per month -- O(n_months x n_rows) index work
    # before a single coefficient was fitted. Sorting by date once turns each
    # window into a row *slice*, found with searchsorted.
    y_panel = ret_sliced.rename("y")
    train_panel = anoms_lagged.copy()
    train_panel["y"] = y_panel
    train_panel = train_panel.dropna(subset=["y"])
    x_cols = list(anom_names)
    has_x = train_panel[x_cols].notna().any(axis=1)
    train_panel = train_panel.loc[has_x]

    date_to_pos = pd.Series(np.arange(n_months), index=eval_dates)

    train_month = date_to_pos.reindex(
        train_panel.index.get_level_values(0)
    ).to_numpy()
    order = np.argsort(train_month, kind="stable")
    train_month = train_month[order]
    x_train = np.ascontiguousarray(
        train_panel[x_cols].to_numpy(dtype=float)[order]
    )
    y_train = np.ascontiguousarray(
        train_panel["y"].to_numpy(dtype=float)[order]
    )
    train_start = np.searchsorted(train_month, np.arange(n_months), side="left")
    train_end = np.searchsorted(train_month, np.arange(n_months), side="right")

    # The forecast panel is `anoms_sliced` reindexed to `ret_sliced.index`, so
    # its rows already sit in the same (date, permno) order the original
    # `.xs(d, level="date")` walked.
    now_month = date_to_pos.reindex(
        anoms_sliced.index.get_level_values(0)
    ).to_numpy()
    now_order = np.argsort(now_month, kind="stable")
    now_month = now_month[now_order]
    x_now = np.ascontiguousarray(
        anoms_sliced[x_cols].to_numpy(dtype=float)[now_order]
    )
    now_index = anoms_sliced.index[now_order]
    now_start = np.searchsorted(now_month, np.arange(n_months), side="left")
    now_end = np.searchsorted(now_month, np.arange(n_months), side="right")

    fit_months = list(range(roll_window, n_months))
    n_workers = max(1, int(n_jobs))
    eret_arr = np.full(x_now.shape[0], np.nan, dtype=float)

    def _absorb(payload: tuple[int, np.ndarray | None, np.ndarray | None]) -> None:
        i, beta_row, eret_rows = payload
        if beta_row is not None:
            betas.loc[eval_dates[i], :] = beta_row
        if eret_rows is not None:
            eret_arr[int(now_start[i]):int(now_end[i])] = eret_rows

    kwargs = {
        "x_train": x_train,
        "y_train": y_train,
        "x_now": x_now,
        "train_start": train_start,
        "train_end": train_end,
        "now_start": now_start,
        "now_end": now_end,
        "roll_window": roll_window,
        "random_state": random_state,
        "n_anoms": n_anoms,
        "cv_mode": cv_mode,
        # Calendar-month label per training row, for `month_grouped` folds.
        "train_month": train_month,
    }

    n_workers = pool_worker_count(n_workers, what="LASSO")
    if n_workers <= 1 or len(fit_months) <= 1:
        for i in fit_months:
            if verbose and ((i + 1) % roll_window == 0):
                LOGGER.info(
                    "Done until %s @ %s.",
                    eval_dates[i].strftime("%Y-%m"),
                    datetime.now().isoformat(timespec="seconds"),
                )
            _absorb(_lasso_fit_month(i, **kwargs))
    else:
        # Months are independent: each fits its own window with a fixed seed,
        # so a pool changes the schedule, not the arithmetic. The panels go to
        # disk as .npy and workers mmap them, so the OS page cache holds one
        # copy rather than one per worker.
        tmpdir = tempfile.mkdtemp(prefix="aa_lasso_")
        try:
            shared: dict[str, Any] = {
                k: v for k, v in kwargs.items() if not isinstance(v, np.ndarray)
            }
            for name in ("x_train", "y_train", "x_now", "train_month"):
                path = os.path.join(tmpdir, f"{name}.npy")
                np.save(path, kwargs[name])
                shared[name] = path
            for name in ("train_start", "train_end", "now_start", "now_end"):
                shared[name] = kwargs[name]

            done = 0
            with ProcessPoolExecutor(
                max_workers=min(n_workers, len(fit_months)),
                mp_context=spawn_context(),
                initializer=_init_lasso_pool_worker,
                initargs=(shared,),
            ) as pool:
                futures = [pool.submit(_lasso_pool_task, i) for i in fit_months]
                for fut in as_completed(futures):
                    _absorb(fut.result())
                    done += 1
                    if verbose and done % roll_window == 0:
                        LOGGER.info(
                            "Done with %d/%d LASSO months @ %s.",
                            done,
                            len(fit_months),
                            datetime.now().isoformat(timespec="seconds"),
                        )
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)

    eret = pd.Series(np.nan, index=returns.index, dtype="float64", name="eret")
    fitted = np.isfinite(eret_arr)
    if fitted.any():
        eret.loc[now_index[fitted]] = eret_arr[fitted]

    if verbose:
        LOGGER.info(
            "Done with LASSO at %s.",
            datetime.now().isoformat(timespec="seconds"),
        )

    return LassoRes(
        eret=eret,
        betas=betas,
        metadata={
            "time_period": time_period,
            "roll_window": roll_window,
            "n_anoms": n_anoms,
            "anom_names": anom_names,
            "random_state": random_state,
            "cv_mode": cv_mode,
            "cv_n_folds": _LASSO_N_FOLDS,
        },
    )


# ---------------------------------------------------------------------------
# makePLSRes.m port  -- Partial Least Squares (Light, Maslov, Rytchkov 2017)
# ---------------------------------------------------------------------------


@dataclass
class PLSRes:
    """Container for the Partial Least Squares forecast-return combination signal.

    MATLAB equivalent: output of ``makePLSRes.m`` (the ``eret`` matrix).

    Attributes
    ----------
    eret : pd.Series
        Forecast returns, MultiIndex (date, permno). NaN outside the
        evaluation window or where the 2-step PLS regression was undefined.
        Aligned to the original (pre-slice) ``returns`` panel.
    lambdas : pd.DataFrame
        Per-month step-1 slopes from the univariate regression of
        ``ret_t`` on each lagged anomaly (no intercept). Index = dates,
        columns = anomaly names. NaN where the univariate fit had no data.
    metadata : dict
        Orchestration context: time period and anomaly names.
    """

    eret: pd.Series = field(default_factory=pd.Series)
    lambdas: pd.DataFrame = field(default_factory=pd.DataFrame)
    metadata: dict[str, Any] = field(default_factory=dict)


def _nanols_univariate_beta(y: np.ndarray, x: np.ndarray) -> float:
    """Univariate no-intercept OLS slope, NaN-row dropped. Mirrors MATLAB ``nanols(y, x)``.

    Given two 1-D arrays ``y`` and ``x``, drops rows where either is NaN, then
    returns ``sum(x*y) / sum(x*x)`` -- the OLS slope of ``y`` on ``x`` without
    an intercept. Returns NaN if fewer than 2 complete-case rows or if the
    denominator is 0 / NaN. This matches MATLAB ``nanols`` (which calls
    ``ols`` under the hood and returns ``res.beta`` scalar for a single
    regressor).
    """
    y = np.asarray(y, dtype=float).ravel()
    x = np.asarray(x, dtype=float).ravel()
    ok = np.isfinite(y) & np.isfinite(x)
    if ok.sum() < 2:
        return np.nan
    xv = x[ok]
    yv = y[ok]
    denom = float(np.dot(xv, xv))
    if not np.isfinite(denom) or denom == 0.0:
        return np.nan
    return float(np.dot(xv, yv) / denom)


def make_pls_res(
    filled_anoms: pd.DataFrame | dict[str, pd.Series] | np.ndarray,
    ret: pd.Series,
    *,
    time_period: tuple[pd.Timestamp | int, pd.Timestamp | int] | None = None,
    anom_labels: list[str] | None = None,
    verbose: bool = True,
) -> PLSRes:
    """
    Build the Partial Least Squares forecast-return combination signal.

    MATLAB equivalent: ``makePLSRes.m`` (Novy-Marx / Velikov 2026), which
    implements the Light / Maslov / Rytchkov (2017) 2-step procedure. For
    each month ``t`` in the evaluation window:

      1. **Step 1 (time-0 loadings).** For each anomaly ``j``, run a
         univariate no-intercept OLS of ``ret_t`` (cross-section of stock
         returns this month) on ``lagX[:, j]`` (cross-section of the lagged
         anomaly). The slope is stored as ``lambda_t[j]`` -- a per-anomaly
         "loading" that captures how predictive last-month's signal was for
         this month's returns.

      2. **Step 2 (fitted values).** For each stock ``s``, run a univariate
         no-intercept OLS of ``X_t[s, :]`` (this month's anomaly values at
         stock ``s``, across anomalies) on ``lambda_t`` (the vector of
         per-anomaly loadings). The slope is stored as ``eret[t, s]`` -- the
         forecast return for stock ``s`` at month ``t``.

    Unlike the FMB / LASSO helpers, there is **no rolling window** here: each
    month's ``eret`` uses only that month's step-1 and step-2 regressions.

    Parameters
    ----------
    filled_anoms : DataFrame, dict, or 3-D ndarray
        Filled anomaly signals (no NaN from missing-data gaps). DataFrame:
        MultiIndex (date, permno) x anomaly columns. dict: ``{name: Series}``
        each MultiIndex (date, permno). 3-D ndarray: MATLAB-style
        ``(nMonths, nStocks, nAnoms)`` -- requires ``anom_labels`` and is
        interpreted relative to ``ret``'s panel.
    ret : pd.Series
        Stock returns (decimals), MultiIndex (date, permno). Used both as the
        dependent variable in step 1 and to fix the output panel shape.
    time_period : tuple, optional
        ``(start, end)`` as YYYYMM ints or Timestamps. Subset applied before
        running the monthly regressions. Matches MATLAB ``timePeriod``.
    anom_labels : list[str], optional
        Required when ``filled_anoms`` is a 3-D ndarray; ignored otherwise.
    verbose : bool
        If True, log progress every 120 months (MATLAB cadence).

    Returns
    -------
    PLSRes

    Notes
    -----
    - Output ``eret`` is re-indexed to the *original* (pre-slice) ``ret``
      panel so pipeline-downstream callers can align without gaps. Values
      outside ``time_period`` are NaN.
    - MATLAB ``nanols(y, x)`` with a single-column ``x`` is a no-intercept
      univariate regression: ``beta = sum(x*y) / sum(x*x)`` over
      complete-case rows. We match that exactly via
      ``_nanols_univariate_beta`` -- no intercept is added in either step.
    - The MATLAB loop uses ``filledAnoms(i-1, :, :)`` to read ``X_{t-1}``,
      which will access the row *before* the evaluation-window start.
      In Python we shift on the full (pre-slice) panel then slice, so the
      first evaluation month can use the lag from outside the window.
    """
    # ---------------- Normalize inputs -------------------------------------
    anoms_dict = _coerce_anoms_to_dict(
        filled_anoms, signal_index=ret.index, labels=anom_labels
    )
    anom_names = list(anoms_dict.keys())
    n_anoms = len(anom_names)
    if n_anoms == 0:
        raise ValueError("filled_anoms must contain at least one anomaly signal")

    if verbose:
        LOGGER.info(
            "Now working on Partial Least Squares with %d anomalies. Run started at %s.",
            n_anoms,
            datetime.now().isoformat(timespec="seconds"),
        )

    # Stack anomalies into a DataFrame over the union of (date, permno).
    anoms_df_full = pd.concat(anoms_dict, axis=1)
    anoms_df_full.columns = anom_names

    # Align the full-panel anomaly frame to the full-panel return index so
    # the rectangular (date x permno) view matches what MATLAB assumes.
    anoms_df_full = anoms_df_full.reindex(ret.index)

    # Shift by 1 calendar month on the FULL panel so that the first in-window
    # month can use a lag drawn from outside the slice -- mirrors MATLAB
    # ``filledAnoms(i-1, :, :)`` when ``i == s``.
    anoms_lagged_full = _calendar_lag_panel(anoms_df_full, 1)

    # ---------------- Time-period subset -----------------------------------
    ret_sliced = _slice_panel_by_time(ret, time_period)
    ret_sliced = pd.to_numeric(ret_sliced, errors="coerce")
    anoms_sliced = _slice_panel_by_time(anoms_df_full, time_period)
    anoms_lagged = _slice_panel_by_time(anoms_lagged_full, time_period)

    # Reindex to the sliced-return index so per-date cross-sections line up.
    anoms_sliced = anoms_sliced.reindex(ret_sliced.index)
    anoms_lagged = anoms_lagged.reindex(ret_sliced.index)

    # Dates in the evaluation window (month-ends).
    eval_dates = ret_sliced.index.get_level_values(0).unique().sort_values()

    # ---------------- Monthly loop ----------------------------------------
    lambdas = pd.DataFrame(
        index=eval_dates, columns=anom_names, dtype="float64"
    )
    # Per-month forecasts; assembled into a single Series at the end.
    temp_eret: dict[pd.Timestamp, pd.Series] = {}

    # Convenience: per-date views.
    ret_by_date = ret_sliced.groupby(level="date")

    # MATLAB progress cadence: log every 120 months of the evaluation loop.
    _log_every = 120

    for i, d in enumerate(eval_dates, start=1):
        if verbose and (i % _log_every == 0):
            LOGGER.info(
                "Done until %s @ %s.",
                d.strftime("%Y-%m"),
                datetime.now().isoformat(timespec="seconds"),
            )

        # ---- Fetch this month's return cross-section ----------------------
        try:
            y_ser = ret_by_date.get_group(d)
        except KeyError:
            continue

        # ---- Fetch lagged-anom cross-section (X_{t-1}) at this month -----
        try:
            lagX = anoms_lagged.xs(d, level="date", drop_level=False)
        except KeyError:
            continue
        lagX = lagX.reindex(y_ser.index)

        # ---- Fetch this month's anom cross-section (X_t) ------------------
        try:
            x_t = anoms_sliced.xs(d, level="date", drop_level=False)
        except KeyError:
            continue
        x_t = x_t.reindex(y_ser.index)

        y_arr = y_ser.to_numpy(dtype=float)  # shape (n_stocks,)
        lagX_arr = lagX.to_numpy(dtype=float)  # shape (n_stocks, n_anoms)
        xt_arr = x_t.to_numpy(dtype=float)  # shape (n_stocks, n_anoms)

        # ---- Step 1: per-anomaly univariate no-intercept OLS --------------
        # For each anomaly j, regress y on lagX[:, j] (with NaN rows dropped)
        # and store the slope as lambda_t[j]. Mirrors MATLAB:
        #   for j = 1:nAnoms
        #       res = nanols(y, x(:, j));
        #       lambda(i, j) = res.beta;
        #   end
        lam_t = np.full(n_anoms, np.nan, dtype=float)
        for j in range(n_anoms):
            lam_t[j] = _nanols_univariate_beta(y_arr, lagX_arr[:, j])

        # Record the loading row (NaN where undefined).
        lambdas.loc[d, :] = lam_t

        # ---- Step 2: per-stock univariate no-intercept OLS ---------------
        # For each stock s, regress X_t[s, :] on lambda_t (with NaN rows
        # dropped) and store the slope as eret[t, s]. Mirrors MATLAB:
        #   for j = 1:nStocks
        #       res = nanols(xt(j,:)', lambda(i,:)');
        #       eret(i, j) = res.beta;
        #   end
        n_stocks = xt_arr.shape[0]
        eret_t = np.full(n_stocks, np.nan, dtype=float)
        # If all loadings are NaN there's nothing to regress on; skip.
        if np.any(np.isfinite(lam_t)):
            for s in range(n_stocks):
                eret_t[s] = _nanols_univariate_beta(xt_arr[s, :], lam_t)

        temp_eret[d] = pd.Series(eret_t, index=y_ser.index)

    # ---------------- Assemble output panel -------------------------------
    if temp_eret:
        eret_sliced = pd.concat(temp_eret.values()).sort_index()
    else:
        eret_sliced = pd.Series(dtype="float64")

    # Re-index back to the original returns panel (matches MATLAB:
    # ``eret = nan(nMonths, nStocks); eret(s:e, :) = temp_eret``).
    eret = pd.Series(np.nan, index=ret.index, dtype="float64", name="eret")
    if not eret_sliced.empty:
        eret.loc[eret_sliced.index] = eret_sliced.to_numpy()

    if verbose:
        LOGGER.info(
            "Done with PLS at %s.",
            datetime.now().isoformat(timespec="seconds"),
        )

    return PLSRes(
        eret=eret,
        lambdas=lambdas,
        metadata={
            "time_period": time_period,
            "n_anoms": n_anoms,
            "anom_names": anom_names,
        },
    )


# ---------------------------------------------------------------------------
# makeIPCARes.m port  -- Instrumented Principal Components Analysis (Kelly,
# Pruitt, Su 2019). MATLAB's ``makeIPCARes`` calls ``runIPCAforMonth``, whose
# alternating-least-squares kernel ``num_IPCA_estimate_ALS`` is vendored
# alongside it in ``Functions/Assay functions/`` and uses nothing outside base
# MATLAB. Both are ported below.
# ---------------------------------------------------------------------------
_IPCA_N_FACTORS: int = 5
_IPCA_MAX_ITER: int = 10_000
_IPCA_TOL: float = 1e-6


@dataclass
class IPCARes:
    """Container for the Instrumented PCA forecast-return combination signal.

    MATLAB equivalent: output of ``makeIPCARes.m`` (the ``eret`` matrix).

    Attributes
    ----------
    eret : pd.Series
        Forecast returns, MultiIndex (date, permno), aligned to the original
        returns panel (NaN outside the estimation window).
    gamma_beta : dict[pd.Timestamp, np.ndarray]
        Per-month ``(nKeptAnoms + 1) x K`` characteristic-to-beta loading
        matrix, constant row last.
    lambda_ : pd.DataFrame
        Per-month mean latent factor path (index = forecast month, K columns).
    diagnostics : pd.DataFrame
        Per-month solver diagnostics: kept-anomaly count, cross-section size,
        ALS iteration count and the tolerance reached.
    metadata : dict
        Orchestration context: time period, anomaly names, solver settings.
    """

    eret: pd.Series = field(default_factory=pd.Series)
    gamma_beta: dict[Any, np.ndarray] = field(default_factory=dict)
    lambda_: pd.DataFrame = field(default_factory=pd.DataFrame)
    diagnostics: pd.DataFrame = field(default_factory=pd.DataFrame)
    metadata: dict[str, Any] = field(default_factory=dict)


def _ipca_als_step(
    gamma_old: np.ndarray,
    W: np.ndarray,
    X: np.ndarray,
    nts: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """One alternating-least-squares sweep of the IPCA estimator.

    Port of ``num_IPCA_estimate_ALS.m``, no-pre-specified-factor branch (the
    only one ``runIPCAforMonth`` reaches, since it calls the 4-argument form).

    Parameters
    ----------
    gamma_old : ndarray, shape (L, K)
        Previous iteration's ``GammaBeta``.
    W : ndarray, shape (L, L, T)
        ``Z_t' Z_t / N_t`` per month.
    X : ndarray, shape (L, T)
        ``Z_t' r_t / N_t`` per month.
    nts : ndarray, shape (T,)
        Cross-section size per month.

    Returns
    -------
    (gamma_new, f_new)
        ``GammaBeta`` (L, K) and the factor path (K, T), both under MATLAB's
        identification convention: ``gamma_new`` orthonormal and each factor's
        time-series mean non-negative.

    Notes
    -----
    MATLAB accumulates equation (7) as ``kron(W_t, F_t F_t')`` and
    ``kron(X_t, F_t)``, then reads the solution back with
    ``reshape(vec, Ktilde, L)'``. ``kron`` puts the ``K`` index fastest, so the
    stacked vector is ``Gamma`` in C order -- which is why the tensor products
    below are built with the ``K`` axis inside the ``L`` axis and reshaped
    directly to ``(L, K)``.
    """
    L, k = gamma_old.shape
    T = int(nts.shape[0])

    # Equation (6): F_t = (G' W_t G) \ (G' X_t)
    gtwg = np.einsum("il,ijt,jm->lmt", gamma_old, W, gamma_old, optimize=True)
    gtx = gamma_old.T @ X
    f_new = np.empty((k, T), dtype=float)
    for t in range(T):
        f_new[:, t] = np.linalg.solve(gtwg[:, :, t], gtx[:, t])

    # Equation (7)
    numer = np.einsum("lt,kt,t->lk", X, f_new, nts, optimize=True).reshape(L * k)
    ff = f_new[:, None, :] * f_new[None, :, :]
    denom = np.tensordot(W, ff * nts, axes=([2], [2])).transpose(0, 2, 1, 3)
    gamma_new = np.linalg.solve(denom.reshape(L * k, L * k), numer).reshape(L, k)

    # GammaBeta orthonormal, F orthogonal. MATLAB `chol(M, 'upper')` returns
    # R with R'R = M; numpy's Cholesky returns the lower factor.
    r1 = np.linalg.cholesky(gamma_new.T @ gamma_new).T
    r2, _, _ = np.linalg.svd(r1 @ f_new @ f_new.T @ r1.T)
    gamma_new = np.linalg.solve(r1.T, gamma_new.T).T @ r2  # (Gamma / R1) * R2
    f_new = np.linalg.solve(r2, r1 @ f_new)

    # Sign convention: each factor's mean is non-negative.
    sg = np.sign(f_new.mean(axis=1))
    sg[sg == 0] = 1.0
    return gamma_new * sg[None, :], f_new * sg[:, None]


# State handed to a spawned IPCA worker by :func:`_init_ipca_pool_worker`.
_IPCA_POOL: dict[str, Any] = {}


def _init_ipca_pool_worker(shared: dict[str, Any]) -> None:
    """Open the packed per-month moments read-only in a spawned worker."""
    global _IPCA_POOL
    _IPCA_POOL = {
        "W_all": np.load(shared["W_all"], mmap_mode="r"),
        "X_all": np.load(shared["X_all"], mmap_mode="r"),
        "nts_all": np.load(shared["nts_all"], mmap_mode="r"),
        "z_all": np.load(shared["z_all"], mmap_mode="r"),
        "keep_wide": (
            None if shared["keep_wide"] is None
            else np.load(shared["keep_wide"], mmap_mode="r")
        ),
        "row_start": shared["row_start"],
        "row_end": shared["row_end"],
        "roll_window": int(shared["roll_window"]),
        "n_anoms": int(shared["n_anoms"]),
        "n_factors": int(shared["n_factors"]),
        "max_iter": int(shared["max_iter"]),
        "tol": float(shared["tol"]),
    }


def _ipca_fit_month(
    p: int,
    *,
    W_all: np.ndarray,
    X_all: np.ndarray,
    nts_all: np.ndarray,
    z_all: np.ndarray,
    keep_wide: np.ndarray | None,
    row_start: np.ndarray,
    row_end: np.ndarray,
    roll_window: int,
    n_anoms: int,
    n_factors: int,
    max_iter: int,
    tol: float,
) -> dict[str, Any] | None:
    """Fit one rolling IPCA month; None where the original loop said ``continue``."""
    if keep_wide is None:
        kept = np.arange(n_anoms)
    else:
        kept = np.flatnonzero(np.asarray(keep_wide[p - 1]))
    if kept.size == 0:
        return None

    cols = np.concatenate([kept, [n_anoms]])
    win = slice(p - roll_window, p)
    W = np.ascontiguousarray(
        np.transpose(np.asarray(W_all[win])[:, cols][:, :, cols], (1, 2, 0))
    )
    X = np.ascontiguousarray(np.asarray(X_all[win])[:, cols].T)
    nts = np.asarray(nts_all[win])
    if not (np.isfinite(W).all() and np.isfinite(X).all()):
        return {"skip": "not_finite", "p": p}

    try:
        gamma_beta, lam, n_iter, reached = _ipca_fit_window(
            W, X, nts, n_factors=n_factors, max_iter=max_iter, tol=tol
        )
    except np.linalg.LinAlgError as exc:
        return {"skip": f"linalg: {exc}", "p": p}

    z_p = np.asarray(z_all[int(row_start[p]):int(row_end[p])])
    return {
        "p": p,
        "gamma_beta": gamma_beta,
        "lam": lam,
        "eret": z_p[:, cols] @ (gamma_beta @ lam),
        "n_kept_anoms": int(kept.size),
        "n_stocks": int(nts[-1]),
        "n_iter": int(n_iter),
        "tol_reached": float(reached),
    }


def _ipca_pool_task(p: int) -> dict[str, Any] | None:
    """Worker entry: one month against :data:`_IPCA_POOL`.

    The ALS inner loop is a dense ``(L*K, L*K)`` solve, which BLAS already
    threads. Running one month per process *and* letting each spawn a full
    thread pool would oversubscribe the machine, so each worker is pinned to a
    single BLAS thread and the month pool owns the parallelism budget (D5).
    """
    try:
        from threadpoolctl import threadpool_limits
    except ImportError:  # pragma: no cover - threadpoolctl ships with sklearn
        return _ipca_fit_month(p, **_IPCA_POOL)
    with threadpool_limits(limits=1):
        return _ipca_fit_month(p, **_IPCA_POOL)


def _ipca_fit_window(
    W: np.ndarray,
    X: np.ndarray,
    nts: np.ndarray,
    *,
    n_factors: int = _IPCA_N_FACTORS,
    max_iter: int = _IPCA_MAX_ITER,
    tol: float = _IPCA_TOL,
) -> tuple[np.ndarray, np.ndarray, int, float]:
    """Run the IPCA ALS loop for one estimation window.

    Port of the solver half of ``runIPCAforMonth.m``: build the starting guess
    from the leading ``K`` singular triplets of ``X`` and iterate
    :func:`_ipca_als_step` to convergence.

    Returns
    -------
    (gamma_beta, lambda_, n_iter, tol_reached)
        ``lambda_`` is ``mean(F, 2)`` -- MATLAB's ``Lambda``.
    """
    u, s, vt = np.linalg.svd(X, full_matrices=False)
    gb_old = u[:, :n_factors]
    f_old = (s[:n_factors, None] * vt[:n_factors, :])

    reached = 1.0
    it = 0
    gb_new, f_new = gb_old, f_old
    while it <= max_iter and reached > tol:
        gb_new, f_new = _ipca_als_step(gb_old, W, X, nts)
        reached = float(
            max(
                np.max(np.abs(gb_new - gb_old)),
                np.max(np.abs(f_new - f_old)),
            )
        )
        gb_old, f_old = gb_new, f_new
        it += 1
    return gb_new, f_new.mean(axis=1), it, reached


def _ipca_month_moments(
    z: np.ndarray,
    xret_next: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Second moments for one characteristic month.

    ``z`` is the ``(nStocks, L)`` instrument matrix for month ``j`` (the
    constant already appended as the last column) and ``xret_next`` the excess
    returns of month ``j + 1``. Rows with any missing instrument or a missing
    return are dropped, mirroring ``runIPCAforMonth``'s
    ``LOC = all(~isnan(chars), 3) & ~isnan(xret)``.
    """
    loc = np.isfinite(z).all(axis=1) & np.isfinite(xret_next)
    n = float(loc.sum())
    if n == 0:
        L = z.shape[1]
        return np.full((L, L), np.nan), np.full(L, np.nan), 0.0
    zt = z[loc]
    return (zt.T @ zt) / n, (zt.T @ xret_next[loc]) / n, n


def make_ipca_res(
    filled_anoms: pd.DataFrame | dict[str, pd.Series] | np.ndarray,
    keep_roll_anoms: pd.DataFrame | np.ndarray | None,
    ret: pd.Series,
    rf: pd.Series,
    *,
    time_period: tuple[pd.Timestamp | int, pd.Timestamp | int] | None = None,
    anom_labels: list[str] | None = None,
    roll_window: int = 120,
    verbose: bool = True,
    n_jobs: int = 1,
    n_factors: int = _IPCA_N_FACTORS,
    max_iter: int = _IPCA_MAX_ITER,
    tol: float = _IPCA_TOL,
) -> IPCARes:
    """Build the Instrumented PCA forecast-return combination signal.

    MATLAB equivalent: ``makeIPCARes.m`` (Novy-Marx / Velikov 2026). For each
    month ``i`` in ``b + T … e - 1`` (MATLAB starts one month later, at
    ``b + T + 1``):

      1. Filter to the anomalies that passed the 10-year / 40%-market-cap
         coverage test as of ``i - 1`` (``keepRollAnoms(i-1, :)``).
      2. Take the ``T``-month window of filled anomalies
         (``filledAnoms(i-T:i-1, :, :)``) against excess returns shifted one
         month forward (``xret(i-T+1:i, :)``), so month ``j``'s
         characteristics are matched to month ``j + 1``'s return.
      3. Fit the IPCA model of Kelly, Pruitt and Su (2019) by alternating
         least squares (``runIPCAforMonth`` → :func:`_ipca_fit_window`),
         yielding ``GammaBeta`` and ``Lambda = mean(F, 2)``.
      4. Forecast month ``i`` as ``[X_i; 1]' GammaBeta Lambda``.

    Parameters
    ----------
    filled_anoms : DataFrame, dict, or 3-D ndarray
        Filled anomaly signals (no NaN from missing-data gaps). DataFrame:
        MultiIndex (date, permno) x anomaly columns. dict: ``{name: Series}``
        each MultiIndex (date, permno). 3-D ndarray: MATLAB-style
        ``(nMonths, nStocks, nAnoms)`` -- requires ``anom_labels``.
    keep_roll_anoms : DataFrame, ndarray, or None
        Rolling-flag matrix (``nMonths x nAnoms`` in MATLAB) indicating
        whether each anomaly has had > 40% of market-cap coverage in the
        trailing 10 years. IPCA uses the previous month's row to pick which
        anomalies enter the estimation. ``None`` keeps every anomaly in every
        month.
    ret : pd.Series
        Stock returns (decimals), MultiIndex (date, permno). Used to build
        the excess-return panel and to fix the output panel shape.
    rf : pd.Series
        Risk-free rate monthly returns (decimals), indexed by month-end
        date. Subtracted row-wise from ``ret`` to form ``xret``. ``None`` is
        treated as an all-zero risk-free rate.
    time_period : tuple, optional
        ``(start, end)`` as YYYYMM ints or Timestamps. Matches MATLAB
        ``timePeriod``.
    anom_labels : list[str], optional
        Required when ``filled_anoms`` is a 3-D ndarray; ignored otherwise.
    roll_window : int, default 120
        Rolling estimation window length in months (MATLAB ``T = 120``).
    verbose : bool
        If True, log start / stop messages (MATLAB cadence).
    n_jobs : int, default 1
        Workers for the rolling-fit loop. Accepted and recorded now so
        ``make_comb_strats`` has one knob to thread; the loop itself is still
        serial.
    n_factors, max_iter, tol
        Solver settings. Defaults match ``runIPCAforMonth.m``: ``K = 5``,
        ``als_opt.MaxIterations = 10000``, ``als_opt.Tolerance = 1e-6``.

    Returns
    -------
    IPCARes

    Raises
    ------
    ValueError
        If the filled-anomaly panel does not share one missing-data pattern
        across signals -- see the note below on hoisted moments.

    Notes
    -----
    - **Hoisted second moments.** MATLAB rebuilds ``W_t = Z_t' Z_t / N_t`` and
      ``X_t = Z_t' r_{t+1} / N_t`` inside every rolling window, so each
      calendar month is re-reduced up to ``T`` times over the sample. Those
      moments depend only on the month, so this port computes them once per
      month and slices the anomaly subset out of the stored matrices. The
      shortcut needs ``LOC`` -- MATLAB's ``all(~isnan(chars), 3) &
      ~isnan(xret)`` -- to be independent of *which* anomalies are kept, which
      holds because ``fill_var`` gives every filled signal exactly the market
      cap's missingness pattern. The invariant is checked, not assumed: a
      panel whose signals disagree on missingness raises rather than quietly
      computing something MATLAB would not.
    - MATLAB abstains on this method for the 157-anomaly protocol run, but
      only because its dense ``(nMonths, nStocks, nAnoms)`` array exhausts
      memory (the gold ``MPE_Results.mat`` stores ``MATLAB:nomem`` /
      "Out of memory." on that row). There is therefore no MATLAB numeric
      reference for this function's output.
    """
    anoms_dict = _coerce_anoms_to_dict(
        filled_anoms, signal_index=ret.index, labels=anom_labels
    )
    anom_names = list(anoms_dict.keys())
    n_anoms = len(anom_names)
    if n_anoms == 0:
        raise ValueError("filled_anoms must contain at least one anomaly signal")

    if verbose:
        LOGGER.info(
            "Now working on IPCA with %d anomalies. Run started at %s.",
            n_anoms,
            datetime.now().isoformat(timespec="seconds"),
        )

    anoms_df_full = pd.concat(anoms_dict, axis=1)
    anoms_df_full.columns = anom_names
    anoms_df_full = anoms_df_full.reindex(ret.index)

    ret_num = pd.to_numeric(ret, errors="coerce")
    ret_sliced = _slice_panel_by_time(ret_num, time_period)
    anoms = _slice_panel_by_time(anoms_df_full, time_period).reindex(ret_sliced.index)

    eval_dates = ret_sliced.index.get_level_values(0).unique().sort_values()
    n_months = len(eval_dates)

    # Excess returns. MATLAB: xret = ret - repmat(rf, 1, nStocks).
    if rf is None:
        xret = ret_sliced
    else:
        rf_num = pd.to_numeric(pd.Series(rf), errors="coerce")
        rf_num.index = pd.to_datetime(rf_num.index)
        xret = ret_sliced - rf_num.reindex(
            ret_sliced.index.get_level_values(0)
        ).to_numpy()

    # ---- Flat panel views ------------------------------------------------
    # Deliberately *not* a dense (nMonths, nStocks, nAnoms) cube: that layout
    # is what exhausts memory in MATLAB (26,746 permnos x 564 months x 158
    # instruments is ~19 GiB before the enhanced panel doubles it). Work off
    # the long panel instead and slice one month at a time.
    permnos = ret_sliced.index.get_level_values(1).unique().sort_values()
    perm_pos = permnos.get_indexer(ret_sliced.index.get_level_values(1))
    month_pos = eval_dates.get_indexer(ret_sliced.index.get_level_values(0))
    row_start = np.searchsorted(month_pos, np.arange(n_months), side="left")
    row_end = np.searchsorted(month_pos, np.arange(n_months), side="right")

    chars = anoms.to_numpy(dtype=float)
    xret_arr = xret.to_numpy(dtype=float)
    n_permnos = len(permnos)
    L_full = n_anoms + 1

    def month_instruments(j: int) -> tuple[np.ndarray, np.ndarray]:
        """Instrument matrix for month ``j`` and its permno positions."""
        rows = slice(row_start[j], row_end[j])
        block = chars[rows]
        z = np.empty((block.shape[0], L_full), dtype=float)
        z[:, :n_anoms] = block
        z[:, n_anoms] = 1.0
        return z, perm_pos[rows]

    def month_returns(j: int) -> np.ndarray:
        """Month ``j`` excess returns scattered onto the full permno axis."""
        rows = slice(row_start[j], row_end[j])
        out = np.full(n_permnos, np.nan)
        out[perm_pos[rows]] = xret_arr[rows]
        return out

    # Per-month moments: month j's characteristics against month j+1's return.
    W_all = np.full((n_months, L_full, L_full), np.nan)
    X_all = np.full((n_months, L_full), np.nan)
    nts_all = np.zeros(n_months)
    for j in range(n_months - 1):
        z_j, pos_j = month_instruments(j)
        # The hoist is only valid when every signal shares one missingness
        # pattern, so MATLAB's `all(~isnan(chars), 3)` does not depend on the
        # kept subset. `fill_var` guarantees it; verify rather than trust.
        fin = np.isfinite(z_j[:, :n_anoms])
        if int(fin.all(axis=1).sum()) != int(fin.any(axis=1).sum()):
            raise ValueError(
                "make_ipca_res requires filled anomaly signals sharing one "
                "missing-data pattern (as produced by fill_var); "
                f"{eval_dates[j].date()} has signals missing where others are "
                "present, so a per-month moment cache would not reproduce "
                "MATLAB's subset-dependent LOC mask."
            )
        W_all[j], X_all[j], nts_all[j] = _ipca_month_moments(
            z_j, month_returns(j + 1)[pos_j]
        )

    # ---- keepRollAnoms ---------------------------------------------------
    keep_wide: np.ndarray | None
    if keep_roll_anoms is None:
        keep_wide = None
    elif isinstance(keep_roll_anoms, pd.DataFrame):
        keep_wide = (
            keep_roll_anoms.reindex(index=eval_dates, columns=anom_names)
            .fillna(False)
            .to_numpy()
            .astype(bool)
        )
    else:
        arr = np.asarray(keep_roll_anoms)
        full_dates = ret.index.get_level_values(0).unique().sort_values()
        if arr.ndim != 2 or arr.shape[1] != n_anoms:
            raise ValueError(
                "keep_roll_anoms ndarray must be (nMonths, nAnoms) with "
                f"nAnoms == {n_anoms}"
            )
        if arr.shape[0] == n_months:
            keep_wide = arr.astype(bool)
        elif arr.shape[0] == len(full_dates):
            # MATLAB shape: rows run over the whole library, so take the slice.
            take = full_dates.get_indexer(eval_dates)
            keep_wide = arr.astype(bool)[take]
        else:
            raise ValueError(
                "keep_roll_anoms has %d rows; expected %d (sample) or %d "
                "(full panel)" % (arr.shape[0], n_months, len(full_dates))
            )

    # ---- Month loop ------------------------------------------------------
    # `p` is a 0-based offset from the sample start. The first fit is month
    # `roll_window`: its window is characteristics of months 0 .. T-1 against
    # returns of months 1 .. T, all inside the sample, so IPCA's first forecast
    # falls in the same month as the other rolling methods' (LASSO's
    # `range(roll_window, n_months)`, Fama-MacBeth's `i >= roll_window`).
    # MATLAB runs `for i = b+T+1 : e-1`, one month later. The last
    # month is left out as in MATLAB: its forecast would earn no return.
    eret_arr = np.full(chars.shape[0], np.nan)
    gamma_by_month: dict[Any, np.ndarray] = {}
    lambda_rows: dict[Any, np.ndarray] = {}
    diag_rows: list[dict[str, Any]] = []
    skipped_months: list[tuple[Any, str]] = []

    fit_months = list(range(roll_window, n_months - 1))
    n_workers = max(1, int(n_jobs))

    # The instrument matrix per month, packed once. `month_instruments` rebuilt
    # this on every call; the rolling loop needs month `p`'s block to form the
    # forecast, so build the whole (n_rows, L) array up front and slice it.
    z_all = np.empty((chars.shape[0], L_full), dtype=float)
    z_all[:, :n_anoms] = chars
    z_all[:, n_anoms] = 1.0

    kwargs: dict[str, Any] = {
        "W_all": W_all,
        "X_all": X_all,
        "nts_all": nts_all,
        "z_all": z_all,
        "keep_wide": keep_wide,
        "row_start": row_start,
        "row_end": row_end,
        "roll_window": roll_window,
        "n_anoms": n_anoms,
        "n_factors": n_factors,
        "max_iter": max_iter,
        "tol": tol,
    }

    def _absorb(out: dict[str, Any] | None) -> None:
        if out is None:
            return
        p = int(out["p"])
        if "skip" in out:
            LOGGER.warning(
                "IPCA skipped %s (%s)", eval_dates[p].date(), out["skip"]
            )
            skipped_months.append((eval_dates[p], str(out["skip"])))
            return
        d = eval_dates[p]
        eret_arr[row_start[p]:row_end[p]] = out["eret"]
        gamma_by_month[d] = out["gamma_beta"]
        lambda_rows[d] = out["lam"]
        diag_rows.append(
            {
                "date": d,
                "n_kept_anoms": out["n_kept_anoms"],
                "n_stocks": out["n_stocks"],
                "n_iter": out["n_iter"],
                "tol_reached": out["tol_reached"],
            }
        )

    n_workers = pool_worker_count(n_workers, what="IPCA")
    if n_workers <= 1 or len(fit_months) <= 1:
        for p in fit_months:
            if verbose and ((p + 1) % roll_window == 0):
                LOGGER.info(
                    "Done until %s @ %s.",
                    eval_dates[p].strftime("%Y-%m"),
                    datetime.now().isoformat(timespec="seconds"),
                )
            _absorb(_ipca_fit_month(p, **kwargs))
    else:
        # Each month's ALS depends only on its own 120-month moment window, so
        # the loop is embarrassingly parallel. The moments are small (a few
        # hundred MiB at full sample), so they go to disk once and workers mmap
        # them rather than each receiving a pickled copy.
        tmpdir = tempfile.mkdtemp(prefix="aa_ipca_")
        try:
            shared: dict[str, Any] = {
                k: v for k, v in kwargs.items()
                if k not in ("W_all", "X_all", "nts_all", "z_all", "keep_wide")
            }
            for name in ("W_all", "X_all", "nts_all", "z_all"):
                path = os.path.join(tmpdir, f"{name}.npy")
                np.save(path, kwargs[name])
                shared[name] = path
            if keep_wide is None:
                shared["keep_wide"] = None
            else:
                path = os.path.join(tmpdir, "keep_wide.npy")
                np.save(path, keep_wide)
                shared["keep_wide"] = path

            done = 0
            with ProcessPoolExecutor(
                max_workers=min(n_workers, len(fit_months)),
                mp_context=spawn_context(),
                initializer=_init_ipca_pool_worker,
                initargs=(shared,),
            ) as pool:
                futures = [pool.submit(_ipca_pool_task, p) for p in fit_months]
                for fut in as_completed(futures):
                    _absorb(fut.result())
                    done += 1
                    if verbose and done % roll_window == 0:
                        LOGGER.info(
                            "Done with %d/%d IPCA months @ %s.",
                            done,
                            len(fit_months),
                            datetime.now().isoformat(timespec="seconds"),
                        )
        finally:
            import shutil

            shutil.rmtree(tmpdir, ignore_errors=True)

    # A pool finishes months out of order, and these three all preserve
    # insertion order -- diag_rows is a list, and both dicts become the row
    # index of a DataFrame the caller will slice by position. Restore date
    # order so the pooled and serial paths are indistinguishable downstream.
    diag_rows.sort(key=lambda r: r["date"])
    skipped_months.sort(key=lambda r: r[0])
    if skipped_months:
        LOGGER.warning(
            "IPCA skipped %d of %d months (first %s, last %s).",
            len(skipped_months), len(fit_months),
            skipped_months[0][0].date(), skipped_months[-1][0].date(),
        )
    gamma_by_month = {d: gamma_by_month[d] for d in sorted(gamma_by_month)}
    lambda_rows = {d: lambda_rows[d] for d in sorted(lambda_rows)}

    # ---- Reassemble on the original panel index --------------------------
    eret = pd.Series(np.nan, index=ret.index, dtype="float64", name="eret")
    eret.loc[ret_sliced.index] = eret_arr

    if verbose:
        LOGGER.info(
            "Done with IPCA calculation at %s.",
            datetime.now().isoformat(timespec="seconds"),
        )

    lambda_df = (
        pd.DataFrame.from_dict(lambda_rows, orient="index")
        if lambda_rows
        else pd.DataFrame()
    )
    if not lambda_df.empty:
        lambda_df.columns = [f"lambda{k + 1}" for k in range(lambda_df.shape[1])]
        lambda_df.index.name = "date"

    return IPCARes(
        eret=eret,
        gamma_beta=gamma_by_month,
        lambda_=lambda_df,
        diagnostics=pd.DataFrame(diag_rows),
        metadata={
            "time_period": time_period,
            "roll_window": roll_window,
            "n_anoms": n_anoms,
            "anom_names": anom_names,
            "n_factors": n_factors,
            "max_iter": max_iter,
            "tol": tol,
            "n_fit_months": len(diag_rows),
            # Months whose fit failed (date, reason); they have no forecast.
            "skipped_months": skipped_months,
        },
    )


# ---------------------------------------------------------------------------
# makeAverageRank.m port  -- trivial cross-sectional aggregation combination
# ---------------------------------------------------------------------------


def make_avg_rank(
    filled_anoms: pd.DataFrame | dict[str, pd.Series] | np.ndarray,
    me: pd.Series | None = None,
    *,
    anom_labels: list[str] | None = None,
    signal_index: pd.MultiIndex | None = None,
    verbose: bool = True,
) -> pd.Series:
    """
    Build the *average-rank* forecast-return combination signal.

    MATLAB equivalent: ``makeAverageRank.m`` (Novy-Marx / Velikov 2026).

    The MATLAB body is a two-liner operating on ``filledAnoms`` (a 3-D array
    ``nMonths x nStocks x nAnoms`` of already *filled-in* anomaly ranks):

    .. code-block:: matlab

        eret = sum(filledAnoms, 3);
        eret(isnan(me)) = nan;

    i.e. sum the anomaly-rank layers along the 3rd (anomaly) axis to get a
    single cross-sectional composite, then mask out stocks with missing
    market cap. Because ``filledAnoms`` has no NaN by construction
    (fill-forward / cross-sectional median imputation upstream), the sum is
    just a plain column-wise addition — *not* a nan-aware sum — matching
    MATLAB's default ``sum`` behavior (NaN propagates).

    Parameters
    ----------
    filled_anoms : DataFrame or dict or 3-D ndarray
        Filled anomaly signals (no NaN from missing-data gaps). DataFrame:
        MultiIndex (date, permno) x anomaly columns. dict: ``{name: Series}``
        each MultiIndex (date, permno). 3-D ndarray: MATLAB-style
        ``(nMonths, nStocks, nAnoms)`` -- requires ``anom_labels`` and
        ``signal_index`` (or ``me`` whose index supplies the panel).
    me : pd.Series, optional
        Market capitalization, MultiIndex (date, permno). Used solely as a
        mask: where ``me`` is NaN the output is set to NaN. Pass ``None`` to
        skip masking (output follows the signal-sum NaN pattern only). Also
        serves as the default ``signal_index`` when ``filled_anoms`` is a
        3-D ndarray.
    anom_labels : list[str], optional
        Required when ``filled_anoms`` is a 3-D ndarray; ignored otherwise.
    signal_index : pd.MultiIndex, optional
        Panel index for resolving 3-D ndarray inputs. If both ``me`` and
        ``signal_index`` are ``None`` and ``filled_anoms`` is an ndarray,
        raises.
    verbose : bool
        If True, log the MATLAB-style start/stop banner.

    Returns
    -------
    pd.Series
        Forecast returns, MultiIndex (date, permno), aligned to the union of
        the anomaly panel and (when provided) ``me``. Values are the sum of
        the anomaly ranks; NaN where ``me`` is NaN.

    Notes
    -----
    - No rolling window applies here: average-rank is a purely
      cross-sectional aggregation done independently each month. The
      "indexing caveat" from rolling ports (``for i = (s+T):e`` -> Python
      ``for i in range(roll_window, n_months)``) is therefore not relevant.
    - Faithful to MATLAB: sum propagates NaN. If callers feed raw
      (un-filled) anomalies with missing values, those rows will be NaN in
      the output.
    - Returns a bare ``pd.Series`` (no dataclass wrapper) because the MATLAB
      function returns a single matrix, and ``make_comb_strats`` already
      accepts a Series via its ``_run_one`` helper.
    """
    # ---------------- Timekeeping banner ----------------------------------
    # Determine n_anoms early (for the banner) based on the input form.
    if isinstance(filled_anoms, np.ndarray):
        n_anoms = filled_anoms.shape[2] if filled_anoms.ndim == 3 else 0
    elif isinstance(filled_anoms, pd.DataFrame):
        n_anoms = filled_anoms.shape[1]
    elif isinstance(filled_anoms, dict):
        n_anoms = len(filled_anoms)
    else:
        n_anoms = 0

    if verbose:
        LOGGER.info(
            "Now working on average rank with %d anomalies. Run started at %s.",
            n_anoms,
            datetime.now().isoformat(timespec="seconds"),
        )

    # ---------------- Normalize anomaly panel ------------------------------
    # Resolve the signal_index used for ndarray reshaping. Prefer the
    # explicit override, then fall back to `me`'s index (the MATLAB caller
    # always has `me` in scope — it's loaded at the top of makeCombStrats).
    if signal_index is None and me is not None:
        signal_index = me.index
    if signal_index is None and isinstance(filled_anoms, np.ndarray):
        raise ValueError(
            "3-D ndarray `filled_anoms` requires `signal_index` or `me` to "
            "recover the (date, permno) panel labels"
        )
    # When not an ndarray, signal_index is only a hint — _coerce_anoms_to_dict
    # ignores it. Provide an empty MultiIndex placeholder to satisfy the type.
    idx_for_coerce = signal_index if signal_index is not None else pd.MultiIndex.from_tuples(
        [], names=["date", "permno"]
    )
    anoms_dict = _coerce_anoms_to_dict(
        filled_anoms, signal_index=idx_for_coerce, labels=anom_labels
    )
    if not anoms_dict:
        raise ValueError("filled_anoms must contain at least one anomaly signal")

    # Stack into a DataFrame (date, permno) x anomaly-name. concat with axis=1
    # handles the union of per-anom indices; rectangle gaps are NaN and will
    # propagate through the sum, matching MATLAB's behavior on the shared grid.
    anoms_df = pd.concat(anoms_dict, axis=1)
    anoms_df.columns = list(anoms_dict.keys())

    # ---------------- Core computation ------------------------------------
    # MATLAB: eret = sum(filledAnoms, 3);
    # Use skipna=False so NaN propagates — matches MATLAB default `sum`.
    eret = anoms_df.sum(axis=1, skipna=False)
    eret.name = "eret"

    # ---------------- Apply the `me` NaN mask -----------------------------
    # MATLAB: eret(isnan(me)) = nan;
    if me is not None:
        me_aligned = pd.to_numeric(me, errors="coerce").reindex(eret.index)
        eret = eret.where(me_aligned.notna(), other=np.nan)
        # Also broaden the output panel to include any (date, permno) cells
        # present in `me` but missing from the anomaly union — those become
        # NaN in MATLAB's rectangular grid as well.
        missing_idx = me_aligned.index.difference(eret.index)
        if len(missing_idx) > 0:
            # Extend with NaNs so downstream reindex calls don't lose cells.
            eret = pd.concat(
                [eret, pd.Series(np.nan, index=missing_idx, name="eret")]
            ).sort_index()

    if verbose:
        LOGGER.info(
            "Done with average rank at %s.",
            datetime.now().isoformat(timespec="seconds"),
        )

    return eret.astype("float64")


def make_weighted_avg_rank(
    filled_anoms: pd.DataFrame | dict[str, pd.Series] | np.ndarray,
    pret: pd.DataFrame | np.ndarray,
    me: pd.Series,
    *,
    time_period: tuple[pd.Timestamp | int, pd.Timestamp | int] | None = None,
    lookback: int = 120,
    anom_labels: list[str] | None = None,
    verbose: bool = True,
) -> pd.Series:
    """
    Build the *weighted-average-rank* forecast-return combination signal.

    MATLAB equivalent: ``makeWeightedAverageRank.m`` (Novy-Marx / Velikov
    2023). For each month ``t`` in the evaluation window (and only once
    ``t`` is at least ``lookback`` months past the start), compute:

      1. ``weights[j] = mean(pret[t-lookback+1 : t, j])`` -- the trailing
         ``lookback``-month average long-short return for anomaly ``j``.
      2. Zero out negative weights (``weights[weights < 0] = 0``) and
         renormalize by the sum of the remaining (non-negative, non-NaN)
         weights.
      3. Forecast return for each stock ``s`` at month ``t`` is
         ``eret[t, s] = sum_j filledAnoms[t, s, j] * weights[j]`` over the
         anomalies with finite weight.

    MATLAB body (for reference)::

        for i = s+lbp:e
            weights = mean(pret(i-lbp+1:i, :), 1)';
            weights(weights<0) = 0;
            weights = weights / sum(weights, 'omitnan');
            ind = find(isfinite(weights));
            eret(i,:) = (permute(filledAnoms(i, :, ind),[2 3 1]) * weights(ind))';
        end

    Parameters
    ----------
    filled_anoms : DataFrame, dict, or 3-D ndarray
        Filled anomaly signals (no NaN from missing-data gaps). DataFrame:
        MultiIndex (date, permno) x anomaly columns. dict: ``{name: Series}``
        each MultiIndex (date, permno). 3-D ndarray: MATLAB-style
        ``(nMonths, nStocks, nAnoms)`` -- requires ``anom_labels`` and is
        interpreted relative to ``me``'s panel.
    pret : pd.DataFrame or 2-D ndarray
        Per-anomaly portfolio long-short returns, indexed by date (month-
        end) with one column per anomaly. MATLAB shape: ``(nMonths,
        nAnoms)``. The anomaly columns must match (in order) the anomalies
        in ``filled_anoms``; for ndarray ``pret`` the caller must guarantee
        this alignment.
    me : pd.Series
        Market capitalization, MultiIndex (date, permno). Fixes the output
        panel shape. Also supplies the (date, permno) labels when
        ``filled_anoms`` is a 3-D ndarray. Following MATLAB, ``eret`` is
        initialized to ``nan(size(me))``.
    time_period : tuple, optional
        ``(start, end)`` as YYYYMM ints or Timestamps. MATLAB ``timePeriod``.
        Determines the evaluation window: the rolling loop runs from
        ``s + lookback`` through ``e`` (inclusive). When ``None`` the full
        range of ``me``'s date index is used.
    lookback : int
        Rolling-window length in months. MATLAB default is 120 (``lbp``).
    anom_labels : list[str], optional
        Required when ``filled_anoms`` is a 3-D ndarray; ignored otherwise.
    verbose : bool
        If True, log the MATLAB-style start/stop banner.

    Returns
    -------
    pd.Series
        Forecast returns, MultiIndex (date, permno), aligned to ``me``.
        NaN outside the evaluation window (including the first ``lookback``
        months inside ``time_period``) and where all anomaly weights were
        non-finite / non-positive.

    Notes
    -----
    - MATLAB indexing: ``for i = s+lbp:e`` with ``s = find(dates==tp(1))``.
      Because MATLAB is 1-based, the first filled row is offset by
      ``lookback`` from the window start -- so the first ``lookback``
      months of the evaluation window are NaN. We mirror that exactly.
    - Weight renormalization in MATLAB uses ``sum(weights, 'omitnan')``
      (i.e. treats NaN trailing returns as absent). We do the same via
      ``np.nansum``. Anomalies whose trailing mean is NaN drop out of the
      forecast for that month.
    - The output panel follows ``me``'s index. Anomalies are multiplied by
      their weights in the shared cross-section; stocks present only in
      ``filled_anoms`` but not in ``me`` are dropped (matches MATLAB's
      ``nan(size(me))`` initialization).
    """
    # ---------------- Timekeeping banner ----------------------------------
    if isinstance(filled_anoms, np.ndarray):
        n_anoms = filled_anoms.shape[2] if filled_anoms.ndim == 3 else 0
    elif isinstance(filled_anoms, pd.DataFrame):
        n_anoms = filled_anoms.shape[1]
    elif isinstance(filled_anoms, dict):
        n_anoms = len(filled_anoms)
    else:
        n_anoms = 0

    if verbose:
        LOGGER.info(
            "Now working on weighted-average rank with %d anomalies. "
            "Run started at %s.",
            n_anoms,
            datetime.now().isoformat(timespec="seconds"),
        )

    # ---------------- Normalize anomaly panel ------------------------------
    if me is None:
        raise ValueError("`me` is required to fix the output panel shape")
    anoms_dict = _coerce_anoms_to_dict(
        filled_anoms, signal_index=me.index, labels=anom_labels
    )
    anom_names = list(anoms_dict.keys())
    if not anom_names:
        raise ValueError("filled_anoms must contain at least one anomaly signal")

    # Stack into a DataFrame (date, permno) x anomaly and align to `me`'s
    # rectangular panel so per-date cross-sections line up with the output.
    anoms_df = pd.concat(anoms_dict, axis=1)
    anoms_df.columns = anom_names
    anoms_df = anoms_df.reindex(me.index)

    # ---------------- Normalize `pret` ------------------------------------
    # Accept DataFrame (date-indexed, columns in anomaly order) or a 2-D
    # ndarray whose columns are already aligned with `anom_names`.
    if isinstance(pret, np.ndarray):
        if pret.ndim != 2:
            raise ValueError("pret ndarray must be 2-D (nMonths, nAnoms)")
        if pret.shape[1] != len(anom_names):
            raise ValueError(
                "pret columns must match number of anomalies in filled_anoms"
            )
        # Recover date index from `me`; MATLAB `dates` is the same date axis.
        pret_dates = me.index.get_level_values(0).unique().sort_values()
        if pret.shape[0] != len(pret_dates):
            raise ValueError(
                "pret rows must match number of unique dates in `me`"
            )
        pret_df = pd.DataFrame(pret, index=pret_dates, columns=anom_names)
    elif isinstance(pret, pd.DataFrame):
        pret_df = pret.copy()
        # If columns don't include every anom name, try positional alignment
        # (MATLAB passes a column-ordered matrix; names might just be 0..k).
        if list(pret_df.columns) != anom_names and pret_df.shape[1] == len(
            anom_names
        ):
            pret_df.columns = anom_names
    else:
        raise TypeError("pret must be a pandas DataFrame or a 2-D ndarray")

    pret_df = pret_df.sort_index()
    pret_arr = pret_df.to_numpy(dtype=float)  # (n_months, n_anoms)
    all_dates = pret_df.index

    # ---------------- Resolve evaluation window ---------------------------
    # MATLAB: s = find(dates==timePeriod(1)); e = find(dates==timePeriod(2));
    if time_period is not None:
        start = _to_month_end(time_period[0])
        end = _to_month_end(time_period[1])
    else:
        start = all_dates.min()
        end = all_dates.max()

    # Locate s, e as positional indices on `all_dates`.
    try:
        s_idx = all_dates.get_loc(start)
        e_idx = all_dates.get_loc(end)
    except KeyError as exc:
        raise ValueError(
            f"time_period bound not present in pret/me date axis: {exc}"
        )
    if isinstance(s_idx, slice) or isinstance(e_idx, slice):
        raise ValueError("time_period bounds must uniquely locate a date")

    # MATLAB `for i = s+lbp:e` (1-based). With s_idx, e_idx 0-based in
    # Python, the equivalent loop is `range(s_idx + lookback, e_idx + 1)`.
    # (MATLAB i=s+lbp maps to Python i=s_idx+lookback because the shift
    # amount is the same in both indexing systems.)
    eval_positions = range(s_idx + lookback, e_idx + 1)

    # ---------------- Initialize output, MATLAB: eret = nan(size(me)) -----
    eret = pd.Series(np.nan, index=me.index, dtype="float64", name="eret")

    # Per-date group slices of the anomaly panel, for O(1) cross-section access.
    anoms_by_date = {
        d: grp for d, grp in anoms_df.groupby(level="date", sort=False)
    }

    # ---------------- Rolling loop ---------------------------------------
    for i in eval_positions:
        # Trailing window [i-lookback+1, i] inclusive -- MATLAB pret(i-lbp+1:i,:)
        window = pret_arr[i - lookback + 1 : i + 1, :]  # (lookback, n_anoms)

        # MATLAB `mean(x, 1)` propagates NaN; replicate via plain `np.mean`
        # so that anomalies with any missing trailing return get weight=NaN.
        weights = np.mean(window, axis=0)  # (n_anoms,)

        # MATLAB: weights(weights<0) = 0
        # Keep NaN as NaN; only non-NaN negatives become 0.
        neg_mask = np.isfinite(weights) & (weights < 0)
        weights = np.where(neg_mask, 0.0, weights)

        # MATLAB: weights = weights / sum(weights, 'omitnan')
        denom = np.nansum(weights)
        if not np.isfinite(denom) or denom == 0.0:
            # No usable weights this month -- leave eret[t, :] as NaN.
            continue
        weights = weights / denom

        # MATLAB: ind = find(isfinite(weights))
        ok = np.isfinite(weights)
        if not ok.any():
            continue

        # This month's cross-section of anomaly signals (rows = stocks).
        d = all_dates[i]
        grp = anoms_by_date.get(d)
        if grp is None or grp.empty:
            continue
        # Matrix multiply: (n_stocks, n_anoms_ok) @ (n_anoms_ok,) -> n_stocks
        X = grp.to_numpy(dtype=float)[:, ok]
        w_ok = weights[ok]
        row = X @ w_ok  # NaN propagates naturally through the matmul.

        eret.loc[grp.index] = row

    if verbose:
        LOGGER.info(
            "Done with weighted-average rank at %s.",
            datetime.now().isoformat(timespec="seconds"),
        )

    return eret


__all__ = [
    "BASIC_SORT_LABELS",
    "FACTOR_MODELS",
    "COMB_STRAT_LABELS",
    "COMB_STRAT_DISPLAY_LABELS",
    "COMB_STRAT_EXPLANATIONS",
    "BasicSortsResults",
    "AnomBenchmarkResults",
    "AnomStratResults",
    "FMBRes",
    "LassoRes",
    "PLSRes",
    "IPCARes",
    "CloseAnomResult",
    "CloseAnomResults",
    "DendrogramResults",
    "DendrogramSignalError",
    "dendrogram_signal_window",
    "CombStratResult",
    "CombStratsResults",
    "make_basic_sorts_results",
    "make_anom_benchmark_results",
    "make_anom_strat_results",
    "make_fmb_res",
    "make_lasso_res",
    "make_pls_res",
    "make_ipca_res",
    "make_close_anom_results",
    "make_dendrogram_results",
    "make_comb_strats",
    "make_avg_rank",
    "make_weighted_avg_rank",
]
