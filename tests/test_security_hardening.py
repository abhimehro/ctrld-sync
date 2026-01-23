import logging
import pytest
from unittest.mock import MagicMock, patch
import httpx
import main

# Mock httpx.HTTPError to include a response with sensitive data
def create_mock_error(status_code, text, request_url="https://example.com"):
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.text = text
    response.request = MagicMock(spec=httpx.Request)
    response.request.url = request_url

    # Use HTTPStatusError which accepts request and response
    error = httpx.HTTPStatusError(f"HTTP Error {status_code}", request=response.request, response=response)
    return error

def test_retry_request_sanitizes_token_in_debug_logs(caplog):
    # Setup sensitive data
    sensitive_token = "SECRET_TOKEN_123"
    main.TOKEN = sensitive_token

    # Configure logging to capture DEBUG
    caplog.set_level(logging.DEBUG)

    # Mock a request function that always raises an error with the token in response
    mock_func = MagicMock()
    error_text = f"Invalid token: {sensitive_token}"
    mock_func.side_effect = create_mock_error(401, error_text)

    # Call _retry_request (it re-raises the exception)
    with pytest.raises(httpx.HTTPError):
        # Set retries to 1 to fail fast
        main._retry_request(mock_func, max_retries=1, delay=0)

    # Check logs
    assert "Response content:" in caplog.text
    assert sensitive_token not in caplog.text
    assert "[REDACTED]" in caplog.text

def test_push_rules_sanitizes_token_in_debug_logs(caplog):
    # Setup sensitive data
    sensitive_token = "SECRET_TOKEN_456"
    main.TOKEN = sensitive_token

    # Configure logging to capture DEBUG
    caplog.set_level(logging.DEBUG)

    # Mock dependencies
    mock_client = MagicMock(spec=httpx.Client)

    # Let's mock client.post to raise error
    error_text = f"Bad Rule with token {sensitive_token}"
    mock_client.post.side_effect = create_mock_error(400, error_text)

    # Patch time.sleep to avoid waiting
    with patch("time.sleep"):
        res = main.push_rules(
            profile_id="p1",
            folder_name="f1",
            folder_id="fid1",
            do=0,
            status=1,
            hostnames=["rule1"],
            existing_rules=set(),
            client=mock_client
        )

        # push_rules catches the error and returns False (or continues if batch failed)
        assert res is False

    # Check logs
    assert "Response content:" in caplog.text
    assert sensitive_token not in caplog.text
    assert "[REDACTED]" in caplog.text

def test_api_client_configuration():
    # Setup token
    main.TOKEN = "test_token"

    with main._api_client() as client:
        # Check User-Agent
        assert client.headers["User-Agent"] == "Control-D-Sync/0.1.0"
        # Check Authorization
        assert client.headers["Authorization"] == "Bearer test_token"
        # Check follow_redirects (in httpx < 0.20 it was allow_redirects, now follow_redirects)
        assert client.follow_redirects is False

def test_gh_client_configuration():
    client = main._gh
    # Check User-Agent
    assert client.headers["User-Agent"] == "Control-D-Sync/0.1.0"
    # Check follow_redirects
    assert client.follow_redirects is False
