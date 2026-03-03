"""Terminal User Interface (TUI) for lazy-splitter.

This package provides an interactive, full-screen terminal application built
on top of `Textual <https://textual.textualize.io/>`_.  Textual is an
**optional** dependency; all TUI functionality degrades gracefully when
Textual is not installed.

Quick start::

    # Launch the TUI (requires ``textual`` to be installed)
    from lazy_splitter.tui.app import LazySplitterApp

    app = LazySplitterApp()
    app.run()

If Textual is unavailable, importing the package still succeeds -- only
concrete usage (instantiating the app or widgets) will raise
:class:`ImportError` with a helpful message.
"""

from __future__ import annotations

__all__ = [
    "TEXTUAL_AVAILABLE",
    "require_textual",
]

# ---------------------------------------------------------------------------
# Optional dependency check
# ---------------------------------------------------------------------------

TEXTUAL_AVAILABLE: bool = False
"""``True`` when the ``textual`` package can be imported."""

try:
    import textual as _textual  # noqa: F401

    TEXTUAL_AVAILABLE = True
except ImportError:  # pragma: no cover
    pass


def require_textual() -> None:
    """Raise :class:`ImportError` with an actionable message if Textual is missing.

    Call this at the top of any function that *requires* Textual so that
    users receive a clear error rather than a cryptic traceback.
    """
    if not TEXTUAL_AVAILABLE:
        raise ImportError(
            "The TUI requires the 'textual' package.  "
            "Install it with:  pip install textual"
        )
