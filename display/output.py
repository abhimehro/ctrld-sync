"""Low-level terminal output helpers."""

from __future__ import annotations

import logging
import sys

from .colors import USE_COLORS, Colors

log = logging.getLogger(__name__)


def _clear_current_line() -> None:
    """Helper to clear the current line on stderr in a TTY."""
    if sys.stderr.isatty():
        sys.stderr.write("\r\033[K")
        sys.stderr.flush()


def _print_hint(hint: str, file=None) -> None:
    """Helper to cleanly print input hints while respecting USE_COLORS to reduce cyclomatic complexity."""
    file = file or sys.stdout
    if USE_COLORS:
        print(f"{Colors.DIM}{hint}{Colors.ENDC}", file=file)
    else:
        print(hint, file=file)


def _print_bold_header(text: str) -> None:
    """Print a bold section header when colors are enabled; plain text otherwise.

    Isolates the USE_COLORS branch so callers (e.g. display_rate_limit_status)
    do not gain cyclomatic complexity from the NO_COLOR / non-TTY fallback.
    """
    if USE_COLORS:
        print(f"{Colors.BOLD}{text}{Colors.ENDC}")
    else:
        print(text)


def _print_completion(msg: str) -> None:
    """Helper to print completion message to stderr or log."""
    _clear_current_line()
    if not sys.stderr.isatty():
        log.info(f"✅ {msg}")
        return

    if USE_COLORS:
        sys.stderr.write(f"{Colors.GREEN}✅ {msg}{Colors.ENDC}\n")
    else:
        sys.stderr.write(f"✅ {msg}\n")
    sys.stderr.flush()


__all__ = [
    "_clear_current_line",
    "_print_hint",
    "_print_bold_header",
    "_print_completion",
]
