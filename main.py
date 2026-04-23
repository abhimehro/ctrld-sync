#!/usr/bin/env python3
"""
Control D Sync
----------------------
A tiny helper that keeps your Control D folders in sync with a set of
remote block-lists.

It does three things:
1. Reads the folder names from the JSON files.
2. Deletes any existing folders with those names (so we start fresh).
3. Re-creates the folders and pushes all rules in batches.

Nothing fancy, just works.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import getpass
import ipaddress
import json
import logging
import os
import random
import re
import shutil
import socket
import stat
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, NotRequired, TypedDict, TypeGuard, cast

import httpx
import yaml
from dotenv import load_dotenv

import api_client
import cache
from api_client import (
    _CONNECT_ERROR_HINT,
    _SERVER_ERROR_HINT,
    _TIMEOUT_HINT,
    MAX_RETRIES,
    RETRY_DELAY,
    _api_delete,
    _api_get,
    _api_post,
    _api_post_form,
    _api_stats,
    _rate_limit_info,
    _rate_limit_lock,
)
from cache import (
    CACHE_TTL_SECONDS,
    _cache_stats,
    _disk_cache,
    get_cache_dir,
    load_disk_cache,
    save_disk_cache,
)


@dataclass(frozen=True)
class RuleAction:
    """Represents a rule action (do and status)."""

    do: int
    status: int


@dataclass
class SyncContext:
    """Context for syncing rules and folders."""

    profile_id: str
    client: httpx.Client
    existing_rules: set[str]
    batch_executor: concurrent.futures.Executor | None = None


# --------------------------------------------------------------------------- #
# TypedDicts – document the shapes of API response and plan objects
# --------------------------------------------------------------------------- #


class FolderAction(TypedDict, total=False):
    """The 'action' sub-object on a folder group or rule group.

    ``do`` controls the rule action type (0 = Block, 1 = Allow).
    ``status`` controls whether the rule is active (1 = enabled, 0 = disabled).
    """

    do: int
    status: int


class FolderGroup(TypedDict):
    """The 'group' object inside a folder JSON response."""

    group: str  # folder display name (required in valid data)
    PK: NotRequired[str]  # folder primary key
    action: NotRequired[FolderAction]


class RuleEntry(TypedDict, total=False):
    """A single rule entry inside a folder's rule list."""

    PK: str  # hostname / primary key
    host: str
    action: FolderAction


class RuleGroup(TypedDict, total=False):
    """A rule group (multi-action format) inside a folder JSON response."""

    rules: list[RuleEntry]
    action: FolderAction


class FolderData(TypedDict):
    """Root shape of the JSON object returned by the blocklist endpoint."""

    group: FolderGroup  # required in valid data
    rules: NotRequired[list[RuleEntry]]  # present in legacy single-action format
    rule_groups: NotRequired[list[RuleGroup]]  # present in multi-action format


class PlanRuleGroup(TypedDict):
    """Per-rule-group summary entry inside a dry-run plan folder."""

    rules: int
    action: int | None
    status: int | None


class PlanFolderEntry(TypedDict):
    """Per-folder summary entry inside a dry-run plan."""

    name: str
    rules: int
    action: NotRequired[int | None]  # single-action format
    status: NotRequired[int | None]  # single-action format
    rule_groups: NotRequired[list[PlanRuleGroup]]  # multi-action format


class PlanEntry(TypedDict):
    """Top-level dry-run plan entry for one profile."""

    profile: str
    folders: list[PlanFolderEntry]


class SyncResult(TypedDict):
    """Per-profile result recorded after a sync run."""

    profile: str
    folders: int
    rules: int
    status_label: str
    success: bool
    duration: float


# --------------------------------------------------------------------------- #
# 0. Bootstrap – load secrets and configure logging
# --------------------------------------------------------------------------- #
# SECURITY: load_dotenv() moved to main() to ensure permissions are checked first

# Respect NO_COLOR standard (https://no-color.org/)
if os.getenv("NO_COLOR"):
    USE_COLORS = False
else:
    USE_COLORS = sys.stderr.isatty() and sys.stdout.isatty()

# Evaluate JSON_LOG immediately so USE_COLORS is finalized
# BEFORE the Colors and Box classes are defined.
_use_json_log: bool = bool(os.getenv("JSON_LOG"))
if _use_json_log:
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


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter() if _use_json_log else ColoredFormatter())
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
        fut.add_done_callback(system.on_future_done)
    """

    def on_future_done(self, future: concurrent.futures.Future) -> None:  # type: ignore[type-arg]
        """Callback invoked when a submitted future completes."""
        exc = future.exception()
        if exc:
            log.error("Background task failed: %s", exc, exc_info=exc)


log = logging.getLogger(__name__)
_alert = AlertSystem()

# --------------------------------------------------------------------------- #
# 1. Configuration defaults
# --------------------------------------------------------------------------- #

CONFIG_FILE = Path("config.yaml")
_DEFAULT_BATCH_SIZE = 200
_DEFAULT_MAX_WORKERS = 4

EMPTY_INPUT_HINT = "💡 Hint: Input cannot be empty."
INVALID_INPUT_HINT = "💡 Hint: That doesn't look right. Please check the value."


def _print_hint(hint: str) -> None:
    """Print a UX hint with optional dim styling."""
    if USE_COLORS:
        print(f"{Colors.DIM}{hint}{Colors.ENDC}")
    else:
        print(hint)


# --------------------------------------------------------------------------- #
# Progress bar helpers
# --------------------------------------------------------------------------- #


def _get_progress_bar_width() -> int:
    """Return a terminal-aware progress bar width clamped between 15 and 50."""
    cols = shutil.get_terminal_size(fallback=(80, 24)).columns
    return max(15, min(50, cols // 4))


def render_progress_bar(current: int, total: int, label: str) -> None:
    """Write an animated progress bar to stderr (no-op when colors are off)."""
    if not USE_COLORS or total == 0:
        return
    width = _get_progress_bar_width()
    filled = int(width * current / total)
    bar = "█" * filled + "·" * (width - filled)
    pct = current / total * 100
    sys.stderr.write(f"\r\033[K{Colors.CYAN}{label}{Colors.ENDC} [{bar}] {pct:5.1f}%")
    sys.stderr.flush()


# --------------------------------------------------------------------------- #
# Table helpers
# --------------------------------------------------------------------------- #


def make_col_separator(
    left: str, mid: str, right: str, horiz: str, col_widths: list[int]
) -> str:
    """Build a horizontal table separator from box-drawing characters."""
    parts = [horiz * (w + 2) for w in col_widths]
    return left + mid.join(parts) + right


def print_line(left: str, mid: str, right: str, col_widths: list[int]) -> str:
    """Return a bold unicode table border line."""
    parts = [Box.H * (w + 2) for w in col_widths]
    inner = left + mid.join(parts) + right
    return f"{Colors.BOLD}{inner}{Colors.ENDC}"


def print_row(cols: list[str], col_widths: list[int]) -> str:
    """Return a formatted table data row with bold separators."""
    cells = []
    for i, (col, w) in enumerate(zip(cols, col_widths)):
        if i == 0:
            cells.append(f"{Colors.BOLD}│{Colors.ENDC} {col:<{w}} ")
        else:
            cells.append(f"{Colors.BOLD}│{Colors.ENDC} {col:>{w}} ")
    cells.append(f"{Colors.BOLD}│{Colors.ENDC}")
    return "".join(cells)


def print_summary_table(
    sync_results: list[SyncResult],
    success_count: int,
    total: int,
    dry_run: bool,
) -> None:
    """Print the final sync summary table."""
    max_profile_len = max((len(r["profile"]) for r in sync_results), default=25)
    profile_col_width = max(25, max_profile_len)
    w_profile = profile_col_width
    w_folders = 10
    w_rules = 12
    w_duration = 10
    w_status = 15
    col_widths = [w_profile, w_folders, w_rules, w_duration, w_status]
    dummy_sep = make_col_separator(Box.TL, Box.T, Box.TR, Box.H, col_widths)
    table_width = len(dummy_sep)
    title_text = " DRY RUN SUMMARY " if dry_run else " SYNC SUMMARY "
    title_color = Colors.CYAN if dry_run else Colors.HEADER
    print("\n" + Box.TL + Box.H * (table_width - 2) + Box.TR)
    visible_title = title_text.strip()
    inner_width = table_width - 2
    pad_left = (inner_width - len(visible_title)) // 2
    pad_right = inner_width - len(visible_title) - pad_left
    print(
        f"{Box.V}{' ' * pad_left}{title_color}{visible_title}{Colors.ENDC}{' ' * pad_right}{Box.V}"
    )
    print(make_col_separator(Box.L, Box.T, Box.R, Box.H, col_widths))
    print(
        f"{Box.V} {Colors.BOLD}{'Profile ID':<{w_profile}}{Colors.ENDC} "
        f"{Box.V} {Colors.BOLD}{'Folders':>{w_folders}}{Colors.ENDC} "
        f"{Box.V} {Colors.BOLD}{'Rules':>{w_rules}}{Colors.ENDC} "
        f"{Box.V} {Colors.BOLD}{'Duration':>{w_duration}}{Colors.ENDC} "
        f"{Box.V} {Colors.BOLD}{'Status':<{w_status}}{Colors.ENDC} {Box.V}"
    )
    print(make_col_separator(Box.L, Box.X, Box.R, Box.H, col_widths))
    total_folders = 0
    total_rules = 0
    total_duration = 0.0
    for res in sync_results:
        status_color = Colors.GREEN if res["success"] else Colors.FAIL
        s_folders = f"{res['folders']:,}"
        s_rules = f"{res['rules']:,}"
        s_duration = f"{res['duration']:.1f}s"
        print(
            f"{Box.V} {res['profile']:<{w_profile}} "
            f"{Box.V} {s_folders:>{w_folders}} "
            f"{Box.V} {s_rules:>{w_rules}} "
            f"{Box.V} {s_duration:>{w_duration}} "
            f"{Box.V} {status_color}{res['status_label']:<{w_status}}{Colors.ENDC} {Box.V}"
        )
        total_folders += res["folders"]
        total_rules += res["rules"]
        total_duration += res["duration"]
    print(make_col_separator(Box.L, Box.X, Box.R, Box.H, col_widths))
    all_success = success_count == total
    if dry_run:
        total_status_text = "✅ Ready" if all_success else "❌ Errors"
    else:
        total_status_text = "✅ All Good" if all_success else "❌ Errors"
    total_status_color = Colors.GREEN if all_success else Colors.FAIL
    s_total_folders = f"{total_folders:,}"
    s_total_rules = f"{total_rules:,}"
    s_total_duration = f"{total_duration:.1f}s"
    print(
        f"{Box.V} {Colors.BOLD}{'TOTAL':<{w_profile}}{Colors.ENDC} "
        f"{Box.V} {s_total_folders:>{w_folders}} "
        f"{Box.V} {s_total_rules:>{w_rules}} "
        f"{Box.V} {s_total_duration:>{w_duration}} "
        f"{Box.V} {total_status_color}{total_status_text:<{w_status}}{Colors.ENDC} {Box.V}"
    )
    print(make_col_separator(Box.BL, Box.B, Box.BR, Box.H, col_widths))
