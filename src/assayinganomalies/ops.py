from __future__ import annotations

import numpy as np
import pandas as pd


def log(x: pd.Series, *, min_positive: float = 0.0) -> pd.Series:
    """
    Safe log helper for panel Series.

    - Returns NaN where x <= min_positive or x is non-finite.
    - Preserves index.
    - Sets a helpful name like 'log(me)' if the input series is named 'me'.
    """
    s = pd.to_numeric(x, errors="coerce")
    s = s.where(np.isfinite(s))
    s = s.where(s > min_positive)
    out = np.log(s)
    base = x.name if getattr(x, "name", None) else "x"
    out.name = f"log({base})"
    return out


__all__ = ["log"]


