"""
Ken French data library downloads.

Currently implements the 25 size/book-to-market portfolios (the monthly
value-weighted block of ``25_Portfolios_5x5``) used by the Fama-French (1993)
replication in ``use_library``.
"""

from __future__ import annotations

import io
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

__all__ = ["FF25_URL", "load_ff25"]

FF25_URL = ("https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
            "25_Portfolios_5x5_CSV.zip")


def load_ff25(url: str = FF25_URL, cache: str | Path | None = None) -> pd.DataFrame:
    """Fetch and parse the monthly value-weighted block of the 25 5x5 portfolios.

    Parameters
    ----------
    url : str
        Zip archive URL on Ken French's data library.
    cache : path-like, optional
        Local CSV cache. If the file exists it is read instead of downloading;
        if it does not exist, the download is saved there. If omitted, the
        file is downloaded to memory on every call.

    Returns
    -------
    pd.DataFrame
        Month-end-indexed portfolio returns as decimals; the -99.99 missing
        codes are masked to NaN.
    """
    cache = Path(cache) if cache is not None else None
    if cache is not None and cache.exists():
        text = cache.read_text(encoding="latin-1")
    else:
        with urllib.request.urlopen(url, timeout=120) as resp:
            blob = resp.read()
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            raw = zf.read(zf.namelist()[0])
        if cache is not None:
            cache.write_bytes(raw)
        text = raw.decode("latin-1")
    lines = text.splitlines()

    header, rows = None, []
    for line in lines:
        cells = [c.strip() for c in line.split(",")]
        if header is None:
            if len(cells) > 20 and not cells[0]:
                header = [c for c in cells[1:] if c]
            continue
        if len(cells[0]) == 6 and cells[0].isdigit():
            vals = [float(c) for c in cells[1:] if c]
            if len(vals) == len(header):
                rows.append([int(cells[0])] + vals)
        elif rows:
            break                      # end of the monthly value-weighted block
    if header is None or not rows:
        raise ValueError("Could not parse the FF25 monthly value-weighted block.")

    out = pd.DataFrame(rows, columns=["yyyymm"] + header)
    out["date"] = pd.to_datetime(out["yyyymm"], format="%Y%m") + pd.offsets.MonthEnd(0)
    out = out.set_index("date").drop(columns="yyyymm")
    n_missing = int((out <= -99.98).sum().sum())
    if n_missing:
        print(f"masked {n_missing} missing values coded -99.99")
    return out.mask(out <= -99.98) / 100.0
