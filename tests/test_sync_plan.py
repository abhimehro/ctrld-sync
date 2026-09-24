"""Tests for fetching and validating folder data during sync planning."""

import logging

import gh_client
import sync


def test_fetch_all_folder_data_revalidates_warmed_cache(monkeypatch, caplog):
    """JSON cached by warm-up must still pass the folder schema validator."""
    url = "https://example.com/malformed.json"
    monkeypatch.setitem(sync._cache, url, {"rules": []})
    monkeypatch.setattr(sync, "validate_folder_url", lambda _url: True)
    monkeypatch.setattr(gh_client, "validate_folder_url", lambda _url: True)

    with caplog.at_level(logging.ERROR):
        result = sync.plan._fetch_all_folder_data([url])

    assert result is None
    assert "No valid folder data found" in caplog.text
