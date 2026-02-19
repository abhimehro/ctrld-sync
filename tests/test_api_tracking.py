"""Test API call tracking functionality"""
import unittest
from unittest.mock import patch, MagicMock
import sys
sys.path.insert(0, '.')


class TestAPITracking(unittest.TestCase):
    """Tests for API call tracking and statistics"""
    
    def setUp(self):
        """Save original counter values before each test."""
        import main
        self.original_control_d_calls = main._api_stats["control_d_api_calls"]
        self.original_blocklist_fetches = main._api_stats["blocklist_fetches"]
    
    def tearDown(self):
        """Restore original counter values after each test."""
        import main
        main._api_stats["control_d_api_calls"] = self.original_control_d_calls
        main._api_stats["blocklist_fetches"] = self.original_blocklist_fetches
    
    def test_api_stats_initialized(self):
        """Test that _api_stats is properly initialized"""
        import main
        # Should have both counters
        self.assertIn("control_d_api_calls", main._api_stats)
        self.assertIn("blocklist_fetches", main._api_stats)
        # Should start at 0
        self.assertIsInstance(main._api_stats["control_d_api_calls"], int)
        self.assertIsInstance(main._api_stats["blocklist_fetches"], int)
    
    @patch('main.httpx.Client')
    def test_api_get_increments_counter(self, mock_client_class):
        """Test that _api_get increments the API call counter"""
        import main
        
        # Record initial value
        initial_count = main._api_stats["control_d_api_calls"]
        
        # Mock the client and response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client.get.return_value = mock_response
        
        # Call _api_get
        main._api_get(mock_client, "http://test.url")
        
        # Verify counter was incremented by 1
        self.assertEqual(main._api_stats["control_d_api_calls"], initial_count + 1)
    
    @patch('main.httpx.Client')
    def test_api_post_increments_counter(self, mock_client_class):
        """Test that _api_post increments the API call counter"""
        import main
        
        # Record initial value
        initial_count = main._api_stats["control_d_api_calls"]
        
        # Mock the client and response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_response
        
        # Call _api_post
        main._api_post(mock_client, "http://test.url", {"key": "value"})
        
        # Verify counter was incremented by 1
        self.assertEqual(main._api_stats["control_d_api_calls"], initial_count + 1)
    
    @patch('main.httpx.Client')
    def test_api_delete_increments_counter(self, mock_client_class):
        """Test that _api_delete increments the API call counter"""
        import main
        
        # Record initial value
        initial_count = main._api_stats["control_d_api_calls"]
        
        # Mock the client and response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_client.delete.return_value = mock_response
        
        # Call _api_delete
        main._api_delete(mock_client, "http://test.url")
        
        # Verify counter was incremented by 1
        self.assertEqual(main._api_stats["control_d_api_calls"], initial_count + 1)
    
    @patch('main._gh')
    def test_gh_get_increments_blocklist_counter(self, mock_gh_client):
        """Test that _gh_get increments the blocklist fetch counter"""
        import main
        
        # Record initial value
        initial_count = main._api_stats["blocklist_fetches"]
        
        # Clear cache to ensure we make a fresh request
        main._cache.clear()
        
        # Mock the streaming response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.iter_bytes.return_value = [b'{"test": "data"}']
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        
        mock_gh_client.stream.return_value = mock_response
        
        # Call _gh_get
        try:
            result = main._gh_get("http://test.blocklist.url")
        except Exception:
            pass  # May fail on validation, we just care about the counter
        
        # Verify blocklist counter was incremented by at least 1
        self.assertGreaterEqual(main._api_stats["blocklist_fetches"], initial_count + 1)


if __name__ == '__main__':
    unittest.main()
