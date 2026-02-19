"""
Tests for retry logic with exponential backoff and jitter.

These tests verify that:
1. Jitter randomizes retry delays to prevent thundering herd
2. Exponential backoff still functions correctly
3. Non-retryable errors (4xx except 429) fail fast
4. Max retries limit is respected
"""

from unittest.mock import Mock, patch
import pytest
import httpx


# Import functions under test
import main


class TestRetryJitter:
    """Tests for jitter in exponential backoff retry logic."""

    def test_jitter_adds_randomness_to_retry_delays(self):
        """Verify that retry delays include jitter and aren't identical."""
        request_func = Mock(side_effect=httpx.TimeoutException("Connection timeout"))
        
        # Collect actual wait times across multiple retry sequences
        wait_times_run1 = []
        wait_times_run2 = []
        
        with patch('time.sleep') as mock_sleep:
            # First run
            try:
                main._retry_request(request_func, max_retries=3, delay=1)
            except httpx.TimeoutException:
                pass
            wait_times_run1 = [call.args[0] for call in mock_sleep.call_args_list]
            
        with patch('time.sleep') as mock_sleep:
            # Second run with fresh mock
            request_func.side_effect = httpx.TimeoutException("Connection timeout")
            try:
                main._retry_request(request_func, max_retries=3, delay=1)
            except httpx.TimeoutException:
                pass
            wait_times_run2 = [call.args[0] for call in mock_sleep.call_args_list]
        
        # Both runs should have same number of retries (2 retries for 3 max_retries)
        assert len(wait_times_run1) == 2
        assert len(wait_times_run2) == 2
        
        # Due to jitter, wait times should differ between runs
        # (with high probability - could theoretically be equal but extremely unlikely)
        assert wait_times_run1 != wait_times_run2, \
            "Jitter should produce different wait times across runs"

    def test_jitter_stays_within_bounds(self):
        """Verify jitter keeps delays within expected range (0.5x to 1.5x base)."""
        request_func = Mock(side_effect=httpx.TimeoutException("Connection timeout"))
        
        with patch('time.sleep') as mock_sleep:
            try:
                main._retry_request(request_func, max_retries=5, delay=1)
            except httpx.TimeoutException:
                pass
            
            wait_times = [call.args[0] for call in mock_sleep.call_args_list]
            
            # Verify each wait time is within jitter bounds
            for attempt, wait_time in enumerate(wait_times):
                base_delay = 1 * (2 ** attempt)  # Exponential backoff formula
                min_expected = base_delay * 0.5
                max_expected = base_delay * 1.5
                
                assert min_expected <= wait_time <= max_expected, \
                    f"Attempt {attempt}: wait time {wait_time:.2f}s outside jitter bounds " \
                    f"[{min_expected:.2f}s, {max_expected:.2f}s]"

    def test_exponential_backoff_still_increases(self):
        """Verify that despite jitter, the exponential base scaling is correct.

        We fix random.random() to a constant so that jitter becomes deterministic,
        and then assert that each delay matches delay * 2**attempt * jitter_factor.
        """
        request_func = Mock(side_effect=httpx.TimeoutException("Connection timeout"))

        # Use a fixed random.random() so jitter multiplier is stable across attempts.
        # Assuming jitter is implemented as: base_delay * (0.5 + random.random()),
        # a fixed return_value of 0.5 yields a jitter_factor of 1.0.
        with patch('time.sleep') as mock_sleep, patch('random.random', return_value=0.5):
            try:
                main._retry_request(request_func, max_retries=5, delay=1)
            except httpx.TimeoutException:
                pass

            wait_times = [call.args[0] for call in mock_sleep.call_args_list]

            jitter_factor = 0.5 + 0.5  # Matches the patched random.random() above
            for attempt, wait_time in enumerate(wait_times):
                base_delay = 1 * (2 ** attempt)
                expected_delay = base_delay * jitter_factor
                # Use approx to avoid brittle float equality while still being strict.
                assert wait_time == pytest.approx(expected_delay), (
                    f"Attempt {attempt}: expected {expected_delay:.2f}s, "
                    f"got {wait_time:.2f}s"
                )
    def test_four_hundred_errors_still_fail_fast(self):
        """Verify 4xx errors (except 429) still don't retry despite jitter."""
        response = Mock(status_code=404)
        error = httpx.HTTPStatusError(
            "Not found",
            request=Mock(),
            response=response
        )
        request_func = Mock(side_effect=error)
        
        with patch('time.sleep') as mock_sleep:
            with pytest.raises(httpx.HTTPStatusError):
                main._retry_request(request_func, max_retries=5, delay=1)
            
            # Should not sleep at all - fail immediately
            assert mock_sleep.call_count == 0

    def test_429_rate_limit_retries_with_jitter(self):
        """Verify 429 rate limit errors retry with jittered backoff."""
        response = Mock(status_code=429)
        response.headers = {}
        error = httpx.HTTPStatusError(
            "Too many requests",
            request=Mock(),
            response=response
        )
        request_func = Mock(side_effect=error)
        
        with patch('time.sleep') as mock_sleep:
            with pytest.raises(httpx.HTTPStatusError):
                main._retry_request(request_func, max_retries=3, delay=1)
            
            # Should retry (2 retries for max_retries=3)
            assert mock_sleep.call_count == 2
            
            # Verify jitter applied to retries
            wait_times = [call.args[0] for call in mock_sleep.call_args_list]
            assert len(wait_times) == 2
            
            # First retry: base=1, range=[0.5, 1.5]
            assert 0.5 <= wait_times[0] <= 1.5

    def test_successful_retry_after_transient_failure(self):
        """Verify successful request after transient failures works correctly."""
        # Fail twice, then succeed
        request_func = Mock(side_effect=[
            httpx.TimeoutException("Timeout 1"),
            httpx.TimeoutException("Timeout 2"),
            Mock(status_code=200)  # Success
        ])
        
        with patch('time.sleep') as mock_sleep:
            response = main._retry_request(request_func, max_retries=5, delay=1)
            
            # Should have made 3 requests total (2 failures + 1 success)
            assert request_func.call_count == 3
            
            # Should have slept twice (after first two failures)
            assert mock_sleep.call_count == 2
            
            # Should return the successful response
            assert response.status_code == 200

    def test_max_retries_respected(self):
        """Verify max_retries limit is still enforced with jitter."""
        request_func = Mock(side_effect=httpx.TimeoutException("Always fails"))
        
        with patch('time.sleep') as mock_sleep:
            with pytest.raises(httpx.TimeoutException):
                main._retry_request(request_func, max_retries=4, delay=1)
            
            # Should attempt exactly max_retries times
            assert request_func.call_count == 4
            
            # Should sleep max_retries-1 times (no sleep after final failure)
            assert mock_sleep.call_count == 3
