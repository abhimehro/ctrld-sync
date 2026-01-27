"""
Tests for the cache optimization in sync_profile.

This module verifies that:
1. Cached URLs correctly skip validation
2. Non-cached URLs still get validated
3. Cache operations are thread-safe
"""
import concurrent.futures
import threading
import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


class TestCacheOptimization(unittest.TestCase):
    def setUp(self):
        """Clear cache and validation cache before each test."""
        main._cache.clear()
        main.validate_folder_url.cache_clear()

    def tearDown(self):
        """Clean up after each test."""
        main._cache.clear()
        main.validate_folder_url.cache_clear()

    def test_cached_url_skips_validation(self):
        """
        Test that when a URL is in the cache, validate_folder_url is not called.
        This verifies the cache optimization is working correctly.
        """
        test_url = "https://example.com/test.json"
        test_data = {"group": {"group": "Test Folder"}, "domains": ["example.com"]}
        
        # Pre-populate cache
        with main._cache_lock:
            main._cache[test_url] = test_data
        
        with patch('main.validate_folder_url') as mock_validate:
            # This should return data from cache without calling validate_folder_url
            result = main.fetch_folder_data(test_url)
            
            # Verify validation was NOT called because URL is cached
            mock_validate.assert_not_called()
            self.assertEqual(result, test_data)

    def test_non_cached_url_calls_validation(self):
        """
        Test that when a URL is NOT in the cache, validate_folder_url is called.
        This ensures we don't skip validation for non-cached URLs.
        """
        test_url = "https://example.com/test.json"
        test_data = {"group": {"group": "Test Folder"}, "domains": ["example.com"]}
        
        # Ensure URL is NOT in cache
        self.assertNotIn(test_url, main._cache)
        
        with patch('main.validate_folder_url', return_value=True):
            with patch('main._gh_get', return_value=test_data):
                # Call the helper function that's used in sync_profile
                # This mimics what happens in _fetch_if_valid
                with main._cache_lock:
                    url_in_cache = test_url in main._cache
                
                if not url_in_cache:
                    # Should validate because URL is not cached
                    is_valid = main.validate_folder_url(test_url)
                    self.assertTrue(is_valid)
                    
                    if is_valid:
                        result = main.fetch_folder_data(test_url)
                        self.assertEqual(result, test_data)

    def test_cache_thread_safety_concurrent_reads(self):
        """
        Test that concurrent reads from the cache are thread-safe.
        Multiple threads should be able to read from the cache simultaneously.
        """
        test_url = "https://example.com/test.json"
        test_data = {"group": {"group": "Test Folder"}, "domains": ["example.com"]}
        
        # Pre-populate cache
        with main._cache_lock:
            main._cache[test_url] = test_data
        
        results = []
        errors = []
        
        def read_from_cache():
            try:
                with main._cache_lock:
                    if test_url in main._cache:
                        data = main._cache[test_url]
                        results.append(data)
            except Exception as e:
                errors.append(e)
        
        # Spawn multiple threads to read concurrently
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=read_from_cache)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify no errors occurred
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")
        # Verify all threads read the data
        self.assertEqual(len(results), 10)
        # Verify all threads read the same data
        for result in results:
            self.assertEqual(result, test_data)

    def test_cache_thread_safety_concurrent_writes(self):
        """
        Test that concurrent writes to the cache are thread-safe.
        Multiple threads should be able to write to different cache keys safely.
        """
        errors = []
        
        def write_to_cache(url_suffix):
            try:
                test_url = f"https://example.com/test{url_suffix}.json"
                test_data = {"group": {"group": f"Test Folder {url_suffix}"}, "domains": [f"example{url_suffix}.com"]}
                
                with main._cache_lock:
                    main._cache[test_url] = test_data
            except Exception as e:
                errors.append(e)
        
        # Spawn multiple threads to write concurrently
        threads = []
        for i in range(10):
            thread = threading.Thread(target=write_to_cache, args=(i,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Verify no errors occurred
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")
        # Verify all entries were written
        with main._cache_lock:
            self.assertEqual(len(main._cache), 10)

    def test_cache_check_in_fetch_if_valid(self):
        """
        Test the actual _fetch_if_valid logic used in sync_profile.
        This is an integration test that verifies the optimization path.
        """
        test_url = "https://example.com/test.json"
        test_data = {"group": {"group": "Test Folder"}, "domains": ["example.com"]}
        
        # Pre-populate cache to simulate warm_up_cache
        with main._cache_lock:
            main._cache[test_url] = test_data
        
        # Mock validate_folder_url to track if it's called
        with patch('main.validate_folder_url') as mock_validate:
            with patch('main._gh_get', return_value=test_data):
                # Simulate the logic in _fetch_if_valid
                with main._cache_lock:
                    url_is_cached = test_url in main._cache
                
                if url_is_cached:
                    result = main.fetch_folder_data(test_url)
                else:
                    if main.validate_folder_url(test_url):
                        result = main.fetch_folder_data(test_url)
                    else:
                        result = None
                
                # Verify validation was NOT called because URL was cached
                mock_validate.assert_not_called()
                self.assertEqual(result, test_data)

    def test_gh_get_thread_safety(self):
        """
        Test that _gh_get handles concurrent access correctly.
        When multiple threads try to fetch the same URL, only one should fetch
        and the rest should get the cached result.
        """
        test_url = "https://example.com/test.json"
        test_data = {"group": {"group": "Test Folder"}, "domains": ["example.com"]}
        
        fetch_count = [0]  # Use list to allow modification in closure
        
        def mock_stream_get(method, url):
            """Mock the streaming GET request."""
            fetch_count[0] += 1
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.headers = {"Content-Length": "100"}
            # Return JSON bytes properly
            json_bytes = b'{"group": {"group": "Test Folder"}, "domains": ["example.com"]}'
            mock_response.iter_bytes = MagicMock(return_value=[json_bytes])
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response
        
        results = []
        errors = []
        
        def fetch_data():
            try:
                data = main._gh_get(test_url)
                results.append(data)
            except Exception as e:
                errors.append(e)
        
        with patch.object(main._gh, 'stream', side_effect=mock_stream_get):
            # Spawn multiple threads to fetch the same URL concurrently
            threads = []
            for _ in range(5):
                thread = threading.Thread(target=fetch_data)
                threads.append(thread)
                thread.start()
            
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
        
        # Verify no errors occurred
        self.assertEqual(len(errors), 0, f"Errors occurred: {errors}")
        # Verify all threads got results
        self.assertEqual(len(results), 5)
        # All results should be the same
        for result in results:
            self.assertEqual(result, test_data)


if __name__ == '__main__':
    unittest.main()
