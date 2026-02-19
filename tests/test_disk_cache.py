"""
Tests for persistent disk cache functionality.

This module verifies:
1. Cache directory creation on multiple platforms
2. Cache loading with graceful error handling
3. Cache saving with atomic writes
4. HTTP cache header support (ETag, Last-Modified)
5. 304 Not Modified handling
6. Cache statistics tracking
"""
import json
import os
import platform
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


class TestDiskCache(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        # Clear in-memory caches
        main._cache.clear()
        main._disk_cache.clear()
        main.validate_folder_url.cache_clear()
        # Reset stats
        main._cache_stats = {"hits": 0, "misses": 0, "validations": 0, "errors": 0}
        
        # Create temporary cache directory for testing
        self.temp_dir = tempfile.mkdtemp()
        self.original_get_cache_dir = main.get_cache_dir
        
    def tearDown(self):
        """Clean up after each test."""
        main._cache.clear()
        main._disk_cache.clear()
        main.validate_folder_url.cache_clear()
        main._cache_stats = {"hits": 0, "misses": 0, "validations": 0, "errors": 0}
        
        # Clean up temp directory
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_get_cache_dir_linux(self):
        """Test that cache directory is correct on Linux."""
        with patch('platform.system', return_value='Linux'):
            with patch.dict(os.environ, {}, clear=False):
                # Without XDG_CACHE_HOME
                if 'XDG_CACHE_HOME' in os.environ:
                    del os.environ['XDG_CACHE_HOME']
                cache_dir = main.get_cache_dir()
                self.assertEqual(cache_dir, Path.home() / ".cache" / "ctrld-sync")
    
    def test_get_cache_dir_macos(self):
        """Test that cache directory is correct on macOS."""
        with patch('platform.system', return_value='Darwin'):
            cache_dir = main.get_cache_dir()
            self.assertEqual(cache_dir, Path.home() / "Library" / "Caches" / "ctrld-sync")
    
    def test_get_cache_dir_windows(self):
        """Test that cache directory is correct on Windows."""
        with patch('platform.system', return_value='Windows'):
            with patch.dict(os.environ, {'LOCALAPPDATA': r'C:\Users\Test\AppData\Local'}):
                cache_dir = main.get_cache_dir()
                # Use string comparison to avoid path separator differences
                expected = Path(r'C:\Users\Test\AppData\Local') / 'ctrld-sync' / 'cache'
                self.assertEqual(cache_dir, expected)
    
    def test_load_disk_cache_no_file(self):
        """Test loading cache when no cache file exists."""
        main.get_cache_dir = lambda: Path(self.temp_dir) / "nonexistent"
        
        main.load_disk_cache()
        
        # Should have empty cache, no errors
        self.assertEqual(len(main._disk_cache), 0)
        self.assertEqual(main._cache_stats["errors"], 0)
    
    def test_load_disk_cache_valid_file(self):
        """Test loading cache from valid cache file."""
        cache_dir = Path(self.temp_dir)
        cache_dir.mkdir(exist_ok=True)
        cache_file = cache_dir / "blocklists.json"
        
        # Create valid cache file
        test_cache = {
            "https://example.com/list1.json": {
                "data": {"group": {"group": "Test"}, "domains": ["example.com"]},
                "etag": "abc123",
                "last_modified": "Mon, 01 Jan 2024 00:00:00 GMT",
                "fetched_at": 1234567890.0,
                "last_validated": 1234567890.0
            }
        }
        with open(cache_file, "w") as f:
            json.dump(test_cache, f)
        
        main.get_cache_dir = lambda: cache_dir
        main.load_disk_cache()
        
        # Should have loaded cache
        self.assertEqual(len(main._disk_cache), 1)
        self.assertIn("https://example.com/list1.json", main._disk_cache)
        self.assertEqual(main._cache_stats["errors"], 0)
    
    def test_load_disk_cache_corrupted_json(self):
        """Test graceful handling of corrupted cache file."""
        cache_dir = Path(self.temp_dir)
        cache_dir.mkdir(exist_ok=True)
        cache_file = cache_dir / "blocklists.json"
        
        # Create corrupted JSON file
        with open(cache_file, "w") as f:
            f.write("{ invalid json }")
        
        main.get_cache_dir = lambda: cache_dir
        main.load_disk_cache()
        
        # Should have empty cache but not crash
        self.assertEqual(len(main._disk_cache), 0)
        self.assertEqual(main._cache_stats["errors"], 1)
    
    def test_load_disk_cache_invalid_format(self):
        """Test graceful handling of invalid cache format."""
        cache_dir = Path(self.temp_dir)
        cache_dir.mkdir(exist_ok=True)
        cache_file = cache_dir / "blocklists.json"
        
        # Create valid JSON but wrong format (list instead of dict)
        with open(cache_file, "w") as f:
            json.dump(["not", "a", "dict"], f)
        
        main.get_cache_dir = lambda: cache_dir
        main.load_disk_cache()
        
        # Should have empty cache but not crash
        self.assertEqual(len(main._disk_cache), 0)
        # No error increment because it's just a warning
    
    def test_save_disk_cache(self):
        """Test saving cache to disk."""
        cache_dir = Path(self.temp_dir)
        main.get_cache_dir = lambda: cache_dir
        
        # Populate cache
        main._disk_cache["https://example.com/test.json"] = {
            "data": {"group": {"group": "Test"}, "domains": ["test.com"]},
            "etag": "xyz789",
            "last_modified": None,
            "fetched_at": 1234567890.0,
            "last_validated": 1234567890.0
        }
        
        main.save_disk_cache()
        
        # Verify file was created
        cache_file = cache_dir / "blocklists.json"
        self.assertTrue(cache_file.exists())
        
        # Verify content
        with open(cache_file, "r") as f:
            loaded = json.load(f)
        
        self.assertEqual(len(loaded), 1)
        self.assertIn("https://example.com/test.json", loaded)
        self.assertEqual(loaded["https://example.com/test.json"]["etag"], "xyz789")
    
    def test_save_disk_cache_atomic_write(self):
        """Test that cache saving uses atomic write (temp file + rename)."""
        cache_dir = Path(self.temp_dir)
        main.get_cache_dir = lambda: cache_dir
        
        main._disk_cache["https://example.com/test.json"] = {
            "data": {"group": {"group": "Test"}, "domains": ["test.com"]},
            "etag": "test",
            "last_modified": None,
            "fetched_at": 1234567890.0,
            "last_validated": 1234567890.0
        }
        
        main.save_disk_cache()
        
        # Verify temp file is gone (was renamed)
        temp_file = cache_dir / "blocklists.tmp"
        self.assertFalse(temp_file.exists())
        
        # Verify final file exists
        cache_file = cache_dir / "blocklists.json"
        self.assertTrue(cache_file.exists())
    
    def test_cache_stats_tracking(self):
        """Test that cache statistics are tracked correctly."""
        test_url = "https://example.com/test.json"
        test_data = {"group": {"group": "Test"}, "domains": ["example.com"]}
        
        # Reset stats
        main._cache_stats = {"hits": 0, "misses": 0, "validations": 0, "errors": 0}
        
        def mock_stream(method, url, headers=None):
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            mock_response.headers = {"Content-Length": "100", "ETag": "test123", "Content-Type": "application/json"}
            json_bytes = json.dumps(test_data).encode()
            mock_response.iter_bytes = MagicMock(return_value=[json_bytes])
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response
        
        with patch.object(main._gh, 'stream', side_effect=mock_stream):
            # First fetch - should be a miss
            result1 = main._gh_get(test_url)
            self.assertEqual(main._cache_stats["misses"], 1)
            self.assertEqual(main._cache_stats["hits"], 0)
            
            # Second fetch - should be a hit (in-memory cache)
            result2 = main._gh_get(test_url)
            self.assertEqual(main._cache_stats["hits"], 1)
            self.assertEqual(main._cache_stats["misses"], 1)
    
    def test_conditional_request_with_etag(self):
        """Test that conditional requests use ETag from disk cache."""
        test_url = "https://example.com/test.json"
        test_data = {"group": {"group": "Test"}, "domains": ["example.com"]}
        
        # Pre-populate disk cache with ETag
        main._disk_cache[test_url] = {
            "data": test_data,
            "etag": "abc123",
            "last_modified": None,
            "fetched_at": 1234567890.0,
            "last_validated": 1234567890.0
        }
        
        def mock_stream(method, url, headers=None):
            # Verify If-None-Match header was sent
            self.assertIsNotNone(headers)
            self.assertEqual(headers.get("If-None-Match"), "abc123")
            
            # Return 304 Not Modified
            mock_response = MagicMock()
            mock_response.status_code = 304
            mock_response.raise_for_status = MagicMock()
            mock_response.headers = {}
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response
        
        with patch.object(main._gh, 'stream', side_effect=mock_stream):
            result = main._gh_get(test_url)
            
            # Should return cached data
            self.assertEqual(result, test_data)
            # Should count as validation, not miss
            self.assertEqual(main._cache_stats["validations"], 1)
            self.assertEqual(main._cache_stats["misses"], 0)
    
    def test_conditional_request_with_last_modified(self):
        """Test that conditional requests use Last-Modified from disk cache."""
        test_url = "https://example.com/test.json"
        test_data = {"group": {"group": "Test"}, "domains": ["example.com"]}
        
        # Pre-populate disk cache with Last-Modified
        main._disk_cache[test_url] = {
            "data": test_data,
            "etag": None,
            "last_modified": "Mon, 01 Jan 2024 00:00:00 GMT",
            "fetched_at": 1234567890.0,
            "last_validated": 1234567890.0
        }
        
        def mock_stream(method, url, headers=None):
            # Verify If-Modified-Since header was sent
            self.assertIsNotNone(headers)
            self.assertEqual(headers.get("If-Modified-Since"), "Mon, 01 Jan 2024 00:00:00 GMT")
            
            # Return 304 Not Modified
            mock_response = MagicMock()
            mock_response.status_code = 304
            mock_response.raise_for_status = MagicMock()
            mock_response.headers = {}
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response
        
        with patch.object(main._gh, 'stream', side_effect=mock_stream):
            result = main._gh_get(test_url)
            
            # Should return cached data
            self.assertEqual(result, test_data)
            # Should count as validation
            self.assertEqual(main._cache_stats["validations"], 1)
    
    def test_ttl_within_ttl_returns_disk_cache_without_request(self):
        """Test that disk cache entries within TTL are returned without an HTTP request."""
        test_url = "https://example.com/test.json"
        test_data = {"group": {"group": "Test"}, "domains": ["example.com"]}
        
        # Pre-populate disk cache with a recent last_validated timestamp (within TTL)
        main._disk_cache[test_url] = {
            "data": test_data,
            "etag": "fresh123",
            "last_modified": None,
            "fetched_at": time.time(),
            "last_validated": time.time(),  # Just validated - within TTL
        }
        
        http_called = []
        
        def mock_stream(method, url, headers=None):
            http_called.append(url)
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"Content-Type": "application/json"}
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response
        
        with patch.object(main._gh, 'stream', side_effect=mock_stream):
            result = main._gh_get(test_url)
        
        # HTTP should NOT have been called (within TTL)
        self.assertEqual(len(http_called), 0)
        # Result should be the cached data
        self.assertEqual(result, test_data)
        # Should count as a hit
        self.assertEqual(main._cache_stats["hits"], 1)
        self.assertEqual(main._cache_stats["misses"], 0)
        self.assertEqual(main._cache_stats["validations"], 0)
    
    def test_ttl_expired_sends_conditional_request(self):
        """Test that disk cache entries beyond TTL trigger a conditional HTTP request."""
        test_url = "https://example.com/test.json"
        test_data = {"group": {"group": "Test"}, "domains": ["example.com"]}
        
        # Pre-populate disk cache with an old last_validated (beyond TTL)
        main._disk_cache[test_url] = {
            "data": test_data,
            "etag": "stale123",
            "last_modified": None,
            "fetched_at": 0.0,       # very old
            "last_validated": 0.0,   # very old - beyond any TTL
        }
        
        def mock_stream(method, url, headers=None):
            # Conditional request should be sent with If-None-Match
            self.assertEqual(headers.get("If-None-Match"), "stale123")
            mock_response = MagicMock()
            mock_response.status_code = 304
            mock_response.raise_for_status = MagicMock()
            mock_response.headers = {}
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            return mock_response
        
        with patch.object(main._gh, 'stream', side_effect=mock_stream):
            result = main._gh_get(test_url)
        
        # Should return cached data (304 response)
        self.assertEqual(result, test_data)
        # Should count as validation (conditional request)
        self.assertEqual(main._cache_stats["validations"], 1)
        self.assertEqual(main._cache_stats["hits"], 0)
    
    def test_clear_cache_deletes_file(self):
        """Test that --clear-cache deletes the cache file."""
        cache_dir = Path(self.temp_dir)
        cache_file = cache_dir / "blocklists.json"
        
        # Create a cache file
        cache_file.write_text('{}')
        self.assertTrue(cache_file.exists())
        
        # Populate in-memory disk cache
        main._disk_cache["https://example.com/test.json"] = {
            "data": {},
            "etag": None,
            "last_modified": None,
            "fetched_at": 0.0,
            "last_validated": 0.0,
        }
        
        with patch('main.get_cache_dir', return_value=cache_dir):
            # Simulate --clear-cache logic
            if cache_file.exists():
                cache_file.unlink()
            main._disk_cache.clear()
        
        # Cache file should be gone
        self.assertFalse(cache_file.exists())
        # In-memory disk cache should be empty
        self.assertEqual(len(main._disk_cache), 0)


if __name__ == '__main__':
    unittest.main()
