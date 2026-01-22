import unittest
from unittest.mock import MagicMock, patch
import sys
import os
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

        # Check logs
        # We look for the specific log message: "Folder '{name}' not found yet..."
        found_unsafe_log = False
        for call in mock_log.info.call_args_list:
            args = call[0]
            msg = args[0] if args else ""
            # The vulnerable code uses f-string: f"Folder '{name}' not found yet..."
            # So the message itself contains the name.
            if f"Folder '{unsafe_name}' not found yet" in str(msg):
                found_unsafe_log = True
                break

        # If we found the log with RAW unsafe_name, it's vulnerable.
        # We want to assertion that we DO find it (demonstrating vulnerability)
        # OR we verify it is NOT there (after fix).

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

if __name__ == '__main__':
    unittest.main()
