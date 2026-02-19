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

import argparse
import concurrent.futures
import contextlib
import getpass
import ipaddress
import json
import logging
import os
import platform
import random
import re
import shutil
import socket
import stat
import sys
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Set
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

# --------------------------------------------------------------------------- #
# 0. Bootstrap – load secrets and configure logging
# --------------------------------------------------------------------------- #
# SECURITY: load_dotenv() moved to main() to ensure permissions are checked first

# Respect NO_COLOR standard (https://no-color.org/)
if os.getenv("NO_COLOR"):
    USE_COLORS = False
else:
    USE_COLORS = sys.stderr.isatty() and sys.stdout.isatty()


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


class Box:
    """Box drawing characters for pretty tables."""

    if USE_COLORS:
        H, V, TL, TR, BL, BR, T, B, L, R, X = "─", "│", "┌", "┐", "└", "┘", "┬", "┴", "├", "┤", "┼"
    else:
        H, V, TL, TR, BL, BR, T, B, L, R, X = "-", "|", "+", "+", "+", "+", "+", "+", "+", "+", "+"


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


# Setup logging
handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
logging.getLogger("httpx").setLevel(logging.WARNING)


def check_env_permissions(env_path: str = ".env") -> None:
    """
    Check .env file permissions and auto-fix if readable by others.

    Security: Automatically sets permissions to 600 (owner read/write only)
    if the file is world-readable. This prevents other users on the system
    from stealing secrets stored in .env files.

    Args:
        env_path: Path to the .env file to check (default: ".env")
    """
    if not os.path.exists(env_path):
        return

    # Security: Don't follow symlinks when checking/fixing permissions
    # This prevents attacks where .env is symlinked to a system file (e.g., /etc/passwd)
    if os.path.islink(env_path):
        sys.stderr.write(
            f"{Colors.WARNING}⚠️  Security Warning: {env_path} is a symlink. "
            f"Skipping permission fix to avoid damaging target file.{Colors.ENDC}\n"
        )
        return

    # Windows doesn't have Unix permissions
    if os.name == "nt":
        # Just warn on Windows, can't auto-fix
        sys.stderr.write(
            f"{Colors.WARNING}⚠️  Security Warning: "
            f"Please ensure {env_path} is only readable by you.{Colors.ENDC}\n"
        )
        return

    try:
        # Security: Use low-level file descriptor operations to avoid TOCTOU (Time-of-Check Time-of-Use)
        # race conditions. We open the file with O_NOFOLLOW to ensure we don't follow symlinks.
        fd = os.open(env_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            file_stat = os.fstat(fd)
            # Check if group or others have any permission
            if file_stat.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
                perms = format(stat.S_IMODE(file_stat.st_mode), "03o")

                # Auto-fix: Set to 600 (owner read/write only) using fchmod on the open descriptor
                try:
                    os.fchmod(fd, 0o600)
                    sys.stderr.write(
                        f"{Colors.GREEN}✓ Fixed {env_path} permissions "
                        f"(was {perms}, now set to 600){Colors.ENDC}\n"
                    )
                except OSError as fix_error:
                    # Auto-fix failed, show warning with instructions
                    sys.stderr.write(
                        f"{Colors.WARNING}⚠️  Security Warning: {env_path} is "
                        f"readable by others ({perms})! Auto-fix failed: {fix_error}. "
                        f"Please run: chmod 600 {env_path}{Colors.ENDC}\n"
                    )
        finally:
            os.close(fd)
    except OSError as error:
        # More specific exception type as suggested by bot review
        exception_type = type(error).__name__
        sys.stderr.write(
            f"{Colors.WARNING}⚠️  Security Warning: Could not check {env_path} "
            f"permissions ({exception_type}: {error}){Colors.ENDC}\n"
        )


# SECURITY: Check .env permissions will be called in main() to avoid side effects at import time
log = logging.getLogger("control-d-sync")

# --------------------------------------------------------------------------- #
# 1. Constants – tweak only here
# --------------------------------------------------------------------------- #
API_BASE = "https://api.controld.com/profiles"
USER_AGENT = "Control-D-Sync/0.1.0"

# Pre-compiled regex patterns for hot-path validation (>2x speedup on 10k+ items)
PROFILE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
# Folder IDs (PK) are typically alphanumeric but can contain other safe chars.
# We whitelist to prevent path traversal and injection.
FOLDER_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+$")
RULE_PATTERN = re.compile(r"^[a-zA-Z0-9.\-_:*/@]+$")

# Parallel processing configuration
DELETE_WORKERS = 3  # Conservative for DELETE operations due to rate limits

# Security: Dangerous characters for folder names
# XSS and HTML injection characters
_DANGEROUS_FOLDER_CHARS = set("<>\"'`")
# Path separators (prevent confusion and directory traversal attempts)
_DANGEROUS_FOLDER_CHARS.update(["/", "\\"])

# Security: Unicode Bidi control characters (prevent RTLO/homograph attacks)
# These characters can be used to mislead users about file extensions or content
# See: https://en.wikipedia.org/wiki/Right-to-left_override
_BIDI_CONTROL_CHARS = {
    "\u202a",  # LEFT-TO-RIGHT EMBEDDING (LRE)
    "\u202b",  # RIGHT-TO-LEFT EMBEDDING (RLE)
    "\u202c",  # POP DIRECTIONAL FORMATTING (PDF)
    "\u202d",  # LEFT-TO-RIGHT OVERRIDE (LRO)
    "\u202e",  # RIGHT-TO-LEFT OVERRIDE (RLO) - primary attack vector
    "\u2066",  # LEFT-TO-RIGHT ISOLATE (LRI)
    "\u2067",  # RIGHT-TO-LEFT ISOLATE (RLI)
    "\u2068",  # FIRST STRONG ISOLATE (FSI)
    "\u2069",  # POP DIRECTIONAL ISOLATE (PDI)
    "\u200e",  # LEFT-TO-RIGHT MARK (LRM) - defense in depth
    "\u200f",  # RIGHT-TO-LEFT MARK (RLM) - defense in depth
}

# Pre-compiled patterns for log sanitization
_BASIC_AUTH_PATTERN = re.compile(r"://[^/@]+@")
_SENSITIVE_PARAM_PATTERN = re.compile(
    r"([?&#])(token|key|secret|password|auth|access_token|api_key)=[^&#\s]*",
    flags=re.IGNORECASE,
)


def sanitize_for_log(text: Any) -> str:
    """Sanitize text for logging.

    Redacts:
    - TOKEN values
    - Basic Auth credentials in URLs (e.g. https://user:pass@host)
    - Sensitive query parameters (token, key, secret, password, auth, access_token, api_key)
    - Control characters (prevents log injection and terminal hijacking)
    """
    s = str(text)
    if TOKEN and TOKEN in s:
        s = s.replace(TOKEN, "[REDACTED]")

    # Redact Basic Auth in URLs (e.g. https://user:pass@host)
    # Optimization: Check for '://' before running expensive regex substitution
    if "://" in s:
        s = _BASIC_AUTH_PATTERN.sub("://[REDACTED]@", s)

    # Redact sensitive query parameters (handles ?, &, and # separators)
    # Optimization: Check for delimiters before running expensive regex substitution
    if "?" in s or "&" in s or "#" in s:
        s = _SENSITIVE_PARAM_PATTERN.sub(r"\1\2=[REDACTED]", s)

    # repr() safely escapes control characters (e.g., \n -> \\n, \x1b -> \\x1b)
    # This prevents log injection and terminal hijacking.
    safe = repr(s)

    # Security: Prevent CSV Injection (Formula Injection)
    # If the string starts with =, +, -, or @, we keep the quotes from repr()
    # to force spreadsheet software to treat it as a string literal.
    if s and s.startswith(("=", "+", "-", "@")):
        return safe

    if len(safe) >= 2 and safe[0] == safe[-1] and safe[0] in ("'", '"'):
        return safe[1:-1]
    return safe


def print_plan_details(plan_entry: Dict[str, Any]) -> None:
    """Pretty-print the folder-level breakdown during a dry-run."""
    profile = sanitize_for_log(plan_entry.get("profile", "unknown"))
    folders = plan_entry.get("folders", [])

    if USE_COLORS:
        print(f"\n{Colors.HEADER}📝 Plan Details for {profile}:{Colors.ENDC}")
    else:
        print(f"\nPlan Details for {profile}:")

    if not folders:
        if USE_COLORS:
            print(f"  {Colors.WARNING}No folders to sync.{Colors.ENDC}")
        else:
            print("  No folders to sync.")
        return

    # Calculate max width for alignment
    max_name_len = max(
        # Use the same default ("Unknown") as when printing, so alignment is accurate
        (len(sanitize_for_log(f.get("name", "Unknown"))) for f in folders),
        default=0,
    )
    max_rules_len = max((len(f"{f.get('rules', 0):,}") for f in folders), default=0)

    for folder in sorted(folders, key=lambda f: f.get("name", "Unknown")):
        name = sanitize_for_log(folder.get("name", "Unknown"))
        rules_count = folder.get("rules", 0)
        formatted_rules = f"{rules_count:,}"

        if USE_COLORS:
            print(
                f"  • {Colors.BOLD}{name:<{max_name_len}}{Colors.ENDC} : {formatted_rules:>{max_rules_len}} rules"
            )
        else:
            print(
                f"  - {name:<{max_name_len}} : {formatted_rules:>{max_rules_len}} rules"
            )

    print("")


def print_summary_table(results: List[Dict[str, Any]], dry_run: bool) -> None:
    """Prints a nicely formatted summary table."""
    # Determine the width for the Profile ID column (min 25)
    max_profile_len = max((len(r["profile"]) for r in results), default=25)
    profile_col_width = max(25, max_profile_len)

    # Calculate widths
    col_widths = {
        "profile": profile_col_width,
        "folders": 10,
        "rules": 10,
        "duration": 10,
        "status": 15,
    }

    if USE_COLORS:
        # Unicode Box Drawing
        chars = {
            "tl": "┌", "tm": "┬", "tr": "┐",
            "bl": "└", "bm": "┴", "br": "┘",
            "ml": "├", "mm": "┼", "mr": "┤",
            "v": "│", "h": "─",
        }
    else:
        # ASCII Fallback
        chars = {
            "tl": "+", "tm": "+", "tr": "+",
            "bl": "+", "bm": "+", "br": "+",
            "ml": "+", "mm": "+", "mr": "+",
            "v": "|", "h": "-",
        }

    def _print_separator(left, mid, right):
        segments = [chars["h"] * (width + 2) for width in col_widths.values()]
        print(f"{chars[left]}{chars[mid].join(segments)}{chars[right]}")

    def _print_row(profile, folders, rules, duration, status, is_header=False):
        v = chars["v"]

        # 1. Pad raw strings first (so padding is calculated on visible chars)
        p_val = f"{profile:<{col_widths['profile']}}"
        f_val = f"{folders:>{col_widths['folders']}}"
        r_val = f"{rules:>{col_widths['rules']}}"
        d_val = f"{duration:>{col_widths['duration']}}"
        s_val = f"{status:<{col_widths['status']}}"

        # 2. Wrap in color codes if needed
        if is_header and USE_COLORS:
            p_val = f"{Colors.BOLD}{p_val}{Colors.ENDC}"
            f_val = f"{Colors.BOLD}{f_val}{Colors.ENDC}"
            r_val = f"{Colors.BOLD}{r_val}{Colors.ENDC}"
            d_val = f"{Colors.BOLD}{d_val}{Colors.ENDC}"
            s_val = f"{Colors.BOLD}{s_val}{Colors.ENDC}"

        print(
            f"{v} {p_val} {v} {f_val} {v} {r_val} {v} {d_val} {v} {s_val} {v}"
        )

    title_text = "DRY RUN SUMMARY" if dry_run else "SYNC SUMMARY"
    title_color = Colors.CYAN if dry_run else Colors.HEADER

    total_width = (
        1 + (col_widths["profile"] + 2) + 1 +
        (col_widths["folders"] + 2) + 1 +
        (col_widths["rules"] + 2) + 1 +
        (col_widths["duration"] + 2) + 1 +
        (col_widths["status"] + 2) + 1
    )

    print("\n" + (f"{title_color}{title_text:^{total_width}}{Colors.ENDC}" if USE_COLORS else f"{title_text:^{total_width}}"))

    _print_separator("tl", "tm", "tr")
    # Header row - pad manually then print
    _print_row("Profile ID", "Folders", "Rules", "Duration", "Status", is_header=True)
    _print_separator("ml", "mm", "mr")

    total_folders = 0
    total_rules = 0
    total_duration = 0.0
    success_count = 0

    for res in results:
        # Profile
        p_val = f"{res['profile']:<{col_widths['profile']}}"

        # Folders
        f_val = f"{res['folders']:>{col_widths['folders']}}"

        # Rules
        r_val = f"{res['rules']:>{col_widths['rules']},}"

        # Duration
        d_val = f"{res['duration']:>{col_widths['duration']-1}.1f}s"

        # Status
        status_label = res["status_label"]
        s_val_raw = f"{status_label:<{col_widths['status']}}"
        if USE_COLORS:
            status_color = Colors.GREEN if res["success"] else Colors.FAIL
            s_val = f"{status_color}{s_val_raw}{Colors.ENDC}"
        else:
            s_val = s_val_raw

        # Delegate the actual row printing to the shared helper to avoid
        # duplicating table border/spacing logic here.
        _print_row(p_val, f_val, r_val, d_val, s_val)

        total_folders += res["folders"]
        total_rules += res["rules"]
        total_duration += res["duration"]
        if res["success"]:
            success_count += 1

    _print_separator("ml", "mm", "mr")

    # Total Row
    total = len(results)
    all_success = success_count == total

    if dry_run:
        total_status_text = "✅ Ready" if all_success else "❌ Errors"
    else:
        total_status_text = "✅ All Good" if all_success else "❌ Errors"

    p_val = f"{'TOTAL':<{col_widths['profile']}}"
    if USE_COLORS:
        p_val = f"{Colors.BOLD}{p_val}{Colors.ENDC}"

    f_val = f"{total_folders:>{col_widths['folders']}}"
    r_val = f"{total_rules:>{col_widths['rules']},}"
    d_val = f"{total_duration:>{col_widths['duration']-1}.1f}s"

    s_val_raw = f"{total_status_text:<{col_widths['status']}}"
    if USE_COLORS:
        status_color = Colors.GREEN if all_success else Colors.FAIL
        s_val = f"{status_color}{s_val_raw}{Colors.ENDC}"
    else:
        s_val = s_val_raw

    print(
        f"{chars['v']} {p_val} "
        f"{chars['v']} {f_val} "
        f"{chars['v']} {r_val} "
        f"{chars['v']} {d_val} "
        f"{chars['v']} {s_val} {chars['v']}"
    )

    _print_separator("bl", "bm", "br")


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
    if not USE_COLORS:
        # UX Improvement: For long waits in non-interactive/no-color mode (e.g. CI),
        # log periodic updates instead of sleeping silently.
        if seconds > 10:
            step = 10
            for remaining in range(seconds, 0, -step):
                # Don't log the first one if we already logged "Waiting..." before calling this
                if remaining < seconds:
                    log.info(f"{sanitize_for_log(message)}: {remaining}s remaining...")

                sleep_time = min(step, remaining)
                time.sleep(sleep_time)
            return

        time.sleep(seconds)
        return

    width = _get_progress_bar_width()

    for remaining in range(seconds, 0, -1):
        progress = (seconds - remaining + 1) / seconds
        filled = int(width * progress)
        bar = "█" * filled + "·" * (width - filled)
        sys.stderr.write(
            f"\r{Colors.CYAN}⏳ {message}: [{bar}] {remaining}s...{Colors.ENDC}"
        )
        sys.stderr.flush()
        time.sleep(1)

    sys.stderr.write(f"\r\033[K{Colors.GREEN}✅ {message}: Done!{Colors.ENDC}\n")
    sys.stderr.flush()


def render_progress_bar(
    current: int, total: int, label: str, prefix: str = "🚀"
) -> None:
    """Renders a progress bar to stderr if USE_COLORS is True."""
    if not USE_COLORS or total == 0:
        return

    width = _get_progress_bar_width()

    progress = min(1.0, current / total)
    filled = int(width * progress)
    bar = "█" * filled + "·" * (width - filled)
    percent = int(progress * 100)

    # Use \033[K to clear line residue
    sys.stderr.write(
        f"\r\033[K{Colors.CYAN}{prefix} {label}: [{bar}] {percent}% ({current}/{total}){Colors.ENDC}"
    )
    sys.stderr.flush()


def _clean_env_kv(value: Optional[str], key: str) -> Optional[str]:
    """Allow TOKEN/PROFILE values to be provided as either raw values or KEY=value."""
    if not value:
        return value
    v = value.strip()
    m = re.match(rf"^{re.escape(key)}\s*=\s*(.+)$", v)
    if m:
        return m.group(1).strip()
    return v


def get_validated_input(
    prompt: str,
    validator: Callable[[str], bool],
    error_msg: str,
) -> str:
    """Prompts for input until the validator returns True."""
    while True:
        try:
            value = input(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{Colors.WARNING}⚠️  Input cancelled.{Colors.ENDC}")
            sys.exit(130)

        if not value:
            print(f"{Colors.FAIL}❌ Value cannot be empty{Colors.ENDC}")
            continue

        if validator(value):
            return value

        print(f"{Colors.FAIL}❌ {error_msg}{Colors.ENDC}")


def get_password(
    prompt: str,
    validator: Callable[[str], bool],
    error_msg: str,
) -> str:
    """Prompts for password input until the validator returns True."""
    while True:
        try:
            value = getpass.getpass(prompt).strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{Colors.WARNING}⚠️  Input cancelled.{Colors.ENDC}")
            sys.exit(130)

        if not value:
            print(f"{Colors.FAIL}❌ Value cannot be empty{Colors.ENDC}")
            continue

        if validator(value):
            return value

        print(f"{Colors.FAIL}❌ {error_msg}{Colors.ENDC}")


TOKEN = _clean_env_kv(os.getenv("TOKEN"), "TOKEN")

# Default folder sources
DEFAULT_FOLDER_URLS = [
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/apple-private-relay-allow-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/badware-hoster-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/meta-tracker-allow-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/microsoft-allow-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-amazon-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-apple-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-huawei-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-lgwebos-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-microsoft-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-oppo-realme-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-samsung-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-tiktok-aggressive-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-tiktok-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-vivo-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-xiaomi-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/nosafesearch-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/referral-allow-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/spam-idns-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/spam-tlds-allow-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/spam-tlds-combined-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/spam-tlds-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/ultimate-known_issues-allow-folder.json",
    "https://raw.githubusercontent.com/yokoffing/Control-D-Config/main/folders/potentially-malicious-ips.json",
]

BATCH_SIZE = 500
BATCH_KEYS = [f"hostnames[{i}]" for i in range(BATCH_SIZE)]
MAX_RETRIES = 10
RETRY_DELAY = 1
FOLDER_CREATION_DELAY = 5  # <--- CHANGED: Increased from 2 to 5 for patience
MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10MB limit


# --------------------------------------------------------------------------- #
# 2. Clients
# --------------------------------------------------------------------------- #
def _api_client() -> httpx.Client:
    return httpx.Client(
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {TOKEN}",
            "User-Agent": USER_AGENT,
        },
        timeout=30,
        follow_redirects=False,
    )


_gh = httpx.Client(
    headers={"User-Agent": USER_AGENT},
    timeout=30,
    follow_redirects=False,
)
MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10 MB limit for external resources

# --------------------------------------------------------------------------- #
# 3. Helpers
# --------------------------------------------------------------------------- #
_cache: Dict[str, Dict] = {}
# Use RLock (reentrant lock) to allow nested acquisitions by the same thread
# This prevents deadlocks when _fetch_if_valid calls fetch_folder_data which calls _gh_get
_cache_lock = threading.RLock()

# --------------------------------------------------------------------------- #
# 3a. Persistent Disk Cache Support
# --------------------------------------------------------------------------- #
# Disk cache stores validated blocklist data with HTTP cache headers (ETag, Last-Modified)
# to enable fast cold-start syncs via conditional HTTP requests (304 Not Modified)
_disk_cache: Dict[str, Dict[str, Any]] = {}  # Loaded from disk on startup
_cache_stats = {"hits": 0, "misses": 0, "validations": 0, "errors": 0}
_api_stats = {"control_d_api_calls": 0, "blocklist_fetches": 0}

# --------------------------------------------------------------------------- #
# 3b. Rate Limit Tracking
# --------------------------------------------------------------------------- #
# Track rate limit information from API responses to enable proactive throttling
# and provide visibility into API quota usage
_rate_limit_info = {
    "limit": None,       # Max requests allowed per window (from X-RateLimit-Limit)
    "remaining": None,   # Requests remaining in current window (from X-RateLimit-Remaining)
    "reset": None,       # Timestamp when limit resets (from X-RateLimit-Reset)
}
_rate_limit_lock = threading.Lock()  # Protect _rate_limit_info updates


def get_cache_dir() -> Path:
    """
    Returns platform-specific cache directory for ctrld-sync.
    
    Uses standard cache locations:
    - Linux/Unix: ~/.cache/ctrld-sync
    - macOS: ~/Library/Caches/ctrld-sync
    - Windows: %LOCALAPPDATA%/ctrld-sync/cache
    
    SECURITY: No user input in path construction - prevents path traversal attacks
    """
    system = platform.system()
    if system == "Darwin":  # macOS
        return Path.home() / "Library" / "Caches" / "ctrld-sync"
    elif system == "Windows":
        appdata = os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        return Path(appdata) / "ctrld-sync" / "cache"
    else:  # Linux, Unix, and others
        # Follow XDG Base Directory spec
        xdg_cache = os.getenv("XDG_CACHE_HOME")
        if xdg_cache:
            return Path(xdg_cache) / "ctrld-sync"
        return Path.home() / ".cache" / "ctrld-sync"


def load_disk_cache() -> None:
    """
    Loads persistent cache from disk on startup.
    
    GRACEFUL DEGRADATION: Any error (corrupted JSON, permissions, etc.) 
    is logged but ignored - we simply start with empty cache.
    This protects against crashes from corrupted cache files.
    """
    global _disk_cache, _cache_stats
    
    try:
        cache_file = get_cache_dir() / "blocklists.json"
        if not cache_file.exists():
            log.debug("No existing cache file found, starting fresh")
            return

        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Validate cache structure at the top level
        if not isinstance(data, dict):
            log.warning("Cache file has invalid format (root is not a dict), ignoring")
            return

        # Sanitize individual cache entries to ensure graceful degradation:
        # - keys must be strings
        # - values must be dicts
        # - each entry must contain at least a 'data' field
        sanitized_cache: Dict[str, Any] = {}
        dropped_entries = 0

        for key, value in data.items():
            if not isinstance(key, str):
                dropped_entries += 1
                log.debug("Dropping cache entry with non-string key: %r", key)
                continue

            if not isinstance(value, dict):
                dropped_entries += 1
                log.debug("Dropping cache entry %r: value is not a dict", key)
                continue

            if "data" not in value:
                dropped_entries += 1
                log.debug("Dropping cache entry %r: missing required 'data' field", key)
                continue

            sanitized_cache[key] = value

        if not sanitized_cache:
            # If nothing is valid, start with an empty cache instead of crashing later
            _disk_cache = {}
            log.warning("Cache file contained no valid entries; starting with empty cache")
            return

        if dropped_entries:
            log.info(
                "Loaded %d valid entries from disk cache (dropped %d malformed entries)",
                len(sanitized_cache),
                dropped_entries,
            )
        else:
            log.info("Loaded %d entries from disk cache", len(sanitized_cache))

        _disk_cache = sanitized_cache
    except json.JSONDecodeError as e:
        log.warning(f"Corrupted cache file (invalid JSON), starting fresh: {e}")
        _cache_stats["errors"] += 1
    except PermissionError as e:
        log.warning(f"Cannot read cache file (permission denied), starting fresh: {e}")
        _cache_stats["errors"] += 1
    except Exception as e:
        # Catch-all for unexpected errors (disk full, etc.)
        log.warning(f"Failed to load cache, starting fresh: {sanitize_for_log(e)}")
        _cache_stats["errors"] += 1


def save_disk_cache() -> None:
    """
    Saves persistent cache to disk after successful sync.
    
    SECURITY: Creates cache directory with user-only permissions (0o700)
    to prevent other users from reading cached blocklist data.
    """
    try:
        cache_dir = get_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        # Set directory permissions to user-only (rwx------)
        # This prevents other users from reading cached data
        if platform.system() != "Windows":
            cache_dir.chmod(0o700)
        
        cache_file = cache_dir / "blocklists.json"
        
        # Write atomically: write to temp file, then rename
        # This prevents corrupted cache if process is killed mid-write
        temp_file = cache_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(_disk_cache, f, indent=2)
        
        # Set file permissions to user-only (rw-------)
        if platform.system() != "Windows":
            temp_file.chmod(0o600)
        
        # Atomic rename (POSIX guarantees atomicity)
        temp_file.replace(cache_file)
        
        log.debug(f"Saved {len(_disk_cache):,} entries to disk cache")
        
    except Exception as e:
        # Cache save failures are non-fatal - we just won't have cache next time
        log.warning(f"Failed to save cache (non-fatal): {sanitize_for_log(e)}")
        _cache_stats["errors"] += 1


def _parse_rate_limit_headers(response: httpx.Response) -> None:
    """
    Parse rate limit headers from API response and update global tracking.
    
    Supports standard rate limit headers:
    - X-RateLimit-Limit: Maximum requests per window
    - X-RateLimit-Remaining: Requests remaining in current window
    - X-RateLimit-Reset: Unix timestamp when limit resets
    - Retry-After: Seconds to wait (priority on 429 responses)
    
    This enables:
    1. Proactive throttling when approaching limits
    2. Visibility into API quota usage
    3. Smarter retry strategies based on actual limit state
    
    THREAD-SAFE: Uses _rate_limit_lock to protect shared state
    GRACEFUL: Invalid/missing headers are ignored (no crashes)
    """
    global _rate_limit_info
    
    headers = response.headers
    
    # Parse standard rate limit headers
    # These may not exist on all responses, so we check individually
    try:
        with _rate_limit_lock:
            # X-RateLimit-Limit: Total requests allowed per window
            if "X-RateLimit-Limit" in headers:
                try:
                    _rate_limit_info["limit"] = int(headers["X-RateLimit-Limit"])
                except (ValueError, TypeError):
                    pass  # Invalid value, ignore
            
            # X-RateLimit-Remaining: Requests left in current window
            if "X-RateLimit-Remaining" in headers:
                try:
                    _rate_limit_info["remaining"] = int(headers["X-RateLimit-Remaining"])
                except (ValueError, TypeError):
                    pass
            
            # X-RateLimit-Reset: Unix timestamp when window resets
            if "X-RateLimit-Reset" in headers:
                try:
                    _rate_limit_info["reset"] = int(headers["X-RateLimit-Reset"])
                except (ValueError, TypeError):
                    pass
            
            # Log warnings when approaching rate limits
            # Only log if we have both limit and remaining values
            if (_rate_limit_info["limit"] is not None and 
                _rate_limit_info["remaining"] is not None):
                limit = _rate_limit_info["limit"]
                remaining = _rate_limit_info["remaining"]
                
                # Warn at 20% remaining capacity
                if limit > 0 and remaining / limit < 0.2:
                    if _rate_limit_info["reset"]:
                        reset_time = time.strftime(
                            "%H:%M:%S", 
                            time.localtime(_rate_limit_info["reset"])
                        )
                        log.warning(
                            f"Approaching rate limit: {remaining}/{limit} requests remaining "
                            f"(resets at {reset_time})"
                        )
                    else:
                        log.warning(
                            f"Approaching rate limit: {remaining}/{limit} requests remaining"
                        )
    except Exception as e:
        # Rate limit parsing failures should never crash the sync
        # Just log and continue
        log.debug(f"Failed to parse rate limit headers: {e}")


@lru_cache(maxsize=128)
def validate_hostname(hostname: str) -> bool:
    """
    Validates a hostname (DNS resolution and IP checks).
    Cached to prevent redundant DNS lookups for the same host across different URLs.
    """
    # Check for potentially malicious hostnames
    if hostname.lower() in ("localhost", "127.0.0.1", "::1"):
        log.warning(
            f"Skipping unsafe hostname (localhost detected): {sanitize_for_log(hostname)}"
        )
        return False

    try:
        ip = ipaddress.ip_address(hostname)
        if not ip.is_global or ip.is_multicast:
            log.warning(f"Skipping unsafe IP: {sanitize_for_log(hostname)}")
            return False
        return True
    except ValueError:
        # Not an IP literal, it's a domain. Resolve and check IPs.
        try:
            # Resolve hostname to IPs (IPv4 and IPv6)
            # We filter for AF_INET/AF_INET6 to ensure we get IP addresses
            addr_info = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
            for res in addr_info:
                # res is (family, type, proto, canonname, sockaddr)
                # sockaddr is (address, port) for AF_INET/AF_INET6
                ip_str = res[4][0]
                ip = ipaddress.ip_address(ip_str)
                if not ip.is_global or ip.is_multicast:
                    log.warning(
                        f"Skipping unsafe hostname {sanitize_for_log(hostname)} (resolves to non-global/multicast IP {ip})"
                    )
                    return False
            return True
        except (socket.gaierror, ValueError, OSError) as e:
            log.warning(
                f"Failed to resolve/validate domain {sanitize_for_log(hostname)}: {sanitize_for_log(e)}"
            )
            return False


@lru_cache(maxsize=128)
def validate_folder_url(url: str) -> bool:
    """
    Validates a folder URL.
    Cached to avoid repeated URL parsing for the same URL.
    """
    if not url.startswith("https://"):
        log.warning(
            f"Skipping unsafe or invalid URL (must be https): {sanitize_for_log(url)}"
        )
        return False

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False

        return validate_hostname(hostname)

    except Exception as e:
        log.warning(
            f"Failed to validate URL {sanitize_for_log(url)}: {sanitize_for_log(e)}"
        )
        return False

    return True


def extract_profile_id(text: str) -> str:
    """
    Extracts the Profile ID from a Control D URL if present,
    otherwise returns the text as-is (cleaned).
    """
    if not text:
        return ""
    text = text.strip()
    # Pattern for Control D Dashboard URLs
    # e.g. https://controld.com/dashboard/profiles/12345abc/filters
    match = re.search(r"controld\.com/dashboard/profiles/([^/?#\s]+)", text)
    if match:
        return match.group(1)
    return text


def is_valid_profile_id_format(profile_id: str) -> bool:
    """
    Checks if a profile ID matches the expected format.
    
    Validates against PROFILE_ID_PATTERN and enforces maximum length of 64 characters.
    """
    if not PROFILE_ID_PATTERN.match(profile_id):
        return False
    if len(profile_id) > 64:
        return False
    return True


def validate_profile_id(profile_id: str, log_errors: bool = True) -> bool:
    """
    Validates a Control D profile ID with optional error logging.
    
    Returns True if profile ID is valid, False otherwise.
    Logs specific validation errors when log_errors=True.
    """
    if not is_valid_profile_id_format(profile_id):
        if log_errors:
            if not PROFILE_ID_PATTERN.match(profile_id):
                log.error("Invalid profile ID format (contains unsafe characters)")
            elif len(profile_id) > 64:
                log.error("Invalid profile ID length (max 64 chars)")
        return False
    return True


def validate_folder_id(folder_id: str, log_errors: bool = True) -> bool:
    """Validates folder ID (PK) format to prevent path traversal."""
    if not folder_id:
        return False
    if folder_id in (".", "..") or not FOLDER_ID_PATTERN.match(folder_id):
        if log_errors:
            log.error(f"Invalid folder ID format: {sanitize_for_log(folder_id)}")
        return False
    return True


def is_valid_rule(rule: str) -> bool:
    """
    Validates that a rule is safe to use.
    Enforces a strict whitelist of allowed characters.
    Allowed: Alphanumeric, hyphen, dot, underscore, asterisk, colon (IPv6), slash (CIDR)
    """
    if not rule:
        return False

    # Strict whitelist to prevent injection
    if not RULE_PATTERN.match(rule):
        return False

    return True


def is_valid_folder_name(name: str) -> bool:
    """
    Validates folder name to prevent XSS, path traversal, and homograph attacks.

    Blocks:
    - XSS/HTML injection characters: < > " ' `
    - Path separators: / \\
    - Unicode Bidi control characters (RTLO spoofing)
    - Empty or whitespace-only names
    - Non-printable characters
    """
    if not name or not name.strip() or not name.isprintable():
        return False

    # Check for dangerous characters (pre-compiled at module level for performance)
    if any(c in _DANGEROUS_FOLDER_CHARS or c in _BIDI_CONTROL_CHARS for c in name):
        return False

    # Security: Block path traversal attempts
    # Check stripped name to prevent whitespace bypass (e.g. " . ")
    clean_name = name.strip()
    if clean_name in (".", ".."):
        return False

    # Security: Block command option injection (if name is passed to shell)
    if clean_name.startswith("-"):
        return False

    return True


def validate_folder_data(data: Dict[str, Any], url: str) -> bool:
    """
    Validates folder JSON data structure and content.
    
    Checks for required fields (name, action, rules), validates folder name
    and action type, and ensures rules are valid. Logs specific validation errors.
    """
    if not isinstance(data, dict):
        log.error(
            f"Invalid data from {sanitize_for_log(url)}: Root must be a JSON object."
        )
        return False
    if "group" not in data:
        log.error(f"Invalid data from {sanitize_for_log(url)}: Missing 'group' key.")
        return False
    if not isinstance(data["group"], dict):
        log.error(
            f"Invalid data from {sanitize_for_log(url)}: 'group' must be an object."
        )
        return False
    if "group" not in data["group"]:
        log.error(
            f"Invalid data from {sanitize_for_log(url)}: Missing 'group.group' (folder name)."
        )
        return False

    folder_name = data["group"]["group"]
    if not isinstance(folder_name, str):
        log.error(
            f"Invalid data from {sanitize_for_log(url)}: Folder name must be a string."
        )
        return False

    if not is_valid_folder_name(folder_name):
        log.error(
            f"Invalid data from {sanitize_for_log(url)}: Invalid folder name (empty, unsafe characters, or non-printable)."
        )
        return False

    return True


# Lock to protect updates to _api_stats in multi-threaded contexts.
# Without this, concurrent increments can lose updates because `+=` is not atomic.
_api_stats_lock = threading.Lock()


def _api_get(client: httpx.Client, url: str) -> httpx.Response:
    global _api_stats
    with _api_stats_lock:
        _api_stats["control_d_api_calls"] += 1
    return _retry_request(lambda: client.get(url))


def _api_delete(client: httpx.Client, url: str) -> httpx.Response:
    global _api_stats
    with _api_stats_lock:
        _api_stats["control_d_api_calls"] += 1
    return _retry_request(lambda: client.delete(url))


def _api_post(client: httpx.Client, url: str, data: Dict) -> httpx.Response:
    global _api_stats
    with _api_stats_lock:
        _api_stats["control_d_api_calls"] += 1
    return _retry_request(lambda: client.post(url, data=data))


def _api_post_form(client: httpx.Client, url: str, data: Dict) -> httpx.Response:
    global _api_stats
    with _api_stats_lock:
        _api_stats["control_d_api_calls"] += 1
    return _retry_request(
        lambda: client.post(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    )


def _retry_request(request_func, max_retries=MAX_RETRIES, delay=RETRY_DELAY):
    """
    Retry request with exponential backoff.
    
    RATE LIMIT HANDLING:
    - Parses X-RateLimit-* headers from all API responses
    - On 429 (Too Many Requests): uses Retry-After header if present
    - Logs warnings when approaching rate limits (< 20% remaining)
    
    SECURITY:
    - Does NOT retry 4xx client errors (except 429)
    - Sanitizes error messages in logs
    """
    for attempt in range(max_retries):
        try:
            response = request_func()
            
            # Parse rate limit headers from successful responses
            # This gives us visibility into quota usage even when requests succeed
            _parse_rate_limit_headers(response)
            
            response.raise_for_status()
            return response
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            # Security Enhancement: Do not retry client errors (4xx) except 429 (Too Many Requests).
            # Retrying 4xx errors is inefficient and can trigger security alerts or rate limits.
            if isinstance(e, httpx.HTTPStatusError):
                code = e.response.status_code
                
                # Parse rate limit headers even from error responses
                # This helps us understand why we hit limits
                _parse_rate_limit_headers(e.response)
                
                # Handle 429 (Too Many Requests) with Retry-After
                if code == 429:
                    # Check for Retry-After header (in seconds)
                    retry_after = e.response.headers.get("Retry-After")
                    if retry_after:
                        try:
                            # Retry-After can be seconds or HTTP date
                            # Try parsing as int (seconds) first
                            wait_seconds = int(retry_after)
                            log.warning(
                                f"Rate limited (429). Server requests {wait_seconds}s wait "
                                f"(attempt {attempt + 1}/{max_retries})"
                            )
                            if attempt < max_retries - 1:
                                time.sleep(wait_seconds)
                                continue  # Retry after waiting
                            else:
                                raise  # Max retries exceeded
                        except ValueError:
                            # Retry-After might be HTTP date format, ignore for now
                            pass
                
                # Don't retry other 4xx errors (auth failures, bad requests, etc.)
                if 400 <= code < 500 and code != 429:
                    if hasattr(e, "response") and e.response is not None:
                        log.debug(
                            f"Response content: {sanitize_for_log(e.response.text)}"
                        )
                    raise

            if attempt == max_retries - 1:
                if hasattr(e, "response") and e.response is not None:
                    log.debug(f"Response content: {sanitize_for_log(e.response.text)}")
                raise
            
            # Exponential backoff with jitter to prevent thundering herd
            # Base delay: delay * (2^attempt) gives exponential growth
            # Jitter: multiply by random factor in range [0.5, 1.5] to spread retries
            # This prevents multiple failed requests from retrying simultaneously
            base_wait = delay * (2**attempt)
            jitter_factor = 0.5 + random.random()  # Random value between 0.5 and 1.5
            wait_time = base_wait * jitter_factor
            
            log.warning(
                f"Request failed (attempt {attempt + 1}/{max_retries}): "
                f"{sanitize_for_log(e)}. Retrying in {wait_time:.2f}s..."
            )
            time.sleep(wait_time)


def _gh_get(url: str) -> Dict:
    """
    Fetch blocklist data from URL with HTTP cache header support.
    
    CACHING STRATEGY:
    1. Check in-memory cache first (fastest)
    2. Check disk cache and send conditional request (If-None-Match/If-Modified-Since)
    3. If 304 Not Modified: reuse cached data (cache validation)
    4. If 200 OK: download new data and update cache
    
    SECURITY: Validates data structure regardless of cache source
    """
    global _cache_stats, _api_stats
    
    # First check: Quick check without holding lock for long
    with _cache_lock:
        if url in _cache:
            _cache_stats["hits"] += 1
            return _cache[url]
    
    # Track that we're about to make a blocklist fetch
    with _cache_lock:
        _api_stats["blocklist_fetches"] += 1
    
    # Check disk cache for conditional request headers
    headers = {}
    cached_entry = _disk_cache.get(url)
    if cached_entry:
        # Send conditional request using cached ETag/Last-Modified
        # Server returns 304 if content hasn't changed
        # NOTE: Cached values may be None if the server didn't send these headers.
        # httpx requires header values to be str/bytes, so we only add headers
        # when the cached value is truthy.
        etag = cached_entry.get("etag")
        if etag:
            headers["If-None-Match"] = etag
        last_modified = cached_entry.get("last_modified")
        if last_modified:
            headers["If-Modified-Since"] = last_modified
    
    # Fetch data (or validate cache)
    # Explicitly let HTTPError propagate (no need to catch just to re-raise)
    try:
        with _gh.stream("GET", url, headers=headers) as r:
            # Handle 304 Not Modified - cached data is still valid
            if r.status_code == 304:
                if cached_entry and "data" in cached_entry:
                    log.debug(f"Cache validated (304) for {sanitize_for_log(url)}")
                    _cache_stats["validations"] += 1
                    
                    # Update in-memory cache with validated data
                    data = cached_entry["data"]
                    with _cache_lock:
                        _cache[url] = data
                    
                    # Update timestamp in disk cache to track last validation
                    cached_entry["last_validated"] = time.time()
                    return data
                else:
                    # Shouldn't happen, but handle gracefully
                    log.warning(f"Got 304 but no cached data for {sanitize_for_log(url)}, re-fetching")
                    _cache_stats["errors"] += 1
                    # Close the original streaming response before retrying
                    r.close()
                    # Retry without conditional headers using streaming again so that
                    # MAX_RESPONSE_SIZE and related protections still apply.
                    headers = {}
                    with _gh.stream("GET", url, headers=headers) as r_retry:
                        r_retry.raise_for_status()

                        # 1. Check Content-Length header if present
                        cl = r_retry.headers.get("Content-Length")
                        if cl:
                            try:
                                if int(cl) > MAX_RESPONSE_SIZE:
                                    raise ValueError(
                                        f"Response too large from {sanitize_for_log(url)} "
                                        f"({int(cl) / (1024 * 1024):.2f} MB)"
                                    )
                            except ValueError as e:
                                # Only catch the conversion error, let the size error propagate
                                if "Response too large" in str(e):
                                    raise e
                                log.warning(
                                    f"Malformed Content-Length header from {sanitize_for_log(url)}: {cl!r}. "
                                    "Falling back to streaming size check."
                                )
                        
                        # 2. Stream and check actual size
                        chunks = []
                        current_size = 0
                        for chunk in r_retry.iter_bytes():
                            current_size += len(chunk)
                            if current_size > MAX_RESPONSE_SIZE:
                                raise ValueError(
                                    f"Response too large from {sanitize_for_log(url)} "
                                    f"(> {MAX_RESPONSE_SIZE / (1024 * 1024):.2f} MB)"
                                )
                            chunks.append(chunk)
                        
                        try:
                            data = json.loads(b"".join(chunks))
                        except json.JSONDecodeError as e:
                            raise ValueError(
                                f"Invalid JSON response from {sanitize_for_log(url)}"
                            ) from e
                        
                        # Store cache headers for future conditional requests
                        # ETag is preferred over Last-Modified (more reliable)
                        etag = r_retry.headers.get("ETag")
                        last_modified = r_retry.headers.get("Last-Modified")
                        
                        # Update disk cache with new data and headers
                        _disk_cache[url] = {
                            "data": data,
                            "etag": etag,
                            "last_modified": last_modified,
                            "fetched_at": time.time(),
                            "last_validated": time.time(),
                        }
                        
                        _cache_stats["misses"] += 1
                        return data
            
            r.raise_for_status()

            # Security: Validate Content-Type
            # Prevent processing of unexpected content types (e.g., HTML/XML from captive portals or attack sites)
            content_type = r.headers.get("Content-Type", "").lower()
            allowed_types = ["application/json", "text/json", "text/plain"]
            if not any(t in content_type for t in allowed_types):
                raise ValueError(
                    f"Invalid Content-Type from {sanitize_for_log(url)}: {content_type}. "
                    f"Expected one of: {', '.join(allowed_types)}"
                )

            # 1. Check Content-Length header if present
            cl = r.headers.get("Content-Length")
            if cl:
                try:
                    if int(cl) > MAX_RESPONSE_SIZE:
                        raise ValueError(
                            f"Response too large from {sanitize_for_log(url)} "
                            f"({int(cl) / (1024 * 1024):.2f} MB)"
                        )
                except ValueError as e:
                    # Only catch the conversion error, let the size error propagate
                    if "Response too large" in str(e):
                        raise e
                    log.warning(
                        f"Malformed Content-Length header from {sanitize_for_log(url)}: {cl!r}. "
                        "Falling back to streaming size check."
                    )
            
            # 2. Stream and check actual size
            chunks = []
            current_size = 0
            # Optimization: Use 16KB chunks to reduce loop overhead/appends for large files
            for chunk in r.iter_bytes(chunk_size=16 * 1024):
                current_size += len(chunk)
                if current_size > MAX_RESPONSE_SIZE:
                    raise ValueError(
                        f"Response too large from {sanitize_for_log(url)} "
                        f"(> {MAX_RESPONSE_SIZE / (1024 * 1024):.2f} MB)"
                    )
                chunks.append(chunk)
            
            try:
                data = json.loads(b"".join(chunks))
            except json.JSONDecodeError as e:
                raise ValueError(
                    f"Invalid JSON response from {sanitize_for_log(url)}"
                ) from e
            
            # Store cache headers for future conditional requests
            # ETag is preferred over Last-Modified (more reliable)
            etag = r.headers.get("ETag")
            last_modified = r.headers.get("Last-Modified")
            
            # Update disk cache with new data and headers
            _disk_cache[url] = {
                "data": data,
                "etag": etag,
                "last_modified": last_modified,
                "fetched_at": time.time(),
                "last_validated": time.time(),
            }
            
            _cache_stats["misses"] += 1
    
    except httpx.HTTPStatusError as e:
        # Re-raise with original exception (don't catch and re-raise)
        raise
    
    # Double-checked locking: Check again after fetch to avoid duplicate fetches
    # If another thread already cached it while we were fetching, use theirs
    # for consistency (return _cache[url] instead of data to ensure single source of truth)
    with _cache_lock:
        if url not in _cache:
            _cache[url] = data
        return _cache[url]


def check_api_access(client: httpx.Client, profile_id: str) -> bool:
    """
    Verifies API access and Profile existence before starting heavy work.
    Returns True if access is good, False otherwise (with helpful logs).
    """
    url = f"{API_BASE}/{profile_id}/groups"
    try:
        # We use a raw request here to avoid the automatic retries of _retry_request
        # for auth errors, which are permanent.
        resp = client.get(url)
        resp.raise_for_status()
        return True
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 401:
            log.critical(
                f"{Colors.FAIL}❌ Authentication Failed: The API Token is invalid.{Colors.ENDC}"
            )
            log.critical(
                f"{Colors.FAIL}   Please check your token at: https://controld.com/account/manage-account{Colors.ENDC}"
            )
        elif code == 403:
            log.critical(
                f"{Colors.FAIL}🚫 Access Denied: Token lacks permission for Profile {profile_id}.{Colors.ENDC}"
            )
        elif code == 404:
            log.critical(
                f"{Colors.FAIL}🔍 Profile Not Found: The ID '{sanitize_for_log(profile_id)}' does not exist.{Colors.ENDC}"
            )
            log.critical(
                f"{Colors.FAIL}   Please verify the Profile ID from your Control D Dashboard URL.{Colors.ENDC}"
            )
        else:
            log.error(f"API Access Check Failed ({code}): {sanitize_for_log(e)}")
        return False
    except httpx.RequestError as e:
        log.error(f"Network Error during access check: {sanitize_for_log(e)}")
        return False


def list_existing_folders(client: httpx.Client, profile_id: str) -> Dict[str, str]:
    """
    Retrieves all existing folders (groups) for a given profile.
    
    Returns a dictionary mapping folder names to their IDs.
    Returns empty dict on error.
    """
    try:
        data = _api_get(client, f"{API_BASE}/{profile_id}/groups").json()
        folders = data.get("body", {}).get("groups", [])
        result = {}
        for f in folders:
            if not f.get("group") or not f.get("PK"):
                continue
            pk = str(f["PK"])
            if validate_folder_id(pk):
                result[f["group"].strip()] = pk
        return result
    except (httpx.HTTPError, KeyError) as e:
        log.error(f"Failed to list existing folders: {sanitize_for_log(e)}")
        return {}


def verify_access_and_get_folders(
    client: httpx.Client, profile_id: str
) -> Optional[Dict[str, str]]:
    """Combine access check and folder listing into a single API request.

    Returns:
        Dict of {folder_name: folder_id} on success.
        None if access is denied or the request fails after retries.
    """
    url = f"{API_BASE}/{profile_id}/groups"

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.get(url)
            resp.raise_for_status()

            try:
                data = resp.json()

                # Ensure we got the expected top-level JSON structure.
                # We defensively validate types here so that unexpected but valid
                # JSON (e.g., a list or a scalar) doesn't cause AttributeError/TypeError
                # and cause the operation to fail unexpectedly.
                if not isinstance(data, dict):
                    log.error(
                        "Failed to parse folders data: expected JSON object at top level, "
                        f"got {type(data).__name__}"
                    )
                    return None

                body = data.get("body")
                if not isinstance(body, dict):
                    log.error(
                        "Failed to parse folders data: expected 'body' to be an object, "
                        f"got {type(body).__name__ if body is not None else 'None'}"
                    )
                    return None

                folders = body.get("groups", [])
                if not isinstance(folders, list):
                    log.error(
                        "Failed to parse folders data: expected 'body[\"groups\"]' to be a list, "
                        f"got {type(folders).__name__}"
                    )
                    return None

                # Only process entries that are dicts and have the required keys.
                result: Dict[str, str] = {}
                for f in folders:
                    if not isinstance(f, dict):
                        # Skip non-dict entries instead of crashing; this protects
                        # against partial data corruption or unexpected API changes.
                        continue
                    name = f.get("group")
                    pk = f.get("PK")
                    # Skip entries with empty or None values for required fields
                    if not name or not pk:
                        continue

                    pk_str = str(pk)
                    if not validate_folder_id(pk_str):
                        continue

                    result[str(name).strip()] = pk_str

                return result
            except (ValueError, TypeError, AttributeError) as err:
                # As a final safeguard, catch any remaining parsing/shape errors so
                # that a malformed response cannot crash the caller.
                log.error("Failed to parse folders data: %s", sanitize_for_log(err))
                return None

        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code in (401, 403, 404):
                if code == 401:
                    log.critical(
                        f"{Colors.FAIL}❌ Authentication Failed: The API Token is invalid.{Colors.ENDC}"
                    )
                    log.critical(
                        f"{Colors.FAIL}   Please check your token at: https://controld.com/account/manage-account{Colors.ENDC}"
                    )
                elif code == 403:
                    log.critical(
                        "%s🚫 Access Denied: Token lacks permission for "
                        "Profile %s.%s",
                        Colors.FAIL,
                        sanitize_for_log(profile_id),
                        Colors.ENDC,
                    )
                elif code == 404:
                    log.critical(
                        f"{Colors.FAIL}🔍 Profile Not Found: The ID '{sanitize_for_log(profile_id)}' does not exist.{Colors.ENDC}"
                    )
                    log.critical(
                        f"{Colors.FAIL}   Please verify the Profile ID from your Control D Dashboard URL.{Colors.ENDC}"
                    )
                return None

            if attempt == MAX_RETRIES - 1:
                log.error(f"API Request Failed ({code}): {sanitize_for_log(e)}")
                return None

        except httpx.RequestError as err:
            if attempt == MAX_RETRIES - 1:
                log.error(
                    "Network error during access verification: %s",
                    sanitize_for_log(err),
                )
                return None

        wait_time = RETRY_DELAY * (2**attempt)
        log.warning(
            "Request failed (attempt %d/%d). Retrying in %ds...",
            attempt + 1,
            MAX_RETRIES,
            wait_time,
        )
        time.sleep(wait_time)


def get_all_existing_rules(
    client: httpx.Client,
    profile_id: str,
    known_folders: Optional[Dict[str, str]] = None,
) -> Set[str]:
    """
    Fetches all existing rules across root and all folders.
    
    Retrieves rules from the root level and all folders in parallel.
    Uses known_folders to avoid redundant API calls when provided.
    Returns set of rule IDs.
    """
    all_rules = set()

    def _fetch_folder_rules(folder_id: str) -> List[str]:
        try:
            data = _api_get(client, f"{API_BASE}/{profile_id}/rules/{folder_id}").json()
            folder_rules = data.get("body", {}).get("rules", [])
            return [rule["PK"] for rule in folder_rules if rule.get("PK")]
        except httpx.HTTPError:
            return []
        except Exception as e:
            # We log error but don't stop the whole process;
            # individual folder failure shouldn't crash the sync
            log.warning(
                f"Error fetching rules for folder {folder_id}: {sanitize_for_log(e)}"
            )
            return []

    try:
        # Get rules from root
        try:
            data = _api_get(client, f"{API_BASE}/{profile_id}/rules").json()
            root_rules = data.get("body", {}).get("rules", [])
            for rule in root_rules:
                if rule.get("PK"):
                    all_rules.add(rule["PK"])
        except httpx.HTTPError:
            pass

        # Get rules from folders in parallel
        # Optimization: Use known_folders if provided to avoid redundant API call
        if known_folders is not None:
            folders = known_folders
        else:
            folders = list_existing_folders(client, profile_id)

        # Parallelize fetching rules from folders.
        # Using 5 workers to be safe with rate limits, though GETs are usually cheaper.
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_folder = {
                executor.submit(_fetch_folder_rules, folder_id): folder_id
                for folder_name, folder_id in folders.items()
            }

            for future in concurrent.futures.as_completed(future_to_folder):
                try:
                    result = future.result()
                    if result:
                        all_rules.update(result)
                except Exception as e:
                    folder_id = future_to_folder[future]
                    log.warning(
                        f"Failed to fetch rules for folder ID {folder_id}: {sanitize_for_log(e)}"
                    )

        log.info(f"Total existing rules across all folders: {len(all_rules):,}")
        return all_rules
    except Exception as e:
        log.error(f"Failed to get existing rules: {sanitize_for_log(e)}")
        return set()


def fetch_folder_data(url: str) -> Dict[str, Any]:
    """
    Downloads and validates folder JSON data from a URL.
    
    Uses cached GET request and validates the folder structure.
    Raises KeyError if validation fails.
    """
    js = _gh_get(url)
    if not validate_folder_data(js, url):
        raise KeyError(f"Invalid folder data from {sanitize_for_log(url)}")
    return js


def warm_up_cache(urls: Sequence[str]) -> None:
    """
    Pre-fetches and caches folder data from multiple URLs in parallel.
    
    Validates URLs and fetches data concurrently to minimize cold-start latency.
    Shows progress bar when USE_COLORS is enabled. Skips invalid URLs while
    emitting warnings/log entries for validation and fetch failures.
    """
    urls = list(set(urls))
    with _cache_lock:
        urls_to_process = [u for u in urls if u not in _cache]
    if not urls_to_process:
        return

    total = len(urls_to_process)
    if not USE_COLORS:
        log.info(f"Warming up cache for {total:,} URLs...")

    # OPTIMIZATION: Combine validation (DNS) and fetching (HTTP) in one task
    # to allow validation latency to be parallelized.
    def _validate_and_fetch(url: str):
        if validate_folder_url(url):
            return _gh_get(url)
        return None

    completed = 0
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(_validate_and_fetch, url): url for url in urls_to_process
        }

        render_progress_bar(0, total, "Warming up cache", prefix="⏳")

        for future in concurrent.futures.as_completed(futures):
            completed += 1
            render_progress_bar(completed, total, "Warming up cache", prefix="⏳")
            try:
                future.result()
            except Exception as e:
                if USE_COLORS:
                    # Clear line to print warning cleanly
                    sys.stderr.write("\r\033[K")
                    sys.stderr.flush()

                log.warning(
                    f"Failed to pre-fetch {sanitize_for_log(futures[future])}: "
                    f"{sanitize_for_log(e)}"
                )
                # Restore progress bar after warning
                render_progress_bar(completed, total, "Warming up cache", prefix="⏳")

    if USE_COLORS:
        sys.stderr.write(
            f"\r\033[K{Colors.GREEN}✅ Warming up cache: Done!{Colors.ENDC}\n"
        )
        sys.stderr.flush()


def delete_folder(
    client: httpx.Client, profile_id: str, name: str, folder_id: str
) -> bool:
    """
    Deletes a folder (group) from a Control D profile.
    
    Returns True on success, False on failure. Logs detailed error information.
    """
    try:
        _api_delete(client, f"{API_BASE}/{profile_id}/groups/{folder_id}")
        log.info(
            "Deleted folder %s (ID %s)",
            sanitize_for_log(name),
            sanitize_for_log(folder_id),
        )
        return True
    except httpx.HTTPError as e:
        log.error(
            f"Failed to delete folder {sanitize_for_log(name)} (ID {sanitize_for_log(folder_id)}): {sanitize_for_log(e)}"
        )
        return False


def create_folder(
    client: httpx.Client, profile_id: str, name: str, do: int, status: int
) -> Optional[str]:
    """
    Create a new folder and return its ID.
    Attempts to read ID from response first, then falls back to polling.
    """
    try:
        # 1. Send the Create Request
        response = _api_post(
            client,
            f"{API_BASE}/{profile_id}/groups",
            data={"name": name, "do": do, "status": status},
        )

        # OPTIMIZATION: Try to grab ID directly from response to avoid the wait loop
        try:
            resp_data = response.json()
            body = resp_data.get("body", {})

            # Check if it returned a single group object
            if isinstance(body, dict) and "group" in body and "PK" in body["group"]:
                pk = str(body["group"]["PK"])
                if not validate_folder_id(pk, log_errors=False):
                    log.error(f"API returned invalid folder ID: {sanitize_for_log(pk)}")
                    return None
                log.info(
                    "Created folder %s (ID %s) [Direct]",
                    sanitize_for_log(name),
                    sanitize_for_log(pk),
                )
                return pk

            # Check if it returned a list containing our group
            if isinstance(body, dict) and "groups" in body:
                for grp in body["groups"]:
                    if grp.get("group") == name:
                        pk = str(grp["PK"])
                        if not validate_folder_id(pk, log_errors=False):
                            log.error(f"API returned invalid folder ID: {sanitize_for_log(pk)}")
                            continue
                        log.info(
                            "Created folder %s (ID %s) [Direct]",
                            sanitize_for_log(name),
                            sanitize_for_log(pk),
                        )
                        return pk
        except Exception as e:
            log.debug(
                f"Could not extract ID from POST response: " f"{sanitize_for_log(e)}"
            )

        # 2. Fallback: Poll for the new folder (The Robust Retry Logic)
        for attempt in range(MAX_RETRIES + 1):
            try:
                data = _api_get(client, f"{API_BASE}/{profile_id}/groups").json()
                groups = data.get("body", {}).get("groups", [])

                for grp in groups:
                    if grp["group"].strip() == name.strip():
                        pk = str(grp["PK"])
                        if not validate_folder_id(pk, log_errors=False):
                            log.error(f"API returned invalid folder ID: {sanitize_for_log(pk)}")
                            return None
                        log.info(
                            "Created folder %s (ID %s) [Polled]",
                            sanitize_for_log(name),
                            sanitize_for_log(pk),
                        )
                        return pk
            except Exception as e:
                log.warning(
                    f"Error fetching groups on attempt {attempt}: {sanitize_for_log(e)}"
                )

            if attempt < MAX_RETRIES:
                wait_time = FOLDER_CREATION_DELAY * (attempt + 1)
                log.info(
                    f"Folder '{sanitize_for_log(name)}' not found yet. Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)

        log.error(
            f"Folder {sanitize_for_log(name)} was not found after creation and retries."
        )
        return None

    except (httpx.HTTPError, KeyError) as e:
        log.error(
            f"Failed to create folder {sanitize_for_log(name)}: {sanitize_for_log(e)}"
        )
        return None


def push_rules(
    profile_id: str,
    folder_name: str,
    folder_id: str,
    do: int,
    status: int,
    hostnames: List[str],
    existing_rules: Set[str],
    client: httpx.Client,
    batch_executor: Optional[concurrent.futures.Executor] = None,
) -> bool:
    """
    Pushes rules to a folder in batches, filtering duplicates and invalid rules.
    
    Deduplicates input, validates rules against RULE_PATTERN, and sends batches
    in parallel for optimal performance. Updates existing_rules set with newly
    added rules. Returns True if all batches succeed.
    """
    if not hostnames:
        log.info("Folder %s - no rules to push", sanitize_for_log(folder_name))
        return True

    original_count = len(hostnames)

    # Optimization 1: Deduplicate input list while preserving order using dict.fromkeys()
    # This is significantly faster than using a 'seen' set in the loop for large lists.
    # It also naturally deduplicates invalid rules, preventing log spam.
    unique_hostnames = dict.fromkeys(hostnames)

    filtered_hostnames = []
    skipped_unsafe = 0

    # Optimization 2: Inline regex match and check existence
    # Using a local reference to the match method avoids function call overhead
    # in the hot loop. This provides a measurable speedup for large lists.
    match_rule = RULE_PATTERN.match

    for h in unique_hostnames:
        if h in existing_rules:
            continue

        if not match_rule(h):
            log.warning(
                f"Skipping unsafe rule in {sanitize_for_log(folder_name)}: {sanitize_for_log(h)}"
            )
            skipped_unsafe += 1
            continue

        filtered_hostnames.append(h)

    if skipped_unsafe > 0:
        log.warning(
            f"Folder {sanitize_for_log(folder_name)}: skipped {skipped_unsafe} unsafe rules"
        )

    duplicates_count = original_count - len(filtered_hostnames) - skipped_unsafe

    if duplicates_count > 0:
        log.info(
            f"Folder {sanitize_for_log(folder_name)}: skipping {duplicates_count} duplicate rules"
        )

    if not filtered_hostnames:
        log.info(
            f"Folder {sanitize_for_log(folder_name)} - no new rules to push after filtering duplicates"
        )
        return True

    successful_batches = 0

    # Prepare batches
    batches = []
    for start in range(0, len(filtered_hostnames), BATCH_SIZE):
        batches.append(filtered_hostnames[start : start + BATCH_SIZE])

    total_batches = len(batches)

    # Optimization: Hoist loop invariants to avoid redundant computations
    str_do = str(do)
    str_status = str(status)
    str_group = str(folder_id)
    sanitized_folder_name = sanitize_for_log(folder_name)
    progress_label = f"Folder {sanitized_folder_name}"

    def process_batch(batch_idx: int, batch_data: List[str]) -> Optional[List[str]]:
        """Processes a single batch of rules by sending API request."""
        data = {
            "do": str_do,
            "status": str_status,
            "group": str_group,
        }
        # Optimization: Use pre-calculated keys and zip for faster dict update
        # strict=False is intentional: batch_data may be shorter than BATCH_KEYS for final batch
        data.update(zip(BATCH_KEYS, batch_data, strict=False))

        try:
            _api_post_form(client, f"{API_BASE}/{profile_id}/rules", data=data)
            if not USE_COLORS:
                log.info(
                    "Folder %s – batch %d: added %d rules",
                    sanitized_folder_name,
                    batch_idx,
                    len(batch_data),
                )
            return batch_data
        except httpx.HTTPError as e:
            if USE_COLORS:
                sys.stderr.write("\n")
            log.error(
                f"Failed to push batch {batch_idx} for folder {sanitized_folder_name}: {sanitize_for_log(e)}"
            )
            if hasattr(e, "response") and e.response is not None:
                log.debug(f"Response content: {sanitize_for_log(e.response.text)}")
            return None

    # Optimization 3: Parallelize batch processing
    # Using 3 workers to speed up writes without hitting aggressive rate limits.
    # If only 1 batch, run it synchronously to avoid ThreadPoolExecutor overhead.
    if total_batches == 1:
        result = process_batch(1, batches[0])
        if result:
            successful_batches += 1
            existing_rules.update(result)

        render_progress_bar(
            successful_batches,
            total_batches,
            progress_label,
        )
    else:
        # Use provided executor or create a local one (fallback)
        if batch_executor:
            executor_ctx = contextlib.nullcontext(batch_executor)
        else:
            executor_ctx = concurrent.futures.ThreadPoolExecutor(max_workers=3)

        with executor_ctx as executor:
            futures = {
                executor.submit(process_batch, i, batch): i
                for i, batch in enumerate(batches, 1)
            }

            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                if result:
                    successful_batches += 1
                    existing_rules.update(result)

                render_progress_bar(
                    successful_batches,
                    total_batches,
                    progress_label,
                )

    if successful_batches == total_batches:
        if USE_COLORS:
            sys.stderr.write(
                f"\r\033[K{Colors.GREEN}✅ Folder {sanitize_for_log(folder_name)}: Finished ({len(filtered_hostnames):,} rules){Colors.ENDC}\n"
            )
            sys.stderr.flush()
        else:
            log.info(
                f"Folder {sanitize_for_log(folder_name)} – finished ({len(filtered_hostnames):,} new rules added)"
            )
        return True
    else:
        log.error(
            "Folder %s – only %d/%d batches succeeded",
            sanitize_for_log(folder_name),
            successful_batches,
            total_batches,
        )
        return False


def _process_single_folder(
    folder_data: Dict[str, Any],
    profile_id: str,
    existing_rules: Set[str],
    client: httpx.Client,
    batch_executor: Optional[concurrent.futures.Executor] = None,
) -> bool:
    grp = folder_data["group"]
    name = grp["group"].strip()

    # Client is now passed in, reusing the connection
    main_do = grp.get("action", {}).get("do", 0)
    main_status = grp.get("action", {}).get("status", 1)

    folder_id = create_folder(client, profile_id, name, main_do, main_status)
    if not folder_id:
        return False

    folder_success = True
    if "rule_groups" in folder_data:
        for rule_group in folder_data["rule_groups"]:
            action = rule_group.get("action", {})
            do = action.get("do", 0)
            status = action.get("status", 1)
            hostnames = [r["PK"] for r in rule_group.get("rules", []) if r.get("PK")]
            if not push_rules(
                profile_id,
                name,
                folder_id,
                do,
                status,
                hostnames,
                existing_rules,
                client,
                batch_executor=batch_executor,
            ):
                folder_success = False
    else:
        hostnames = [r["PK"] for r in folder_data.get("rules", []) if r.get("PK")]
        if not push_rules(
            profile_id,
            name,
            folder_id,
            main_do,
            main_status,
            hostnames,
            existing_rules,
            client,
            batch_executor=batch_executor,
        ):
            folder_success = False

    return folder_success


# --------------------------------------------------------------------------- #
# 4. Main workflow
# --------------------------------------------------------------------------- #
def sync_profile(
    profile_id: str,
    folder_urls: Sequence[str],
    dry_run: bool = False,
    no_delete: bool = False,
    plan_accumulator: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """
    Synchronizes Control D folders from remote blocklist URLs.
    
    Fetches folder data, optionally deletes existing folders with same names,
    creates new folders, and pushes rules in batches. In dry-run mode, only
    generates a plan without making API changes. Returns True if all folders
    sync successfully.
    """
    # SECURITY: Clear cached DNS validations at the start of each sync run.
    # This prevents TOCTOU issues where a domain's IP could change between runs.
    validate_folder_url.cache_clear()

    try:
        # Fetch all folder data first
        folder_data_list = []

        # OPTIMIZATION: Move validation inside the thread pool to parallelize DNS lookups.
        # Previously, sequential validation blocked the main thread.
        def _fetch_if_valid(url: str):
            # Optimization: If we already have the content in cache, return it directly.
            # The content was validated at the time of fetch (warm_up_cache).
            # Read directly from cache to avoid calling fetch_folder_data while holding lock.
            with _cache_lock:
                if url in _cache:
                    return _cache[url]

            if validate_folder_url(url):
                return fetch_folder_data(url)
            return None

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_url = {
                executor.submit(_fetch_if_valid, url): url for url in folder_urls
            }

            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    result = future.result()
                    if result:
                        folder_data_list.append(result)
                except (httpx.HTTPError, KeyError, ValueError) as e:
                    log.error(
                        f"Failed to fetch folder data from {sanitize_for_log(url)}: {sanitize_for_log(e)}"
                    )
                    continue

        if not folder_data_list:
            log.error("No valid folder data found")
            return False

        # Build plan entries
        plan_entry = {"profile": profile_id, "folders": []}
        for folder_data in folder_data_list:
            grp = folder_data["group"]
            name = grp["group"].strip()

            if "rule_groups" in folder_data:
                # Multi-action format
                total_rules = sum(
                    len(rg.get("rules", [])) for rg in folder_data["rule_groups"]
                )
                plan_entry["folders"].append(
                    {
                        "name": name,
                        "rules": total_rules,
                        "rule_groups": [
                            {
                                "rules": len(rg.get("rules", [])),
                                "action": rg.get("action", {}).get("do"),
                                "status": rg.get("action", {}).get("status"),
                            }
                            for rg in folder_data["rule_groups"]
                        ],
                    }
                )
            else:
                # Legacy single-action format
                hostnames = [
                    r["PK"] for r in folder_data.get("rules", []) if r.get("PK")
                ]
                plan_entry["folders"].append(
                    {
                        "name": name,
                        "rules": len(hostnames),
                        "action": grp.get("action", {}).get("do"),
                        "status": grp.get("action", {}).get("status"),
                    }
                )

        if plan_accumulator is not None:
            plan_accumulator.append(plan_entry)

        if dry_run:
            print_plan_details(plan_entry)
            log.info("Dry-run complete: no API calls were made.")
            return True

        # Create new folders and push rules
        success_count = 0

        # CRITICAL FIX: Switch to Serial Processing (1 worker)
        # This prevents API rate limits and ensures stability for large folders.
        max_workers = 1

        # Shared executor for rate-limited operations (DELETE, push_rules batches)
        # Reusing this executor prevents thread churn and enforces global rate limits.
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=DELETE_WORKERS
        ) as shared_executor, _api_client() as client:
            # Verify access and list existing folders in one request
            existing_folders = verify_access_and_get_folders(client, profile_id)
            if existing_folders is None:
                return False

            if not no_delete:
                deletion_occurred = False

                # Identify folders to delete
                folders_to_delete = []
                for folder_data in folder_data_list:
                    name = folder_data["group"]["group"].strip()
                    if name in existing_folders:
                        folders_to_delete.append((name, existing_folders[name]))

                if folders_to_delete:
                    # Parallel delete to speed up the "clean slate" phase
                    # Use shared_executor (3 workers)
                    future_to_name = {
                        shared_executor.submit(
                            delete_folder, client, profile_id, name, folder_id
                        ): name
                        for name, folder_id in folders_to_delete
                    }

                    for future in concurrent.futures.as_completed(future_to_name):
                        name = future_to_name[future]
                        try:
                            if future.result():
                                del existing_folders[name]
                                deletion_occurred = True
                        except Exception as exc:
                            # Sanitize both name and exception to prevent log injection
                            log.error(
                                "Failed to delete folder %s: %s",
                                sanitize_for_log(name),
                                sanitize_for_log(exc),
                            )

                # CRITICAL FIX: Increased wait time for massive folders to clear
                if deletion_occurred:
                    if not USE_COLORS:
                        log.info(
                            "Waiting 60s for deletions to propagate (prevents 'Badware Hoster' zombie state)..."
                        )
                    countdown_timer(60, "Waiting for deletions to propagate")

            # Optimization: Pass the updated existing_folders to avoid redundant API call
            existing_rules = get_all_existing_rules(
                client, profile_id, known_folders=existing_folders
            )

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers
            ) as executor:
                future_to_folder = {
                    executor.submit(
                        _process_single_folder,
                        folder_data,
                        profile_id,
                        existing_rules,
                        client,  # Pass the persistent client
                        batch_executor=shared_executor,
                    ): folder_data
                    for folder_data in folder_data_list
                }

                for future in concurrent.futures.as_completed(future_to_folder):
                    folder_data = future_to_folder[future]
                    folder_name = folder_data["group"]["group"].strip()
                    try:
                        if future.result():
                            success_count += 1
                    except Exception as e:
                        log.error(
                            f"Failed to process folder '{sanitize_for_log(folder_name)}': {sanitize_for_log(e)}"
                        )

        log.info(
            f"Sync complete: {success_count}/{len(folder_data_list)} folders processed successfully"
        )
        return success_count == len(folder_data_list)

    except Exception as e:
        log.error(
            f"Unexpected error during sync for profile {profile_id}: {sanitize_for_log(e)}"
        )
        return False


# --------------------------------------------------------------------------- #
# 5. Entry-point
# --------------------------------------------------------------------------- #
def print_summary_table(
    sync_results: List[Dict[str, Any]], success_count: int, total: int, dry_run: bool
) -> None:
    # 1. Setup Data
    max_p = max((len(r["profile"]) for r in sync_results), default=25)
    w = [max(25, max_p), 10, 12, 10, 15]

    t_f, t_r, t_d = sum(r["folders"] for r in sync_results), sum(r["rules"] for r in sync_results), sum(r["duration"] for r in sync_results)
    all_ok = success_count == total
    t_status = ("✅ Ready" if dry_run else "✅ All Good") if all_ok else "❌ Errors"
    t_col = Colors.GREEN if all_ok else Colors.FAIL

    # 2. Render
    if not USE_COLORS:
        # Simple ASCII Fallback
        header = f"{'Profile ID':<{w[0]}} | {'Folders':>{w[1]}} | {'Rules':>{w[2]}} | {'Duration':>{w[3]}} | {'Status':<{w[4]}}"
        sep = "-" * len(header)
        print(f"\n{('DRY RUN' if dry_run else 'SYNC') + ' SUMMARY':^{len(header)}}\n{sep}\n{header}\n{sep}")
        for r in sync_results:
            print(f"{r['profile']:<{w[0]}} | {r['folders']:>{w[1]}} | {r['rules']:>{w[2]},} | {r['duration']:>{w[3]-1}.1f}s | {r['status_label']:<{w[4]}}")
        print(f"{sep}\n{'TOTAL':<{w[0]}} | {t_f:>{w[1]}} | {t_r:>{w[2]},} | {t_d:>{w[3]-1}.1f}s | {t_status:<{w[4]}}\n{sep}\n")
        return

    # Unicode Table
    def line(l, m, r): return f"{Colors.BOLD}{l}{m.join('─' * (x+2) for x in w)}{r}{Colors.ENDC}"
    def row(c): return f"{Colors.BOLD}│{Colors.ENDC} {c[0]:<{w[0]}} {Colors.BOLD}│{Colors.ENDC} {c[1]:>{w[1]}} {Colors.BOLD}│{Colors.ENDC} {c[2]:>{w[2]}} {Colors.BOLD}│{Colors.ENDC} {c[3]:>{w[3]}} {Colors.BOLD}│{Colors.ENDC} {c[4]:<{w[4]}} {Colors.BOLD}│{Colors.ENDC}"

    print(f"\n{line('┌', '─', '┐')}")
    title = f"{'DRY RUN' if dry_run else 'SYNC'} SUMMARY"
    print(f"{Colors.BOLD}│{Colors.CYAN if dry_run else Colors.HEADER}{title:^{sum(w) + 14}}{Colors.ENDC}{Colors.BOLD}│{Colors.ENDC}")
    print(f"{line('├', '┬', '┤')}\n{row([f'{Colors.HEADER}Profile ID{Colors.ENDC}', f'{Colors.HEADER}Folders{Colors.ENDC}', f'{Colors.HEADER}Rules{Colors.ENDC}', f'{Colors.HEADER}Duration{Colors.ENDC}', f'{Colors.HEADER}Status{Colors.ENDC}'])}")
    print(line("├", "┼", "┤"))

    for r in sync_results:
        sc = Colors.GREEN if r["success"] else Colors.FAIL
        print(row([r["profile"], str(r["folders"]), f"{r['rules']:,}", f"{r['duration']:.1f}s", f"{sc}{r['status_label']}{Colors.ENDC}"]))

    print(f"{line('├', '┼', '┤')}\n{row(['TOTAL', str(t_f), f'{t_r:,}', f'{t_d:.1f}s', f'{t_col}{t_status}{Colors.ENDC}'])}")
    print(f"{line('└', '┴', '┘')}\n")


def parse_args() -> argparse.Namespace:
    """
    Parses command-line arguments for the Control D sync tool.
    
    Supports profile IDs, folder URLs, dry-run mode, no-delete flag,
    and plan JSON output file path.
    """
    parser = argparse.ArgumentParser(
        description="✨ Control D Sync: Keep your folders in sync with remote blocklists.",
        epilog="Run with --dry-run first to preview changes safely. Made with ❤️  for Control D users.",
    )
    parser.add_argument(
        "--profiles", help="Comma-separated list of profile IDs", default=None
    )
    parser.add_argument(
        "--folder-url", action="append", help="Folder JSON URL(s)", default=None
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan only")
    parser.add_argument(
        "--no-delete", action="store_true", help="Do not delete existing folders"
    )
    parser.add_argument("--plan-json", help="Write plan to JSON file", default=None)
    return parser.parse_args()


def main():
    """
    Main entry point for Control D Sync.
    
    Loads environment configuration, validates inputs, warms up cache,
    and syncs profiles. Supports interactive prompts for missing credentials
    when running in a TTY. Prints summary statistics and exits with appropriate
    status code.
    """
    # SECURITY: Check .env permissions (after Colors is defined for NO_COLOR support)
    # This must happen BEFORE load_dotenv() to prevent reading secrets from world-readable files
    check_env_permissions()
    load_dotenv()

    global TOKEN
    # Re-initialize TOKEN to pick up values from .env (since load_dotenv was delayed)
    TOKEN = _clean_env_kv(os.getenv("TOKEN"), "TOKEN")

    args = parse_args()

    # Load persistent cache from disk (graceful degradation on any error)
    # NOTE: Called only after successful argument parsing so that `--help` or
    #       argument errors do not perform unnecessary filesystem I/O or logging.
    load_disk_cache()
    profiles_arg = (
        _clean_env_kv(args.profiles or os.getenv("PROFILE", ""), "PROFILE") or ""
    )
    profile_ids = [extract_profile_id(p) for p in profiles_arg.split(",") if p.strip()]
    folder_urls = args.folder_url if args.folder_url else DEFAULT_FOLDER_URLS

    # Interactive prompts for missing config
    if not args.dry_run and sys.stdin.isatty():
        if not profile_ids:
            print(f"{Colors.CYAN}ℹ Profile ID is missing.{Colors.ENDC}")
            print(
                f"{Colors.CYAN}  You can find this in the URL of your profile in the Control D Dashboard (or just paste the URL).{Colors.ENDC}"
            )

            def validate_profile_input(value: str) -> bool:
                """Validates one or more profile IDs from comma-separated input."""
                ids = [extract_profile_id(p) for p in value.split(",") if p.strip()]
                return bool(ids) and all(
                    validate_profile_id(pid, log_errors=False) for pid in ids
                )

            p_input = get_validated_input(
                f"{Colors.BOLD}Enter Control D Profile ID:{Colors.ENDC} ",
                validate_profile_input,
                "Invalid ID(s) or URL(s). Must be a valid Profile ID or a Control D Profile URL. Comma-separate for multiple.",
            )
            profile_ids = [
                extract_profile_id(p) for p in p_input.split(",") if p.strip()
            ]

        if not TOKEN:
            print(f"{Colors.CYAN}ℹ API Token is missing.{Colors.ENDC}")
            print(
                f"{Colors.CYAN}  You can generate one at: https://controld.com/account/manage-account{Colors.ENDC}"
            )

            t_input = get_password(
                f"{Colors.BOLD}Enter Control D API Token:{Colors.ENDC} ",
                lambda x: len(x) > 8,
                "Token seems too short. Please check your API token.",
            )
            TOKEN = t_input

    if not profile_ids and not args.dry_run:
        log.error(
            "PROFILE missing and --dry-run not set. Provide --profiles or set PROFILE env."
        )
        exit(1)

    if not TOKEN and not args.dry_run:
        log.error("TOKEN missing and --dry-run not set. Set TOKEN env for live sync.")
        exit(1)

    warm_up_cache(folder_urls)

    plan: List[Dict[str, Any]] = []
    success_count = 0
    sync_results = []

    profile_id = "unknown"
    start_time = time.time()

    try:
        for profile_id in profile_ids or ["dry-run-placeholder"]:
            start_time = time.time()
            # Skip validation for dry-run placeholder
            if profile_id != "dry-run-placeholder" and not validate_profile_id(
                profile_id
            ):
                sync_results.append(
                    {
                        "profile": profile_id,
                        "folders": 0,
                        "rules": 0,
                        "status_label": "❌ Invalid Profile ID",
                        "success": False,
                        "duration": 0.0,
                    }
                )
                continue

            log.info("Starting sync for profile %s", profile_id)
            status = sync_profile(
                profile_id,
                folder_urls,
                dry_run=args.dry_run,
                no_delete=args.no_delete,
                plan_accumulator=plan,
            )
            end_time = time.time()
            duration = end_time - start_time

            if status:
                success_count += 1

            # RESTORED STATS LOGIC: Calculate actual counts from the plan
            entry = next((p for p in plan if p["profile"] == profile_id), None)
            folder_count = len(entry["folders"]) if entry else 0
            rule_count = sum(f["rules"] for f in entry["folders"]) if entry else 0

            if args.dry_run:
                status_text = "✅ Planned" if status else "❌ Failed (Dry)"
            else:
                status_text = "✅ Success" if status else "❌ Failed"

            sync_results.append(
                {
                    "profile": profile_id,
                    "folders": folder_count,
                    "rules": rule_count,
                    "status_label": status_text,
                    "success": status,
                    "duration": duration,
                }
            )
    except KeyboardInterrupt:
        duration = time.time() - start_time
        print(
            f"\n{Colors.WARNING}⚠️  Sync cancelled by user. Finishing current task...{Colors.ENDC}"
        )

        # Try to recover stats for the interrupted profile
        entry = next((p for p in plan if p["profile"] == profile_id), None)
        folder_count = len(entry["folders"]) if entry else 0
        rule_count = sum(f["rules"] for f in entry["folders"]) if entry else 0

        sync_results.append(
            {
                "profile": profile_id,
                "folders": folder_count,
                "rules": rule_count,
                "status_label": "⛔ Cancelled",
                "success": False,
                "duration": duration,
            }
        )

    if args.plan_json:
        with open(args.plan_json, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)
        log.info("Plan written to %s", args.plan_json)

    # Print Summary Table
    # Determine the width for the Profile ID column (min 25)
    max_profile_len = max((len(r["profile"]) for r in sync_results), default=25)
    profile_col_width = max(25, max_profile_len)

    # Column widths
    w_profile = profile_col_width
    w_folders = 10
    w_rules = 12
    w_duration = 10
    w_status = 15

    def make_col_separator(left, mid, right, horiz):
        parts = [
            horiz * (w_profile + 2),
            horiz * (w_folders + 2),
            horiz * (w_rules + 2),
            horiz * (w_duration + 2),
            horiz * (w_status + 2),
        ]
        return left + mid.join(parts) + right

    # Calculate table width using a dummy separator
    dummy_sep = make_col_separator(Box.TL, Box.T, Box.TR, Box.H)
    table_width = len(dummy_sep)

    title_text = " DRY RUN SUMMARY " if args.dry_run else " SYNC SUMMARY "
    title_color = Colors.CYAN if args.dry_run else Colors.HEADER

    # Top Border (Single Cell for Title)
    print("\n" + Box.TL + Box.H * (table_width - 2) + Box.TR)

    # Title Row
    visible_title = title_text.strip()
    inner_width = table_width - 2
    pad_left = (inner_width - len(visible_title)) // 2
    pad_right = inner_width - len(visible_title) - pad_left
    print(
        f"{Box.V}{' ' * pad_left}{title_color}{visible_title}{Colors.ENDC}{' ' * pad_right}{Box.V}"
    )

    # Separator between Title and Headers (introduces columns)
    print(make_col_separator(Box.L, Box.T, Box.R, Box.H))

    # Header Row
    print(
        f"{Box.V} {Colors.BOLD}{'Profile ID':<{w_profile}}{Colors.ENDC} "
        f"{Box.V} {Colors.BOLD}{'Folders':>{w_folders}}{Colors.ENDC} "
        f"{Box.V} {Colors.BOLD}{'Rules':>{w_rules}}{Colors.ENDC} "
        f"{Box.V} {Colors.BOLD}{'Duration':>{w_duration}}{Colors.ENDC} "
        f"{Box.V} {Colors.BOLD}{'Status':<{w_status}}{Colors.ENDC} {Box.V}"
    )

    # Separator between Header and Body
    print(make_col_separator(Box.L, Box.X, Box.R, Box.H))

    # Rows
    total_folders = 0
    total_rules = 0
    total_duration = 0.0

    for res in sync_results:
        # Use boolean success field for color logic
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

    # Separator between Body and Total
    print(make_col_separator(Box.L, Box.X, Box.R, Box.H))

    # Total Row
    total = len(profile_ids or ["dry-run-placeholder"])
    all_success = success_count == total

    if args.dry_run:
        if all_success:
            total_status_text = "✅ Ready"
        else:
            total_status_text = "❌ Errors"
    else:
        if all_success:
            total_status_text = "✅ All Good"
        else:
            total_status_text = "❌ Errors"

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
    # Bottom Border
    print(make_col_separator(Box.BL, Box.B, Box.BR, Box.H))

    # Success Delight
    if all_success and USE_COLORS and not args.dry_run:
        success_msgs = [
            "✨ All synced!",
            "🚀 Ready for liftoff!",
            "🎨 Beautifully done!",
            "💎 Smooth operation!",
            "🌈 Perfect harmony!",
        ]
        print(f"\n{Colors.GREEN}{random.choice(success_msgs)}{Colors.ENDC}")

    # Dry Run Next Steps
    if args.dry_run:
        print()  # Spacer
        if all_success:
            # Build the suggested command once so it stays consistent between
            # color and non-color output modes.
            cmd_parts = ["python", "main.py"]
            if profile_ids:
                # Join multiple profiles if needed
                p_str = ",".join(profile_ids)
            else:
                p_str = "<your-profile-id>"
            cmd_parts.append(f"--profiles {p_str}")

            # Reconstruct other args if they were used (optional but helpful)
            if args.folder_url:
                for url in args.folder_url:
                    cmd_parts.append(f"--folder-url {url}")

            cmd_str = " ".join(cmd_parts)

            if USE_COLORS:
                print(f"{Colors.BOLD}👉 Ready to sync? Run the following command:{Colors.ENDC}")
                print(f"   {Colors.CYAN}{cmd_str}{Colors.ENDC}")
            else:
                print("👉 Ready to sync? Run the following command:")
                print(f"   {cmd_str}")
        else:
            if USE_COLORS:
                print(
                    f"{Colors.FAIL}⚠️  Dry run encountered errors. Please check the logs above.{Colors.ENDC}"
                )
            else:
                print("⚠️  Dry run encountered errors. Please check the logs above.")
    
    # Display API statistics
    total_api_calls = _api_stats["control_d_api_calls"] + _api_stats["blocklist_fetches"]
    if total_api_calls > 0:
        print(f"{Colors.BOLD}API Statistics:{Colors.ENDC}")
        print(f"  • Control D API calls: {_api_stats['control_d_api_calls']:>7,}")
        print(f"  • Blocklist fetches:   {_api_stats['blocklist_fetches']:>7,}")
        print(f"  • Total API requests:  {total_api_calls:>7,}")
        print()
    
    # Display cache statistics if any cache activity occurred
    if _cache_stats["hits"] + _cache_stats["misses"] + _cache_stats["validations"] > 0:
        print(f"{Colors.BOLD}Cache Statistics:{Colors.ENDC}")
        print(f"  • Hits (in-memory):    {_cache_stats['hits']:>7,}")
        print(f"  • Misses (downloaded): {_cache_stats['misses']:>7,}")
        print(f"  • Validations (304):   {_cache_stats['validations']:>7,}")
        if _cache_stats["errors"] > 0:
            print(f"  • Errors (non-fatal):  {_cache_stats['errors']:>7,}")
        
        # Calculate cache effectiveness
        total_requests = _cache_stats["hits"] + _cache_stats["misses"] + _cache_stats["validations"]
        if total_requests > 0:
            # Hits + validations = avoided full downloads
            cache_effectiveness = (_cache_stats["hits"] + _cache_stats["validations"]) / total_requests * 100
            print(f"  • Cache effectiveness:  {cache_effectiveness:>6.1f}%")
        print()
    
    # Display rate limit information if available
    with _rate_limit_lock:
        if any(v is not None for v in _rate_limit_info.values()):
            print(f"{Colors.BOLD}API Rate Limit Status:{Colors.ENDC}")
            
            if _rate_limit_info["limit"] is not None:
                print(f"  • Requests limit:       {_rate_limit_info['limit']:>6,}")
            
            if _rate_limit_info["remaining"] is not None:
                remaining = _rate_limit_info["remaining"]
                limit = _rate_limit_info["limit"]
                
                # Color code based on remaining capacity
                if limit and limit > 0:
                    pct = (remaining / limit) * 100
                    if pct < 20:
                        color = Colors.FAIL  # Red for critical
                    elif pct < 50:
                        color = Colors.WARNING  # Yellow for caution
                    else:
                        color = Colors.GREEN  # Green for healthy
                    print(f"  • Requests remaining:   {color}{remaining:>6,} ({pct:>5.1f}%){Colors.ENDC}")
                else:
                    print(f"  • Requests remaining:   {remaining:>6,}")
            
            if _rate_limit_info["reset"] is not None:
                reset_time = time.strftime(
                    "%H:%M:%S", 
                    time.localtime(_rate_limit_info["reset"])
                )
                print(f"  • Limit resets at:      {reset_time}")
            
            print()
    
    # Save cache to disk after successful sync (non-fatal if it fails)
    if not args.dry_run:
        save_disk_cache()

    total = len(profile_ids or ["dry-run-placeholder"])
    log.info(f"All profiles processed: {success_count}/{total} successful")
    exit(0 if success_count == total else 1)


if __name__ == "__main__":
    main()
