
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

        # This should fail after we implement the fix.
        # Currently it might pass because we only check JSON validity.
        try:
            main._gh_get("https://example.com/malicious.html")
            # If it doesn't raise, we fail the test (once fixed)
            # But for TDD, we expect this to fail AFTER the fix.
            # For now, let's assert that it *should* raise ValueError
        except ValueError as e:
            self.assertIn("Invalid Content-Type", str(e))
            return

        # If we are here, no exception was raised.
        # This confirms the vulnerability (or lack of validation).
        # We can mark this as "expected failure" or just print it.
        # For now, I'll fail the test so I can see it pass later.
        self.fail("Should have raised ValueError for text/html Content-Type")

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

if __name__ == '__main__':
    unittest.main()
