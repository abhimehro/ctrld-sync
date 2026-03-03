"""
cache.py — Persistent disk-cache subsystem for ctrld-sync.

Provides:
- Platform-specific cache directory resolution (get_cache_dir)
- Loading/saving a JSON blocklist cache with graceful degradation (load_disk_cache,
  save_disk_cache)
- Parallel URL warm-up that pre-populates the in-memory cache before sync
  (warm_up_cache)

Module-level state
------------------
_disk_cache : dict[str, dict[str, Any]]
    Blocklist entries loaded from disk at startup.  Keys are URLs; values are
    dicts with at minimum a ``data`` key.  Access via in-place mutations
    (``_disk_cache.clear()``, ``_disk_cache.update(…)``) so that callers that
    imported the name still reference the same live object.

_cache_stats : dict[str, int]
    Running counters for hits, misses, conditional-request validations, and
    errors.  Updated in-place so importers always see current values.

CACHE_TTL_SECONDS : int
    How long (in seconds) a cached entry is considered fresh before a
    conditional HTTP request is sent to validate it (default: 24 h).
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import platform
import sys
from pathlib import Path
from typing import Any, Sequence

log = logging.getLogger("control-d-sync")

# --------------------------------------------------------------------------- #
# Module-level cache state
# --------------------------------------------------------------------------- #
# 24 hours: within TTL, serve from disk without an HTTP request.
CACHE_TTL_SECONDS: int = 24 * 60 * 60

# Blocklist entries keyed by URL.  Populated by load_disk_cache() at startup.
# Always mutate in-place so that names imported via ``from cache import …``
# continue to reference the same underlying dict object.
_disk_cache: dict[str, dict[str, Any]] = {}

# Running counters – updated by load_disk_cache, save_disk_cache, and _gh_get.
_cache_stats: dict[str, int] = {
    "hits": 0,
    "misses": 0,
    "validations": 0,
    "errors": 0,
}


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _sanitize(text: Any) -> str:
    """Minimal log-safe representation of *text* for cache I/O error messages.

    Uses ``repr()`` to escape control characters (prevents log injection /
    terminal hijacking).  Strips the surrounding quote pair that repr() adds
    for plain strings so that log lines read naturally.
    """
    s = repr(str(text))
    # repr wraps strings in matching single or double quotes – strip them.
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        return s[1:-1]
    return s


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def get_cache_dir() -> Path:
    """Return the platform-specific cache directory for ctrld-sync.

    Uses standard cache locations:
    - Linux/Unix: ~/.cache/ctrld-sync  (or $XDG_CACHE_HOME/ctrld-sync)
    - macOS:      ~/Library/Caches/ctrld-sync
    - Windows:    %LOCALAPPDATA%/ctrld-sync/cache

    SECURITY: No user input reaches path construction – prevents path
    traversal attacks.
    """
    system = platform.system()
    if system == "Darwin":  # macOS
        return Path.home() / "Library" / "Caches" / "ctrld-sync"
    elif system == "Windows":
        appdata = os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
        return Path(appdata) / "ctrld-sync" / "cache"
    else:  # Linux, Unix, and others – follow XDG Base Directory spec
        xdg_cache = os.getenv("XDG_CACHE_HOME")
        if xdg_cache:
            return Path(xdg_cache) / "ctrld-sync"
        return Path.home() / ".cache" / "ctrld-sync"


def load_disk_cache() -> None:
    """Load the persistent blocklist cache from disk at startup.

    GRACEFUL DEGRADATION: Any error (corrupted JSON, missing file, permission
    denied, etc.) is logged but otherwise ignored – the sync continues with an
    empty cache.  This prevents crashes from a stale or corrupted cache file.

    The function mutates ``_disk_cache`` **in-place** (clear + update) rather
    than reassigning the module-level name so that all importers that hold a
    reference to the dict always see the live data.
    """
    try:
        cache_file = get_cache_dir() / "blocklists.json"
        if not cache_file.exists():
            log.debug("No existing cache file found, starting fresh")
            return

        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Validate cache structure at the top level.
        if not isinstance(data, dict):
            log.warning("Cache file has invalid format (root is not a dict), ignoring")
            return

        # Sanitize individual entries:  key must be str, value must be a dict
        # containing at least a 'data' field.  Drop anything malformed so that
        # a partly-corrupt cache never causes a crash downstream.
        sanitized_cache: dict[str, Any] = {}
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
            # Nothing valid – reset to empty and return.
            _disk_cache.clear()
            log.warning(
                "Cache file contained no valid entries; starting with empty cache"
            )
            return

        if dropped_entries:
            log.info(
                "Loaded %d valid entries from disk cache (dropped %d malformed entries)",
                len(sanitized_cache),
                dropped_entries,
            )
        else:
            log.info("Loaded %d entries from disk cache", len(sanitized_cache))

        # In-place update so all existing references to _disk_cache stay valid.
        _disk_cache.clear()
        _disk_cache.update(sanitized_cache)
    except json.JSONDecodeError as e:
        log.warning(f"Corrupted cache file (invalid JSON), starting fresh: {_sanitize(e)}")
        _cache_stats["errors"] += 1
    except PermissionError as e:
        log.warning(
            f"Cannot read cache file (permission denied), starting fresh: {_sanitize(e)}"
        )
        _cache_stats["errors"] += 1
    except Exception as e:
        # Catch-all for unexpected errors (disk full, etc.)
        log.warning(f"Failed to load cache, starting fresh: {_sanitize(e)}")
        _cache_stats["errors"] += 1


def save_disk_cache() -> None:
    """Flush the in-memory disk cache to disk after a successful sync.

    SECURITY: Creates the cache directory with user-only permissions (0o700)
    and the cache file with 0o600 to prevent other OS users from reading
    cached blocklist data.

    Writes atomically via a temp file + rename so that a process crash
    mid-write cannot leave a corrupted cache.
    """
    try:
        cache_dir = get_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Set directory permissions to user-only (rwx------).
        if platform.system() != "Windows":
            cache_dir.chmod(0o700)

        cache_file = cache_dir / "blocklists.json"
        temp_file = cache_file.with_suffix(".tmp")

        # Security: use os.open so the file is created with 0o600 from the
        # start, avoiding a TOCTOU race where a world-readable file exists
        # briefly before a subsequent chmod.
        fd = os.open(temp_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(_disk_cache, f, indent=2)

        # POSIX guarantees rename is atomic.
        temp_file.replace(cache_file)

        if log.isEnabledFor(logging.DEBUG):
            log.debug(f"Saved {len(_disk_cache):,} entries to disk cache")

    except Exception as e:
        # Cache save failures are non-fatal; next run simply starts without cache.
        log.warning(f"Failed to save cache (non-fatal): {_sanitize(e)}")
        _cache_stats["errors"] += 1


def warm_up_cache(urls: Sequence[str]) -> None:
    """Pre-fetch and cache folder data for *urls* in parallel.

    Validates each URL and fetches its content concurrently to minimise
    cold-start latency.  Shows a progress bar when colours are enabled.
    Invalid or un-fetchable URLs are skipped with a warning.

    This function deliberately imports ``main`` lazily (inside the function
    body) to avoid a circular import at module load time.  By the time this
    function is invoked, ``main`` is always fully initialised and available in
    ``sys.modules``.
    """
    # Deferred import: cache.py is imported by main.py, so a top-level
    # ``import main`` here would create a circular dependency.  A local import
    # is safe because warm_up_cache is only ever called after main.py has
    # finished loading.
    import main as _m

    urls = list(set(urls))
    with _m._cache_lock:
        urls_to_process = [u for u in urls if u not in _m._cache]
    if not urls_to_process:
        return

    total = len(urls_to_process)
    if not _m.USE_COLORS:
        log.info(f"Warming up cache for {total:,} URLs...")

    # OPTIMIZATION: Combine validation (DNS) and fetching (HTTP) in one task
    # to allow validation latency to be parallelised.
    def _validate_and_fetch(url: str):
        if _m.validate_folder_url(url):
            return _m._gh_get(url)
        return None

    completed = 0
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(_validate_and_fetch, url): url for url in urls_to_process
        }

        _m.render_progress_bar(0, total, "Warming up cache", prefix="⏳")

        for future in concurrent.futures.as_completed(futures):
            completed += 1
            _m.render_progress_bar(completed, total, "Warming up cache", prefix="⏳")
            try:
                future.result()
            except Exception as e:
                if _m.USE_COLORS:
                    # Clear line to print warning cleanly.
                    sys.stderr.write("\r\033[K")
                    sys.stderr.flush()

                log.warning(
                    f"Failed to pre-fetch {_m.sanitize_for_log(futures[future])}: "
                    f"{_m.sanitize_for_log(e)}"
                )
                # Restore progress bar after warning.
                _m.render_progress_bar(completed, total, "Warming up cache", prefix="⏳")

    if _m.USE_COLORS:
        sys.stderr.write(
            f"\r\033[K{_m.Colors.GREEN}✅ Warming up cache: Done!{_m.Colors.ENDC}\n"
        )
        sys.stderr.flush()
