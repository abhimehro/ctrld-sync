
import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import json

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main
import httpx

class TestContentTypeValidation(unittest.TestCase):
    def setUp(self):
        # Clear cache before each test
        main._cache.clear()
        main._disk_cache.clear()

    @patch('main._gh.stream')
    def test_allow_application_json(self, mock_stream):
        """Test that application/json is allowed."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = httpx.Headers({'Content-Type': 'application/json'})
        mock_response.iter_bytes.return_value = [b'{"group": {"group": "test"}}']
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        mock_stream.return_value = mock_response

        # Should not raise exception
        result = main._gh_get("https://example.com/valid.json")
        self.assertEqual(result, {"group": {"group": "test"}})

    @patch('main._gh.stream')
    def test_allow_text_plain(self, mock_stream):
        """Test that text/plain (used by GitHub raw) is allowed."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = httpx.Headers({'Content-Type': 'text/plain; charset=utf-8'})
        mock_response.iter_bytes.return_value = [b'{"group": {"group": "test"}}']
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        mock_stream.return_value = mock_response

        # Should not raise exception
        result = main._gh_get("https://example.com/raw.json")
        self.assertEqual(result, {"group": {"group": "test"}})

    @patch('main._gh.stream')
    def test_reject_text_html(self, mock_stream):
        """Test that text/html is rejected even if content is valid JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = httpx.Headers({'Content-Type': 'text/html'})
        # Even if the body is valid JSON, the Content-Type is wrong
        mock_response.iter_bytes.return_value = [b'{"group": {"group": "test"}}']
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        mock_stream.return_value = mock_response

        with self.assertRaises(ValueError) as cm:
            main._gh_get("https://example.com/malicious.html")
        self.assertIn("Invalid Content-Type", str(cm.exception))

    @patch('main._gh.stream')
    def test_reject_xml(self, mock_stream):
        """Test that application/xml is rejected."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = httpx.Headers({'Content-Type': 'application/xml'})
        mock_response.iter_bytes.return_value = [b'{"group": {"group": "test"}}']
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        mock_stream.return_value = mock_response

        with self.assertRaises(ValueError) as cm:
            main._gh_get("https://example.com/data.xml")
        self.assertIn("Invalid Content-Type", str(cm.exception))

    @patch('main._gh.stream')
    def test_reject_missing_content_type(self, mock_stream):
        """Test that responses without a Content-Type header are rejected."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        # Simulate a response with no Content-Type header at all
        mock_response.headers = httpx.Headers({})
        # Body is valid JSON so failure should be due to missing header, not parsing
        mock_response.iter_bytes.return_value = [b'{"group": {"group": "test"}}']
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        mock_stream.return_value = mock_response

        with self.assertRaises(ValueError) as cm:
            main._gh_get("https://example.com/no-header")
        self.assertIn("Invalid Content-Type", str(cm.exception))
    @patch('main._gh.stream')
    def test_304_retry_with_invalid_content_type(self, mock_stream):
        """Ensure Content-Type validation also applies after a 304 retry path."""
        # First response: 304 Not Modified with no cached body. This should
        # force _gh_get to enter its retry logic and perform a second request.
        mock_304 = MagicMock()
        mock_304.status_code = 304
        mock_304.headers = httpx.Headers()
        mock_304.iter_bytes.return_value = [b'']
        mock_304.__enter__.return_value = mock_304
        mock_304.__exit__.return_value = None

        # Second response: 200 OK but with an invalid Content-Type that should
        # be rejected even though the body contains valid JSON.
        mock_invalid_ct = MagicMock()
        mock_invalid_ct.status_code = 200
        mock_invalid_ct.headers = httpx.Headers({'Content-Type': 'text/html'})
        mock_invalid_ct.iter_bytes.return_value = [b'{"group": {"group": "test"}}']
        mock_invalid_ct.__enter__.return_value = mock_invalid_ct
        mock_invalid_ct.__exit__.return_value = None

        # Simulate the retry sequence: first a 304, then the invalid 200.
        mock_stream.side_effect = [mock_304, mock_invalid_ct]

        # The final 200 response should still be subject to Content-Type
        # validation, causing _gh_get to raise a ValueError.
        with self.assertRaises(ValueError) as cm:
            main._gh_get("https://example.com/retry.json")
        self.assertIn("Invalid Content-Type", str(cm.exception))
    @patch('main._gh.stream')
    def test_allow_text_json(self, mock_stream):
        """Test that text/json is allowed and parsed as JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = httpx.Headers({'Content-Type': 'text/json; charset=utf-8'})
        mock_response.iter_bytes.return_value = [b'{"group": {"group": "test"}}']
        mock_response.__enter__.return_value = mock_response
        mock_response.__exit__.return_value = None

        mock_stream.return_value = mock_response

        # Should not raise exception and should parse JSON correctly
        result = main._gh_get("https://example.com/data.json")
        self.assertEqual(result, {"group": {"group": "test"}})
if __name__ == '__main__':
    unittest.main()
