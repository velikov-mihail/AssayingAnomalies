"""
Headless plotting policy for the toolkit.

Nothing in this package ever wants an interactive window: figures are written
to PDF for the LaTeX assay. On a headless Linux node, picking a GUI backend is
at best a warning and at worst an import error or a blocked process, so we pin
``Agg`` unless the caller has deliberately asked for something else through
``MPLBACKEND``.

Import this module (the package ``__init__`` does) before matplotlib is used.
"""

from __future__ import annotations

import logging
import os

LOGGER = logging.getLogger("assayinganomalies.plotting")

HEADLESS_BACKEND = "Agg"
BACKEND_ENV = "MPLBACKEND"

_applied = False


def use_headless_backend(*, force: bool = False) -> str | None:
    """
    Select the ``Agg`` backend and return the backend actually in use.

    Idempotent. Returns None when matplotlib is not installed (it is an
    optional ``analytics`` extra). A user who has set ``MPLBACKEND`` is left
    alone — that is the documented escape hatch for interactive work — unless
    ``force=True``.
    """
    global _applied

    try:
        import matplotlib
    except ImportError:
        return None

    if _applied and not force:
        return matplotlib.get_backend()

    chosen = os.environ.get(BACKEND_ENV)
    if chosen and not force:
        LOGGER.debug("%s=%s set by the caller; leaving the backend alone", BACKEND_ENV, chosen)
        _applied = True
        return matplotlib.get_backend()

    try:
        matplotlib.use(HEADLESS_BACKEND)
    except Exception as exc:  # pragma: no cover - broken matplotlib install
        LOGGER.warning("could not select the %s backend (%s)", HEADLESS_BACKEND, exc)
        return matplotlib.get_backend()

    _applied = True
    return matplotlib.get_backend()


def is_interactive_backend() -> bool:
    """True only when the current backend can actually put a window on screen."""
    try:
        import matplotlib
    except ImportError:
        return False
    return matplotlib.get_backend().lower() not in {"agg", "pdf", "ps", "svg", "cairo", "template"}


def maybe_show(plt) -> bool:
    """
    ``plt.show()`` when a window is possible, otherwise a no-op.

    Returns whether the figure was shown. Under ``Agg``, ``plt.show()`` is a
    warning-emitting no-op; skipping it keeps batch logs clean and makes the
    intent explicit at every call site.
    """
    if not is_interactive_backend():
        LOGGER.debug("headless backend; not showing the figure")
        return False
    plt.show()
    return True


# Applied on import so that merely importing the package (or this module) is
# enough to make a run headless-safe; see assayinganomalies/__init__.py.
use_headless_backend()


__all__ = [
    "HEADLESS_BACKEND",
    "BACKEND_ENV",
    "use_headless_backend",
    "is_interactive_backend",
    "maybe_show",
]
