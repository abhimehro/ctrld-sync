
import unittest
from unittest.mock import MagicMock, patch
import logging
import concurrent.futures
import sys
import os

# Set dummy env vars before importing main
os.environ["TOKEN"] = "dummy_token"

import main

# Suppress logging
logging.getLogger("control-d-sync").setLevel(logging.CRITICAL)

class TestClientReuse(unittest.TestCase):
    def test_client_creation_count(self):
        # Mock data
        profile_id = "test_profile"
        folder_urls = ["http://example.com/folder1.json", "http://example.com/folder2.json"]

        # Mock folder data fetch
        mock_folder_data = {
            "group": {"group": "Test Folder", "action": {"do": 0, "status": 1}},
            "rules": [{"PK": "google.com"}]
        }

        # We need to patch several things
        with patch('main.fetch_folder_data', return_value=mock_folder_data) as mock_fetch, \
             patch('main._api_client') as mock_api_client_ctor, \
             patch('main.list_existing_folders', return_value={}) as mock_list_folders, \
             patch('main.get_all_existing_rules', return_value=set()) as mock_get_rules, \
             patch('main.create_folder', return_value="folder_123") as mock_create, \
             patch('main.push_rules', return_value=True) as mock_push:

            # Setup mock client context manager
            mock_client_instance = MagicMock()
            mock_api_client_ctor.return_value.__enter__.return_value = mock_client_instance

            # Run sync_profile
            # We use 3 URLs to simulate 3 folders processing
            urls = ["u1", "u2", "u3"]
            # Mock fetch returning same data for all

            # Since fetch_folder_data is mocked, we don't need real URLs.
            # But sync_profile calls validate_folder_url which checks https://
            valid_urls = ["https://example.com/1", "https://example.com/2", "https://example.com/3"]

            result = main.sync_profile(profile_id, valid_urls, dry_run=False)

            self.assertTrue(result, "Sync should succeed")

            # Count how many times _api_client was CALLED (not the instance, but the factory function)
            # 1 initial call + 3 folder calls = 4 calls expected currently
            print(f"Client factory called {mock_api_client_ctor.call_count} times")

            # Assert 1 call (reused for all folders)
            self.assertEqual(mock_api_client_ctor.call_count, 1)

if __name__ == '__main__':
    unittest.main()
