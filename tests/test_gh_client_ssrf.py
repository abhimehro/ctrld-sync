"""SSRF regression tests for the gh_client fetch path.

These prove that _gh_get() and fetch_folder_data() reject malicious URLs
before opening an HTTP stream, even when the cache is seeded.
"""

import socket
from unittest.mock import MagicMock, patch

import httpx
import pytest

import cache
import gh_client
import validation


@pytest.fixture(autouse=True)
def _clear_state(_default_test_blocklist_allowlist):
    """Reset allowlist to production defaults and clear all caches between SSRF tests."""
    import main

    main.set_allowed_blocklist_domains(None)
    gh_client._cache.clear()
    cache._disk_cache.clear()
    validation.validate_folder_url.cache_clear()
    validation.validate_hostname.cache_clear()
    yield
    main.set_allowed_blocklist_domains(None)
    gh_client._cache.clear()
    cache._disk_cache.clear()
    validation.validate_folder_url.cache_clear()
    validation.validate_hostname.cache_clear()


def _addrinfo(ip: str):
    """Return a socket.getaddrinfo replacement that resolves every host to *ip*."""

    def _resolve(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, 0))]

    return _resolve


def _make_valid_folder_response() -> MagicMock:
    """Build a mock httpx streaming response containing valid folder data."""
    body = b'{"group": {"group": "Test"}, "rules": [{"PK": "example.com"}]}'
    response = MagicMock()
    response.status_code = 200
    response.headers = httpx.Headers(
        {
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
        }
    )
    response.iter_bytes = MagicMock(return_value=[body])
    response.raise_for_status = MagicMock()
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=None)
    return response


class TestGhClientSSRF:
    """Verify _gh_get() and fetch_folder_data() fail closed on unsafe URLs."""

    @pytest.mark.parametrize(
        "func,url",
        [
            (gh_client._gh_get, "http://example.com/data.json"),
            (gh_client._gh_get, "https://127.0.0.1/data.json"),
            (gh_client._gh_get, "https://169.254.169.254/latest/meta-data/"),
            (gh_client._gh_get, "https://example.com/data.json"),
            (gh_client._gh_get, "https://10.0.0.1/data.json"),
            (gh_client.fetch_folder_data, "https://127.0.0.1/data.json"),
            (gh_client.fetch_folder_data, "https://example.com/data.json"),
        ],
    )
    def test_rejects_unsafe_url_without_streaming(self, func, url):
        with patch.object(gh_client._gh, "stream") as mock_stream:
            with pytest.raises(ValueError, match="Unsafe or invalid blocklist URL"):
                func(url)
        mock_stream.assert_not_called()

    @pytest.mark.parametrize(
        "func",
        [gh_client._gh_get, gh_client.fetch_folder_data],
    )
    def test_rejects_allowlisted_domain_resolving_to_private_ip(
        self, monkeypatch, func
    ):
        monkeypatch.setattr(socket, "getaddrinfo", _addrinfo("127.0.0.1"))
        with patch.object(gh_client._gh, "stream") as mock_stream:
            with pytest.raises(ValueError, match="Unsafe or invalid blocklist URL"):
                func("https://raw.githubusercontent.com/evil/repo/data.json")
        mock_stream.assert_not_called()

    @pytest.mark.parametrize(
        "func",
        [gh_client._gh_get, gh_client.fetch_folder_data],
    )
    def test_accepts_allowlisted_public_url(self, monkeypatch, func):
        monkeypatch.setattr(socket, "getaddrinfo", _addrinfo("8.8.8.8"))
        response = _make_valid_folder_response()
        with patch.object(
            gh_client._gh, "stream", return_value=response
        ) as mock_stream:
            result = func("https://raw.githubusercontent.com/org/repo/data.json")
        mock_stream.assert_called_once()
        assert result["group"]["group"] == "Test"  # nosec B101

    def test_memory_cache_cannot_bypass_validation(self):
        bad_url = "https://127.0.0.1/data.json"
        gh_client._cache[bad_url] = {"group": {"group": "Poison"}}
        with patch.object(gh_client._gh, "stream") as mock_stream:
            with pytest.raises(ValueError, match="Unsafe or invalid blocklist URL"):
                gh_client._gh_get(bad_url)
        mock_stream.assert_not_called()

    def test_disk_cache_cannot_bypass_validation(self):
        bad_url = "https://169.254.169.254/latest/meta-data/"
        cache._disk_cache[bad_url] = {
            "data": {"group": {"group": "Poison"}},
            "etag": None,
            "last_modified": None,
            "fetched_at": 0.0,
            "last_validated": 0.0,
        }
        with patch.object(gh_client._gh, "stream") as mock_stream:
            with pytest.raises(ValueError, match="Unsafe or invalid blocklist URL"):
                gh_client._gh_get(bad_url)
        mock_stream.assert_not_called()
