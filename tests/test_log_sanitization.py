import unittest
from unittest.mock import MagicMock, patch
import main

class TestLogSanitization(unittest.TestCase):
    def test_sanitize_for_log_escapes_ansi(self):
        """Test that sanitize_for_log escapes ANSI characters."""
        # ANSI Red color
        malicious_input = "\x1b[31mMalicious"
        sanitized = main.sanitize_for_log(malicious_input)

        # repr() escapes \x1b as \x1b (4 chars: \, x, 1, b)
        # So the output string should contain literal backslash
        self.assertIn("\\x1b", sanitized)
        # It should NOT contain the actual escape character
        self.assertNotIn("\x1b", sanitized)

    @patch('main.log')
    @patch('main.time.sleep')
    @patch('main._api_post')
    @patch('main._api_get')
    def test_create_folder_logs_unsafe_name(self, mock_get, mock_post, mock_sleep, mock_log):
        """
        Verify that create_folder logs the raw name if not sanitized.
        We expect this to FAIL (or show raw usage) before the fix.
        """
        # Setup
        main.MAX_RETRIES = 1
        main.FOLDER_CREATION_DELAY = 0

        # Mock POST to succeed (returns None, assuming polling needed if direct ID missing)
        mock_post.return_value.json.return_value = {"body": {"group": {"something": "else"}}}

        # Mock GET to return empty groups (fail to find)
        mock_get.return_value.json.return_value = {"body": {"groups": []}}

        unsafe_name = "\x1b[31mUNSAFE"

        # Call
        client = MagicMock()
        main.create_folder(client, "pid", unsafe_name, 0, 1)

        # Check logs: ensure we do not log the raw unsafe name, but do log the sanitized name.
        # For this test file, I want it to PASS when the code is FIXED.
        # So I should assert that I DO NOT find raw unsafe_name, but I DO find sanitized name.

        sanitized_name = main.sanitize_for_log(unsafe_name)

        found_sanitized = False
        found_raw = False

        for call in mock_log.info.call_args_list:
            args = call[0]
            # Since it is an f-string in the source, we can't easily check format args.
            # We have to check the string content.
            # But wait, if the source is f"Folder '{name}'...", logging receives the formatted string.
            log_msg = args[0]
            if unsafe_name in log_msg:
                found_raw = True
            if sanitized_name in log_msg:
                found_sanitized = True

        if found_raw:
            print("VULNERABILITY DETECTED: Raw unsafe name found in logs.")

        # This assertion will FAIL before fix, and PASS after fix.
        self.assertTrue(found_sanitized, "Should find sanitized name in logs")
        self.assertFalse(found_raw, "Should not find raw name in logs")

    def test_sanitize_for_log_redacts_credentials(self):
        """Test that sanitize_for_log redacts Basic Auth and sensitive query params."""
        # Test Basic Auth
        url_with_auth = "https://user:password123@example.com/folder.json"
        sanitized = main.sanitize_for_log(url_with_auth)
        self.assertNotIn("password123", sanitized)
        self.assertIn("[REDACTED]", sanitized)

        # Test Query Params
        url_with_param = "https://example.com/folder.json?secret=mysecretkey"
        sanitized_param = main.sanitize_for_log(url_with_param)
        self.assertNotIn("mysecretkey", sanitized_param)
        self.assertIn("[REDACTED]", sanitized_param)

        # Test Case Insensitivity
        url_with_token = "https://example.com/folder.json?TOKEN=mytoken"
        sanitized_token = main.sanitize_for_log(url_with_token)
        self.assertNotIn("mytoken", sanitized_token)
        self.assertIn("[REDACTED]", sanitized_token)

if __name__ == '__main__':
    unittest.main()
