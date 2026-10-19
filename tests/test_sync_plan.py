"""Tests for fetching and validating folder data during sync planning."""

import logging
from unittest.mock import patch

import cache
import sync


def test_fetch_all_folder_data_revalidates_warmed_cache(monkeypatch, caplog):
    """JSON cached by warm-up must still pass the folder schema validator.

    When the cached payload fails validation, the entry is evicted from both
    memory and disk caches and the URL is re-fetched via fetch_folder_data.
    """
    url = "https://example.com/malformed.json"
    malformed_data = {"rules": []}
    valid_data = {
        "group": {"group": "Test Folder"},
        "rules": [{"PK": "example.com"}],
    }
    monkeypatch.setitem(sync._cache, url, malformed_data)
    monkeypatch.setitem(
        cache._disk_cache,
        url,
        {"data": malformed_data, "fetched_at": 0, "last_validated": 0},
    )
    monkeypatch.setattr(sync, "validate_folder_url", lambda _url: True)

    with (
        patch("sync.plan.fetch_folder_data", return_value=valid_data) as mock_fetch,
        patch(
            "sync.plan.validate_folder_data", wraps=sync.plan.validate_folder_data
        ) as mock_validate_data,
        caplog.at_level(logging.ERROR),
    ):
        result = sync.plan._fetch_all_folder_data([url])

    mock_validate_data.assert_called_once_with(malformed_data, url)
    mock_fetch.assert_called_once_with(url)
    assert result == [valid_data]
    with sync._cache_lock:
        assert url not in sync._cache
    assert url not in cache._disk_cache
