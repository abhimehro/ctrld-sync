"""Progress bars and countdown timers."""

from __future__ import annotations

import logging
import shutil
import sys
import time

from .colors import USE_COLORS, Colors
from validation import sanitize_for_log

log = logging.getLogger(__name__)


def _get_progress_bar_width() -> int:
    """Calculate dynamic progress bar width based on terminal size.

    Returns width clamped between 15 and 50 characters, approximately
    40% of terminal width. This ensures progress bars are readable on
    narrow terminals while utilizing space on wider displays.
    """
    cols, _ = shutil.get_terminal_size(fallback=(80, 24))
    return max(15, min(50, int(cols * 0.4)))


def countdown_timer(seconds: int, message: str = "Waiting") -> None:
    """Show a countdown in interactive/color mode; in no-color/non-interactive
    mode, sleep silently for short waits and log periodic heartbeat messages
    for longer waits."""
    if not USE_COLORS or not sys.stderr.isatty():
        # Non-interactive countdown
        if seconds > 10:
            for remaining in range(seconds, 0, -10):
                # Don't log the first one if we already logged "Waiting..." before calling this
                if remaining < seconds:
                    log.info(f"{sanitize_for_log(message)}: {remaining}s remaining...")
                time.sleep(min(10, remaining))
        else:
            time.sleep(seconds)
        log.info(f"✅ {sanitize_for_log(message)}: Done!")
        return
    width = _get_progress_bar_width()
    max_len = len(str(seconds))

    for remaining in range(seconds, 0, -1):
        progress = (seconds - remaining + 1) / seconds
        filled = int(width * progress)
        bar = (
            "█" * filled
            + f"{Colors.DIM}"
            + "·" * (width - filled)
            + f"{Colors.ENDC}{Colors.CYAN}"
        )
        sys.stderr.write(
            f"\r\033[K{Colors.CYAN}⏳ {message}: [{bar}] {remaining:>{max_len}}s...{Colors.ENDC}"
        )
        sys.stderr.flush()
        time.sleep(1)

    sys.stderr.write(f"\r\033[K{Colors.GREEN}✅ {message}: Done!{Colors.ENDC}\n")
    sys.stderr.flush()


def render_progress_bar(
    current: int, total: int, label: str, prefix: str = "🚀"
) -> None:
    """Renders a progress bar to stderr if USE_COLORS is True."""
    if not USE_COLORS:
        return
    if not sys.stderr.isatty():
        return
    if total == 0:
        return
    width = _get_progress_bar_width()

    progress = min(1.0, current / total)
    filled = int(width * progress)
    bar = (
        "█" * filled
        + f"{Colors.DIM}"
        + "·" * (width - filled)
        + f"{Colors.ENDC}{Colors.CYAN}"
    )
    percent = int(progress * 100)

    total_str = str(total)

    # Use \033[K to clear line residue
    sys.stderr.write(
        f"\r\033[K{Colors.CYAN}{prefix} {label}: [{bar}] {percent:>3}% ({current:>{len(total_str)}}/{total_str}){Colors.ENDC}"
    )
    sys.stderr.flush()


__all__ = ["countdown_timer", "render_progress_bar", "_get_progress_bar_width"]
