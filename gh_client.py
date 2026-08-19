"""GitHub / blocklist fetch client with in-memory and disk caching."""

from __future__ import annotations

import concurrent.futures
import itertools
import json
import logging
import threading
import time
from collections.abc import Sequence
from typing import Any, cast

import httpx

import config
from api_client import _api_stats
from cache import CACHE_TTL_SECONDS, _cache_stats, _disk_cache
from display import (
    USE_COLORS,
    _clear_current_line,
    _print_completion,
    pluralize,
    render_progress_bar,
)
from models import FolderData
from validation import sanitize_for_log, validate_folder_data, validate_folder_url

log = logging.getLogger(__name__)

_gh = httpx.Client(
    headers={"User-Agent": config.USER_AGENT},
    # SECURITY: Explicit timeouts prevent resource exhaustion/DoS via Slowloris
    timeout=httpx.Timeout(10.0, connect=5.0),
    follow_redirects=False,
)

_cache: dict[str, dict] = {}

_cache_lock = threading.RLock()


def _validate_url_or_raise(url: str) -> None:
    """Fail-closed SSRF guard: validate a blocklist URL before any network or cache use."""
    if not validate_folder_url(url):
        raise ValueError(f"Unsafe or invalid blocklist URL: {sanitize_for_log(url)}")


def _validate_content_type(url: str, r: httpx.Response) -> None:
    """Validate that the response Content-Type is acceptable for JSON bodies."""
    ct = r.headers.get("Content-Type", "").lower()
    if not any(t in ct for t in ("application/json", "text/json", "text/plain")):
        raise ValueError(
            f"Invalid Content-Type from {sanitize_for_log(url)}: {sanitize_for_log(ct)}."
        )


def _content_length_if_over_limit(url: str, cl: str | None) -> int | None:
    """Return the parsed Content-Length if it exceeds MAX_RESPONSE_SIZE.

    Logs a warning and returns None when the header is malformed or within the
    limit, so the caller can fall back to the streaming size check.
    """
    if not cl:
        return None
    try:
        declared = int(cl)
    except ValueError:
        log.warning(
            f"Malformed Content-Length header from {sanitize_for_log(url)}: "
            f"{sanitize_for_log(cl)}. Falling back to streaming check."
        )
        return None
    if declared > config.MAX_RESPONSE_SIZE:
        return declared
    return None


def _read_body(url: str, r: httpx.Response) -> bytes:
    """Stream and return the response body, enforcing MAX_RESPONSE_SIZE."""
    declared = _content_length_if_over_limit(url, r.headers.get("Content-Length"))
    if declared is not None:
        raise ValueError(
            f"Response too large from {sanitize_for_log(url)} "
            f"({declared / (1024 * 1024):.2f} MB)"
        )

    chunks: list[bytes] = []
    current_size = 0
    for chunk in r.iter_bytes(chunk_size=16 * 1024):
        current_size += len(chunk)
        if current_size > config.MAX_RESPONSE_SIZE:
            raise ValueError(
                f"Response too large from {sanitize_for_log(url)} "
                f"(> {config.MAX_RESPONSE_SIZE / (1024 * 1024):.2f} MB)"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _parse_json_bytes(url: str, body_bytes: bytes) -> Any:
    """Parse a JSON body, re-raising JSONDecodeError as a sanitized ValueError."""
    try:
        return json.loads(body_bytes)
    except json.JSONDecodeError:
        raise ValueError(
            f"Invalid JSON response from {sanitize_for_log(url)}"
        ) from None


def _build_cache_entry(data: Any, r: httpx.Response) -> dict[str, Any]:
    """Build a disk-cache entry from parsed data and response headers."""
    return {
        "data": data,
        "etag": r.headers.get("ETag"),
        "last_modified": r.headers.get("Last-Modified"),
        "fetched_at": time.time(),
        "last_validated": time.time(),
    }


def _record_cache_miss() -> None:
    """Increment the cache-miss counter."""
    _cache_stats["misses"] += 1


def _parse_and_cache_response(url: str, r: httpx.Response) -> dict:
    """Validate, stream, parse, and cache a blocklist response."""
    _validate_content_type(url, r)
    body_bytes = _read_body(url, r)
    data = _parse_json_bytes(url, body_bytes)

    # Update disk cache with new data and headers
    _disk_cache[url] = _build_cache_entry(data, r)

    _record_cache_miss()
    return cast(dict, data)


def _get_memory_cached(url: str) -> dict | None:
    """Return the in-memory cached entry if present, incrementing hits."""
    with _cache_lock:
        if (cached := _cache.get(url)) is not None:
            _cache_stats["hits"] += 1
            return cached
    return None


def _count_blocklist_fetch() -> None:
    """Increment the blocklist fetch counter before issuing a request."""
    with _cache_lock:
        _api_stats["blocklist_fetches"] += 1


def _serve_disk_ttl_hit(url: str, cached_entry: dict[str, Any]) -> dict:
    """Return a disk-cached entry that is still within TTL, promoting it to memory."""
    data = cached_entry["data"]
    with _cache_lock:
        _cache[url] = data
    _cache_stats["hits"] += 1
    if log.isEnabledFor(logging.DEBUG):
        log.debug(f"Disk cache hit (within TTL) for {sanitize_for_log(url)}")
    return cast(dict, data)


def _build_conditional_headers(cached_entry: dict[str, Any]) -> dict[str, str]:
    """Build If-None-Match / If-Modified-Since headers from a disk-cache entry."""
    headers: dict[str, str] = {}
    etag = cached_entry.get("etag")
    if etag:
        headers["If-None-Match"] = etag
    last_modified = cached_entry.get("last_modified")
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    return headers


def _handle_304_with_data(url: str, cached_entry: dict[str, Any]) -> dict:
    """Handle a 304 Not Modified response when cached data is available."""
    if log.isEnabledFor(logging.DEBUG):
        log.debug(f"Cache validated (304) for {sanitize_for_log(url)}")
    _cache_stats["validations"] += 1

    data = cached_entry["data"]
    with _cache_lock:
        _cache[url] = data

    # Update timestamp in disk cache to track last validation
    cached_entry["last_validated"] = time.time()
    return cast(dict, data)


def _fetch_unconditional(url: str, headers: dict[str, str]) -> dict:
    """Issue a fresh GET request and parse/store its response."""
    with _gh.stream("GET", url, headers=headers) as r:
        r.raise_for_status()
        return _parse_and_cache_response(url, r)


def _sanitize_http_status_error(e: httpx.HTTPStatusError) -> httpx.HTTPStatusError:
    """Construct an HTTPStatusError whose message has been sanitized."""
    return httpx.HTTPStatusError(
        sanitize_for_log(str(e)),
        request=e.request,
        response=e.response,
    )


def _gh_get(url: str) -> dict:
    """
    Fetch blocklist data from URL with HTTP cache header support.

    CACHING STRATEGY:
    1. Check in-memory cache first (fastest)
    2. Check disk cache and send conditional request (If-None-Match/If-Modified-Since)
    3. If 304 Not Modified: reuse cached data (cache validation)
    4. If 200 OK: download new data and update cache

    SECURITY: Validates data structure regardless of cache source
    """
    # SECURITY: Fail-closed SSRF guard before any cache or network access.
    _validate_url_or_raise(url)

    # First check: Quick check without holding lock for long
    if (cached := _get_memory_cached(url)) is not None:
        return cached

    # Track that we're about to make a blocklist fetch
    _count_blocklist_fetch()

    # Check disk cache for TTL-based hit or conditional request headers
    headers: dict[str, str] = {}
    cached_entry = _disk_cache.get(url)
    if cached_entry:
        last_validated = cached_entry.get("last_validated", 0)
        if time.time() - last_validated < CACHE_TTL_SECONDS:
            # Within TTL: return cached data directly without any HTTP request
            return _serve_disk_ttl_hit(url, cached_entry)
        # Beyond TTL: send conditional request using cached ETag/Last-Modified
        # Server returns 304 if content hasn't changed
        # NOTE: Cached values may be None if the server didn't send these headers.
        headers = _build_conditional_headers(cached_entry)

    # Fetch data (or validate cache)
    # Explicitly let HTTPError propagate (no need to catch just to re-raise)
    try:
        with _gh.stream("GET", url, headers=headers) as r:
            # Handle 304 Not Modified - cached data is still valid
            if r.status_code == 304:
                if cached_entry and "data" in cached_entry:
                    return _handle_304_with_data(url, cached_entry)

                # Shouldn't happen, but handle gracefully
                log.warning(
                    f"Got 304 but no cached data for {sanitize_for_log(url)}, re-fetching"
                )
                _cache_stats["errors"] += 1
                # Close the original streaming response before retrying
                r.close()
                # Retry without conditional headers using streaming again so that
                # MAX_RESPONSE_SIZE and related protections still apply.
                return _fetch_unconditional(url, {})

            r.raise_for_status()
            data = _parse_and_cache_response(url, r)
    except httpx.HTTPStatusError as e:
        # Re-raise with sanitized exception to prevent data leakage
        raise _sanitize_http_status_error(e) from None

    # Double-checked locking: Check again after fetch to avoid duplicate fetches
    # If another thread already cached it while we were fetching, use theirs
    # for consistency (return _cache[url] instead of data to ensure single source of truth)
    with _cache_lock:
        return _cache.setdefault(url, data)


def fetch_folder_data(url: str) -> FolderData:
    """
    Downloads and validates folder JSON data from a URL.

    Uses cached GET request and validates the folder structure.
    Raises httpx.HTTPStatusError (with actionable hint) on HTTP failure,
    or KeyError if validation of the returned data fails.
    """
    # SECURITY: Fail-closed SSRF guard in case callers bypass higher-level checks.
    _validate_url_or_raise(url)

    try:
        js = _gh_get(url)
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        hint = config._STATUS_HINTS.get(status, f"HTTP {status}")
        # Include the original error message so we keep the numeric status code
        # and reason phrase (e.g., "401 Unauthorized") in addition to our hint.
        original_msg = str(e)
        raise httpx.HTTPStatusError(
            f"{sanitize_for_log(original_msg)} | hint: {hint} | url: {sanitize_for_log(url)}",
            request=e.request,
            response=e.response,
        ) from None
    if not validate_folder_data(js, url):
        raise KeyError(f"Invalid folder data from {sanitize_for_log(url)}")
    return js


def _validate_and_fetch_url(url: str) -> Any:
    if validate_folder_url(url):
        return _gh_get(url)
    return None


def warm_up_cache(urls: Sequence[str]) -> None:
    """
    Pre-fetches and caches folder data from multiple URLs in parallel.

    Validates URLs and fetches data concurrently to minimize cold-start latency.
    Shows progress bar when USE_COLORS is enabled. Skips invalid URLs while
    emitting warnings/log entries for validation and fetch failures.
    """
    urls = list(set(urls))
    with _cache_lock:
        urls_to_process = list(itertools.filterfalse(_cache.__contains__, urls))
    if not urls_to_process:
        return

    total = len(urls_to_process)
    if not USE_COLORS:
        log.info(f"⏳ Warming up cache for {total:,} {pluralize(total, 'URL')}...")

    completed = 0
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(_validate_and_fetch_url, url): url
            for url in urls_to_process
        }

        render_progress_bar(0, total, "Warming up cache", prefix="⏳")

        for future in concurrent.futures.as_completed(futures):
            completed += 1
            render_progress_bar(completed, total, "Warming up cache", prefix="⏳")
            try:
                future.result()
            except Exception as e:
                _clear_current_line()
                log.warning(
                    f"Failed to pre-fetch {sanitize_for_log(futures[future])}: "
                    f"{sanitize_for_log(e)}"
                )
                # Restore progress bar after warning
                render_progress_bar(completed, total, "Warming up cache", prefix="⏳")

    _print_completion("Warming up cache: Done!")


__all__ = [
    "_gh",
    "_cache",
    "_cache_lock",
    "_gh_get",
    "fetch_folder_data",
    "_validate_and_fetch_url",
    "warm_up_cache",
    "_parse_and_cache_response",
]
