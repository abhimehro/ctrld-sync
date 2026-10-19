"""Tests for fetching and validating folder data during sync planning."""

import logging
from unittest.mock import patch

import gh_client
import sync


def test_fetch_all_folder_data_revalidates_warmed_cache(monkeypatch, caplog):
    """JSON cached by warm-up must still pass the folder schema validator."""
    url = "https://example.com/malformed.json"
    malformed_data = {"rules": []}
    monkeypatch.setitem(sync._cache, url, malformed_data)
    monkeypatch.setattr(sync, "validate_folder_url", lambda _url: True)
    monkeypatch.setattr(gh_client, "validate_folder_url", lambda _url: True)

    with (
        patch.object(
            gh_client._gh, "stream", side_effect=AssertionError("Unexpected network access")
        ) as mock_stream,
        patch.object(
            gh_client, "validate_folder_data", wraps=gh_client.validate_folder_data
        ) as mock_validate_data,
        caplog.at_level(logging.ERROR),
    ):
        result = sync.plan._fetch_all_folder_data([url])

    mock_stream.assert_not_called()
    mock_validate_data.assert_called_once_with(malformed_data, url)
    assert result is None
    assert "No valid folder data found" in caplog.text
