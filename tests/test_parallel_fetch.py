
import unittest
from unittest.mock import MagicMock, patch
import time
import concurrent.futures
import sys
import os

# Add root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main

class TestParallelFetch(unittest.TestCase):
    def setUp(self):
        self.main = main
        self.client = MagicMock()
        self.profile_id = "test_profile"
        self.folder_urls = ["https://example.com/folder.json"]

        # Mock fetch_folder_data to return dummy data
        self.folder_data = {
            "group": {"group": "test_folder", "action": {"do": 0, "status": 1}},
            "rules": [{"PK": "rule1"}]
        }

    @patch("main.get_all_existing_rules")
    @patch("main.delete_folder")
    @patch("main.verify_access_and_get_folders")
    @patch("main.fetch_folder_data")
    @patch("main.validate_folder_url")
    @patch("main.countdown_timer")
    def test_parallel_execution(self, mock_timer, mock_validate, mock_fetch, mock_verify, mock_delete, mock_get_rules):
        """
        Verify that get_all_existing_rules runs in parallel with delete_folder.
        """
        # Setup mocks
        mock_validate.return_value = True
        mock_fetch.return_value = self.folder_data

        # existing folders: test_folder (to be deleted), keep_folder (to be kept)
        mock_verify.return_value = {
            "test_folder": "id_1",
            "keep_folder": "id_2"
        }

        # Latency simulation
        def slow_get_rules(*args, **kwargs):
            time.sleep(1.0)
            return {"rule_from_keep"}

        def slow_delete(*args, **kwargs):
            time.sleep(1.0)
            return True

        mock_get_rules.side_effect = slow_get_rules
        mock_delete.side_effect = slow_delete

        # Mock create_folder and push_rules to avoid errors
        with patch("main.create_folder") as mock_create, \
             patch("main.push_rules") as mock_push:

            mock_create.return_value = "new_id"
            mock_push.return_value = True

            start = time.perf_counter()
            self.main.sync_profile(self.profile_id, self.folder_urls, no_delete=False)
            elapsed = time.perf_counter() - start

            # Assertions
            self.assertTrue(mock_delete.called, "delete_folder should be called")
            self.assertTrue(mock_get_rules.called, "get_all_existing_rules should be called")

            # Verify get_all_existing_rules was called with ONLY keep_folder
            call_args = mock_get_rules.call_args
            # args: client, profile_id, known_folders
            known_folders = call_args[0][2] if len(call_args[0]) > 2 else call_args[1]['known_folders']

            self.assertIn("keep_folder", known_folders)
            self.assertNotIn("test_folder", known_folders, "Should not fetch rules from deleted folder")

            # Timing check
            # If serial: 1s (delete) + 1s (fetch) + overhead = ~2s
            # If parallel: max(1s, 1s) + overhead = ~1s
            # Note: sync_profile also has overhead (fetch_folder_data etc), but that's mocked to be fast.
            # We allow some buffer, but it should be significantly less than 2s
            print(f"Elapsed time: {elapsed:.2f}s")

            # A purely serial implementation would be expected to FAIL this test (take > 2s).
            # This test asserts the optimized parallel implementation, which should PASS (take < 1.5s).

            # Verify optimization effectiveness (should be close to max(1.0, 1.0) = 1.0s, allow 1.5s buffer)
            self.assertLess(elapsed, 1.5, "Parallel execution took too long")
