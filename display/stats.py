"""API, cache, and rate-limit statistics rendering."""

from __future__ import annotations

import time

from api_client import _api_stats, _rate_limit_info, _rate_limit_lock
from cache import _cache_stats

from .colors import Colors
from .output import _print_bold_header


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
    "display_api_statistics",
    "display_cache_statistics",
    "display_rate_limit_status",
    "display_statistics",
]
