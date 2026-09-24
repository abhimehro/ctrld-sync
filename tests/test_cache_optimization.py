"""
Tests for the cache optimization in sync_profile.

This module verifies that:
1. Cached responses avoid redundant network requests without skipping validation
2. Non-cached URLs are validated before fetching
3. Cache operations are thread-safe
"""

import os
import sys
import threading
import unittest
from unittest.mock import MagicMock, patch

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main
import sync


class TestCacheOptimization(unittest.TestCase):
    def setUp(self):
        """Clear cache and validation cache before each test."""
        main._cache.clear()
        main.validate_folder_url.cache_clear()
        main.validate_hostname.cache_clear()
        # Bypass gh_client's SSRF gate so these cache/HTTP behavior tests stay
        # deterministic and do not hit DNS for https://example.com URLs.
        self._validate_patch = patch("gh_client.validate_folder_url", return_value=True)
        self._validate_patch.start()

    def tearDown(self):
        """Clean up after each test."""
        self._validate_patch.stop()
        main._cache.clear()
        main.validate_folder_url.cache_clear()
        main.validate_hostname.cache_clear()

    def test_cached_url_avoids_network_but_validates_schema(self):
        """A memory-cache hit must still pass folder-data validation."""
        test_url = "https://example.com/test.json"
        test_data = {"group": {"group": "Test Folder"}, "domains": ["example.com"]}

        # Pre-populate cache
        with main._cache_lock:
            main._cache[test_url] = test_data

        with (
            patch("gh_client._gh.stream") as mock_stream,
            patch(
                "gh_client.validate_folder_data", wraps=main.validate_folder_data
            ) as mock_validate_data,
        ):
            result = main.fetch_folder_data(test_url)

        mock_stream.assert_not_called()
        mock_validate_data.assert_called_once_with(test_data, test_url)
        self.assertEqual(result, test_data)

    def test_non_cached_url_calls_validation(self):
        """
        Test that when a URL is NOT in the cache during sync_profile,
        validate_folder_url is called before fetching.
        This exercises the _fetch_if_valid behavior where validation is
        required for non-cached URLs.
        """
        test_url = "https://example.com/test.json"
        from main import FolderData

        test_data: FolderData = {
            "group": {"group": "Test Folder"},
            "rules": [{"PK": "example.com"}],
        }

        # Ensure URL is NOT in cache
        self.assertNotIn(test_url, main._cache)

        with (
            patch("sync.plan.sync.validate_folder_url", return_value=True) as mock_validate,
            patch("sync.plan.fetch_folder_data", return_value=test_data) as mock_fetch,
        ):
            result = sync.plan._fetch_all_folder_data([test_url])

        mock_validate.assert_called_once_with(test_url)
        mock_fetch.assert_called_once_with(test_url)
        self.assertEqual(result, [test_data])

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
                test_data = {
                    "group": {"group": f"Test Folder {url_suffix}"},
                    "domains": [f"example{url_suffix}.com"],
                }

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

    def test_fetch_if_valid_revalidates_cached_data(self):
        """The planning fetch path validates data populated by warm_up_cache."""
        test_url = "https://example.com/test.json"
        from main import FolderData

        test_data: FolderData = {
            "group": {"group": "Test Folder"},
            "rules": [{"PK": "example.com"}],
        }

        # Pre-populate cache to simulate warm_up_cache
        with main._cache_lock:
            main._cache[test_url] = test_data  # type: ignore[assignment]

        with (
            patch("sync.plan.sync.validate_folder_url", return_value=True),
            patch("gh_client._gh.stream") as mock_stream,
            patch(
                "gh_client.validate_folder_data", wraps=main.validate_folder_data
            ) as mock_validate_data,
        ):
            result = sync.plan._fetch_all_folder_data([test_url])

        mock_stream.assert_not_called()
        mock_validate_data.assert_called_once_with(test_data, test_url)
        self.assertEqual(result, [test_data])

    def test_gh_get_thread_safety(self):
        """
        Test that _gh_get handles concurrent access correctly.
        When multiple threads try to fetch the same URL, the double-checked
        locking pattern should minimize redundant fetches (though some may
        still occur if threads enter the fetch section before any completes).
        """
        test_url = "https://example.com/test.json"
        test_data = {"group": {"group": "Test Folder"}, "domains": ["example.com"]}

        class FetchTracker:
            """Track fetch count using a class to avoid closure issues.
            Uses a separate lock from main._cache_lock to avoid any potential
            ordering issues with the test's mock patches and actual cache operations."""

            def __init__(self):
                self.count = 0
                self.lock = threading.Lock()

            def increment(self):
                with self.lock:
                    self.count += 1

        tracker = FetchTracker()

        def mock_stream_get(method, url, headers=None):
            """Mock the streaming GET request."""
            tracker.increment()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.headers = {
                "Content-Length": "100",
                "Content-Type": "application/json",
            }
            # Return JSON bytes properly
            json_bytes = (
                b'{"group": {"group": "Test Folder"}, "domains": ["example.com"]}'
            )
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

        with patch.object(main._gh, "stream", side_effect=mock_stream_get):
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

        # Verify fetch count - with double-checked locking, we should have
        # at most 5 fetches (worst case) but ideally fewer
        self.assertLessEqual(
            tracker.count, 5, f"Expected at most 5 fetches, got {tracker.count}"
        )


if __name__ == "__main__":
    unittest.main()
