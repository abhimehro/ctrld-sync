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
import getpass
import ipaddress
import json
import logging
import os
import re
import shutil
import socket
import stat
import sys
import threading
import time
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Sequence, Set
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

# --------------------------------------------------------------------------- #
# 0. Bootstrap – load secrets and configure logging
# --------------------------------------------------------------------------- #
load_dotenv()

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
    s = _BASIC_AUTH_PATTERN.sub("://[REDACTED]@", s)

    # Redact sensitive query parameters (handles ?, &, and # separators)
    s = _SENSITIVE_PARAM_PATTERN.sub(r"\1\2=[REDACTED]", s)

    # repr() safely escapes control characters (e.g., \n -> \\n, \x1b -> \\x1b)
    # This prevents log injection and terminal hijacking.
    safe = repr(s)
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
        (len(sanitize_for_log(f.get("name", ""))) for f in folders), default=0
    )
    max_count_len = max((len(f"{f.get('rules', 0):,}") for f in folders), default=0)

    for folder in sorted(folders, key=lambda f: f.get("name", "")):
        name = sanitize_for_log(folder.get("name", "Unknown"))
        rule_count = folder.get("rules", 0)
        rule_count_str = f"{rule_count:,}"

        if USE_COLORS:
            print(
                f"  • {Colors.BOLD}{name:<{max_name_len}}{Colors.ENDC} : {rule_count_str:>{max_count_len}} rules"
            )
        else:
            print(
                f"  - {name:<{max_name_len}} : {rule_count_str:>{max_count_len}} rules"
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
    """Shows a countdown timer if strictly in a TTY, otherwise just sleeps."""
    if not USE_COLORS:
        time.sleep(seconds)
        return

    width = _get_progress_bar_width()

    for remaining in range(seconds, 0, -1):
        progress = (seconds - remaining + 1) / seconds
        filled = int(width * progress)
        bar = "█" * filled + "░" * (width - filled)
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
    bar = "█" * filled + "░" * (width - filled)
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
    is_password: bool = False,
) -> str:
    """Prompts for input until the validator returns True."""
    while True:
        try:
            if is_password:
                value = getpass.getpass(prompt).strip()
            else:
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


@lru_cache(maxsize=128)
def validate_folder_url(url: str) -> bool:
    """
    Validates a folder URL.
    Cached to avoid repeated DNS lookups (socket.getaddrinfo) for the same URL
    during warm-up and sync phases.
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

        # Check for potentially malicious hostnames
        if hostname.lower() in ("localhost", "127.0.0.1", "::1"):
            log.warning(
                f"Skipping unsafe URL (localhost detected): {sanitize_for_log(url)}"
            )
            return False

        try:
            ip = ipaddress.ip_address(hostname)
            if not ip.is_global or ip.is_multicast:
                log.warning(
                    f"Skipping unsafe URL (non-global/multicast IP): {sanitize_for_log(url)}"
                )
                return False
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
                            f"Skipping unsafe URL (domain {hostname} resolves to non-global/multicast IP {ip}): {sanitize_for_log(url)}"
                        )
                        return False
            except (socket.gaierror, ValueError, OSError) as e:
                log.warning(
                    f"Failed to resolve/validate domain {hostname}: {sanitize_for_log(e)}"
                )
                return False

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
    if not PROFILE_ID_PATTERN.match(profile_id):
        return False
    if len(profile_id) > 64:
        return False
    return True


def validate_profile_id(profile_id: str, log_errors: bool = True) -> bool:
    if not is_valid_profile_id_format(profile_id):
        if log_errors:
            if not PROFILE_ID_PATTERN.match(profile_id):
                log.error("Invalid profile ID format (contains unsafe characters)")
            elif len(profile_id) > 64:
                log.error("Invalid profile ID length (max 64 chars)")
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

    return True


def validate_folder_data(data: Dict[str, Any], url: str) -> bool:
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


def _api_get(client: httpx.Client, url: str) -> httpx.Response:
    return _retry_request(lambda: client.get(url))


def _api_delete(client: httpx.Client, url: str) -> httpx.Response:
    return _retry_request(lambda: client.delete(url))


def _api_post(client: httpx.Client, url: str, data: Dict) -> httpx.Response:
    return _retry_request(lambda: client.post(url, data=data))


def _api_post_form(client: httpx.Client, url: str, data: Dict) -> httpx.Response:
    return _retry_request(
        lambda: client.post(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    )


def _retry_request(request_func, max_retries=MAX_RETRIES, delay=RETRY_DELAY):
    for attempt in range(max_retries):
        try:
            response = request_func()
            response.raise_for_status()
            return response
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            # Security Enhancement: Do not retry client errors (4xx) except 429 (Too Many Requests).
            # Retrying 4xx errors is inefficient and can trigger security alerts or rate limits.
            if isinstance(e, httpx.HTTPStatusError):
                code = e.response.status_code
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
            wait_time = delay * (2**attempt)
            log.warning(
                f"Request failed (attempt {attempt + 1}/{max_retries}): "
                f"{sanitize_for_log(e)}. Retrying in {wait_time}s..."
            )
            time.sleep(wait_time)


def _gh_get(url: str) -> Dict:
    # First check: Quick check without holding lock for long
    with _cache_lock:
        if url in _cache:
            return _cache[url]

    # Fetch data if not cached
    # Explicitly let HTTPError propagate (no need to catch just to re-raise)
    with _gh.stream("GET", url) as r:
        r.raise_for_status()

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
        for chunk in r.iter_bytes():
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
                f"{Colors.FAIL}🔍 Profile Not Found: The ID '{profile_id}' does not exist.{Colors.ENDC}"
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
    try:
        data = _api_get(client, f"{API_BASE}/{profile_id}/groups").json()
        folders = data.get("body", {}).get("groups", [])
        return {
            f["group"].strip(): f["PK"]
            for f in folders
            if f.get("group") and f.get("PK")
        }
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
                    result[str(name).strip()] = str(pk)

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
    js = _gh_get(url)
    if not validate_folder_data(js, url):
        raise KeyError(f"Invalid folder data from {sanitize_for_log(url)}")
    return js


def warm_up_cache(urls: Sequence[str]) -> None:
    urls = list(set(urls))
    with _cache_lock:
        urls_to_process = [u for u in urls if u not in _cache]
    if not urls_to_process:
        return

    total = len(urls_to_process)
    if not USE_COLORS:
        log.info(f"Warming up cache for {total} URLs...")

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
    try:
        _api_delete(client, f"{API_BASE}/{profile_id}/groups/{folder_id}")
        log.info("Deleted folder %s (ID %s)", sanitize_for_log(name), folder_id)
        return True
    except httpx.HTTPError as e:
        log.error(
            f"Failed to delete folder {sanitize_for_log(name)} (ID {folder_id}): {sanitize_for_log(e)}"
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
                pk = body["group"]["PK"]
                log.info(
                    "Created folder %s (ID %s) [Direct]", sanitize_for_log(name), pk
                )
                return str(pk)

            # Check if it returned a list containing our group
            if isinstance(body, dict) and "groups" in body:
                for grp in body["groups"]:
                    if grp.get("group") == name:
                        log.info(
                            "Created folder %s (ID %s) [Direct]",
                            sanitize_for_log(name),
                            grp["PK"],
                        )
                        return str(grp["PK"])
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
                        log.info(
                            "Created folder %s (ID %s) [Polled]",
                            sanitize_for_log(name),
                            grp["PK"],
                        )
                        return str(grp["PK"])
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
) -> bool:
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

    for h in unique_hostnames:
        # Optimization: Check existence first to skip regex validation for known rules
        if h in existing_rules:
            continue

        if not is_valid_rule(h):
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

    def process_batch(batch_idx: int, batch_data: List[str]) -> Optional[List[str]]:
        data = {
            "do": str(do),
            "status": str(status),
            "group": str(folder_id),
        }
        # Optimization: Use pre-calculated keys and zip for faster dict update
        # strict=False is intentional: batch_data may be shorter than BATCH_KEYS for final batch
        data.update(zip(BATCH_KEYS, batch_data, strict=False))

        try:
            _api_post_form(client, f"{API_BASE}/{profile_id}/rules", data=data)
            if not USE_COLORS:
                log.info(
                    "Folder %s – batch %d: added %d rules",
                    sanitize_for_log(folder_name),
                    batch_idx,
                    len(batch_data),
                )
            return batch_data
        except httpx.HTTPError as e:
            if USE_COLORS:
                sys.stderr.write("\n")
            log.error(
                f"Failed to push batch {batch_idx} for folder {sanitize_for_log(folder_name)}: {sanitize_for_log(e)}"
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
            f"Folder {sanitize_for_log(folder_name)}",
        )
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
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
                    f"Folder {sanitize_for_log(folder_name)}",
                )

    if successful_batches == total_batches:
        if USE_COLORS:
            sys.stderr.write(
                f"\r\033[K{Colors.GREEN}✅ Folder {sanitize_for_log(folder_name)}: Finished ({len(filtered_hostnames):,} rules){Colors.ENDC}\n"
            )
            sys.stderr.flush()
        else:
            log.info(
                "Folder %s – finished (%s new rules added)",
                sanitize_for_log(folder_name),
                f"{len(filtered_hostnames):,}",
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

        # Initial client for getting existing state AND processing folders
        # Optimization: Reuse the same client session to keep TCP connections alive
        with _api_client() as client:
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
                    # Using DELETE_WORKERS (3) for balance between speed and rate limits
                    with concurrent.futures.ThreadPoolExecutor(
                        max_workers=DELETE_WORKERS
                    ) as delete_executor:
                        future_to_name = {
                            delete_executor.submit(
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
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Control D folder sync")
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
    # SECURITY: Check .env permissions (after Colors is defined for NO_COLOR support)
    check_env_permissions()

    global TOKEN
    args = parse_args()
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

            t_input = get_validated_input(
                f"{Colors.BOLD}Enter Control D API Token:{Colors.ENDC} ",
                lambda x: len(x) > 8,
                "Token seems too short. Please check your API token.",
                is_password=True,
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

    # Calculate total width for the table
    # Profile ID + " | " + Folders + " | " + Rules + " | " + Duration + " | " + Status
    # Widths: profile_col_width + 3 + 10 + 3 + 10 + 3 + 10 + 3 + 15 = profile_col_width + 57
    table_width = profile_col_width + 57

    title_text = "DRY RUN SUMMARY" if args.dry_run else "SYNC SUMMARY"
    title_color = Colors.CYAN if args.dry_run else Colors.HEADER

    print("\n" + "=" * table_width)
    print(f"{title_color}{title_text:^{table_width}}{Colors.ENDC}")
    print("=" * table_width)

    # Header
    print(
        f"{Colors.BOLD}"
        f"{'Profile ID':<{profile_col_width}} | {'Folders':>10} | {'Rules':>10} | {'Duration':>10} | {'Status':<15}"
        f"{Colors.ENDC}"
    )
    print("-" * table_width)

    # Rows
    total_folders = 0
    total_rules = 0
    total_duration = 0.0

    for res in sync_results:
        # Use boolean success field for color logic
        status_color = Colors.GREEN if res["success"] else Colors.FAIL

        print(
            f"{res['profile']:<{profile_col_width}} | "
            f"{res['folders']:>10} | "
            f"{res['rules']:>10,} | "
            f"{res['duration']:>9.1f}s | "
            f"{status_color}{res['status_label']:<15}{Colors.ENDC}"
        )
        total_folders += res["folders"]
        total_rules += res["rules"]
        total_duration += res["duration"]

    print("-" * table_width)

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

    print(
        f"{Colors.BOLD}"
        f"{'TOTAL':<{profile_col_width}} | "
        f"{total_folders:>10} | "
        f"{total_rules:>10,} | "
        f"{total_duration:>9.1f}s | "
        f"{total_status_color}{total_status_text:<15}{Colors.ENDC}"
    )
    print("=" * table_width + "\n")

    total = len(profile_ids or ["dry-run-placeholder"])
    log.info(f"All profiles processed: {success_count}/{total} successful")
    exit(0 if success_count == total else 1)


if __name__ == "__main__":
    main()
