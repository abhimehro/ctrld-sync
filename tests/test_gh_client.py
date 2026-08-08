"""Characterization and regression tests for gh_client.py."""

import json
import logging
import os
import sys
import threading
import time
from unittest.mock import MagicMock, patch

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import api_client
import cache
import config
import gh_client
import validation


def _make_json_body(data: dict) -> bytes:
    return json.dumps(data).encode()


def _make_stream_response(
    status_code: int = 200,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    raise_for_status: Exception | None = None,
) -> MagicMock:
    """Build a MagicMock that behaves like an httpx streaming response context."""
    response = MagicMock()
    response.status_code = status_code
    merged_headers = {"Content-Type": "application/json"} | (headers or {})
    response.headers = httpx.Headers(merged_headers)
    if body is not None:
        response.iter_bytes = MagicMock(
            side_effect=lambda chunk_size=16 * 1024: (
                body[i : i + chunk_size] for i in range(0, len(body), chunk_size)
            )
        )
    else:
        response.iter_bytes = MagicMock(return_value=[])
    response.raise_for_status = MagicMock()
    if raise_for_status is not None:
        response.raise_for_status.side_effect = raise_for_status
    response.__enter__ = MagicMock(return_value=response)
    response.__exit__ = MagicMock(return_value=None)
    response.close = MagicMock()
    return response


def _make_http_status_error(
    status_code: int, message: str | None = None
) -> httpx.HTTPStatusError:
    request = MagicMock(spec=httpx.Request)
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.request = request
    return httpx.HTTPStatusError(
        message or f"{status_code} Error",
        request=request,
        response=response,
    )


@pytest.fixture(autouse=True)
def _isolate_client_state():
    """Snapshot live stats/dicts so tests can assert on deltas, not absolutes."""
    stats_before = dict(cache._cache_stats)
    api_before = dict(api_client._api_stats)
    token_before = validation._token
    gh_client._cache.clear()
    cache._disk_cache.clear()
    validation.validate_folder_url.cache_clear()
    validation.validate_hostname.cache_clear()
    yield
    gh_client._cache.clear()
    cache._disk_cache.clear()
    validation.validate_folder_url.cache_clear()
    validation.validate_hostname.cache_clear()
    cache._cache_stats.clear()
    cache._cache_stats.update(stats_before)
    api_client._api_stats.clear()
    api_client._api_stats.update(api_before)
    validation.set_token_for_redaction(token_before)


class TestParseAndCacheResponse:
    """Regression tests for _parse_and_cache_response and its helpers."""

    def test_parses_valid_json_and_caches(self):
        url = "https://example.com/valid.json"
        data = {"group": {"group": "Test"}}
        body = _make_json_body(data)
        response = _make_stream_response(body=body)

        misses_before = cache._cache_stats["misses"]
        result = gh_client._parse_and_cache_response(url, response)

        assert result == data  # nosec B101
        assert cache._cache_stats["misses"] == misses_before + 1  # nosec B101
        assert cache._disk_cache[url]["data"] == data  # nosec B101
        assert "etag" in cache._disk_cache[url]  # nosec B101
        assert "fetched_at" in cache._disk_cache[url]  # nosec B101
        assert "last_validated" in cache._disk_cache[url]  # nosec B101

    @pytest.mark.parametrize(
        "content_type",
        [
            "application/json",
            "text/plain; charset=utf-8",
            "text/json",
            "application/json; charset=utf-8",
        ],
    )
    def test_accepts_allowed_content_types(self, content_type):
        url = "https://example.com/ct.json"
        data = {"group": {"group": "Test"}}
        response = _make_stream_response(
            body=_make_json_body(data), headers={"Content-Type": content_type}
        )

        result = gh_client._parse_and_cache_response(url, response)
        assert result == data  # nosec B101

    @pytest.mark.parametrize(
        "content_type",
        ["text/html", "application/xml"],
    )
    def test_rejects_disallowed_content_types(self, content_type):
        url = "https://example.com/ct.json"
        response = _make_stream_response(
            body=b'{"group": {"group": "Test"}}',
            headers={"Content-Type": content_type},
        )

        with pytest.raises(ValueError, match="Invalid Content-Type"):
            gh_client._parse_and_cache_response(url, response)

    def test_content_length_too_large_string_does_not_spuriously_raise(self, caplog):
        """Regression for the crafted-Content-Length bug (ABHI-1634 §2a)."""
        url = "https://example.com/crafted.json"
        data = {"group": {"group": "Test"}}
        response = _make_stream_response(
            body=_make_json_body(data),
            headers={"Content-Length": "Response too large"},
        )

        with caplog.at_level(logging.WARNING):
            result = gh_client._parse_and_cache_response(url, response)

        assert result == data  # nosec B101
        assert "Malformed Content-Length header" in caplog.text  # nosec B101
        response.iter_bytes.assert_called_once()

    def test_malformed_content_length_falls_back_to_streaming(self, caplog):
        url = "https://example.com/malformed.json"
        data = {"group": {"group": "Test"}}
        response = _make_stream_response(
            body=_make_json_body(data),
            headers={"Content-Length": "abc"},
        )

        with caplog.at_level(logging.WARNING):
            result = gh_client._parse_and_cache_response(url, response)

        assert result == data  # nosec B101
        assert "Malformed Content-Length header" in caplog.text  # nosec B101

    def test_content_length_over_max_raises_before_reading_body(self):
        url = "https://example.com/huge.json"
        response = _make_stream_response(
            body=b'{"group": {"group": "Test"}}',
            headers={"Content-Length": str(config.MAX_RESPONSE_SIZE + 1)},
        )

        with pytest.raises(ValueError, match="Response too large"):
            gh_client._parse_and_cache_response(url, response)

        response.iter_bytes.assert_not_called()

    def test_streaming_body_over_max_raises_during_iteration(self):
        url = "https://example.com/huge.json"
        response = _make_stream_response(
            body=b"x" * (config.MAX_RESPONSE_SIZE + 1),
            headers={"Content-Length": str(config.MAX_RESPONSE_SIZE - 1)},
        )

        with pytest.raises(ValueError, match="Response too large"):
            gh_client._parse_and_cache_response(url, response)

        response.iter_bytes.assert_called_once()

    def test_invalid_json_does_not_write_disk_cache_entry(self):
        url = "https://example.com/bad.json"
        response = _make_stream_response(body=b"not json")

        with pytest.raises(ValueError, match="Invalid JSON response"):
            gh_client._parse_and_cache_response(url, response)

        assert url not in cache._disk_cache  # nosec B101


class TestGhGet:
    """Regression tests for _gh_get cache and HTTP handling."""

    def test_in_memory_hit_returns_cached_object(self):
        url = "https://example.com/cached.json"
        data = {"group": {"group": "Test"}}
        gh_client._cache[url] = data

        hits_before = cache._cache_stats["hits"]
        with patch.object(gh_client._gh, "stream") as mock_stream:
            result = gh_client._gh_get(url)

        assert result is data  # nosec B101
        assert cache._cache_stats["hits"] == hits_before + 1  # nosec B101
        mock_stream.assert_not_called()

    def test_disk_ttl_hit_returns_without_http_and_counts_fetch(self):
        url = "https://example.com/ttl.json"
        data = {"group": {"group": "Test"}}
        cache._disk_cache[url] = {
            "data": data,
            "etag": None,
            "last_modified": None,
            "fetched_at": time.time(),
            "last_validated": time.time(),
        }

        hits_before = cache._cache_stats["hits"]
        fetches_before = api_client._api_stats["blocklist_fetches"]

        with patch.object(gh_client._gh, "stream") as mock_stream:
            result = gh_client._gh_get(url)

        assert result == data  # nosec B101
        assert result is data  # nosec B101
        assert cache._cache_stats["hits"] == hits_before + 1  # nosec B101
        assert api_client._api_stats["blocklist_fetches"] == fetches_before + 1  # nosec B101
        assert gh_client._cache[url] is data  # nosec B101
        mock_stream.assert_not_called()

    @pytest.mark.parametrize(
        ("etag", "last_modified", "expected_headers"),
        [
            ("abc123", None, {"If-None-Match": "abc123"}),
            (
                None,
                "Mon, 01 Jan 2024 00:00:00 GMT",
                {"If-Modified-Since": "Mon, 01 Jan 2024 00:00:00 GMT"},
            ),
            (
                "abc123",
                "Mon, 01 Jan 2024 00:00:00 GMT",
                {
                    "If-None-Match": "abc123",
                    "If-Modified-Since": "Mon, 01 Jan 2024 00:00:00 GMT",
                },
            ),
            (None, None, {}),
        ],
    )
    def test_conditional_headers_from_disk_cache(
        self, etag, last_modified, expected_headers
    ):
        url = "https://example.com/cond.json"
        data = {"group": {"group": "Test"}}
        cache._disk_cache[url] = {
            "data": data,
            "etag": etag,
            "last_modified": last_modified,
            "fetched_at": 0.0,
            "last_validated": 0.0,
        }

        captured = {}

        def mock_stream(method, stream_url, headers=None):
            captured["headers"] = headers
            return _make_stream_response(status_code=304, headers={})

        with patch.object(gh_client._gh, "stream", side_effect=mock_stream):
            result = gh_client._gh_get(url)

        assert result == data  # nosec B101
        assert captured["headers"] == expected_headers  # nosec B101

    def test_304_with_cached_data_validates_and_updates_timestamp(self):
        url = "https://example.com/304.json"
        data = {"group": {"group": "Test"}}
        cache._disk_cache[url] = {
            "data": data,
            "etag": "abc123",
            "last_modified": None,
            "fetched_at": 0.0,
            "last_validated": 0.0,
        }

        validations_before = cache._cache_stats["validations"]
        response = _make_stream_response(status_code=304)

        with patch.object(gh_client._gh, "stream", return_value=response):
            result = gh_client._gh_get(url)

        assert result is data  # nosec B101
        assert cache._cache_stats["validations"] == validations_before + 1  # nosec B101
        assert gh_client._cache[url] is data  # nosec B101
        assert cache._disk_cache[url]["last_validated"] > 0.0  # nosec B101

    def test_304_without_cached_data_retries_unconditionally(self, caplog):
        url = "https://example.com/304-retry.json"
        cache._disk_cache[url] = {
            "etag": "abc123",
            "last_modified": None,
            "fetched_at": 0.0,
            "last_validated": 0.0,
        }
        data = {"group": {"group": "Test"}}

        resp_304 = _make_stream_response(status_code=304, headers={})
        resp_200 = _make_stream_response(status_code=200, body=_make_json_body(data))

        errors_before = cache._cache_stats["errors"]

        call_count = []

        def mock_stream(method, stream_url, headers=None):
            if not call_count:
                call_count.append(1)
                assert headers.get("If-None-Match") == "abc123"  # nosec B101
                return resp_304
            call_count.append(2)
            assert headers == {}  # nosec B101
            return resp_200

        with caplog.at_level(logging.WARNING):
            with patch.object(
                gh_client._gh, "stream", side_effect=mock_stream
            ) as patched_stream:
                result = gh_client._gh_get(url)

        assert result == data  # nosec B101
        assert cache._cache_stats["errors"] == errors_before + 1  # nosec B101
        assert "Got 304 but no cached data" in caplog.text  # nosec B101
        assert patched_stream.call_count == 2  # nosec B101

    def test_http_status_error_is_sanitized_and_suppresses_cause(self, monkeypatch):
        url = "https://example.com/secret.json?token=TOPSECRET"
        err = _make_http_status_error(404, "404 Not Found: token=TOPSECRET")
        response = _make_stream_response(raise_for_status=err)

        monkeypatch.setattr(validation, "_token", "TOPSECRET")

        with patch.object(gh_client._gh, "stream", return_value=response):
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                gh_client._gh_get(url)

        assert "TOPSECRET" not in str(exc_info.value)  # nosec B101
        assert "[REDACTED]" in str(exc_info.value)  # nosec B101
        assert exc_info.value.__cause__ is None  # nosec B101

    def test_double_checked_locking_returns_first_callers_object(self):
        url = "https://example.com/race.json"
        data = {"group": {"group": "Test"}}
        barrier = threading.Barrier(2, timeout=10)

        def make_response(*args, **kwargs):
            return _make_stream_response(body=_make_json_body(data))

        def wrapped_parse(stream_url, r):
            # Parse without touching the disk cache so the second thread cannot
            # take a disk TTL shortcut before the double-checked lock.
            body = b"".join(r.iter_bytes())
            result = json.loads(body)
            barrier.wait()
            return result

        results = []
        errors = []

        def fetch():
            try:
                results.append(gh_client._gh_get(url))
            except Exception as e:  # pragma: no cover
                errors.append(e)

        with patch.object(gh_client._gh, "stream", side_effect=make_response):
            with patch.object(
                gh_client, "_parse_and_cache_response", side_effect=wrapped_parse
            ):
                threads = [threading.Thread(target=fetch) for _ in range(2)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()

        assert not errors  # nosec B101
        assert len(results) == 2  # nosec B101
        assert results[0] is results[1]  # nosec B101


class TestFetchFolderData:
    """Regression tests for fetch_folder_data error/hint handling."""

    def test_returns_data_when_valid(self):
        url = "https://example.com/folder.json"
        data = {"group": {"group": "Test"}, "rules": [{"PK": "example.com"}]}

        with patch.object(gh_client, "_gh_get", return_value=data):
            result = gh_client.fetch_folder_data(url)

        assert result is data  # nosec B101

    def test_http_error_includes_status_hint_and_sanitized_url(self):
        url = "https://example.com/folder.json?token=SECRET"
        err = _make_http_status_error(401, "401 Unauthorized")

        with patch.object(gh_client, "_gh_get", side_effect=err):
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                gh_client.fetch_folder_data(url)

        msg = str(exc_info.value)
        assert "TOKEN" in msg  # nosec B101
        assert "SECRET" not in msg  # nosec B101
        assert "example.com/folder.json" in msg  # nosec B101

    def test_validation_failure_raises_key_error(self):
        url = "https://example.com/folder.json"

        with patch.object(gh_client, "_gh_get", return_value={"bad": "data"}):
            with patch.object(gh_client, "validate_folder_data", return_value=False):
                with pytest.raises(KeyError, match="Invalid folder data"):
                    gh_client.fetch_folder_data(url)


class TestWarmUpCache:
    """Regression tests for warm_up_cache."""

    def test_swallows_per_url_exceptions_and_completes(self, monkeypatch, caplog):
        urls = ["https://example.com/ok.json", "https://example.com/fail.json"]

        def fake_gh_get(stream_url: str) -> dict:
            if "fail" in stream_url:
                raise ValueError("boom")
            return {"group": {"group": "Test"}}

        monkeypatch.setattr(gh_client, "validate_folder_url", lambda url: True)
        monkeypatch.setattr(gh_client, "_gh_get", fake_gh_get)
        completion = MagicMock()
        monkeypatch.setattr(gh_client, "_print_completion", completion)
        monkeypatch.setattr(gh_client, "_clear_current_line", MagicMock())
        monkeypatch.setattr(gh_client, "render_progress_bar", MagicMock())
        monkeypatch.setattr(gh_client, "USE_COLORS", True)

        with caplog.at_level(logging.WARNING):
            gh_client.warm_up_cache(urls)

        completion.assert_called_once_with("Warming up cache: Done!")
        assert any("Failed to pre-fetch" in r.message for r in caplog.records)  # nosec B101

    def test_skips_urls_already_in_memory_cache(self, monkeypatch):
        url = "https://example.com/already.json"
        data = {"group": {"group": "Test"}}
        gh_client._cache[url] = data

        fake_gh_get = MagicMock()
        monkeypatch.setattr(gh_client, "_gh_get", fake_gh_get)

        gh_client.warm_up_cache([url])

        fake_gh_get.assert_not_called()


class TestValidateAndFetchUrl:
    """Regression tests for _validate_and_fetch_url."""

    def test_returns_none_for_invalid_url(self, monkeypatch):
        url = "https://notallowed.example/data.json"
        fake_gh_get = MagicMock()
        monkeypatch.setattr(gh_client, "_gh_get", fake_gh_get)

        result = gh_client._validate_and_fetch_url(url)

        assert result is None  # nosec B101
        fake_gh_get.assert_not_called()
