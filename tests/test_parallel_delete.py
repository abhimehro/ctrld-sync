
import concurrent.futures
import time
from unittest.mock import MagicMock
import pytest
import main

def test_delete_existing_folders_parallel(monkeypatch):
    """
    Verify that delete_existing_folders_parallel:
    1. Runs in parallel (speed check).
    2. Updates existing_folders correctly.
    3. Returns True if deletions occurred.
    """

    # Mock delete_folder to simulate network delay
    # Each deletion takes 0.1s
    mock_delete = MagicMock()
    def slow_delete(client, profile_id, name, folder_id):
        time.sleep(0.1)
        return True

    mock_delete.side_effect = slow_delete
    monkeypatch.setattr(main, "delete_folder", mock_delete)

    # Mock log to avoid clutter
    mock_log = MagicMock()
    monkeypatch.setattr(main, "log", mock_log)

    # Setup
    client = MagicMock()
    profile_id = "test_profile"

    # 10 folders to delete
    # "group" -> "group" structure mimics the API response structure used in main.py
    folder_data_list = [{"group": {"group": f"Folder {i}"}} for i in range(10)]

    # All these folders exist in existing_folders
    existing_folders = {f"Folder {i}": f"id_{i}" for i in range(10)}
    original_len = len(existing_folders)

    # Add one folder that exists but is NOT in folder_data_list (should NOT be deleted)
    existing_folders["Keep Me"] = "id_keep"

    # Add one folder in data list that does NOT exist (should check but skip deletion)
    folder_data_list.append({"group": {"group": "New Folder"}})

    start_time = time.time()
    result = main.delete_existing_folders_parallel(
        client, profile_id, folder_data_list, existing_folders
    )
    end_time = time.time()
    duration = end_time - start_time

    # Assertions
    assert result is True

    # Check that the 10 folders were deleted
    for i in range(10):
        assert f"Folder {i}" not in existing_folders

    # Check that "Keep Me" is still there
    assert "Keep Me" in existing_folders
    assert existing_folders["Keep Me"] == "id_keep"

    # Check that "New Folder" is not in existing_folders (it wasn't there to begin with)
    assert "New Folder" not in existing_folders

    # Check performance
    # 10 tasks * 0.1s = 1.0s sequential time.
    # With 5 workers, it should take roughly 0.2s + overhead.
    # We assert it takes < 0.6s to be safe but prove parallelism.
    assert duration < 0.6, f"Execution took {duration}s, expected < 0.6s (parallel)"

    # Verify mock calls
    assert mock_delete.call_count == 10

def test_delete_existing_folders_parallel_no_deletions(monkeypatch):
    """Verify behavior when no folders match."""
    client = MagicMock()
    profile_id = "test_profile"
    folder_data_list = [{"group": {"group": "Folder A"}}]
    existing_folders = {"Folder B": "id_b"} # No match

    result = main.delete_existing_folders_parallel(
        client, profile_id, folder_data_list, existing_folders
    )

    assert result is False
    assert "Folder B" in existing_folders

def test_delete_existing_folders_parallel_partial_failure(monkeypatch):
    """Verify behavior when some deletions fail."""

    # Mock delete_folder: Fail for even numbers
    mock_delete = MagicMock()
    def conditional_delete(client, profile_id, name, folder_id):
        # name is "Folder i"
        num = int(name.split()[1])
        return num % 2 != 0 # Return True for odd (success), False for even (fail)

    mock_delete.side_effect = conditional_delete
    monkeypatch.setattr(main, "delete_folder", mock_delete)

    client = MagicMock()
    profile_id = "test_profile"
    folder_data_list = [{"group": {"group": f"Folder {i}"}} for i in range(10)]
    existing_folders = {f"Folder {i}": f"id_{i}" for i in range(10)}

    result = main.delete_existing_folders_parallel(
        client, profile_id, folder_data_list, existing_folders
    )

    assert result is True # At least one succeeded

    # Check results
    for i in range(10):
        name = f"Folder {i}"
        if i % 2 != 0:
            # Odd: Succeeded, should be removed
            assert name not in existing_folders
        else:
            # Even: Failed, should remain
            assert name in existing_folders
