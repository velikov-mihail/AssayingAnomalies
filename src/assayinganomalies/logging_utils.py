"""
Shared console/log emission helpers.

The MATLAB originals print progress with ``fprintf``, so the ports keep the
same stdout output. Two things go wrong if that is *all* they do:

1. A run redirected to a file on Windows gets a ``cp1252`` stdout, and a single
   non-ASCII character in a progress line raises ``UnicodeEncodeError`` — which
   once killed a protocol run ten minutes in.
2. Anything printed with a bare ``print`` never reaches the ``logging`` file
   handler, so a heartbeat visible on the console is missing from the run log.

:func:`safe_print` fixes the first, :func:`emit` fixes both.
"""

from __future__ import annotations

import logging
import sys

__all__ = ["safe_print", "emit"]


def safe_print(msg: str) -> None:
    """``print`` that survives a non-UTF-8 stdout (Windows cp1252 redirects)."""
    try:
        print(msg, flush=True)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(msg.encode(enc, "replace").decode(enc, "replace"), flush=True)


def emit(logger: logging.Logger, msg: str) -> None:
    """Send one progress line to both stdout and ``logger`` at INFO.

    Callers that tail the log file and callers watching the console then see
    the same run, which a bare ``print`` does not give them.
    """
    safe_print(msg)
    logger.info("%s", msg)
