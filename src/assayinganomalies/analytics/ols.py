"""
NaN-tolerant OLS utilities.

Python ports of the MATLAB/jplv7 helpers used throughout the toolkit:

- ``nanols``  : ``Functions/Utilities/nanols.m`` — OLS after dropping rows
  with any NaN in ``[y x]``.
- ``prt``     : the jplv7 ``prt`` display for an OLS result struct.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

__all__ = ["OlsRes", "nanols", "prt"]


@dataclass
class OlsRes:
    """Python analogue of the MATLAB ``nanols``/``ols`` result struct."""

    beta: np.ndarray
    tstat: np.ndarray
    bstd: np.ndarray
    resid: np.ndarray
    yhat: np.ndarray
    sige: float
    rsqr: float
    rbar: float
    nobs: int
    nvar: int
    labels: list


def nanols(y, x, labels=None) -> OlsRes:
    """Port of ``nanols.m``: OLS after dropping rows with any NaN."""
    y = np.asarray(pd.Series(y).astype(float))
    X = np.asarray(x, dtype=float)
    if X.ndim == 1:
        X = X[:, None]
    ok = np.isfinite(y) & np.isfinite(X).all(axis=1)
    y, X = y[ok], X[ok]
    n, k = X.shape
    labels = labels or [f"x{i}" for i in range(1, k + 1)]
    if n < 2:
        nan_k = np.full(k, np.nan)
        return OlsRes(nan_k, nan_k, nan_k, np.array([]), np.array([]),
                      np.nan, np.nan, np.nan, 0, k, labels)
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ (X.T @ y)
    yhat = X @ beta
    resid = y - yhat
    sige = float(resid @ resid) / (n - k)
    bstd = np.sqrt(np.diag(sige * XtX_inv))
    tstat = beta / bstd
    ss_tot = float(((y - y.mean()) ** 2).sum())
    rsqr = 1 - float(resid @ resid) / ss_tot if ss_tot > 0 else np.nan
    rbar = 1 - (1 - rsqr) * (n - 1) / (n - k) if np.isfinite(rsqr) and n > k else np.nan
    return OlsRes(beta, tstat, bstd, resid, yhat, sige, rsqr, rbar, n, k, labels)


def prt(res: OlsRes, title: str = "Ordinary Least-squares Estimates") -> None:
    """Port of the jplv7 ``prt`` display for an OLS result."""
    print(title)
    print(f"R-squared      = {res.rsqr:8.4f}")
    print(f"Rbar-squared   = {res.rbar:8.4f}")
    print(f"sigma^2        = {res.sige:8.4f}")
    print(f"Nobs, Nvars    = {res.nobs:6d}, {res.nvar:4d}")
    print("***********************************************")
    print(f"{'Variable':<14}{'Coefficient':>14}{'t-statistic':>14}")
    for lab, b, t in zip(res.labels, res.beta, res.tstat):
        print(f"{lab:<14}{b:14.6f}{t:14.6f}")
    print()
