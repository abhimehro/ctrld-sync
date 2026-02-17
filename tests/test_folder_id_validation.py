import importlib
import sys
from unittest.mock import MagicMock, patch

import httpx
import pytest

import main


def reload_main_with_env(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    with patch("sys.stderr") as mock_stderr, patch("sys.stdout") as mock_stdout:
        mock_stderr.isatty.return_value = True
        mock_stdout.isatty.return_value = True

        module = sys.modules.get("main")
        if module is None:
            module = importlib.import_module("main")

        importlib.reload(module)
        return module


def test_verify_access_and_get_folders_filters_malicious_ids(monkeypatch):
    """
    Verify that verify_access_and_get_folders filters out malicious Folder IDs
    containing path traversal characters (../).
    """
    m = reload_main_with_env(monkeypatch)
    mock_client = MagicMock()

    # Malicious Folder ID with path traversal
    malicious_id = "../../etc/passwd"
    # Malicious Folder ID with dangerous characters
    malicious_id_2 = "foo;rm -rf /"

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "body": {
            "groups": [
                {"group": "Safe Folder", "PK": "safe_id_123"},
                {"group": "Safe Folder 2", "PK": "safe-id-456_789"},
                {"group": "Malicious Folder", "PK": malicious_id},
                {"group": "Malicious Folder 2", "PK": malicious_id_2}
            ]
        }
    }
    mock_client.get.return_value = mock_response
    mock_response.raise_for_status.return_value = None

    # Function should filter out malicious IDs
    result = m.verify_access_and_get_folders(mock_client, "valid_profile")

    assert result is not None

    # Check that valid IDs are preserved
    assert "Safe Folder" in result
    assert result["Safe Folder"] == "safe_id_123"
    assert "Safe Folder 2" in result
    assert result["Safe Folder 2"] == "safe-id-456_789"

    # Check that malicious IDs are removed
    assert "Malicious Folder" not in result
    assert "Malicious Folder 2" not in result
