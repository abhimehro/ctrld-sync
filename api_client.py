"""
API client layer for Control D Sync.

Provides HTTP retry logic, rate-limit header tracking, and thin wrappers
around httpx calls.  Extracted from main.py to improve testability and make
it easier to add retry strategies or swap the HTTP library in the future.

**Dependency contract with main.py**
-------------------------------------
This module is intentionally free of imports from main.py to avoid circular
imports.  Instead, main.py injects the application's token-aware sanitization
function after it is defined::

    import api_client
    api_client._sanitize_fn = sanitize_for_log  # set once at module load

``_sanitize_fn`` defaults to ``str`` so that api_client is usable in
isolation (e.g., in unit tests that don't import main).  Any callable with
the signature ``(Any) -> str`` is accepted.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any
from collections.abc import Callable

import httpx
import contextlib

log = logging.getLogger(__name__)

__all__ = [
    "MAX_RETRIES",
    "RETRY_DELAY",
    "MAX_RETRY_DELAY",
    "retry_with_jitter",
    "_TIMEOUT_HINT",      # imported by main.py for use outside _retry_request
    "_CONNECT_ERROR_HINT",  # exported for reuse outside _retry_request
    "_SERVER_ERROR_HINT", # companion to _TIMEOUT_HINT; exported for use in main.py if needed
    "_4XX_HINTS",         # per-status client-error hints; imported by main.py as single source of truth
    "_api_stats",         # accessed by main.py for metrics reporting
    "_api_stats_lock",
    "_rate_limit_info",
    "_rate_limit_lock",
    "_sanitize_fn",       # injection point for token-aware sanitizer
    "_api_get",           # HTTP wrapper used by main.py
    "_api_delete",        # HTTP wrapper used by main.py
    "_api_post",          # HTTP wrapper used by main.py
    "_api_post_form",     # HTTP wrapper used by main.py
]

# --------------------------------------------------------------------------- #
# HTTP retry constants
# --------------------------------------------------------------------------- #
MAX_RETRIES = 10
RETRY_DELAY = 1
MAX_RETRY_DELAY = 60.0  # Maximum retry delay in seconds (caps exponential growth)

# Actionable guidance for network timeout errors (also imported by main.py for
# use in functions that don't go through _retry_request).
_TIMEOUT_HINT = "Connection timed out. Check your network and the Control D API status."

# Actionable guidance for transport-layer connection failures (DNS, refused, unreachable)
_CONNECT_ERROR_HINT = (
    "Connection failed. Check your network connection and DNS resolution, "
    "and verify the Control D API is reachable."
)

# Actionable guidance for 5xx server errors that are retried but may indicate an outage.
_SERVER_ERROR_HINT = (
    "Server error. The Control D API may be experiencing issues; "
    "check https://status.controld.com and try again later."
)

# Actionable guidance for 4xx client errors logged as warnings before re-raising
_4XX_HINTS: dict[int, str] = {
    401: "Check that your TOKEN environment variable is set and valid.",
    403: "Check that your API token has the required permissions for this profile.",
    404: "Check that the PROFILE or folder ID exists in your Control D account.",
}

# --------------------------------------------------------------------------- #
# Shared mutable state – in-place mutations keep importers' references live
# --------------------------------------------------------------------------- #

# API call statistics (used by main.py for the summary table)
_api_stats: dict[str, int] = {"control_d_api_calls": 0, "blocklist_fetches": 0}

# Rate-limit information parsed from API response headers
_rate_limit_info: dict[str, int | None] = {
    "limit": None,      # Max requests allowed per window (X-RateLimit-Limit)
    "remaining": None,  # Requests remaining in current window (X-RateLimit-Remaining)
    "reset": None,      # Timestamp when limit resets (X-RateLimit-Reset)
}

# Locks that protect the dicts above from concurrent writes
_api_stats_lock = threading.Lock()
_rate_limit_lock = threading.Lock()

# --------------------------------------------------------------------------- #
# Sanitisation hook — see module docstring for the injection contract.
# Defaults to str() so api_client.py is usable in isolation (e.g., tests).
# --------------------------------------------------------------------------- #
_sanitize_fn: Callable[[Any], str] = str
# --------------------------------------------------------------------------- #
# Rate-limit header parsing
# --------------------------------------------------------------------------- #

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
    headers = response.headers

    # Parse standard rate limit headers
    # These may not exist on all responses, so we check individually
    try:
        with _rate_limit_lock:
            # X-RateLimit-Limit: Total requests allowed per window
            if "X-RateLimit-Limit" in headers:
                with contextlib.suppress(ValueError, TypeError):
                    _rate_limit_info["limit"] = int(headers["X-RateLimit-Limit"])

            # X-RateLimit-Remaining: Requests left in current window
            if "X-RateLimit-Remaining" in headers:
                with contextlib.suppress(ValueError, TypeError):
                    _rate_limit_info["remaining"] = int(
                        headers["X-RateLimit-Remaining"]
                    )

            # X-RateLimit-Reset: Unix timestamp when window resets
            if "X-RateLimit-Reset" in headers:
                with contextlib.suppress(ValueError, TypeError):
                    _rate_limit_info["reset"] = int(headers["X-RateLimit-Reset"])

            # Log warnings when approaching rate limits
            # Only log if we have both limit and remaining values
            if (
                _rate_limit_info["limit"] is not None
                and _rate_limit_info["remaining"] is not None
            ):
                limit = _rate_limit_info["limit"]
                remaining = _rate_limit_info["remaining"]

                # Warn at 20% remaining capacity
                if limit > 0 and remaining / limit < 0.2:
                    if _rate_limit_info["reset"]:
                        reset_time = time.strftime(
                            "%H:%M:%S", time.localtime(_rate_limit_info["reset"])
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
        if log.isEnabledFor(logging.DEBUG):
            log.debug(f"Failed to parse rate limit headers: {e}")


# --------------------------------------------------------------------------- #
# Retry helpers
# --------------------------------------------------------------------------- #

def retry_with_jitter(
    attempt: int, base_delay: float = 1.0, max_delay: float = MAX_RETRY_DELAY
) -> float:
    """Calculate retry delay with exponential backoff and full jitter.

    Full jitter draws uniformly from [0, min(base_delay * 2^attempt, max_delay))
    to spread retries evenly across the full window and prevent thundering herd.

    Args:
        attempt: Retry attempt number (0-indexed)
        base_delay: Base delay in seconds (default: 1.0)
        max_delay: Maximum delay cap in seconds (default: MAX_RETRY_DELAY)

    Returns:
        Delay in seconds with full jitter applied
    """
    exponential_delay = min(base_delay * (2.0**attempt), max_delay)
    return exponential_delay * random.random()


def _retry_request(
    request_func: Callable[[], httpx.Response],
    max_retries: int = MAX_RETRIES,
    delay: float = RETRY_DELAY,
) -> httpx.Response:
    """
    Retry request with exponential backoff and full jitter.

    RETRY STRATEGY:
    - Uses retry_with_jitter() for full jitter: delay drawn from [0, min(delay*2^attempt, MAX_RETRY_DELAY)]
    - Full jitter prevents thundering herd when multiple clients fail simultaneously

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
                            raise  # Max retries exceeded
                        except ValueError:
                            # Retry-After might be HTTP date format, ignore for now
                            pass

                # Don't retry other 4xx errors (auth failures, bad requests, etc.)
                if 400 <= code < 500 and code != 429:
                    hint = _4XX_HINTS.get(code, "")
                    hint_suffix = f" | hint: {hint}" if hint else ""
                    log.warning(
                        f"API request failed with HTTP {code}{hint_suffix}: "
                        f"{_sanitize_fn(e)}"
                    )
                    if (
                        hasattr(e, "response")
                        and e.response is not None
                        and log.isEnabledFor(logging.DEBUG)
                    ):
                        log.debug(
                            f"Response content: {_sanitize_fn(e.response.text)}"
                        )
                    raise

            if attempt == max_retries - 1:
                if (
                    hasattr(e, "response")
                    and e.response is not None
                    and log.isEnabledFor(logging.DEBUG)
                ):
                    log.debug(f"Response content: {_sanitize_fn(e.response.text)}")
                raise

            # Full jitter exponential backoff: delay drawn from [0, min(delay * 2^attempt, MAX_RETRY_DELAY)]
            # Spreads retries evenly across the full window to prevent thundering herd
            wait_time = retry_with_jitter(attempt, base_delay=delay)

            if isinstance(e, httpx.TimeoutException):
                hint = f" | hint: {_TIMEOUT_HINT}"
            elif isinstance(e, httpx.ConnectError):
                hint = f" | hint: {_CONNECT_ERROR_HINT}"
            elif (
                isinstance(e, httpx.HTTPStatusError)
                and hasattr(e, "response")
                and e.response is not None
                and e.response.status_code >= 500
            ):
                # Server-side error hint for 5xx responses
                hint = f" | hint: {_SERVER_ERROR_HINT}"
            else:
                hint = ""
            log.warning(
                f"Request failed (attempt {attempt + 1}/{max_retries}): "
                f"{_sanitize_fn(e)}{hint}. Retrying in {wait_time:.2f}s..."
            )
            time.sleep(wait_time)

    raise RuntimeError("_retry_request called with max_retries=0")


# --------------------------------------------------------------------------- #
# Thin API call wrappers (increment stats counter then delegate to _retry_request)
# --------------------------------------------------------------------------- #

def _api_get(client: httpx.Client, url: str) -> httpx.Response:
    with _api_stats_lock:
        _api_stats["control_d_api_calls"] += 1
    return _retry_request(lambda: client.get(url))


def _api_delete(client: httpx.Client, url: str) -> httpx.Response:
    with _api_stats_lock:
        _api_stats["control_d_api_calls"] += 1
    return _retry_request(lambda: client.delete(url))


def _api_post(client: httpx.Client, url: str, data: dict) -> httpx.Response:
    with _api_stats_lock:
        _api_stats["control_d_api_calls"] += 1
    return _retry_request(lambda: client.post(url, data=data))


def _api_post_form(client: httpx.Client, url: str, data: dict) -> httpx.Response:
    with _api_stats_lock:
        _api_stats["control_d_api_calls"] += 1
    return _retry_request(
        lambda: client.post(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
    )
