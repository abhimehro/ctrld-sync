"""
Tests for rate limit header parsing and handling.

These tests verify that:
1. Rate limit headers are correctly parsed from API responses
2. 429 (Too Many Requests) responses honor Retry-After header
3. Rate limit warnings are logged when approaching limits
4. Thread-safe access to rate limit state
"""

import threading
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

import main


class TestRateLimitParsing:
    """Test parsing of rate limit headers from API responses."""

    def setup_method(self):
        """Reset rate limit info before each test."""
        with main._rate_limit_lock:
            main._rate_limit_info["limit"] = None
            main._rate_limit_info["remaining"] = None
            main._rate_limit_info["reset"] = None

    def test_parse_rate_limit_headers_all_present(self):
        """Test parsing when all rate limit headers are present."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.headers = {
            "X-RateLimit-Limit": "100",
            "X-RateLimit-Remaining": "75",
            "X-RateLimit-Reset": "1708225200",  # Some future timestamp
        }

        main._parse_rate_limit_headers(mock_response)

        with main._rate_limit_lock:
            assert main._rate_limit_info["limit"] == 100
            assert main._rate_limit_info["remaining"] == 75
            assert main._rate_limit_info["reset"] == 1708225200

    def test_parse_rate_limit_headers_partial(self):
        """Test parsing when only some headers are present."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.headers = {
            "X-RateLimit-Remaining": "50",
        }

        main._parse_rate_limit_headers(mock_response)

        with main._rate_limit_lock:
            assert main._rate_limit_info["limit"] is None
            assert main._rate_limit_info["remaining"] == 50
            assert main._rate_limit_info["reset"] is None

    def test_parse_rate_limit_headers_missing(self):
        """Test parsing when no rate limit headers are present."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.headers = {}

        # Store original values
        with main._rate_limit_lock:
            original_limit = main._rate_limit_info["limit"]
            original_remaining = main._rate_limit_info["remaining"]
            original_reset = main._rate_limit_info["reset"]

        main._parse_rate_limit_headers(mock_response)

        # Values should remain unchanged
        with main._rate_limit_lock:
            assert main._rate_limit_info["limit"] == original_limit
            assert main._rate_limit_info["remaining"] == original_remaining
            assert main._rate_limit_info["reset"] == original_reset

    def test_parse_rate_limit_headers_invalid_values(self):
        """Test graceful handling of invalid header values."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.headers = {
            "X-RateLimit-Limit": "not-a-number",
            "X-RateLimit-Remaining": "also-invalid",
            "X-RateLimit-Reset": "bad-timestamp",
        }

        # Should not crash, just ignore invalid values
        main._parse_rate_limit_headers(mock_response)

        with main._rate_limit_lock:
            # Values should remain unchanged (None if setup was clean)
            assert main._rate_limit_info["limit"] is None
            assert main._rate_limit_info["remaining"] is None
            assert main._rate_limit_info["reset"] is None

    def test_parse_rate_limit_low_remaining_warning(self, caplog):
        """Test warning when approaching rate limit (< 20% remaining)."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.headers = {
            "X-RateLimit-Limit": "100",
            "X-RateLimit-Remaining": "15",  # 15% remaining
            "X-RateLimit-Reset": str(int(time.time()) + 3600),
        }

        with caplog.at_level("WARNING"):
            main._parse_rate_limit_headers(mock_response)

        # Should log a warning about approaching rate limit
        assert any("Approaching rate limit" in record.message for record in caplog.records)

    def test_parse_rate_limit_healthy_no_warning(self, caplog):
        """Test no warning when rate limit is healthy (> 20% remaining)."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.headers = {
            "X-RateLimit-Limit": "100",
            "X-RateLimit-Remaining": "80",  # 80% remaining
        }

        with caplog.at_level("WARNING"):
            main._parse_rate_limit_headers(mock_response)

        # Should NOT log a warning
        assert not any("Approaching rate limit" in record.message for record in caplog.records)

    def test_rate_limit_thread_safety(self):
        """Test thread-safe access to rate limit info."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.headers = {
            "X-RateLimit-Limit": "100",
            "X-RateLimit-Remaining": "50",
        }

        # Parse from multiple threads concurrently
        threads = []
        for _ in range(10):
            t = threading.Thread(target=main._parse_rate_limit_headers, args=(mock_response,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Should have consistent state (no crashes or corrupted data)
        with main._rate_limit_lock:
            assert main._rate_limit_info["limit"] == 100
            assert main._rate_limit_info["remaining"] == 50


class TestRetryWithRateLimit:
    """Test retry logic with rate limit handling."""

    def setup_method(self):
        """Reset rate limit info before each test."""
        with main._rate_limit_lock:
            main._rate_limit_info["limit"] = None
            main._rate_limit_info["remaining"] = None
            main._rate_limit_info["reset"] = None

    def test_retry_429_with_retry_after(self, caplog):
        """Test that 429 response honors Retry-After header."""
        mock_request = MagicMock()
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 429
        mock_response.headers = {
            "Retry-After": "2",  # 2 seconds
            "X-RateLimit-Remaining": "0",
        }
        mock_response.request = mock_request

        error = httpx.HTTPStatusError(
            "429 Too Many Requests",
            request=mock_request,
            response=mock_response,
        )

        # First call raises 429, second call succeeds
        success_response = MagicMock(spec=httpx.Response)
        success_response.raise_for_status = MagicMock()
        success_response.headers = {}

        request_func = MagicMock(side_effect=[error, success_response])

        start_time = time.time()
        with caplog.at_level("WARNING"):
            result = main._retry_request(request_func, max_retries=3, delay=1)
        elapsed = time.time() - start_time

        # Should have waited ~2 seconds (from Retry-After)
        assert elapsed >= 2.0
        assert result == success_response

        # Should log rate limit message
        assert any("Rate limited (429)" in record.message for record in caplog.records)

    def test_successful_request_parses_headers(self):
        """Test that successful requests parse rate limit headers."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {
            "X-RateLimit-Limit": "100",
            "X-RateLimit-Remaining": "99",
        }

        request_func = MagicMock(return_value=mock_response)

        main._retry_request(request_func)

        # Rate limit info should be updated
        with main._rate_limit_lock:
            assert main._rate_limit_info["limit"] == 100
            assert main._rate_limit_info["remaining"] == 99

    def test_failed_request_parses_headers(self):
        """Test that failed requests also parse rate limit headers."""
        mock_request = MagicMock()
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_response.headers = {
            "X-RateLimit-Remaining": "50",
        }
        mock_response.request = mock_request
        mock_response.text = "Server error"

        error = httpx.HTTPStatusError(
            "500 Server Error",
            request=mock_request,
            response=mock_response,
        )

        request_func = MagicMock(side_effect=error)

        with pytest.raises(httpx.HTTPStatusError):
            main._retry_request(request_func, max_retries=1, delay=0.1)

        # Rate limit info should still be updated from error response
        with main._rate_limit_lock:
            assert main._rate_limit_info["remaining"] == 50

    @patch('random.random', return_value=0.5)
    def test_429_without_retry_after_uses_exponential_backoff(self, mock_random):
        """Test that 429 without Retry-After falls back to exponential backoff."""
        mock_request = MagicMock()
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 429
        mock_response.headers = {}  # No Retry-After
        mock_response.request = mock_request

        error = httpx.HTTPStatusError(
            "429 Too Many Requests",
            request=mock_request,
            response=mock_response,
        )

        # Fail twice with 429, then succeed
        success_response = MagicMock(spec=httpx.Response)
        success_response.raise_for_status = MagicMock()
        success_response.headers = {}

        request_func = MagicMock(side_effect=[error, error, success_response])

        # With delay=1, backoff should be: 1s, 2s
        # Total wait should be >= 3 seconds (assuming jitter factor 1.0)
        start_time = time.time()
        result = main._retry_request(request_func, max_retries=3, delay=1)
        elapsed = time.time() - start_time

        assert elapsed >= 3.0
        assert result == success_response
