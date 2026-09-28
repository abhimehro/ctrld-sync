import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

import main


def _json_stream_response(content_type: str) -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    response.headers = httpx.Headers({"Content-Type": content_type})
    response.iter_bytes.return_value = [b'{"group": {"group": "test"}}']
    response.__enter__.return_value = response
    response.__exit__.return_value = None
    return response


class TestContentTypeValidation(unittest.TestCase):
    def setUp(self):
        # Bypass gh_client's SSRF gate so content-type tests stay deterministic
        # and do not hit DNS for https://example.com URLs.
        self._validate_patch = patch("gh_client.validate_folder_url", return_value=True)
        self._validate_patch.start()

    def tearDown(self):
        self._validate_patch.stop()
        # Clear cache before each test
        main._cache.clear()
        main._disk_cache.clear()

    @patch("main._gh.stream")
    def test_allow_application_json(self, mock_stream):
        """Test that application/json is allowed."""
        mock_stream.return_value = _json_stream_response("application/json")

        # Should not raise exception
        result = main._gh_get("https://example.com/valid.json")
        self.assertEqual(result, {"group": {"group": "test"}})

    @patch("main._gh.stream")
    def test_allow_text_plain(self, mock_stream):
        """Test that text/plain (used by GitHub raw) is allowed."""
        mock_stream.return_value = _json_stream_response("text/plain; charset=utf-8")

        # Should not raise exception
        result = main._gh_get("https://example.com/raw.json")
        self.assertEqual(result, {"group": {"group": "test"}})

    @patch("main._gh.stream")
    def test_reject_text_html(self, mock_stream):
        """Test that text/html is rejected even if content is valid JSON."""
        # Even if the body is valid JSON, the Content-Type is wrong
        mock_stream.return_value = _json_stream_response("text/html")

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

    @patch("main._gh.stream")
    def test_reject_xml(self, mock_stream):
        """Test that application/xml is rejected."""
        mock_stream.return_value = _json_stream_response("application/xml")

        with self.assertRaises(ValueError) as cm:
            main._gh_get("https://example.com/data.xml")
        self.assertIn("Invalid Content-Type", str(cm.exception))

    @patch("main._gh.stream")
    def test_reject_lookalike_content_types(self, mock_stream):
        """Media types containing an allowed type as a prefix are rejected."""
        for content_type in (
            "application/jsonp",
            "application/json-evil",
            "text/plaintext",
        ):
            with self.subTest(content_type=content_type):
                mock_stream.return_value = _json_stream_response(content_type)

                with self.assertRaisesRegex(ValueError, "Invalid Content-Type"):
                    main._gh_get("https://example.com/lookalike.json")


if __name__ == "__main__":
    unittest.main()
