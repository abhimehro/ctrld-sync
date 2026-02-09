"""Tests for exception logging and sanitization.

This module verifies that sensitive data (tokens, secrets, credentials) in
exception messages are properly redacted before being written to logs.
"""

import unittest
from unittest.mock import MagicMock, patch
import httpx
import main


class TestExceptionLogging(unittest.TestCase):
    """Test suite for exception logging with sanitization."""

    @patch('main.log')
    @patch('main.TOKEN', 'TEST_TOKEN_XYZ')
    def test_check_api_access_redacts_exception(self, mock_log):
        """Test that check_api_access redacts tokens in exception messages."""
        # Setup
        client = MagicMock()
        profile_id = "test_profile"

        # Simulate a RequestError containing the test token
        # This simulates a situation where the exception message might
        # contain the URL with token
        error_message = (
            "Connection error to "
            "https://api.controld.com?token=TEST_TOKEN_XYZ"
        )
        client.get.side_effect = httpx.RequestError(
            error_message, request=MagicMock()
        )

        # Action
        main.check_api_access(client, profile_id)

        # Assertion
        # We expect log.error to be called
        self.assertTrue(
            mock_log.error.called, "log.error should have been called"
        )

        # Check the arguments passed to log.error
        # The code is: log.error(f"Network Error during access check: {e}")
        # So the first argument should contain the redacted message
        # Since it is an f-string, the redaction must happen BEFORE
        # formatting or inside the f-string expression
        args = mock_log.error.call_args[0]
        logged_message = args[0]

        # Verify secret is NOT present
        self.assertNotIn(
            "TEST_TOKEN_XYZ", logged_message, "Secret token leaked in logs!"
        )

        # Verify redaction placeholder IS present
        self.assertIn(
            "[REDACTED]", logged_message, "Redaction placeholder missing!"
        )

    @patch('main.log')
    @patch('main.socket.getaddrinfo')
    def test_validate_folder_url_redacts_exception(
        self, mock_getaddrinfo, mock_log
    ):
        """Test validate_folder_url redacts sensitive data in exceptions."""
        # Setup - simulate an exception during DNS resolution that
        # contains a sensitive URL
        test_url = "https://example.com/list?api_key=SECRET_API_KEY_456"

        # Create an exception that might contain the URL
        mock_getaddrinfo.side_effect = OSError(
            f"Failed to resolve {test_url}"
        )

        # Action
        result = main.validate_folder_url(test_url)

        # Assertions
        self.assertFalse(result, "URL validation should fail")
        self.assertTrue(
            mock_log.warning.called, "log.warning should have been called"
        )

        # Get all warning calls
        warning_calls = mock_log.warning.call_args_list

        # Check that none of the logged messages contain the secret
        for call in warning_calls:
            logged_message = str(call[0][0])
            self.assertNotIn(
                "SECRET_API_KEY_456",
                logged_message,
                "Secret API key leaked in logs!"
            )

    @patch('main.log')
    def test_fetch_folder_rules_redacts_exception(self, mock_log):
        """Test exception handlers in get_all_existing_rules redact."""
        # Setup
        client = MagicMock()
        profile_id = "test_profile"
        folder_id = "folder_123"

        # Create the exception with sensitive data
        error_with_token = ValueError(
            "API error at https://api.controld.com?token=TEST_SECRET_789"
        )

        # Mock _api_get to succeed for root but fail for folder rules
        with patch('main._api_get') as mock_api_get:
            def api_get_side_effect(client_arg, url):
                if url.endswith("/rules"):
                    # Root rules succeed
                    mock_response = MagicMock()
                    mock_response.json.return_value = {"body": {"rules": []}}
                    return mock_response
                else:
                    # Folder rules fail with our error
                    raise error_with_token

            mock_api_get.side_effect = api_get_side_effect

            # Provide known_folders to ensure _fetch_folder_rules is called
            main.get_all_existing_rules(
                client, profile_id, known_folders={"Test Folder": folder_id}
            )

        # Assertion - verify the exception was sanitized
        # Either log.warning was called from _fetch_folder_rules (line 859)
        # or from the outer exception handler (line 895-896)
        self.assertTrue(
            mock_log.warning.called, "log.warning should have been called"
        )

        # Get warning calls
        warning_calls = mock_log.warning.call_args_list

        # Check that the secret is redacted in all warnings
        for call in warning_calls:
            logged_message = str(call[0][0])
            self.assertNotIn(
                "TEST_SECRET_789",
                logged_message,
                "Secret token leaked in logs!"
            )

    @patch('main.log')
    @patch('main._api_post')
    def test_create_folder_redacts_exception(self, mock_api_post, mock_log):
        """Test that create_folder redacts tokens in debug log messages."""
        # Setup
        client = MagicMock()
        profile_id = "test_profile"
        folder_name = "Test Folder"

        # Mock the API response to return data but cause an exception
        # when trying to extract the ID
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "body": {
                "groups": "invalid_format_causes_exception_with_token=ABC123"
            }
        }
        mock_api_post.return_value = mock_response

        # We need to also mock list_existing_folders to avoid the fallback
        with patch('main.list_existing_folders') as mock_list:
            mock_list.return_value = {}

            # Action - this will try the direct ID extraction, fail, and log
            try:
                # Pass placeholder MagicMock instances for additional required arguments.
                # We only care about logging/redaction behavior, not the actual folder creation.
                main.create_folder(client, profile_id, folder_name, MagicMock(), MagicMock())
            except Exception:
                pass  # We expect this might fail, we're testing the logging

        # Assertion - if debug was called, verify redaction
        if mock_log.debug.called:
            debug_calls = mock_log.debug.call_args_list

            for call in debug_calls:
                # Extract the logged message from the first positional arg
                logged_message = str(call[0][0])
                # The message should not contain raw exception data
                # that might have tokens. In this test, the mocked
                # response includes "token=ABC123" in the data, so we
                # verify that value is not leaked to the logs.
                self.assertNotIn(
                    "ABC123",
                    logged_message,
                    "Token value leaked in debug logs!"
                )

    @patch('main.log')
    def test_retry_request_redacts_exception(self, mock_log):
        """Test that _retry_request redacts tokens in warning messages."""
        # Setup - create an exception with sensitive data
        error_with_token = httpx.RequestError(
            "Connection to https://api.example.com?secret=HIDDEN_KEY_999",
            request=MagicMock()
        )

        # Create a failing request function
        def failing_request():
            raise error_with_token

        # Action
        try:
            main._retry_request(failing_request, max_retries=2, delay=0.01)
        except httpx.RequestError:
            pass  # Expected to fail after retries

        # Assertion
        self.assertTrue(
            mock_log.warning.called, "log.warning should have been called"
        )

        # Get all warning calls
        warning_calls = mock_log.warning.call_args_list

        # Check that the secret is redacted
        for call in warning_calls:
            logged_message = str(call[0][0])
            self.assertNotIn(
                "HIDDEN_KEY_999",
                logged_message,
                "Secret key leaked in logs!"
            )


if __name__ == '__main__':
    unittest.main()
