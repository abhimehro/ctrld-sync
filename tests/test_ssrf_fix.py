import pytest
import httpx
from unittest.mock import MagicMock
import main

@pytest.fixture(autouse=True)
def clear_cache():
    main._cache.clear()

def test_gh_get_blocks_private_ip_after_connect(monkeypatch):
    """
    Test that _gh_get raises ValueError if the connection was established to a private IP.
    This simulates a DNS Rebinding attack where the initial check passes but the connection goes to private IP.
    """

    # Mock response stream with private IP
    mock_stream = MagicMock()
    mock_stream.get_extra_info.return_value = ('127.0.0.1', 443)

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.extensions = {"network_stream": mock_stream}
    mock_response.headers = {}
    mock_response.iter_bytes.return_value = [b'{}']
    mock_response.raise_for_status.return_value = None

    # Context manager mock for stream()
    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_response
    mock_context.__exit__.return_value = None

    # Mock _gh.stream
    mock_gh = MagicMock()
    mock_gh.stream.return_value = mock_context

    monkeypatch.setattr(main, "_gh", mock_gh)

    # We expect ValueError because of our security fix
    # Before the fix, this test will FAIL (it won't raise)
    with pytest.raises(ValueError, match="Security Alert: Domain resolved to private IP"):
        main._gh_get("https://example.com/config.json")

def test_gh_get_allows_public_ip_after_connect(monkeypatch):
    """
    Test that _gh_get allows connection if established to a public IP.
    """

    # Mock response stream with public IP
    mock_stream = MagicMock()
    mock_stream.get_extra_info.return_value = ('8.8.8.8', 443)

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.extensions = {"network_stream": mock_stream}
    mock_response.headers = {}
    mock_response.iter_bytes.return_value = [b'{"valid": "json"}']
    mock_response.raise_for_status.return_value = None

    # Context manager mock
    mock_context = MagicMock()
    mock_context.__enter__.return_value = mock_response
    mock_context.__exit__.return_value = None

    # Mock _gh.stream
    mock_gh = MagicMock()
    mock_gh.stream.return_value = mock_context

    monkeypatch.setattr(main, "_gh", mock_gh)

    # Should not raise
    result = main._gh_get("https://example.com/config.json")
    assert result == {"valid": "json"}
