"""
Performance regression tests with baseline thresholds.

These benchmarks guard against unintentional slowdowns on hot paths.
Run with: uv run pytest tests/test_performance_regression.py --benchmark-only
"""

import sys
import os

import pytest
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main

# Maximum acceptable mean execution time (seconds) for hot-path operations.
_MAX_MEAN_S = 0.001  # 1 ms


class TestPerformanceRegression:
    """Performance regression tests with baseline thresholds."""

    def test_validate_hostname_performance(self, benchmark):
        """Hostname validation should complete in <1ms on average."""
        # Use a private IP so no real DNS lookup occurs, making the test fast and deterministic
        main.validate_hostname.cache_clear()
        result = benchmark(main.validate_hostname, "192.168.1.1")
        assert result is False  # Private IP is rejected
        assert benchmark.stats["mean"] < _MAX_MEAN_S

    def test_validate_hostname_cached_performance(self, benchmark):
        """Cached hostname validation should be significantly faster than <1ms."""
        # Prime the cache with a known private IP
        main.validate_hostname.cache_clear()
        main.validate_hostname("10.0.0.1")
        # Now benchmark the cached call
        result = benchmark(main.validate_hostname, "10.0.0.1")
        assert result is False
        assert benchmark.stats["mean"] < _MAX_MEAN_S

    def test_rate_limit_parsing_performance(self, benchmark):
        """Rate limit header parsing should complete in <1ms on average."""
        headers = {
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "4999",
            "X-RateLimit-Reset": "1640000000",
        }
        mock_response = httpx.Response(200, headers=headers)

        result = benchmark(main._parse_rate_limit_headers, mock_response)
        assert result is None  # Function returns None
        assert benchmark.stats["mean"] < _MAX_MEAN_S

    def test_rate_limit_parsing_empty_headers_performance(self, benchmark):
        """Rate limit parsing with no rate-limit headers should complete in <1ms."""
        mock_response = httpx.Response(200, headers={})
        result = benchmark(main._parse_rate_limit_headers, mock_response)
        assert result is None
        assert benchmark.stats["mean"] < _MAX_MEAN_S
