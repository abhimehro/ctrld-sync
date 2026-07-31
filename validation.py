"""Validation, sanitization, and security helpers."""

from __future__ import annotations

import httpx
import ipaddress
import logging
import re
import socket
from functools import lru_cache
from typing import Any, TypeGuard

from models import FolderData

log = logging.getLogger(__name__)

PROFILE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
_PROFILE_URL_PATTERN = re.compile(r"controld\.com/dashboard/profiles/([^/?#\s]+)")

FOLDER_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+$")

_ALLOWED_RULE_CHARS = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_:*/@"
)

_DANGEROUS_FOLDER_CHARS = set("<>\"'`/\\")

MAX_FOLDER_NAME_LENGTH = 64
MAX_RULE_LENGTH = 255
MAX_PROFILE_ID_LENGTH = 64
MAX_FOLDER_ID_LENGTH = 64
MAX_URL_LENGTH = 2048
MAX_HOSTNAME_LENGTH = 253

DEFAULT_HTTP_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

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

_ALL_FORBIDDEN_FOLDER_CHARS = frozenset(_DANGEROUS_FOLDER_CHARS | _BIDI_CONTROL_CHARS)
_UNSAFE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

DEFAULT_ALLOWED_BLOCKLIST_DOMAINS: frozenset[str] = frozenset(
    {
        "raw.githubusercontent.com",
        "github.com",
        "yokoffing.github.io",
    }
)

_ALLOWED_BLOCKLIST_DOMAINS: frozenset[str] = DEFAULT_ALLOWED_BLOCKLIST_DOMAINS

_BASIC_AUTH_PATTERN = re.compile(r"://[^/@]+@")
_SENSITIVE_PARAM_PATTERN = re.compile(
    r"([?&#])(token|key|secret|password|auth|access_token|api_key|authorization)=[^&#\s]*",
    flags=re.IGNORECASE,
)

# Token-aware redaction state.  Set via set_token_for_redaction() from main.
_token: str = ""


def set_token_for_redaction(token: str | None) -> None:
    """Set the token value that sanitize_for_log will redact from output."""
    global _token
    _token = token or ""


def sanitize_for_log(text: Any) -> str:
    """Sanitize text for logging.

    Redacts:
    - TOKEN values
    - Basic Auth credentials in URLs (e.g. https://user:pass@host)
    - Sensitive query parameters (token, key, secret, password, auth, access_token, api_key)
    - Control characters (prevents log injection and terminal hijacking)
    """
    s = str(text)
    if _token and _token in s:
        s = s.replace(_token, "[REDACTED]")

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

_CGNAT_NETWORK = ipaddress.IPv4Network("100.64.0.0/10")

def _is_safe_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Rejects non-global, reserved, link-local, loopback, multicast, unspecified, and IPv4 CGNAT addresses."""
    if ip.is_multicast:
        return False
    if ip.is_unspecified:
        return False
    if ip.is_loopback:
        return False
    if ip.is_private:
        return False
    if ip.is_link_local:
        return False
    if ip.is_reserved:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        return _is_safe_ip(ip.ipv4_mapped)
    if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT_NETWORK:
        return False
    return ip.is_global

def _resolve_and_validate_domain(hostname: str) -> bool:
    try:
        # Resolve hostname to IPs (IPv4 and IPv6)
        # We filter for AF_INET/AF_INET6 to ensure we get IP addresses
        addr_info = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        for res in addr_info:
            # res is (family, type, proto, canonname, sockaddr)
            # sockaddr is (address, port) for AF_INET/AF_INET6
            ip_str = res[4][0]
            ip = ipaddress.ip_address(ip_str)
            if not _is_safe_ip(ip):
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
def validate_hostname(hostname: str) -> bool:
    """
    Validates a hostname (DNS resolution and IP checks).
    Cached to prevent redundant DNS lookups for the same host across different URLs.
    """
    if len(hostname) > MAX_HOSTNAME_LENGTH:
        log.warning(
            f"Skipping unsafe hostname (exceeds {MAX_HOSTNAME_LENGTH} chars): {sanitize_for_log(hostname)}"
        )
        return False

    # Check for potentially malicious hostnames
    if hostname.lower() in _UNSAFE_HOSTS:
        log.warning(
            f"Skipping unsafe hostname (localhost detected): {sanitize_for_log(hostname)}"
        )
        return False

    try:
        ip = ipaddress.ip_address(hostname)
        if not _is_safe_ip(ip):
            log.warning(f"Skipping unsafe IP: {sanitize_for_log(hostname)}")
            return False
        return True
    except ValueError:
        # Not an IP literal, it's a domain. Resolve and check IPs.
        return _resolve_and_validate_domain(hostname)

def _is_allowed_blocklist_domain(
    hostname: str, allowed_domains: frozenset[str]
) -> bool:
    if hostname in allowed_domains:
        return True
    parts = hostname.split(".")
    for i in range(  # noqa: SIM110 - optimization: any(generator) is slow
        1, len(parts)
    ):
        if ".".join(parts[i:]) in allowed_domains:
            return True
    return False

@lru_cache(maxsize=128)
def validate_folder_url(
    url: str, allowed_domains: frozenset[str] | None = None
) -> bool:
    """
    Validates a folder URL.
    Cached to avoid repeated URL parsing for the same URL.
    """
    if len(url) > MAX_URL_LENGTH:
        log.warning(
            f"Skipping unsafe URL (exceeds {MAX_URL_LENGTH} chars): {sanitize_for_log(url)}"
        )
        return False

    if not url.startswith("https://"):
        log.warning(
            f"Skipping unsafe or invalid URL (must be https): {sanitize_for_log(url)}"
        )
        return False

    try:
        parsed = httpx.URL(url)
        hostname = parsed.host
        if not hostname:
            return False

        domains_to_check = (
            allowed_domains
            if allowed_domains is not None
            else _ALLOWED_BLOCKLIST_DOMAINS
        )
        hostname = hostname.lower()
        if domains_to_check and not _is_allowed_blocklist_domain(
            hostname, domains_to_check
        ):
            log.warning(
                f"Skipping URL with non-allowlisted domain {sanitize_for_log(hostname)}: "
                f"{sanitize_for_log(url)}"
            )
            return False

        return validate_hostname(hostname)

    except Exception as e:
        log.warning(
            f"Failed to validate URL {sanitize_for_log(url)}: {sanitize_for_log(e)}"
        )
        return False

def set_allowed_blocklist_domains(domains: list[str] | None) -> None:
    """Set the runtime allowed blocklist domains for SSRF protection."""
    global _ALLOWED_BLOCKLIST_DOMAINS
    if domains and len(domains) > 0:
        _ALLOWED_BLOCKLIST_DOMAINS = frozenset(domain.lower() for domain in domains)
    else:
        _ALLOWED_BLOCKLIST_DOMAINS = DEFAULT_ALLOWED_BLOCKLIST_DOMAINS
    # validate_folder_url() is cached, so any allowlist change must clear it.
    validate_folder_url.cache_clear()

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
    match = _PROFILE_URL_PATTERN.search(text)
    if match:
        return match.group(1)
    return text

def is_valid_profile_id_format(profile_id: str) -> bool:
    """
    Checks if a profile ID matches the expected format.

    Validates against PROFILE_ID_PATTERN and enforces maximum length of 64 characters.
    """
    if "\x00" in profile_id:
        return False

    if len(profile_id) > MAX_PROFILE_ID_LENGTH:
        return False

    return bool(PROFILE_ID_PATTERN.match(profile_id))

def validate_profile_id(profile_id: str, log_errors: bool = True) -> bool:
    """
    Validates a Control D profile ID with optional error logging.

    Returns True if profile ID is valid, False otherwise.
    Logs specific validation errors when log_errors=True.
    """
    if is_valid_profile_id_format(profile_id):
        return True

    if not PROFILE_ID_PATTERN.match(profile_id):
        return _log_validation_error(
            "Invalid profile ID format (contains unsafe characters)", log_errors
        )

    if len(profile_id) > MAX_PROFILE_ID_LENGTH:
        return _log_validation_error(
            f"Invalid profile ID length (max {MAX_PROFILE_ID_LENGTH} chars)", log_errors
        )

    return False

def _log_validation_error(msg: str, log_errors: bool) -> bool:
    """Helper to conditionally log validation errors and return False."""
    if log_errors:
        log.error(msg)
    return False

def validate_folder_id(folder_id: str, log_errors: bool = True) -> bool:
    """Validates folder ID (PK) format to prevent path traversal."""
    if not folder_id:
        return False

    if len(folder_id) > MAX_FOLDER_ID_LENGTH:
        msg = f"Invalid folder ID length (max {MAX_FOLDER_ID_LENGTH} chars): {sanitize_for_log(folder_id)}"
        return _log_validation_error(msg, log_errors)

    if "\x00" in folder_id:
        msg = f"Invalid folder ID format (null byte): {sanitize_for_log(folder_id)}"
        return _log_validation_error(msg, log_errors)

    is_path_traversal = folder_id in (".", "..")
    is_invalid_format = not FOLDER_ID_PATTERN.match(folder_id)

    if is_path_traversal or is_invalid_format:
        msg = f"Invalid folder ID format: {sanitize_for_log(folder_id)}"
        return _log_validation_error(msg, log_errors)

    return True

def is_valid_rule(rule: str) -> bool:
    """
    Validates that a rule is safe to use.
    Enforces a strict whitelist of allowed characters.
    Allowed: Alphanumeric, hyphen, dot, underscore, asterisk, colon (IPv6), slash (CIDR)
    """
    if not rule:
        return False

    if len(rule) > MAX_RULE_LENGTH:
        return False

    # Strict whitelist to prevent injection
    return bool(rule) and _ALLOWED_RULE_CHARS.issuperset(rule)

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

    if len(name) > MAX_FOLDER_NAME_LENGTH:
        return False

    # Check for dangerous characters (pre-compiled at module level for performance)
    if not _ALL_FORBIDDEN_FOLDER_CHARS.isdisjoint(name):
        return False

    # Security: Block path traversal attempts
    # Check stripped name to prevent whitespace bypass (e.g. " . ")
    clean_name = name.strip()
    if clean_name in (".", ".."):
        return False

    # Security: Block command option injection (if name is passed to shell)
    return not clean_name.startswith("-")

def _is_valid_rule_list(rules_list: Any) -> bool:
    """Helper to quickly validate a list of rules without generator overhead."""
    if not isinstance(rules_list, list):
        return False
    for r in rules_list:
        if type(r) is not dict or (
            (pk := r.get("PK")) is not None and type(pk) is not str
        ):
            return False
    return True

def _log_invalid_rules(rules_list: list[Any], url: str, prefix: str) -> bool:
    """Helper to log specific validation errors for a list of rules.

    This is only called after the fast-path ``_is_valid_rule_list`` check has
    already determined the list is invalid, so we always return ``False``.
    The fallthrough case (no specific per-rule error matched) can occur when
    the fast-path uses strict ``type(...) is`` checks while this helper uses
    ``isinstance(...)`` — in that case we still return ``False`` to preserve
    the known-invalid verdict rather than accidentally accepting the data.
    """
    for j, rule in enumerate(rules_list):
        if not isinstance(rule, dict):
            log.error(
                f"Invalid data from {sanitize_for_log(url)}: {prefix}[{j}] must be an object."
            )
            return False
        if (pk := rule.get("PK")) is not None and not isinstance(pk, str):
            log.error(
                f"Invalid data from {sanitize_for_log(url)}: {prefix}[{j}].PK must be a string."
            )
            return False
    return False

def validate_folder_data(data: dict[str, Any], url: str) -> TypeGuard[FolderData]:
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

    # Validate 'rules' if present (must be a list of dicts with string PK values)
    if "rules" in data:
        if not isinstance(data["rules"], list):
            log.error(
                f"Invalid data from {sanitize_for_log(url)}: 'rules' must be a list."
            )
            return False

        # Optimization: Fast path inline type check avoids function call overhead per rule.
        # Fallback identifies the exact error for logging.
        rules_list = data["rules"]
        if not _is_valid_rule_list(rules_list):
            return _log_invalid_rules(rules_list, url, "rules")

    # Validate 'rule_groups' if present (must be a list of dicts)
    if "rule_groups" in data:
        if not isinstance(data["rule_groups"], list):
            log.error(
                f"Invalid data from {sanitize_for_log(url)}: 'rule_groups' must be a list."
            )
            return False
        for i, rg in enumerate(data["rule_groups"]):
            if not isinstance(rg, dict):
                log.error(
                    f"Invalid data from {sanitize_for_log(url)}: rule_groups[{i}] must be an object."
                )
                return False
            if "rules" in rg:
                if not isinstance(rg["rules"], list):
                    log.error(
                        f"Invalid data from {sanitize_for_log(url)}: rule_groups[{i}].rules must be a list."
                    )
                    return False

                # Ensure each rule within the group is an object (dict) and has a string PK,
                # because later code treats each rule as a mapping (e.g., rule.get(...)).
                rg_rules_list = rg["rules"]
                # Optimization: Fast path inline type check avoids function call overhead per rule.
                # Fallback identifies the exact error for logging.
                if not _is_valid_rule_list(rg_rules_list):
                    return _log_invalid_rules(
                        rg_rules_list, url, f"rule_groups[{i}].rules"
                    )

    return True


__all__ = ['sanitize_for_log', 'set_token_for_redaction', 'validate_hostname', 'validate_folder_url', 'set_allowed_blocklist_domains', 'extract_profile_id', 'is_valid_profile_id_format', 'validate_profile_id', 'validate_folder_id', 'is_valid_rule', 'is_valid_folder_name', 'validate_folder_data', 'DEFAULT_ALLOWED_BLOCKLIST_DOMAINS', 'MAX_RULE_LENGTH', '_ALLOWED_RULE_CHARS']
