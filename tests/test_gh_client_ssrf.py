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


def _private_addrinfo(host, *args, **kwargs):
    """Simulate a DNS resolution to a loopback address."""
    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("127.0.0.1", 0),
        )
    ]


def _public_addrinfo(host, *args, **kwargs):
    """Simulate a DNS resolution to a public address."""
    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("8.8.8.8", 0),
        )
    ]


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


class TestGhGetSSRF:
    """Verify _gh_get() fails closed on unsafe URLs."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://example.com/data.json",
            "https://127.0.0.1/data.json",
            "https://169.254.169.254/latest/meta-data/",
            "https://example.com/data.json",
            "https://10.0.0.1/data.json",
        ],
    )
    def test_rejects_unsafe_url_without_streaming(self, url):
        with patch.object(gh_client._gh, "stream") as mock_stream:
            with pytest.raises(ValueError, match="Unsafe or invalid blocklist URL"):
                gh_client._gh_get(url)
        mock_stream.assert_not_called()

    def test_rejects_allowlisted_domain_resolving_to_private_ip(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", _private_addrinfo)
        with patch.object(gh_client._gh, "stream") as mock_stream:
            with pytest.raises(ValueError, match="Unsafe or invalid blocklist URL"):
                gh_client._gh_get(
                    "https://raw.githubusercontent.com/evil/repo/data.json"
                )
        mock_stream.assert_not_called()

    def test_accepts_allowlisted_domain_resolving_to_public_ip(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", _public_addrinfo)
        response = _make_valid_folder_response()
        with patch.object(
            gh_client._gh, "stream", return_value=response
        ) as mock_stream:
            result = gh_client._gh_get(
                "https://raw.githubusercontent.com/org/repo/data.json"
            )
        mock_stream.assert_called_once()
        assert result == {
            "group": {"group": "Test"},
            "rules": [{"PK": "example.com"}],
        }

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


class TestFetchFolderDataSSRF:
    """Verify fetch_folder_data() also fails closed."""

    def test_rejects_internal_ip(self):
        with patch.object(gh_client._gh, "stream") as mock_stream:
            with pytest.raises(ValueError, match="Unsafe or invalid blocklist URL"):
                gh_client.fetch_folder_data("https://127.0.0.1/data.json")
        mock_stream.assert_not_called()

    def test_accepts_allowlisted_public_url(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", _public_addrinfo)
        response = _make_valid_folder_response()
        with patch.object(
            gh_client._gh, "stream", return_value=response
        ) as mock_stream:
            result = gh_client.fetch_folder_data(
                "https://raw.githubusercontent.com/org/repo/data.json"
            )
        mock_stream.assert_called_once()
        assert result["group"]["group"] == "Test"
