"""
Signal file I/O for the assay protocol.

MATLAB equivalents:
  - Functions/Asset pricing/getAnomalySignals.m
  - test_signal.m cancel-branch defaults (MPE signalInfo)
  - getSignalInfo.m (form CSV) — best-effort parse; defaults always available
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

__all__ = [
    "SignalInfo",
    "MPE_DEFAULT_SIGNAL_INFO",
    "get_signal_info",
    "default_mpe_signal_info",
    "get_anomaly_signals",
    "load_signal_csv",
    "yyyymm_to_month_end",
    "month_end_to_yyyymm",
]


@dataclass
class SignalInfo:
    """Metadata for a proposed anomaly signal (MATLAB form / protocol fields).

    Fields mirror MATLAB ``signalInfo`` used by ``runTestSignal`` /
    ``test_signal.m``. Snake_case aliases are accepted at construction via
    :meth:`from_mapping` and exposed as properties for Python callers.
    """

    Authors: str = ""
    email: str = ""
    PaperTitle: str = ""
    SignalName: str = ""
    SignalAcronym: str = ""
    fileLink: str = ""
    # free-form extras (not used by MATLAB gold)
    extras: dict[str, Any] = field(default_factory=dict)

    # ---- pythonic aliases -------------------------------------------------
    @property
    def authors(self) -> str:
        return self.Authors

    @property
    def paper_title(self) -> str:
        return self.PaperTitle

    @property
    def name(self) -> str:
        return self.SignalName

    @property
    def acronym(self) -> str:
        return self.SignalAcronym

    @property
    def file_link(self) -> str:
        return self.fileLink

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        extras = d.pop("extras", {}) or {}
        d.update(extras)
        return d

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any] | None) -> "SignalInfo":
        if data is None:
            return default_mpe_signal_info()
        if isinstance(data, SignalInfo):
            return data
        # Support nested {"info": {...}} from SignalTester
        if "info" in data and isinstance(data["info"], Mapping):
            data = data["info"]  # type: ignore[assignment]
        aliases = {
            "authors": "Authors",
            "Authors": "Authors",
            "email": "email",
            "paper_title": "PaperTitle",
            "PaperTitle": "PaperTitle",
            "name": "SignalName",
            "SignalName": "SignalName",
            "signal_name": "SignalName",
            "acronym": "SignalAcronym",
            "SignalAcronym": "SignalAcronym",
            "signal_acronym": "SignalAcronym",
            "file_link": "fileLink",
            "fileLink": "fileLink",
            "file_path": "fileLink",
        }
        known = {
            "Authors": "",
            "email": "",
            "PaperTitle": "",
            "SignalName": "",
            "SignalAcronym": "",
            "fileLink": "",
        }
        extras: dict[str, Any] = {}
        for k, v in data.items():
            if k == "extras" and isinstance(v, Mapping):
                extras.update(v)
                continue
            canon = aliases.get(str(k))
            if canon is not None:
                known[canon] = "" if v is None else str(v)
            else:
                extras[str(k)] = v
        return cls(**known, extras=extras)


# Cancel-branch of test_signal.m (and gold ResStruct.signalInfo).
MPE_DEFAULT_SIGNAL_INFO = SignalInfo(
    Authors="Robert Novy-Marx and Mihail Velikov",
    email="assayinganomalies@gmail.com",
    PaperTitle="Assaying Anomalies",
    SignalName="Monetary Policy Exposure",
    SignalAcronym="MPE",
    fileLink="mpe.csv",
)


def default_mpe_signal_info(file_link: str | Path | None = None) -> SignalInfo:
    """MATLAB cancel-branch MPE metadata; optional override of ``fileLink``."""
    info = SignalInfo(
        Authors=MPE_DEFAULT_SIGNAL_INFO.Authors,
        email=MPE_DEFAULT_SIGNAL_INFO.email,
        PaperTitle=MPE_DEFAULT_SIGNAL_INFO.PaperTitle,
        SignalName=MPE_DEFAULT_SIGNAL_INFO.SignalName,
        SignalAcronym=MPE_DEFAULT_SIGNAL_INFO.SignalAcronym,
        fileLink=str(file_link) if file_link is not None else MPE_DEFAULT_SIGNAL_INFO.fileLink,
    )
    return info


def get_signal_info(
    source: str | Path | Mapping[str, Any] | None = None,
    *,
    file_link: str | Path | None = None,
) -> SignalInfo:
    """Resolve signal metadata.

    Parameters
    ----------
    source
        - ``None``: MATLAB cancel-branch MPE defaults.
        - Mapping / SignalInfo: normalized via :meth:`SignalInfo.from_mapping`.
        - Path to a small form-export CSV: best-effort parse of name/value
          rows or a single-row wide table with the MATLAB field names.
    file_link
        Override ``fileLink`` after resolve (e.g. absolute path to ``mpe.csv``).
    """
    if source is None:
        info = default_mpe_signal_info(file_link)
    elif isinstance(source, (str, Path)) and Path(source).is_file():
        info = _parse_form_csv(Path(source))
        if file_link is not None:
            info.fileLink = str(file_link)
    else:
        info = SignalInfo.from_mapping(source if not isinstance(source, (str, Path)) else {"fileLink": str(source)})
        if file_link is not None:
            info.fileLink = str(file_link)
    if file_link is not None and not info.fileLink:
        info.fileLink = str(file_link)
    return info


def _parse_form_csv(path: Path) -> SignalInfo:
    """Best-effort parse of a website form export used by MATLAB getSignalInfo."""
    df = pd.read_csv(path)
    if df.empty:
        return default_mpe_signal_info()
    # Wide one-row form
    if len(df) == 1 and any(c in df.columns for c in ("SignalAcronym", "signal_acronym", "Authors")):
        return SignalInfo.from_mapping(df.iloc[0].to_dict())
    # Two-column key/value
    if df.shape[1] >= 2:
        keys = df.iloc[:, 0].astype(str).str.strip()
        vals = df.iloc[:, 1]
        return SignalInfo.from_mapping(dict(zip(keys, vals)))
    return default_mpe_signal_info(file_link=str(path))


def yyyymm_to_month_end(yyyymm: int | float | str) -> pd.Timestamp:
    """Convert YYYYMM (MATLAB library ``dates``) to month-end Timestamp."""
    v = int(float(yyyymm))
    y, m = divmod(v, 100)
    if not (1 <= m <= 12):
        raise ValueError(f"invalid YYYYMM month: {yyyymm}")
    return pd.Timestamp(year=y, month=m, day=1) + pd.offsets.MonthEnd(0)


def month_end_to_yyyymm(ts: pd.Timestamp | Any) -> int:
    """Month-end (or any) Timestamp → YYYYMM int."""
    t = pd.Timestamp(ts)
    return int(t.year * 100 + t.month)


def get_anomaly_signals(
    file_name: str | Path,
    permno_column: str | int = "permno",
    dates_column: str | int = "dates",
    *,
    anomaly_names: Sequence[str] | int | Sequence[int] | None = None,
    dates_format: str = "yyyymm",
    panel_index: pd.MultiIndex | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Load long (permno × month × signal) CSV into a (date, permno)-indexed panel.

    MATLAB: ``getAnomalySignals.m``. When ``panel_index`` is supplied the
    result is left-joined onto that full library grid (NaN outside the CSV),
    matching the MATLAB outer join onto ``dates`` × ``permno``.

    Returns
    -------
    (panel, labels)
        ``panel`` has one column per anomaly signal; MultiIndex
        ``(date, permno)`` with month-end dates. ``labels`` are column names
        in the same order as ``panel.columns``.
    """
    path = Path(file_name)
    if not path.is_file():
        # MATLAB also allowed URL; we only support local paths in the port
        raise FileNotFoundError(f"signal file not found: {file_name}")

    header = pd.read_csv(path, nrows=0)
    cols = list(header.columns)

    def _resolve_col(spec: str | int, kind: str) -> str:
        if isinstance(spec, int):
            if spec < 0 or spec >= len(cols):
                raise ValueError(f"wrong {kind} column index: {spec}")
            return cols[spec]
        if spec not in cols:
            raise ValueError(f"wrong {kind} column: {spec!r}; available={cols}")
        return spec

    pcol = _resolve_col(permno_column, "permno")
    dcol = _resolve_col(dates_column, "dates")

    if anomaly_names is None or anomaly_names == "":
        labels = [c for c in cols if c not in (pcol, dcol)]
    elif isinstance(anomaly_names, (int, np.integer)):
        labels = [cols[int(anomaly_names)]]
    elif isinstance(anomaly_names, str):
        labels = [anomaly_names]
    elif isinstance(anomaly_names, Sequence) and anomaly_names and isinstance(anomaly_names[0], (int, np.integer)):
        labels = [cols[int(i)] for i in anomaly_names]  # type: ignore[arg-type]
    else:
        labels = [str(x) for x in anomaly_names]  # type: ignore[union-attr]
        missing = [c for c in labels if c not in cols]
        if missing:
            raise ValueError(f"wrong anomaly header names: {missing}")

    if not labels:
        raise ValueError(f"no anomaly columns found in {path}")

    usecols = [pcol, dcol, *labels]
    raw = pd.read_csv(path, usecols=usecols)

    # Dates → month-end
    if dates_format == "yyyymm":
        dates = raw[dcol].map(yyyymm_to_month_end)
    else:
        dates = pd.to_datetime(raw[dcol], format=dates_format, errors="coerce")
        dates = dates + pd.offsets.MonthEnd(0)

    raw = raw.copy()
    raw["_date"] = dates
    raw["_permno"] = pd.to_numeric(raw[pcol], errors="coerce").astype("Int64")
    raw = raw.dropna(subset=["_date", "_permno"])
    raw["_permno"] = raw["_permno"].astype(np.int64)

    # Keep last observation on duplicate (permno, date) for a signal
    raw = raw.sort_values(["_date", "_permno"])
    raw = raw.drop_duplicates(subset=["_date", "_permno"], keep="last")

    pieces: list[pd.Series] = []
    for lab in labels:
        s = pd.Series(
            pd.to_numeric(raw[lab], errors="coerce").to_numpy(dtype=float),
            index=pd.MultiIndex.from_arrays(
                [raw["_date"].to_numpy(), raw["_permno"].to_numpy()],
                names=["date", "permno"],
            ),
            name=str(lab),
        )
        pieces.append(s)

    panel = pd.concat(pieces, axis=1)
    panel = panel.sort_index()

    if panel_index is not None:
        # Left-join onto library grid (MATLAB outerjoin onto dates×permno)
        panel = panel.reindex(panel_index)

    return panel, [str(c) for c in panel.columns]


def load_signal_csv(
    file_name: str | Path,
    *,
    signal_column: str | None = None,
    permno_column: str | int = "permno",
    dates_column: str | int = "dates",
    dates_format: str = "yyyymm",
    panel_index: pd.MultiIndex | None = None,
) -> pd.Series:
    """Load a single signal column as a MultiIndex Series (convenience wrapper)."""
    names: Sequence[str] | None = None if signal_column is None else [signal_column]
    panel, labels = get_anomaly_signals(
        file_name,
        permno_column,
        dates_column,
        anomaly_names=names,
        dates_format=dates_format,
        panel_index=panel_index,
    )
    if signal_column is None:
        if panel.shape[1] != 1:
            raise ValueError(
                f"expected one signal column, got {list(panel.columns)}; "
                "pass signal_column=..."
            )
        col = panel.columns[0]
    else:
        col = signal_column if signal_column in panel.columns else labels[0]
    return panel[col].rename(str(col))
