"""Terminal color palette and box-drawing characters."""

from __future__ import annotations

import os
import sys

# Respect NO_COLOR standard (https://no-color.org/).
if os.getenv("NO_COLOR"):
    USE_COLORS = False
else:
    USE_COLORS = sys.stderr.isatty() and sys.stdout.isatty()
if os.getenv("JSON_LOG"):
    USE_COLORS = False


class Colors:
    if USE_COLORS:
        HEADER = "\033[95m"
        BLUE = "\033[94m"
        CYAN = "\033[96m"
        GREEN = "\033[92m"
        WARNING = "\033[93m"
        FAIL = "\033[91m"
        ENDC = "\033[0m"
        BOLD = "\033[1m"
        UNDERLINE = "\033[4m"
        DIM = "\033[2m"
    else:
        HEADER = ""
        BLUE = ""
        CYAN = ""
        GREEN = ""
        WARNING = ""
        FAIL = ""
        ENDC = ""
        BOLD = ""
        UNDERLINE = ""
        DIM = ""


class Box:
    """Box drawing characters for pretty tables."""

    if USE_COLORS:
        H, V, TL, TR, BL, BR, T, B, L, R, X = (
            "─",
            "│",
            "┌",
            "┐",
            "└",
            "┘",
            "┬",
            "┴",
            "├",
            "┤",
            "┼",
        )
    else:
        H, V, TL, TR, BL, BR, T, B, L, R, X = (
            "-",
            "|",
            "+",
            "+",
            "+",
            "+",
            "+",
            "+",
            "+",
            "+",
            "+",
        )


__all__ = ["USE_COLORS", "Colors", "Box"]
