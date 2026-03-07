"""
Tests for actionable warning logs in api_client._retry_request() error paths.

Covers:
- _4XX_HINTS dict contains expected codes (401, 403, 404)
- log.warning() is emitted for 401, 403, 404 with correct hint text
- log.warning() is emitted for other 4xx codes without a hint suffix
- 429 behavior is unchanged (no log.warning from 4xx branch)
- _sanitize_fn is applied to the exception in the warning message
- ConnectError hint (_CONNECT_ERROR_HINT) is surfaced in retry warning logs
- _SERVER_ERROR_HINT is emitted for 5xx responses (500, 503)
"""

import logging
from unittest.mock import MagicMock, patch

import httpx
import pytest

import api_client


def _make_http_error(status_code: int) -> httpx.HTTPStatusError:
    """Create a minimal HTTPStatusError with the given status code."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_response.headers = {}
    mock_response.text = "error body"
    mock_request = MagicMock(spec=httpx.Request)
    return httpx.HTTPStatusError(
        f"{status_code} Error",
        request=mock_request,
        response=mock_response,
    )


class TestFourXXHintsDict:
    """Verify the _4XX_HINTS constant exists and contains the required entries."""

    def test_hints_dict_exists(self):
        assert hasattr(api_client, "_4XX_HINTS")
        assert isinstance(api_client._4XX_HINTS, dict)

    def test_hint_401_mentions_token(self):
        assert 401 in api_client._4XX_HINTS
        assert "TOKEN" in api_client._4XX_HINTS[401]

    def test_hint_403_mentions_permissions(self):
        assert 403 in api_client._4XX_HINTS
        assert "permission" in api_client._4XX_HINTS[403].lower()

    def test_hint_404_mentions_folder(self):
        assert 404 in api_client._4XX_HINTS
        assert "folder" in api_client._4XX_HINTS[404].lower()


class TestRetryRequestFourXXWarnings:
    """Verify _retry_request() emits log.warning() for 4xx errors before re-raising."""

    def test_401_warning_logged(self, caplog):
        error = _make_http_error(401)
        request_func = MagicMock(side_effect=error)

        with caplog.at_level(logging.WARNING, logger="api_client"):
            with pytest.raises(httpx.HTTPStatusError):
                api_client._retry_request(request_func, max_retries=1, delay=0.01)

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert warnings, "Expected a WARNING log for HTTP 401"
        warning_text = warnings[0].message
        assert "401" in warning_text
        assert "TOKEN" in warning_text

    def test_403_warning_logged(self, caplog):
        error = _make_http_error(403)
        request_func = MagicMock(side_effect=error)

        with caplog.at_level(logging.WARNING, logger="api_client"):
            with pytest.raises(httpx.HTTPStatusError):
                api_client._retry_request(request_func, max_retries=1, delay=0.01)

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert warnings, "Expected a WARNING log for HTTP 403"
        warning_text = warnings[0].message
        assert "403" in warning_text
        assert "permission" in warning_text.lower()

    def test_404_warning_logged(self, caplog):
        error = _make_http_error(404)
        request_func = MagicMock(side_effect=error)

        with caplog.at_level(logging.WARNING, logger="api_client"):
            with pytest.raises(httpx.HTTPStatusError):
                api_client._retry_request(request_func, max_retries=1, delay=0.01)

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert warnings, "Expected a WARNING log for HTTP 404"
        warning_text = warnings[0].message
        assert "404" in warning_text
        assert "folder" in warning_text.lower()

    def test_other_4xx_warning_logged_without_hint(self, caplog):
        """HTTP 400 should still log a warning but without a hint suffix."""
        error = _make_http_error(400)
        request_func = MagicMock(side_effect=error)

        with caplog.at_level(logging.WARNING, logger="api_client"):
            with pytest.raises(httpx.HTTPStatusError):
                api_client._retry_request(request_func, max_retries=1, delay=0.01)

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert warnings, "Expected a WARNING log for HTTP 400"
        warning_text = warnings[0].message
        assert "400" in warning_text
        assert "hint:" not in warning_text

    def test_429_does_not_use_4xx_branch(self, caplog):
        """429 should NOT produce a warning from the 4xx branch (it has its own path)."""
        mock_request = MagicMock(spec=httpx.Request)
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 429
        mock_response.headers = {}  # No Retry-After
        mock_response.request = mock_request
        error = httpx.HTTPStatusError(
            "429 Too Many Requests",
            request=mock_request,
            response=mock_response,
        )
        # Only 1 retry so it exhausts and raises without succeeding
        request_func = MagicMock(side_effect=error)

        with caplog.at_level(logging.WARNING, logger="api_client"):
            with pytest.raises(httpx.HTTPStatusError):
                api_client._retry_request(request_func, max_retries=1, delay=0.01)

        # The 4xx branch warning should NOT appear for 429
        four_xx_warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING" and "API request failed with HTTP" in r.message
        ]
        assert not four_xx_warnings, "429 should not trigger the 4xx branch warning"

    def test_sanitize_fn_applied_to_exception(self, caplog):
        """The exception in the warning message passes through _sanitize_fn."""
        error = _make_http_error(401)

        with patch.object(api_client, "_sanitize_fn", side_effect=lambda x: f"SANITIZED({str(x)})"):
            request_func = MagicMock(side_effect=error)

            with caplog.at_level(logging.WARNING, logger="api_client"):
                with pytest.raises(httpx.HTTPStatusError):
                    api_client._retry_request(request_func, max_retries=1, delay=0.01)

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert warnings
        assert "SANITIZED(" in warnings[0].message


class TestConnectErrorHint:
    """Verify _CONNECT_ERROR_HINT constant and its appearance in retry warnings."""

    def test_connect_error_hint_constant_exists(self):
        assert hasattr(api_client, "_CONNECT_ERROR_HINT")
        assert "Connection failed" in api_client._CONNECT_ERROR_HINT

    def test_connect_error_hint_in_all(self):
        assert "_CONNECT_ERROR_HINT" in api_client.__all__

    def test_connect_error_hint_in_retry_warning(self, caplog):
        """ConnectError during a retry attempt should surface the connect-error hint."""
        mock_request = MagicMock(spec=httpx.Request)
        error = httpx.ConnectError("Connection refused", request=mock_request)
        request_func = MagicMock(side_effect=error)

        with caplog.at_level(logging.WARNING, logger="api_client"):
            with pytest.raises(httpx.ConnectError):
                api_client._retry_request(request_func, max_retries=2, delay=0.01)

        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert warnings, "Expected a WARNING log for ConnectError"
        warning_text = warnings[0].message
        assert "hint: Connection failed" in warning_text


class TestServerErrorHint:
    """Verify _SERVER_ERROR_HINT is defined and emitted on 5xx retries."""

    def test_server_error_hint_constant_exists(self):
        assert hasattr(api_client, "_SERVER_ERROR_HINT")
        assert "Server error" in api_client._SERVER_ERROR_HINT
        assert "status.controld.com" in api_client._SERVER_ERROR_HINT

    def test_server_error_hint_in_all(self):
        assert "_SERVER_ERROR_HINT" in api_client.__all__

    def test_500_retry_warning_includes_hint(self, caplog):
        """A 500 response that is retried should include the server error hint."""
        error = _make_http_error(500)
        request_func = MagicMock(side_effect=error)

        with caplog.at_level(logging.WARNING, logger="api_client"):
            with pytest.raises(httpx.HTTPStatusError):
                api_client._retry_request(request_func, max_retries=2, delay=0.01)

        retry_warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING" and "Retrying" in r.message
        ]
        assert retry_warnings, "Expected a retry WARNING for HTTP 500"
        assert "hint: Server error" in retry_warnings[0].message

    def test_503_retry_warning_includes_hint(self, caplog):
        """A 503 response that is retried should also include the server error hint."""
        error = _make_http_error(503)
        request_func = MagicMock(side_effect=error)

        with caplog.at_level(logging.WARNING, logger="api_client"):
            with pytest.raises(httpx.HTTPStatusError):
                api_client._retry_request(request_func, max_retries=2, delay=0.01)

        retry_warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING" and "Retrying" in r.message
        ]
        assert retry_warnings, "Expected a retry WARNING for HTTP 503"
        assert "hint: Server error" in retry_warnings[0].message

    def test_timeout_hint_unchanged(self, caplog):
        """_TIMEOUT_HINT should still appear for TimeoutException, not _SERVER_ERROR_HINT."""
        error = httpx.TimeoutException("timed out", request=MagicMock())
        request_func = MagicMock(side_effect=error)

        with caplog.at_level(logging.WARNING, logger="api_client"):
            with pytest.raises(httpx.TimeoutException):
                api_client._retry_request(request_func, max_retries=2, delay=0.01)

        retry_warnings = [
            r for r in caplog.records
            if r.levelname == "WARNING" and "Retrying" in r.message
        ]
        assert retry_warnings
        assert api_client._TIMEOUT_HINT in retry_warnings[0].message
        assert "Server error" not in retry_warnings[0].message


class TestRetryRequestGuards:
    """Verify _retry_request raises RuntimeError for max_retries <= 0 (empty-range guard)."""

    def test_retry_request_zero_max_retries_raises(self):
        """_retry_request raises RuntimeError when max_retries=0 (empty range guard)."""
        with pytest.raises(RuntimeError, match="_retry_request called with max_retries=0"):
            api_client._retry_request(lambda: None, max_retries=0)

    def test_retry_request_negative_max_retries_raises(self):
        """Negative max_retries also produces an empty range, triggering the RuntimeError."""
        with pytest.raises(RuntimeError, match="_retry_request called"):
            api_client._retry_request(lambda: None, max_retries=-1)
