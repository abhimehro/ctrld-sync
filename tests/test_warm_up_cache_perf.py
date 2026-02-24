import time
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main

class TestWarmUpCachePerf(unittest.TestCase):
    def setUp(self):
        main._cache.clear()
        main._disk_cache.clear()
        main.validate_folder_url.cache_clear()

    def tearDown(self):
        main._cache.clear()
        main._disk_cache.clear()
        main.validate_folder_url.cache_clear()

    def test_warm_up_skips_validation_for_fresh_cache(self):
        """
        Test that warm_up_cache skips validate_folder_url if the URL is in disk cache and fresh.
        """
        test_url = "https://example.com/test.json"
        test_data = {"group": {"group": "Test Folder"}, "domains": ["example.com"]}

        # Populate disk cache with fresh entry
        main._disk_cache[test_url] = {
            "data": test_data,
            "last_validated": time.time(), # Fresh
            "fetched_at": time.time(),
        }

        # Mock validate_folder_url to ensure it is NOT called
        # Mock _gh_get to verify it IS called (which will use the cache)
        with patch('main.validate_folder_url') as mock_validate:
            with patch('main._gh_get', return_value=test_data) as mock_gh_get:

                main.warm_up_cache([test_url])

                # Verify _gh_get was called (it handles cache retrieval)
                mock_gh_get.assert_called_with(test_url)

                # Verify validate_folder_url was NOT called
                # This assertion will FAIL before the fix
                mock_validate.assert_not_called()

    def test_warm_up_calls_validation_for_stale_cache(self):
        """
        Test that warm_up_cache calls validate_folder_url if the URL is stale in disk cache.
        """
        test_url = "https://example.com/test.json"
        test_data = {"group": {"group": "Test Folder"}, "domains": ["example.com"]}

        # Populate disk cache with STALE entry
        stale_time = time.time() - (main.CACHE_TTL_SECONDS + 100)
        main._disk_cache[test_url] = {
            "data": test_data,
            "last_validated": stale_time,
            "fetched_at": stale_time,
        }

        with patch('main.validate_folder_url', return_value=True) as mock_validate:
            with patch('main._gh_get', return_value=test_data) as mock_gh_get:

                main.warm_up_cache([test_url])

                # Verify validate_folder_url WAS called
                mock_validate.assert_called_with(test_url)

                # Verify _gh_get was called
                mock_gh_get.assert_called_with(test_url)

    def test_warm_up_calls_validation_for_missing_cache(self):
        """
        Test that warm_up_cache calls validate_folder_url if the URL is not in disk cache.
        """
        test_url = "https://example.com/test.json"
        test_data = {"group": {"group": "Test Folder"}, "domains": ["example.com"]}

        # Cache is empty

        with patch('main.validate_folder_url', return_value=True) as mock_validate:
            with patch('main._gh_get', return_value=test_data) as mock_gh_get:

                main.warm_up_cache([test_url])

                # Verify validate_folder_url WAS called
                mock_validate.assert_called_with(test_url)

                # Verify _gh_get was called
                mock_gh_get.assert_called_with(test_url)

if __name__ == '__main__':
    unittest.main()
