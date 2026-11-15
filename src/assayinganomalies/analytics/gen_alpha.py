"""
Generalized (net) alpha and net MVE portfolio helpers.

MATLAB equivalents:
  - Functions/Asset pricing/calcMve.m
  - Functions/Asset pricing/calcNetMve.m
  - Functions/Asset pricing/calcGenAlpha.m

Net gen-α (Novy-Marx / Velikov 2016) is the intercept of regressing the
cost-adjusted MVE of (factors, anomaly), scaled by the anomaly weight, on
the cost-adjusted MVE of the factors alone.

Both MVE portfolios and the regression use the same months: those in which
the anomaly return, its cost and every factor return and cost are finite.
MATLAB ``calcGenAlpha.m`` estimates the factor-only MVE on every
month with factor data, which for a strategy that starts after the window
opens re-optimizes the factor weights on a shorter sample and manufactures an
intercept.

Short positions. The net MVE portfolio may hold a factor or the anomaly short.
By default a short position earns ``-gross - cost``, with the same cost series
as a long one. That is exact when the costs are those of
``convention="dollar"`` (each leg back to $1 at a trade: the trades are the
same whichever leg is long). Under ``convention="capital"`` the strategy held
short is a different strategy with its own capital and its own cost
(``analytics/held.py``, "The strategy held short"). ``calc_gen_alpha`` and
``estimate_gen_alpha`` therefore take two optional arguments,
``anom_tcosts_short`` and ``factor_tcosts_short``: when given, a short
position is charged them, in the search for the MVE portfolios and in the
returns of the portfolios found. A protocol run under ``"capital"`` passes
both.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .ols import OlsRes, nanols, prt

LOGGER = logging.getLogger("assayinganomalies.analytics.gen_alpha")

__all__ = [
    "calc_mve",
    "calc_net_mve",
    "calc_gen_alpha",
    "classify_gen_alpha",
    "estimate_gen_alpha",
    "summarize_gen_alpha_outcomes",
    "GenAlphaOutcome",
    "GEN_ALPHA_STATUSES",
    "factor_matrix_for_gen_alpha",
    "factor_short_tcosts_for_gen_alpha",
    "GEN_ALPHA_FACTOR_COLS",
    "GEN_ALPHA_TCOST_COLS",
    "SHORT_TCOST_SUFFIX",
]

#: A factor-cost frame may carry, beside ``smb_tc`` .., the cost of each factor
#: held short under this suffix (``smb_tc_short`` ..); see
#: :func:`factor_short_tcosts_for_gen_alpha`.
SHORT_TCOST_SUFFIX = "_short"


# Factor-model codes used by makeBasicSortsResults gen-α block.
# MATLAB loads plain `smb` (not smb2) even for models 5/6.
GEN_ALPHA_FACTOR_COLS: dict[int, list[str]] = {
    1: ["mkt"],
    3: ["mkt", "smb", "hml"],
    4: ["mkt", "smb", "hml", "mom"],
    5: ["mkt", "smb", "hml", "rmw", "cma"],
    6: ["mkt", "smb", "hml", "rmw", "cma", "mom"],
}

GEN_ALPHA_TCOST_COLS: dict[int, list[str]] = {
    1: ["mkt_tc"],
    3: ["mkt_tc", "smb_tc", "hml_tc"],
    4: ["mkt_tc", "smb_tc", "hml_tc", "umd_tc"],
    5: ["mkt_tc", "smb_tc", "hml_tc", "rmw_tc", "cma_tc"],
    6: ["mkt_tc", "smb_tc", "hml_tc", "rmw_tc", "cma_tc", "umd_tc"],
}


def calc_mve(rets: np.ndarray | pd.DataFrame) -> tuple[np.ndarray, float]:
    """Port of MATLAB ``calcMve``: tangency-portfolio weights and Sharpe.

    Parameters
    ----------
    rets
        T × K asset returns. Rows with any non-finite entry are dropped
        (``isfinite(sum(rets,2))``).

    Returns
    -------
    weights : (K,) float ndarray
        Tangency weights (sum of absolute weights is not constrained to 1;
        they scale so that weighted means match the usual mean-variance formula).
    SR : float
        Ex-post Sharpe of the weighted portfolio.
    """
    r = np.asarray(rets, dtype=float)
    if r.ndim == 1:
        r = r[:, None]
    if r.size == 0 or r.shape[1] == 0:
        raise ValueError("Input rets is empty.")

    finite = np.isfinite(r).all(axis=1)
    r = r[finite, :]
    n_assets = r.shape[1]
    if r.shape[0] < 2:
        # Degenerate sample: mirror zero-useful tangency
        return np.zeros(n_assets), 0.0

    mu = r.mean(axis=0)  # (K,)
    sigma = np.cov(r, rowvar=False, ddof=1)
    if n_assets == 1:
        sigma = np.atleast_2d(float(sigma))
        mu_col = float(mu[0])
        weights = np.array([1.0 * np.sign(mu_col)], dtype=float)
        # match MATLAB: SR = weights * muR / sqrt(SigmaR)
        denom = float(np.sqrt(sigma[0, 0]))
        sr = float(weights[0] * mu_col / denom) if denom > 0 else 0.0
        return weights, sr

    # weights = (Σ^{-1} μ) / (1' Σ^{-1} μ)
    try:
        sigma_inv = np.linalg.inv(sigma)
    except np.linalg.LinAlgError:
        sigma_inv = np.linalg.pinv(sigma)
    ones = np.ones(n_assets)
    denom = float(ones @ sigma_inv @ mu)
    if not np.isfinite(denom) or denom == 0.0:
        return np.zeros(n_assets), 0.0
    weights = (sigma_inv @ mu) / denom
    port_var = float(weights @ sigma @ weights)
    if port_var <= 0 or not np.isfinite(port_var):
        return weights, 0.0
    sr = float((weights @ mu) / np.sqrt(port_var))
    return np.asarray(weights, dtype=float), sr


def calc_net_mve(
    rets: np.ndarray | pd.DataFrame,
    rets_s: np.ndarray | pd.DataFrame,
) -> tuple[np.ndarray, float]:
    """Port of MATLAB ``calcNetMve``.

    Search long / short / not-held combinations of non-market factors and
    return the highest-Sharpe MVE among combinations where every *included*
    non-market weight is strictly positive. Column 0 is treated as the
    market (costless; always held long in the signed-factor search).

    Parameters
    ----------
    rets, rets_s
        T × K gross long-side and short-side net returns (already
        cost-adjusted by the caller, same as MATLAB).

    Returns
    -------
    weights : (K,) float ndarray
        Signed MVE weights (short legs negative).
    SR : float
        Best attained Sharpe.
    """
    r_long = np.asarray(rets, dtype=float)
    r_short = np.asarray(rets_s, dtype=float)
    if r_long.ndim == 1:
        r_long = r_long[:, None]
    if r_short.ndim == 1:
        r_short = r_short[:, None]
    if r_long.shape != r_short.shape:
        raise ValueError("rets and rets_s must have the same shape.")

    n_factors = r_long.shape[1]
    sr = 0.0
    weights = np.zeros(n_factors, dtype=float)

    if n_factors == 0:
        return weights, sr

    if n_factors == 1:
        # Single-asset: compare long vs short mean/std Sharpe.
        # MATLAB mean/std: NaN propagates; std normalizes by N-1 (flag=0).
        long_m = float(np.mean(r_long[:, 0]))
        long_s = float(np.std(r_long[:, 0], ddof=1))
        short_m = float(np.mean(r_short[:, 0]))
        short_s = float(np.std(r_short[:, 0], ddof=1))
        long_sr = long_m / long_s if long_s > 0 and np.isfinite(long_s) else float("nan")
        short_sr = short_m / short_s if short_s > 0 and np.isfinite(short_s) else float("nan")
        if (
            np.isfinite(long_sr)
            and (not np.isfinite(short_sr) or long_sr > short_sr)
            and long_sr > 0
        ):
            return np.array([1.0]), float(long_sr)
        if (
            np.isfinite(short_sr)
            and (not np.isfinite(long_sr) or short_sr > long_sr)
            and short_sr > 0
        ):
            return np.array([-1.0]), float(short_sr)
        return weights, sr

    # n_factors > 1: try unconstrained MVE first, then enumerate 3^(K-1) combs.
    start_weights, start_sr = calc_mve(r_long)
    non_mkt = start_weights[1:]
    n_non_mkt = n_factors - 1
    if np.sum(non_mkt > 0) == n_non_mkt and start_sr > sr:
        return start_weights, float(start_sr)

    n_combs = 3 ** (n_factors - 1)
    # posIndex: col 0 always long (=1); cols 1.. use base-3 digits {0,1,2}
    # MATLAB: xt = [nCombs:-1:1]'-1; ttemp = mod(xt,3); xt=(xt-ttemp)/3
    pos_index = np.zeros((n_combs, n_factors), dtype=int)
    pos_index[:, 0] = 1
    xt = np.arange(n_combs - 1, -1, -1, dtype=int)  # nCombs-1 … 0
    for i in range(1, n_factors):
        ttemp = xt % 3
        xt = (xt - ttemp) // 3
        pos_index[:, i] = ttemp

    for i in range(n_combs):
        this_pos = pos_index[i]
        this_rets = r_long.copy()
        ind_short = this_pos == 2
        if np.any(ind_short):
            this_rets[:, ind_short] = r_short[:, ind_short]
        ind_not_held = this_pos == 0
        held = ~ind_not_held
        held_rets = this_rets[:, held]
        n_left = int(held.sum())
        if n_left == 0:
            continue
        comb_w, comb_sr = calc_mve(held_rets)
        # All non-market held weights strictly positive
        if n_left == 1 or np.sum(comb_w[1:] > 0) == (n_left - 1):
            if comb_sr > sr:
                sr = float(comb_sr)
                temp = np.zeros(n_factors, dtype=float)
                # map held weights back; short legs flip sign
                held_idx = np.where(held)[0]
                for j, h in enumerate(held_idx):
                    if this_pos[h] == 1:
                        temp[h] = comb_w[j]
                    elif this_pos[h] == 2:
                        temp[h] = -comb_w[j]
                weights = temp
    return weights, sr


def calc_gen_alpha(
    anom_ret: np.ndarray | pd.Series,
    anom_tcosts: np.ndarray | pd.Series,
    factor_rets: np.ndarray | pd.DataFrame,
    factor_tcosts: np.ndarray | pd.DataFrame,
    print_res: bool = False,
    *,
    anom_tcosts_short: np.ndarray | pd.Series | None = None,
    factor_tcosts_short: np.ndarray | pd.DataFrame | None = None,
) -> tuple[OlsRes, np.ndarray, np.ndarray]:
    """Port of MATLAB ``calcGenAlpha``, with both MVEs on a common sample.

    Departure from MATLAB: the factor-only MVE ``w_x`` and the
    joint MVE ``w_x_y`` are estimated on the same months, those in which the
    anomaly return, its cost and every factor return and cost are finite
    (``_common_rows``). MATLAB estimates ``w_x`` on every month with factor
    data, so for a strategy that starts after the window opens the joint MVE
    re-optimizes the factor weights on the shorter sample and the intercept
    picks up that in-sample gain, divided by ``|w_y|``. The regression sample
    is unchanged (it was already the common months), and a strategy covering
    every month gets bit-for-bit the MATLAB result. The intercept is per unit
    of ``|w_y|``, positive whichever side the net MVE holds (NMV 2016).

    Parameters
    ----------
    anom_ret
        Gross anomaly long-short returns (T,).
    anom_tcosts
        Trading costs of the anomaly L/S (T,).
    factor_rets
        Gross factor returns (T × K).
    factor_tcosts
        Factor trading costs (T × K), same columns/order as ``factor_rets``.
    print_res
        If True, print the OLS result via ``prt``.
    anom_tcosts_short
        Optional. Trading costs of the anomaly held short (T,): the cost of
        the same two portfolios with the legs exchanged
        (``SortResult.tcosts_ts_short``). Needed only when the costs were
        computed with ``convention="capital"``, under which this is not
        ``anom_tcosts``. When omitted, a short position is charged
        ``anom_tcosts``.
    factor_tcosts_short
        Optional. The same for the factors (T x K, columns as
        ``factor_tcosts``). When omitted, a short position in a factor is
        charged ``factor_tcosts``; if ``anom_tcosts_short`` is given without
        it, a warning says so.

    With neither optional argument the calculation is the one this function
    always did. With them, the net return of a short position is
    ``-gross - short cost`` in the search for both MVE portfolios, and the
    returns of the portfolios found charge each asset its long cost where its
    weight is positive and its short cost where it is negative.

    Returns
    -------
    alpha_res : OlsRes
        OLS of 100·y on [1, x] where y is the cost-adjusted MVE of
        (factors, anomaly) scaled by |w_y| and x is the cost-adjusted
        factor MVE.
    w_x_y : (K+1,) ndarray
        MVE weights on (factors, anomaly).
    w_x : (K,) ndarray
        MVE weights on factors alone.
    """
    y_anom = np.asarray(pd.Series(anom_ret).astype(float), dtype=float).ravel()
    tc_anom = np.asarray(pd.Series(anom_tcosts).astype(float), dtype=float).ravel()
    f_rets = np.asarray(factor_rets, dtype=float)
    f_tc = np.asarray(factor_tcosts, dtype=float)
    if f_rets.ndim == 1:
        f_rets = f_rets[:, None]
    if f_tc.ndim == 1:
        f_tc = f_tc[:, None]

    for name, frame in (("factor_rets", factor_rets), ("factor_tcosts", factor_tcosts)):
        if isinstance(frame, pd.DataFrame) and frame.columns.has_duplicates:
            dups = sorted({str(c) for c in frame.columns[frame.columns.duplicated()]})
            raise ValueError(f"{name} has duplicate column labels {dups}.")

    t = y_anom.shape[0]
    if tc_anom.shape[0] != t or f_rets.shape[0] != t or f_tc.shape[0] != t:
        raise ValueError(
            "Anomaly return and factors return series are different lengths."
        )
    # Validate before the net-MVE search: a factor without a matching cost
    # column (or the reverse) would silently pair the wrong series.
    if f_rets.shape[1] != f_tc.shape[1]:
        raise ValueError(
            f"factor_rets has {f_rets.shape[1]} columns but factor_tcosts has "
            f"{f_tc.shape[1]}; each factor needs exactly one cost column."
        )

    gross_anom_factors = np.column_stack([f_rets, y_anom])
    tcosts_anom_factors = np.column_stack([f_tc, tc_anom])

    # Costs of short positions, when they are not the costs of long ones.
    short_costs = anom_tcosts_short is not None or factor_tcosts_short is not None
    tc_anom_s, f_tc_s = tc_anom, f_tc
    if anom_tcosts_short is not None:
        tc_anom_s = np.asarray(pd.Series(anom_tcosts_short).astype(float), dtype=float).ravel()
        if tc_anom_s.shape[0] != t:
            raise ValueError("anom_tcosts_short and anom_ret are different lengths.")
    if factor_tcosts_short is not None:
        f_tc_s = np.asarray(factor_tcosts_short, dtype=float)
        if f_tc_s.ndim == 1:
            f_tc_s = f_tc_s[:, None]
        if f_tc_s.shape != f_tc.shape:
            raise ValueError(
                f"factor_tcosts_short has shape {f_tc_s.shape}; expected {f_tc.shape}, "
                "the shape of factor_tcosts."
            )
    elif anom_tcosts_short is not None and f_tc.size and np.nansum(np.abs(f_tc)) > 0:
        LOGGER.warning(
            "calc_gen_alpha: anom_tcosts_short was given without factor_tcosts_short; "
            "a factor held short is charged its ordinary cost"
        )
    # Short costs equal to the long ones change nothing: the ordinary calculation.
    short_costs = short_costs and not (
        np.array_equal(tc_anom_s, tc_anom, equal_nan=True)
        and np.array_equal(f_tc_s, f_tc, equal_nan=True)
    )
    tcosts_short_anom_factors = np.column_stack([f_tc_s, tc_anom_s])

    # One sample for both MVEs (and, as before, the regression).
    rows = _common_rows(y_anom, tc_anom, f_rets, f_tc)
    if short_costs:
        rows &= np.isfinite(tcosts_short_anom_factors).all(axis=1)
    g_c, tc_c = gross_anom_factors[rows], tcosts_anom_factors[rows]
    f_c, ftc_c = f_rets[rows], f_tc[rows]
    tcs_c, ftcs_c = tcosts_short_anom_factors[rows], f_tc_s[rows]

    if rows.sum() < 2:
        # No covariance from fewer than two months: zero weights, as calc_mve
        # returns for a degenerate sample (classify_gen_alpha: "unavailable").
        w_x_y = np.zeros(gross_anom_factors.shape[1])
        w_x = np.zeros(f_rets.shape[1])
    else:
        w_x_y, _ = calc_net_mve(g_c - tc_c, -g_c - tcs_c)
        w_x, _ = calc_net_mve(f_c - ftc_c, -f_c - ftcs_c)

    def _net(gross: np.ndarray, long_tc: np.ndarray, short_tc: np.ndarray, w: np.ndarray):
        """Net return of the portfolio ``w``: long costs on its long positions,
        short costs on its short ones."""
        if not short_costs:
            return gross @ w - long_tc @ np.abs(w)
        return gross @ w - long_tc @ np.maximum(w, 0.0) - short_tc @ np.maximum(-w, 0.0)

    if w_x_y[-1] != 0:
        y = _net(
            gross_anom_factors, tcosts_anom_factors, tcosts_short_anom_factors, w_x_y
        ) / abs(float(w_x_y[-1]))
        x = _net(f_rets, f_tc, f_tc_s, w_x)
        # Outside the common rows y is already non-finite; make it explicit.
        y = np.where(rows, y, np.nan)
        X = np.column_stack([np.ones(t), x])
        alpha_res = nanols(100.0 * y, X, labels=["const", "mve_x"])
    else:
        # MATLAB: ols(ones(size(anomRet)), nan(size(anomRet))) → nans
        alpha_res = OlsRes(
            beta=np.array([np.nan]),
            tstat=np.array([np.nan]),
            bstd=np.array([np.nan]),
            resid=np.array([]),
            yhat=np.array([]),
            sige=np.nan,
            rsqr=np.nan,
            rbar=np.nan,
            nobs=t,
            nvar=1,
            labels=["const"],
        )

    if print_res:
        prt(alpha_res)
    return alpha_res, w_x_y, w_x


# ---------------------------------------------------------------------------
# Outcome classification
# ---------------------------------------------------------------------------
# MATLAB `makeResToPrint` sets every NaN net generalized alpha to zero. A NaN
# there has two unrelated causes: the anomaly gets zero weight in the net MVE
# portfolio (it does not expand the frontier, so its generalized alpha *is*
# zero), or the calculation never produced a number. Only the first is an
# economic zero; the second must stay missing.
GEN_ALPHA_STATUSES: tuple[str, ...] = ("success", "zero", "unavailable", "failed")


@dataclass(frozen=True)
class GenAlphaOutcome:
    """What one generalized-alpha calculation produced.

    Attributes
    ----------
    status
        ``"success"``: a finite intercept from a held anomaly.
        ``"zero"``: the anomaly has zero weight in the net MVE portfolio, so
        its generalized alpha is zero by construction (no t-statistic).
        ``"unavailable"``: too few complete months, or no finite estimate.
        ``"failed"``: the calculation raised.
    value
        Generalized alpha in %/month: the intercept, ``0.0`` for ``"zero"``,
        NaN otherwise.
    tstat
        t-statistic of the intercept for ``"success"``, NaN otherwise.
    n_obs
        Complete months (all factor and anomaly net returns finite), or -1
        when unknown. Both MVEs and the regression use exactly these months.
    reason
        Human-readable cause for anything other than ``"success"``.
    w_anom
        The anomaly's weight in the net MVE portfolio of (factors, anomaly),
        ``w_x_y[-1]``: negative when the portfolio holds the strategy short,
        0.0 for ``"zero"``, NaN when unknown. ``value`` is per unit of
        ``|w_anom|`` (NMV 2016), so a tiny weight can make a modest intercept
        look large; the weight is recorded so reports can show it.
    """

    status: str
    value: float = float("nan")
    tstat: float = float("nan")
    n_obs: int = -1
    reason: str = ""
    w_anom: float = float("nan")

    def __post_init__(self) -> None:
        if self.status not in GEN_ALPHA_STATUSES:
            raise ValueError(f"status must be one of {GEN_ALPHA_STATUSES}; got {self.status!r}")

    @property
    def is_valid(self) -> bool:
        """True when ``value`` belongs in a distribution (success or zero)."""
        return self.status in ("success", "zero")

    @classmethod
    def failed(cls, exc: BaseException, n_obs: int = -1) -> "GenAlphaOutcome":
        return cls("failed", n_obs=n_obs, reason=f"{type(exc).__name__}: {exc}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "value": float(self.value),
            "tstat": float(self.tstat),
            "n_obs": int(self.n_obs),
            "reason": self.reason,
            "w_anom": float(self.w_anom),
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "GenAlphaOutcome":
        return cls(
            status=str(d["status"]),
            value=float(d.get("value", np.nan)),
            tstat=float(d.get("tstat", np.nan)),
            n_obs=int(d.get("n_obs", -1)),
            reason=str(d.get("reason", "")),
            w_anom=float(d.get("w_anom", np.nan)),
        )


def _common_rows(anom_ret, anom_tcosts, factor_rets, factor_tcosts) -> np.ndarray:
    """Boolean mask of the months in which the anomaly return, its cost and
    every factor return and cost are finite: the one sample on which
    ``calc_gen_alpha`` estimates both MVEs and the regression."""
    y = np.asarray(anom_ret, dtype=float).reshape(-1, 1)
    tc = np.asarray(anom_tcosts, dtype=float).reshape(-1, 1)
    f = np.asarray(factor_rets, dtype=float)
    ftc = np.asarray(factor_tcosts, dtype=float)
    if f.ndim == 1:
        f = f[:, None]
    if ftc.ndim == 1:
        ftc = ftc[:, None]
    return np.isfinite(np.column_stack([f, ftc, y, tc])).all(axis=1)


def _complete_obs(
    anom_ret, anom_tcosts, factor_rets, factor_tcosts,
    anom_tcosts_short=None, factor_tcosts_short=None,
) -> int:
    """Months in which every factor and the anomaly have finite net returns
    (also as short positions, when their short costs are given)."""
    rows = _common_rows(anom_ret, anom_tcosts, factor_rets, factor_tcosts)
    for extra in (anom_tcosts_short, factor_tcosts_short):
        if extra is not None:
            arr = np.asarray(extra, dtype=float)
            rows = rows & np.isfinite(arr.reshape(len(rows), -1)).all(axis=1)
    return int(rows.sum())


def classify_gen_alpha(
    alpha_res: OlsRes | None,
    w_x_y: np.ndarray | None,
    n_obs: int = -1,
) -> GenAlphaOutcome:
    """Classify a ``calc_gen_alpha`` result as success, zero or unavailable.

    ``n_obs`` is the number of complete months; pass -1 when unknown (for
    example a stored result without its inputs) to skip the sample check.
    With ``K`` factors plus the anomaly the sample covariance of the ``K + 1``
    net returns is singular below ``K + 2`` months, and ``calc_mve`` then
    returns zero weights for lack of data rather than for economic reasons,
    so such a sample is ``"unavailable"``, never ``"zero"``.
    """
    if alpha_res is None or w_x_y is None:
        return GenAlphaOutcome("unavailable", n_obs=n_obs, reason="no estimate stored")
    w = np.asarray(w_x_y, dtype=float).ravel()
    if w.size == 0:
        return GenAlphaOutcome("unavailable", n_obs=n_obs, reason="empty MVE weights")
    n_min = w.size + 1
    if 0 <= n_obs < n_min:
        return GenAlphaOutcome(
            "unavailable",
            n_obs=n_obs,
            reason=f"{n_obs} complete months for {w.size} assets; need at least {n_min}",
        )
    w_anom = float(w[-1])
    if w_anom == 0:
        return GenAlphaOutcome(
            "zero", value=0.0, n_obs=n_obs,
            reason="anomaly has zero weight in the net MVE portfolio", w_anom=0.0,
        )
    beta = np.asarray(getattr(alpha_res, "beta", []), dtype=float).ravel()
    tstat = np.asarray(getattr(alpha_res, "tstat", []), dtype=float).ravel()
    b0 = float(beta[0]) if beta.size else np.nan
    if not np.isfinite(b0):
        return GenAlphaOutcome(
            "unavailable", n_obs=n_obs, reason="non-finite intercept", w_anom=w_anom
        )
    t0 = float(tstat[0]) if tstat.size else np.nan
    return GenAlphaOutcome("success", value=b0, tstat=t0, n_obs=n_obs, w_anom=w_anom)


def estimate_gen_alpha(
    anom_ret: np.ndarray | pd.Series,
    anom_tcosts: np.ndarray | pd.Series,
    factor_rets: np.ndarray | pd.DataFrame,
    factor_tcosts: np.ndarray | pd.DataFrame,
    *,
    anom_tcosts_short: np.ndarray | pd.Series | None = None,
    factor_tcosts_short: np.ndarray | pd.DataFrame | None = None,
) -> tuple[GenAlphaOutcome, OlsRes | None, np.ndarray | None, np.ndarray | None]:
    """Run ``calc_gen_alpha`` and classify what it produced.

    ``anom_tcosts_short`` and ``factor_tcosts_short`` are the optional costs
    of short positions (see ``calc_gen_alpha``); leave them out when the costs
    are those of ``convention="dollar"``.

    Exceptions are caught and reported as ``"failed"`` with the error in
    ``reason``; they never become a number. Returns
    ``(outcome, alpha_res, w_x_y, w_x)``, the last three None on failure.
    """
    # Short-position costs are passed on only when there are some.
    short_kw = {}
    if anom_tcosts_short is not None:
        short_kw["anom_tcosts_short"] = anom_tcosts_short
    if factor_tcosts_short is not None:
        short_kw["factor_tcosts_short"] = factor_tcosts_short
    try:
        alpha_res, w_x_y, w_x = calc_gen_alpha(
            anom_ret, anom_tcosts, factor_rets, factor_tcosts, print_res=False, **short_kw
        )
        n_obs = _complete_obs(
            anom_ret, anom_tcosts, factor_rets, factor_tcosts,
            anom_tcosts_short, factor_tcosts_short,
        )
    except Exception as exc:  # noqa: BLE001 -- recorded as a failed outcome
        return GenAlphaOutcome.failed(exc), None, None, None
    return classify_gen_alpha(alpha_res, w_x_y, n_obs), alpha_res, w_x_y, w_x


def summarize_gen_alpha_outcomes(
    outcomes: Mapping[Any, GenAlphaOutcome],
) -> dict[str, Any]:
    """Counts per status, one record for every non-success outcome, and the
    anomaly's net-MVE weight for every key (``w_anom``; NaN when unknown)."""
    counts = {s: 0 for s in GEN_ALPHA_STATUSES}
    issues: list[dict[str, Any]] = []
    for key, oc in outcomes.items():
        counts[oc.status] += 1
        if oc.status != "success":
            issues.append({"key": key, **oc.to_dict()})
    return {
        "counts": counts,
        "n_valid": counts["success"] + counts["zero"],
        "n_total": len(outcomes),
        "issues": issues,
        "w_anom": {key: float(oc.w_anom) for key, oc in outcomes.items()},
    }


def factor_matrix_for_gen_alpha(
    factor_model: int,
    dates: pd.Index,
    factors: pd.DataFrame | None = None,
    factor_tcosts: pd.DataFrame | None = None,
    *,
    db_path: Any = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Select and align factor returns / tcosts for a gen-α factor model code.

    Mirrors the ``switch f`` block in ``makeBasicSortsResults.m`` (plain
    ``smb``, not ``smb2``). Columns are selected by name, so a full factor
    bundle that also carries ``smb2`` (the ordinary FF5/FF6 SMB) is used
    as-is; ``smb2`` is never renamed onto ``smb``. An explicit ``factors``
    frame is authoritative: ``load_factors`` runs only when it is omitted.

    Aliases (``mktrf``, ``umd``; ``mom_tc`` for costs) are used only when the
    canonical column is absent, so a frame carrying both spellings keeps its
    canonical column. Repeated column labels collapse to one column when the
    copies are identical and raise ``ValueError`` when they differ. The
    returned frames always have one column per model factor, in the same
    order, so returns and costs pair up position by position.
    """
    if factor_model not in GEN_ALPHA_FACTOR_COLS:
        raise ValueError(
            f"factor_model must be one of {sorted(GEN_ALPHA_FACTOR_COLS)}; "
            f"got {factor_model}."
        )
    fcols = GEN_ALPHA_FACTOR_COLS[factor_model]
    tcols = GEN_ALPHA_TCOST_COLS[factor_model]

    from . import sorts

    if factors is None:
        factors = sorts.load_factors(db_path)

    fac = sorts._canonical_factor_names(factors)
    missing = [c for c in fcols if c not in fac.columns]
    if missing:
        raise ValueError(f"Missing factor columns for gen-α model {factor_model}: {missing}")
    f_df = _select_unique(fac, fcols, "factors").reindex(dates)

    if factor_tcosts is None:
        tc_df = pd.DataFrame(0.0, index=dates, columns=tcols)
    else:
        tc = factor_tcosts
        # Allow mom_tc alias for umd_tc
        if "umd_tc" not in tc.columns and "mom_tc" in tc.columns:
            tc = tc.rename(columns={"mom_tc": "umd_tc"})
        tc_sel = _select_unique(tc, [c for c in tcols if c in tc.columns], "factor_tcosts")
        for c in tcols:
            if c not in tc_sel.columns:
                tc_sel[c] = 0.0
        tc_df = tc_sel[tcols].reindex(dates)

    if list(f_df.columns) != fcols or tc_df.shape != f_df.shape:
        raise ValueError(
            f"gen-α model {factor_model}: factor returns {f_df.shape} "
            f"{list(f_df.columns)} and factor costs {tc_df.shape} "
            f"{list(tc_df.columns)} do not line up."
        )
    return f_df, tc_df


def factor_short_tcosts_for_gen_alpha(
    factor_model: int,
    dates: pd.Index,
    factor_tcosts: pd.DataFrame | None,
) -> pd.DataFrame | None:
    """The costs of the model's factors held short, or None when there are none.

    ``factor_tcosts`` may carry, beside ``smb_tc`` .., columns ``smb_tc_short``
    .. (``SHORT_TCOST_SUFFIX``): the cost of each factor with its sides
    exchanged, which under ``convention="capital"`` is not its ordinary cost.
    A protocol run under ``"capital"`` loads them from the database. Returns a
    frame aligned with the second output of :func:`factor_matrix_for_gen_alpha`
    (same dates, same columns, same order); a factor without a short column
    keeps its ordinary cost (``mkt_tc`` always does). Returns None when
    ``factor_tcosts`` has no short column for this model, so that the caller
    passes nothing and the calculation is the ordinary one.
    """
    if factor_tcosts is None:
        return None
    tc = factor_tcosts
    if "umd_tc" not in tc.columns and "mom_tc" in tc.columns:
        tc = tc.rename(columns={"mom_tc": "umd_tc", f"mom_tc{SHORT_TCOST_SUFFIX}": f"umd_tc{SHORT_TCOST_SUFFIX}"})
    tcols = GEN_ALPHA_TCOST_COLS[factor_model]
    short = {c: f"{c}{SHORT_TCOST_SUFFIX}" for c in tcols if f"{c}{SHORT_TCOST_SUFFIX}" in tc.columns}
    if not short:
        return None
    use = [short.get(c, c) for c in tcols]
    sel = _select_unique(tc, [c for c in use if c in tc.columns], "factor_tcosts")
    out = pd.DataFrame(index=tc.index)
    for c, src in zip(tcols, use):
        out[c] = sel[src] if src in sel.columns else 0.0
    return out[tcols].reindex(dates)


def _select_unique(df: pd.DataFrame, cols: list[str], what: str) -> pd.DataFrame:
    """Select ``cols`` by name, one column each.

    ``df[cols]`` returns every column carrying a repeated label, which is how
    a duplicated ``smb`` turned a three-factor model into four columns. Here a
    repeated label is collapsed when all copies agree (NaN equal to NaN) and
    rejected when they do not, since there is no principled way to pick one.
    """
    out: dict[str, pd.Series] = {}
    for c in cols:
        block = df.loc[:, df.columns == c]
        first = block.iloc[:, 0]
        for k in range(1, block.shape[1]):
            if not np.array_equal(
                first.to_numpy(dtype=float),
                block.iloc[:, k].to_numpy(dtype=float),
                equal_nan=True,
            ):
                raise ValueError(
                    f"{what} has {block.shape[1]} columns named {c!r} with "
                    "different values; keep exactly one before estimating "
                    "generalized alpha."
                )
        out[c] = first
    return pd.DataFrame(out, index=df.index, columns=cols)
