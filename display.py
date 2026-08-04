"""Terminal UI, prompts, tables, and progress helpers."""

from __future__ import annotations

import concurrent.futures
import getpass
import json
import logging
import os
import re
import secrets
import shutil
import sys
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from api_client import _api_stats, _rate_limit_info, _rate_limit_lock
from cache import _cache_stats
from models import PlanEntry, PlanFolderEntry, SyncResult
from validation import sanitize_for_log

log = logging.getLogger(__name__)

# Respect NO_COLOR standard (https://no-color.org/) and JSON_LOG for structured output.
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


class ColoredFormatter(logging.Formatter):
    """Custom formatter to add colors to log levels."""

    LEVEL_COLORS = {
        logging.DEBUG: Colors.BLUE,
        logging.INFO: Colors.CYAN,
        logging.WARNING: Colors.WARNING,
        logging.ERROR: Colors.FAIL,
        logging.CRITICAL: Colors.FAIL + Colors.BOLD,
    }

    def __init__(self, fmt=None, datefmt=None, style="%", validate=True):
        super().__init__(fmt, datefmt, style, validate)
        self.delegate_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S"
        )

    def format(self, record):
        original_levelname = record.levelname
        color = self.LEVEL_COLORS.get(record.levelno, Colors.ENDC)
        padded_level = f"{original_levelname:<8}"
        record.levelname = f"{color}{padded_level}{Colors.ENDC}"
        result = self.delegate_formatter.format(record)
        record.levelname = original_levelname
        return result


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record for structured/observability pipelines.

    Activated by setting the ``JSON_LOG`` environment variable to a non-empty
    value (e.g. ``JSON_LOG=1``).  When active, ``USE_COLORS`` is also disabled
    so that ANSI escape codes never pollute the JSON stream.

    Each line contains at minimum:
        ``time``    – ISO-8601 timestamp (UTC, second precision)
        ``level``   – log level name (DEBUG / INFO / WARNING / ERROR / CRITICAL)
        ``logger``  – logger name
        ``message`` – formatted log message
    """

    @staticmethod
    def converter(
        t: float | None,
    ) -> time.struct_time:  # ensure timestamps are always UTC
        return time.gmtime(t)

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, str] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            # Mirror stdlib logging.Formatter behavior:
            # cache the formatted exception in record.exc_text so that
            # other formatters/handlers don't need to reformat it.
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            if record.exc_text:
                payload["exc"] = record.exc_text
        return json.dumps(payload)


def configure_logging() -> None:
    """Configure the root logger for the CLI.

    Emits coloured text by default and structured JSON lines when ``JSON_LOG``
    is set.  Also suppresses noisy ``httpx`` library logs.
    """
    if os.getenv("JSON_LOG"):
        formatter: logging.Formatter = JsonFormatter()
    else:
        formatter = ColoredFormatter()
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    logging.getLogger("httpx").setLevel(logging.WARNING)


class AlertSystem:
    """Handles async enqueue callbacks and structured error logging.

    Attaches to ``concurrent.futures.Future`` objects via
    ``add_done_callback`` so that errors surfacing inside worker threads are
    captured and logged in a single, consistent place.

    **Architectural role:** Rather than scattering ``try/except`` blocks
    around every ``executor.submit()`` call, callers register a single
    ``AlertSystem`` callback on each future.  This centralises error
    observability and makes it easy to extend (e.g. add metrics, alerts, or
    structured logging) without touching every call site.

    Usage::

        system = AlertSystem()
        fut = executor.submit(some_task)
        fut.add_done_callback(system._on_enqueue_done)
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        # Allow callers (and tests) to inject a custom logger; fall back to the
        # module-level logger so production behaviour stays unchanged.
        # Use the same named logger as the rest of this module to keep logs
        # consistent and to honour the "module-level logger" contract.
        self.logger = logger or logging.getLogger("control-d-sync")

    def _on_enqueue_done(
        self,
        future: concurrent.futures.Future[
            Any
        ],  # Accept futures of any return type; we only inspect exceptions
    ) -> None:
        """Callback invoked when an enqueue future completes.

        Three code paths ("branches") are handled here:

        * **Branch A** – ``future.exception()`` returns ``None``: normal
          completion; nothing extra is logged.
        * **Branch B** – ``future.exception()`` returns a non-``None``
          exception object: we log this as an error and pass the exception
          instance as ``exc_info`` so that the full traceback is preserved and
          log handlers (and tests) can inspect the real error.
        * **Branch C** – ``future.exception()`` itself raises (e.g. the future
          was cancelled before we could inspect it): we catch *that* secondary
          exception and log it, again passing the actual exception instance as
          ``exc_info`` so that the full traceback is preserved and callers can
          programmatically inspect the real error.
        """
        try:
            exc = future.exception()
            if exc is not None:
                # We are *not* in an ``except`` block here, so there is no
                # active exception for logging to pull from ``sys.exc_info()``.
                # Construct the (type, value, traceback) tuple explicitly so the
                # original worker-thread traceback is preserved.
                self.logger.error(
                    "Enqueued task raised an exception",
                    exc_info=(type(exc), exc, exc.__traceback__),
                )
        except Exception:
            # Here we *are* in an ``except`` context, so logging can safely use
            # the current exception from ``sys.exc_info()``. Using
            # ``exc_info=True`` is the idiomatic way to log this traceback.
            self.logger.error(
                "Unexpected error while inspecting enqueue future",
                exc_info=True,
            )


EMPTY_INPUT_HINT = (
    "   💡 Hint: Please type a value and press Enter, or press Ctrl+C/Ctrl+D to cancel."
)
INVALID_INPUT_HINT = "   💡 Hint: Please check your input and try again, or press Ctrl+C/Ctrl+D to cancel."


def pluralize(count: int, singular: str, plural: str | None = None) -> str:
    """Helper to cleanly pluralize nouns based on count."""
    if plural is None:
        plural = f"{singular}s"
    return singular if count == 1 else plural


def _get_action_text(folder: PlanFolderEntry) -> str:
    """Determine the action label (Block/Allow/Mixed) for a given folder."""
    actions = {rg.get("action") for rg in folder.get("rule_groups") or []}
    if len(actions) > 1:
        label, icon, color = "Mixed", "⚠️ ", Colors.WARNING
    else:
        action_val = next(iter(actions)) if actions else folder.get("action")
        if action_val not in (0, 1):
            action_val = folder.get("action")

        prop_map: dict[int | None | str, tuple[str, str, str]] = {
            0: ("Block", "⛔", Colors.FAIL),
            1: ("Allow", "✅", Colors.GREEN),
        }
        label, icon, color = prop_map.get(
            action_val, ("Block (Default)", "⛔", Colors.FAIL)
        )

    if USE_COLORS:
        return f"({color}{icon} {label}{Colors.ENDC})"
    return f"({icon} {label})"


def print_plan_details(plan_entry: PlanEntry) -> None:
    """Pretty-print the folder-level breakdown during a dry-run."""
    profile = sanitize_for_log(plan_entry.get("profile", "unknown"))
    if profile == "dry-run-placeholder":
        profile = "(Unspecified)"
    folders = plan_entry.get("folders", [])

    if USE_COLORS:
        print(f"\n{Colors.HEADER}📝 Plan Details for {profile}:{Colors.ENDC}")
    else:
        print(f"\n📝 Plan Details for {profile}:")

    if not folders:
        if USE_COLORS:
            print(f"  {Colors.WARNING}⚠️  No folders to sync.{Colors.ENDC}")
        else:
            print("  ⚠️  No folders to sync.")
        _print_hint(
            "  💡 Hint: Add folder URLs using --folder-url or in your config.yaml"
        )
        return

    # Calculate max width for alignment
    max_name_len = max(
        # Use the same default ("Unknown") as when printing, so alignment is accurate
        (_display_len(sanitize_for_log(f.get("name", "Unknown"))) for f in folders),
        default=0,
    )
    max_rules_len = max((len(f"{f.get('rules', 0):,}") for f in folders), default=0)

    for folder in sorted(folders, key=lambda f: f.get("name", "Unknown")):
        name = sanitize_for_log(folder.get("name", "Unknown"))
        rules_count = folder.get("rules", 0)
        formatted_rules = f"{rules_count:,}"

        action_text = _get_action_text(folder)
        padded_name = _pad_string(name, max_name_len, "<")

        if USE_COLORS:
            print(
                f"  • {Colors.BOLD}{padded_name}{Colors.ENDC} : {formatted_rules:>{max_rules_len}} {pluralize(rules_count, 'rule'):<5} {action_text}"
            )
        else:
            print(
                f"  - {padded_name} : {formatted_rules:>{max_rules_len}} {pluralize(rules_count, 'rule'):<5} {action_text}"
            )

    print("")


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


def print_line(left_char: str, mid_char: str, right_char: str, w: list[int]) -> str:
    """Format a horizontal table separator line."""
    return f"{Colors.BOLD}{make_col_separator(left_char, mid_char, right_char, Box.H, w)}{Colors.ENDC}"


def print_row(cols: list[str], w: list[int]) -> str:
    """Format a row of table data."""
    col0 = _pad_string(cols[0], w[0], "<")
    col1 = _pad_string(cols[1], w[1], ">")
    col2 = _pad_string(cols[2], w[2], ">")
    col3 = _pad_string(cols[3], w[3], ">")
    col4 = _pad_string(cols[4], w[4], "<")
    return f"{Colors.BOLD}│{Colors.ENDC} {col0} {Colors.BOLD}│{Colors.ENDC} {col1} {Colors.BOLD}│{Colors.ENDC} {col2} {Colors.BOLD}│{Colors.ENDC} {col3} {Colors.BOLD}│{Colors.ENDC} {col4} {Colors.BOLD}│{Colors.ENDC}"


@dataclass
class _SummaryStats:
    t_f: int
    t_r: int
    t_d: float
    t_status: str
    t_col: str


def _get_display_profile(profile: str) -> str:
    return "(Unspecified)" if profile == "dry-run-placeholder" else profile


def _print_hint_if_no_folders(t_f: int) -> None:
    if t_f == 0:
        _print_hint(
            "  💡 Hint: Add folder URLs using --folder-url or in your config.yaml"
        )


def _render_ascii_table(
    sync_results: list[SyncResult], w: list[int], stats: _SummaryStats, dry_run: bool
) -> None:
    header = f"{'Profile ID':<{w[0]}} | {'Folders':>{w[1]}} | {'Rules':>{w[2]}} | {'Duration':>{w[3]}} | {'Status':<{w[4]}}"
    sep = "-" * len(header)
    title = f"📋 {'DRY RUN' if dry_run else 'SYNC'} SUMMARY"
    padded_title = _pad_string(title, len(header), align="^")
    print(f"\n{padded_title}\n{sep}\n{header}\n{sep}")
    for r in sync_results:
        display_profile = _get_display_profile(r["profile"])
        print(
            f"{display_profile:<{w[0]}} | {r['folders']:>{w[1]}} | {r['rules']:>{w[2]},} | {r['duration']:>{w[3] - 1}.1f}s | {_pad_string(r['status_label'], w[4], align='<')}"
        )
    print(
        f"{sep}\n{'TOTAL':<{w[0]}} | {stats.t_f:>{w[1]}} | {stats.t_r:>{w[2]},} | {stats.t_d:>{w[3] - 1}.1f}s | {_pad_string(stats.t_status, w[4], align='<')}\n{sep}\n"
    )
    print()


def _render_unicode_table(
    sync_results: list[SyncResult], w: list[int], stats: _SummaryStats, dry_run: bool
) -> None:
    print(f"\n{print_line('┌', '─', '┐', w)}")
    title = f"📋 {'DRY RUN' if dry_run else 'SYNC'} SUMMARY"
    padded_title = _pad_string(title, sum(w) + 14, align="^")
    print(
        f"{Colors.BOLD}│{Colors.CYAN if dry_run else Colors.HEADER}{padded_title}{Colors.ENDC}{Colors.BOLD}│{Colors.ENDC}"
    )
    print(
        f"{print_line('├', '┬', '┤', w)}\n{print_row([f'{Colors.HEADER}Profile ID{Colors.ENDC}', f'{Colors.HEADER}Folders{Colors.ENDC}', f'{Colors.HEADER}Rules{Colors.ENDC}', f'{Colors.HEADER}Duration{Colors.ENDC}', f'{Colors.HEADER}Status{Colors.ENDC}'], w)}"
    )
    print(print_line("├", "┼", "┤", w))

    for r in sync_results:
        sc = Colors.GREEN if r["success"] else Colors.FAIL
        display_profile = _get_display_profile(r["profile"])
        print(
            print_row(
                [
                    display_profile,
                    str(r["folders"]),
                    f"{r['rules']:,}",
                    f"{r['duration']:.1f}s",
                    f"{sc}{r['status_label']}{Colors.ENDC}",
                ],
                w,
            )
        )

    print(
        f"{print_line('├', '┼', '┤', w)}\n{print_row(['TOTAL', str(stats.t_f), f'{stats.t_r:,}', f'{stats.t_d:.1f}s', f'{stats.t_col}{stats.t_status}{Colors.ENDC}'], w)}"
    )
    print(f"{print_line('└', '┴', '┘', w)}\n")


def print_summary_table(
    sync_results: list[SyncResult], success_count: int, total: int, dry_run: bool
) -> None:
    max_p = max((_display_len(r["profile"]) for r in sync_results), default=25)
    w = [max(25, max_p), 10, 12, 10, 15]

    t_f, t_r, t_d = (
        sum(r["folders"] for r in sync_results),
        sum(r["rules"] for r in sync_results),
        sum(r["duration"] for r in sync_results),
    )
    all_ok = success_count == total
    if all_ok:
        t_status = "✅ Ready" if dry_run else "✅ All Good"
        t_col = Colors.GREEN
    elif success_count > 0:
        t_status = "⚠️ Partial"
        t_col = Colors.WARNING
    else:
        t_status = "❌ Errors"
        t_col = Colors.FAIL
    stats = _SummaryStats(t_f, t_r, t_d, t_status, t_col)

    if not USE_COLORS:
        _render_ascii_table(sync_results, w, stats, dry_run)
        _print_hint_if_no_folders(t_f)
        return

    _render_unicode_table(sync_results, w, stats, dry_run)
    _print_hint_if_no_folders(t_f)


def _print_success_text(all_success: bool, success_count: int, total: int) -> None:
    """Helper to print the success or partial success message."""
    if all_success:
        success_msgs = [
            "✨ All synced!",
            "🚀 Ready for liftoff!",
            "🎨 Beautifully done!",
            "💎 Smooth operation!",
            "🌈 Perfect harmony!",
        ]
        chosen_msg = secrets.choice(success_msgs)
    else:
        chosen_msg = (
            f"⚠️  Synced {success_count} out of {total} profile(s). Check errors above."
        )

    if USE_COLORS:
        color = Colors.GREEN if all_success else Colors.WARNING
        print(f"\n{color}{chosen_msg}{Colors.ENDC}")
    else:
        print(f"\n{chosen_msg}")


def _print_dashboard_url(profile_ids: list[str]) -> None:
    """Helper to print the dashboard URL."""
    is_single_profile = (
        profile_ids
        and len(profile_ids) == 1
        and profile_ids[0] != "dry-run-placeholder"
    )
    is_multi_profile = len(profile_ids) > 1

    if not is_single_profile and not is_multi_profile:
        return

    dashboard_url = (
        f"https://controld.com/dashboard/profiles/{profile_ids[0]}/filters"
        if is_single_profile
        else "https://controld.com/dashboard/profiles"
    )

    if USE_COLORS:
        print(
            f"{Colors.CYAN}👀 View your changes: {Colors.UNDERLINE}{dashboard_url}{Colors.ENDC}"
        )
    else:
        print(f"👀 View your changes: {dashboard_url}")


def print_success_message(
    profile_ids: list[str], success_count: int, total: int
) -> None:
    """Prints a random success message and a link to the Control D dashboard."""
    all_success = success_count == total
    _print_success_text(all_success, success_count, total)
    _print_dashboard_url(profile_ids)


def make_col_separator(
    left: str, mid: str, right: str, horiz: str, col_widths: list[int]
) -> str:
    """Generates a table row separator with given box drawing characters and column widths."""
    parts = [horiz * (w + 2) for w in col_widths]
    return left + mid.join(parts) + right


def display_api_statistics() -> None:
    """Display API statistics."""
    total_api_calls = (
        _api_stats["control_d_api_calls"] + _api_stats["blocklist_fetches"]
    )
    if total_api_calls > 0:
        _print_bold_header("📊 API Statistics:")
        print(f"  • Control D API calls: {_api_stats['control_d_api_calls']:>7,}")
        print(f"  • Blocklist fetches:   {_api_stats['blocklist_fetches']:>7,}")
        print(f"  • Total API requests:  {total_api_calls:>7,}")
        print()


def display_cache_statistics() -> None:
    """Display cache statistics if any cache activity occurred."""
    if _cache_stats["hits"] + _cache_stats["misses"] + _cache_stats["validations"] > 0:
        _print_bold_header("⚡ Cache Statistics:")
        print(f"  • Hits (in-memory):    {_cache_stats['hits']:>7,}")
        print(f"  • Misses (downloaded): {_cache_stats['misses']:>7,}")
        print(f"  • Validations (304):   {_cache_stats['validations']:>7,}")
        if _cache_stats["errors"] > 0:
            print(f"  • Errors (non-fatal):  {_cache_stats['errors']:>7,}")

        # Calculate cache effectiveness
        total_requests = (
            _cache_stats["hits"] + _cache_stats["misses"] + _cache_stats["validations"]
        )
        if total_requests > 0:
            # Hits + validations = avoided full downloads
            cache_effectiveness = (
                (_cache_stats["hits"] + _cache_stats["validations"])
                / total_requests
                * 100
            )
            print(f"  • Cache effectiveness:  {cache_effectiveness:>6.1f}%")
        print()


def display_rate_limit_status() -> None:
    """Display rate limit information if available."""
    with _rate_limit_lock:
        if not any(v is not None for v in _rate_limit_info.values()):
            return

        _print_bold_header("🚦 API Rate Limit Status:")

        if _rate_limit_info["limit"] is not None:
            print(f"  • Requests limit:       {_rate_limit_info['limit']:>6,}")

        if _rate_limit_info["remaining"] is not None:
            remaining = _rate_limit_info["remaining"]
            limit = _rate_limit_info["limit"]
            if limit and limit > 0:
                pct = (remaining / limit) * 100
                color = (
                    Colors.FAIL
                    if pct < 20
                    else (Colors.WARNING if pct < 50 else Colors.GREEN)
                )
                print(
                    f"  • Requests remaining:   {color}{remaining:>6,} ({pct:>5.1f}%){Colors.ENDC}"
                )
            else:
                print(f"  • Requests remaining:   {remaining:>6,}")

        if _rate_limit_info["reset"] is not None:
            reset_time = time.strftime(
                "%H:%M:%S", time.localtime(_rate_limit_info["reset"])
            )
            print(f"  • Limit resets at:      {reset_time}")

        print()


def display_statistics() -> None:
    """Display API, cache, and rate limit statistics."""
    display_api_statistics()
    display_cache_statistics()
    display_rate_limit_status()


__all__ = [
    "USE_COLORS",
    "Colors",
    "Box",
    "ColoredFormatter",
    "JsonFormatter",
    "AlertSystem",
    "pluralize",
    "countdown_timer",
    "render_progress_bar",
    "get_password",
    "get_validated_input",
    "print_plan_details",
    "print_summary_table",
    "print_success_message",
    "display_statistics",
    "_clear_current_line",
    "_print_hint",
    "_print_bold_header",
    "_print_completion",
    "_display_len",
    "_pad_string",
    "print_line",
    "print_row",
    "_SummaryStats",
    "_get_display_profile",
    "_render_ascii_table",
    "_render_unicode_table",
    "_print_success_text",
    "_print_dashboard_url",
    "_ANSI_ESCAPE_PATTERN",
    "EMPTY_INPUT_HINT",
    "INVALID_INPUT_HINT",
    "make_col_separator",
]
