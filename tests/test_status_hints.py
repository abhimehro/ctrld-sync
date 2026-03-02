"""
Tests for actionable HTTP status code hints in API error messages.

Covers:
- _STATUS_HINTS dict contains expected codes
- fetch_folder_data() re-raises with hint on HTTP error
- push_rules() includes hint in log message on HTTP error
"""

import os
import sys
from unittest.mock import MagicMock, patch

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main


def _make_http_status_error(status_code: int) -> httpx.HTTPStatusError:
    """Create a minimal HTTPStatusError with the given status code."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_request = MagicMock(spec=httpx.Request)
    return httpx.HTTPStatusError(
        f"{status_code} Error",
        request=mock_request,
        response=mock_response,
    )


class TestStatusHintsDict:
    """Verify the _STATUS_HINTS constant exists and contains the required entries."""

    def test_hints_dict_exists(self):
        assert hasattr(main, "_STATUS_HINTS")
        assert isinstance(main._STATUS_HINTS, dict)

    def test_hint_401(self):
        assert 401 in main._STATUS_HINTS
        assert "TOKEN" in main._STATUS_HINTS[401]

    def test_hint_403(self):
        assert 403 in main._STATUS_HINTS
        assert "permission" in main._STATUS_HINTS[403].lower()

    def test_hint_404(self):
        assert 404 in main._STATUS_HINTS
        assert "folder" in main._STATUS_HINTS[404].lower()

    def test_hint_429(self):
        assert 429 in main._STATUS_HINTS
        assert "rate" in main._STATUS_HINTS[429].lower()

    def test_hint_500(self):
        assert 500 in main._STATUS_HINTS

    def test_unknown_code_not_in_hints(self):
        # Codes not in the dict should gracefully fall back via .get()
        assert main._STATUS_HINTS.get(418, "HTTP 418") == "HTTP 418"


class TestFetchFolderDataHints:
    """Verify fetch_folder_data() surfaces actionable hints on HTTP errors."""

    def test_401_hint_in_message(self):
        err = _make_http_status_error(401)
        with patch.object(main, "_gh_get", side_effect=err):
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                main.fetch_folder_data("https://example.com/data.json")
        msg = str(exc_info.value)
        assert "TOKEN" in msg

    def test_403_hint_in_message(self):
        err = _make_http_status_error(403)
        with patch.object(main, "_gh_get", side_effect=err):
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                main.fetch_folder_data("https://example.com/data.json")
        msg = str(exc_info.value)
        assert "permission" in msg.lower()

    def test_404_hint_in_message(self):
        err = _make_http_status_error(404)
        with patch.object(main, "_gh_get", side_effect=err):
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                main.fetch_folder_data("https://example.com/data.json")
        msg = str(exc_info.value)
        assert "folder" in msg.lower()

    def test_429_hint_in_message(self):
        err = _make_http_status_error(429)
        with patch.object(main, "_gh_get", side_effect=err):
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                main.fetch_folder_data("https://example.com/data.json")
        msg = str(exc_info.value)
        assert "rate" in msg.lower()

    def test_unknown_status_fallback(self):
        err = _make_http_status_error(503)
        with patch.object(main, "_gh_get", side_effect=err):
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                main.fetch_folder_data("https://example.com/data.json")
        msg = str(exc_info.value)
        assert "HTTP 503" in msg

    def test_url_sanitized_in_message(self):
        """URL in the error message must pass through sanitize_for_log (no creds)."""
        err = _make_http_status_error(401)
        secret_url = "https://example.com/data.json?token=SUPERSECRET"
        with patch.object(main, "_gh_get", side_effect=err):
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                main.fetch_folder_data(secret_url)
        msg = str(exc_info.value)
        assert "SUPERSECRET" not in msg

    def test_invalid_folder_data_still_raises_key_error(self):
        """Validation failure (not HTTP error) still raises KeyError."""
        with patch.object(main, "_gh_get", return_value={"bad": "data"}):
            with patch.object(main, "validate_folder_data", return_value=False):
                with pytest.raises(KeyError):
                    main.fetch_folder_data("https://example.com/data.json")


class TestPushRulesBatchHints:
    """Verify push_rules() includes status hints in log messages on HTTP errors."""

    def test_401_hint_logged_on_batch_failure(self):
        err = _make_http_status_error(401)
        mock_client = MagicMock()
        mock_log = MagicMock()

        with patch.object(main, "_api_post_form", side_effect=err):
            with patch.object(main, "log", mock_log):
                with patch.object(main, "USE_COLORS", False):
                    main.push_rules(
                        "profile", "folder", "fid", 1, 1,
                        ["example.com"], set(), mock_client
                    )

        error_calls = str(mock_log.error.call_args_list)
        assert "TOKEN" in error_calls

    def test_429_hint_logged_on_batch_failure(self):
        err = _make_http_status_error(429)
        mock_client = MagicMock()
        mock_log = MagicMock()

        with patch.object(main, "_api_post_form", side_effect=err):
            with patch.object(main, "log", mock_log):
                with patch.object(main, "USE_COLORS", False):
                    main.push_rules(
                        "profile", "folder", "fid", 1, 1,
                        ["example.com"], set(), mock_client
                    )

        error_calls = str(mock_log.error.call_args_list)
        assert "rate" in error_calls.lower()

    def test_unknown_status_fallback_logged(self):
        err = _make_http_status_error(503)
        mock_client = MagicMock()
        mock_log = MagicMock()

        with patch.object(main, "_api_post_form", side_effect=err):
            with patch.object(main, "log", mock_log):
                with patch.object(main, "USE_COLORS", False):
                    main.push_rules(
                        "profile", "folder", "fid", 1, 1,
                        ["example.com"], set(), mock_client
                    )

        error_calls = str(mock_log.error.call_args_list)
        assert "HTTP 503" in error_calls
