"""
Tests for the warm_up_cache optimization.

This module verifies that warm_up_cache skips DNS validation when the
URL is already fresh in the disk cache.
"""
import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import time

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# We do NOT import main at top level to avoid holding a stale reference
# if other tests reload the module.

class TestWarmUpCachePerf(unittest.TestCase):
    def setUp(self):
        """Reset cache state before each test."""
        # Get the current main module from sys.modules
        # If not present, import it
        if 'main' in sys.modules:
            self.main = sys.modules['main']
        else:
            import main
            self.main = main

        self.main._cache.clear()
        self.main._disk_cache.clear()
        self.main.validate_folder_url.cache_clear()

    def tearDown(self):
        """Clean up after each test."""
        self.main._cache.clear()
        self.main._disk_cache.clear()
        self.main.validate_folder_url.cache_clear()

    def test_warm_up_skips_validation_for_fresh_cache(self):
        """
        Test that warm_up_cache does NOT call validate_folder_url
        if the URL is present in _disk_cache and fresh (within TTL).
        """
        test_url = "https://example.com/fresh.json"
        test_data = {"group": {"group": "Fresh Folder"}, "rules": []}

        # Populate disk cache with a FRESH entry
        with self.main._cache_lock:
            self.main._disk_cache[test_url] = {
                "data": test_data,
                "fetched_at": time.time(),
                "last_validated": time.time(), # Just now
                "etag": "123",
                "last_modified": "Tue, 15 Nov 1994 12:45:26 GMT"
            }

        # Mock validate_folder_url to track calls
        with patch('main.validate_folder_url') as mock_validate:
            # Mock _gh_get to return data without network
            with patch('main._gh_get', return_value=test_data) as mock_gh_get:

                self.main.warm_up_cache([test_url])

                # VERIFICATION: validate_folder_url should NOT be called
                mock_validate.assert_not_called()

                # _gh_get should still be called (it handles cache retrieval)
                mock_gh_get.assert_called_with(test_url)

    def test_warm_up_calls_validation_for_stale_cache(self):
        """
        Test that warm_up_cache DOES call validate_folder_url
        if the URL is present in _disk_cache but STALE (expired TTL).
        """
        test_url = "https://example.com/stale.json"
        test_data = {"group": {"group": "Stale Folder"}, "rules": []}

        # Populate disk cache with a STALE entry (older than TTL)
        stale_time = time.time() - (self.main.CACHE_TTL_SECONDS + 3600) # 1 hour past TTL
        with self.main._cache_lock:
            self.main._disk_cache[test_url] = {
                "data": test_data,
                "fetched_at": stale_time,
                "last_validated": stale_time,
                "etag": "123",
                "last_modified": "Tue, 15 Nov 1994 12:45:26 GMT"
            }

        with patch('main.validate_folder_url', return_value=True) as mock_validate:
            with patch('main._gh_get', return_value=test_data):

                self.main.warm_up_cache([test_url])

                # VERIFICATION: validate_folder_url SHOULD be called for stale entry
                mock_validate.assert_called_with(test_url)

    def test_warm_up_calls_validation_for_missing_cache(self):
        """
        Test that warm_up_cache DOES call validate_folder_url
        if the URL is NOT present in _disk_cache.
        """
        test_url = "https://example.com/missing.json"
        test_data = {"group": {"group": "Missing Folder"}, "rules": []}

        # Ensure cache is empty
        self.assertNotIn(test_url, self.main._disk_cache)

        with patch('main.validate_folder_url', return_value=True) as mock_validate:
            with patch('main._gh_get', return_value=test_data):

                self.main.warm_up_cache([test_url])

                # VERIFICATION: validate_folder_url SHOULD be called for missing entry
                mock_validate.assert_called_with(test_url)

if __name__ == '__main__':
    unittest.main()
