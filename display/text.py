"""Unicode display-width and text helpers."""

from __future__ import annotations

import re
import unicodedata


def pluralize(count: int, singular: str, plural: str | None = None) -> str:
    """Helper to cleanly pluralize nouns based on count."""
    if plural is None:
        plural = f"{singular}s"
    return singular if count == 1 else plural


_ANSI_ESCAPE_PATTERN = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _display_len(s: str) -> int:
    """Calculate display width of a string considering full-width characters and ignoring ANSI codes."""
    if s.isascii() and "\x1b" not in s:
        return len(s)
    stripped = _ANSI_ESCAPE_PATTERN.sub("", s)
    # OPTIMIZATION: C-speed list comprehension avoids Python loop overhead
    return len(stripped) + len(
        [
            1
            for c in stripped
            if unicodedata.east_asian_width(c) in ("W", "F")
            or (ord(c) >= 0x2600 and unicodedata.category(c) in ("So", "Sk"))
        ]
    )


def _pad_string(s: str, width: int, align: str = "<") -> str:
    """Pad string considering full-width characters."""
    pad_len = width - _display_len(s)
    if pad_len < 0:
        pad_len = 0
    if align == "<":
        return s + " " * pad_len
    if align == ">":
        return " " * pad_len + s
    if align == "^":
        left = pad_len // 2
        right = pad_len - left
        return " " * left + s + " " * right
    return s


__all__ = ["pluralize", "_ANSI_ESCAPE_PATTERN", "_display_len", "_pad_string"]
