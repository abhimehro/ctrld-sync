"""Interactive prompt helpers."""

from __future__ import annotations

import getpass
import sys
from collections.abc import Callable

from .colors import USE_COLORS, Colors
from .output import _clear_current_line, _print_hint
from .text import _ANSI_ESCAPE_PATTERN

EMPTY_INPUT_HINT = (
    "   💡 Hint: Please type a value and press Enter, or press Ctrl+C/Ctrl+D to cancel."
)
INVALID_INPUT_HINT = "   💡 Hint: Please check your input and try again, or press Ctrl+C/Ctrl+D to cancel."


def get_validated_input(
    prompt: str,
    validator: Callable[[str], bool],
    error_msg: str,
) -> str:
    """Prompts for input until the validator returns True."""
    while _ANSI_ESCAPE_PATTERN.sub("", prompt).startswith("\n"):
        print()
        prompt = prompt.replace("\n", "", 1)

    if not _ANSI_ESCAPE_PATTERN.sub("", prompt).endswith(" "):
        prompt += " "

    while True:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
            value = input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            _clear_current_line()
            print(f"{Colors.WARNING}⚠️  Input cancelled.{Colors.ENDC}", file=sys.stderr)
            sys.exit(130)

        if not value:
            print(
                f"{Colors.FAIL}❌ Value cannot be empty{Colors.ENDC}", file=sys.stderr
            )
            _print_hint(EMPTY_INPUT_HINT, file=sys.stderr)
            print(file=sys.stderr)
            continue

        if validator(value):
            return value

        print(f"{Colors.FAIL}❌ {error_msg}{Colors.ENDC}", file=sys.stderr)
        _print_hint(INVALID_INPUT_HINT, file=sys.stderr)
        print(file=sys.stderr)


def _format_password_prompt(prompt: str) -> str:
    """Formats the password prompt to ensure it contains standard hints and spaces."""
    while _ANSI_ESCAPE_PATTERN.sub("", prompt).startswith("\n"):
        print()
        prompt = prompt.replace("\n", "", 1)

    if "(typing will be hidden)" not in prompt:
        if USE_COLORS:
            prompt = (
                f"{prompt.rstrip()} {Colors.DIM}(typing will be hidden){Colors.ENDC} "
            )
        else:
            prompt = f"{prompt.rstrip()} (typing will be hidden) "
    if not _ANSI_ESCAPE_PATTERN.sub("", prompt).endswith(" "):
        prompt += " "
    return prompt


def get_password(
    prompt: str,
    validator: Callable[[str], bool],
    error_msg: str,
) -> str:
    """Prompts for password input until the validator returns True.

    If the prompt does not already advertise that input is hidden, append a
    "(typing will be hidden)" hint so a screen-reader or fresh user knows
    why characters do not echo. Callers that want to render the hint with
    their own styling (e.g. dimmed colors at a specific position) can opt
    out by including the literal substring "(typing will be hidden)" in
    the prompt they pass.
    """
    prompt = _format_password_prompt(prompt)

    while True:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
            value = getpass.getpass(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            _clear_current_line()
            print(f"{Colors.WARNING}⚠️  Input cancelled.{Colors.ENDC}", file=sys.stderr)
            sys.exit(130)

        if not value:
            print(
                f"{Colors.FAIL}❌ Value cannot be empty{Colors.ENDC}", file=sys.stderr
            )
            _print_hint(EMPTY_INPUT_HINT, file=sys.stderr)
            print(file=sys.stderr)
            continue

        if validator(value):
            return value

        print(f"{Colors.FAIL}❌ {error_msg}{Colors.ENDC}", file=sys.stderr)
        _print_hint(INVALID_INPUT_HINT, file=sys.stderr)
        print(file=sys.stderr)


__all__ = [
    "EMPTY_INPUT_HINT",
    "INVALID_INPUT_HINT",
    "get_password",
    "get_validated_input",
    "_format_password_prompt",
]
