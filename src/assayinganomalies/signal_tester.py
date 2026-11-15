"""
Signal testing helpers — thin public wrap around :func:`run_test_signal`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .analytics.protocol import ProtocolResult, run_test_signal
from .client import AssayClient
from .signal_io import SignalInfo, default_mpe_signal_info, get_signal_info

__all__ = ["SignalTester", "SignalInfo", "default_mpe_signal_info", "get_signal_info"]


class SignalTester:
    """High-level entry for the assay protocol (MATLAB ``test_signal`` / ``runTestSignal``)."""

    def __init__(self, client: AssayClient | None = None):
        self.client = client or AssayClient.from_config()

    def run(
        self,
        signal: pd.Series | pd.DataFrame | str | Path | None = None,
        info: SignalInfo | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ProtocolResult:
        """
        Run the full assay protocol.

        Parameters
        ----------
        signal
            MultiIndex panel, CSV path, or ``None`` (uses ``info.fileLink``).
        info
            :class:`SignalInfo` or mapping (defaults to MPE cancel-branch metadata).
        **kwargs
            Forwarded to :func:`assayinganomalies.analytics.protocol.run_test_signal`
            (e.g. ``max_anoms``, ``save``, ``out_dir``, ``compute_gen_alpha``).
        """
        metadata = get_signal_info(info)
        if "db_path" not in kwargs and self.client is not None:
            kwargs.setdefault("db_path", self.client.db_path)
        return run_test_signal(signal, metadata, **kwargs)
