import unittest
from unittest.mock import MagicMock, patch
import httpx
import main

class TestExceptionLogging(unittest.TestCase):
    @patch('main.log')
    @patch('main.TOKEN', 'SECRET_TOKEN_123')
    def test_check_api_access_redacts_exception(self, mock_log):
        # Setup
        client = MagicMock()
        profile_id = "test_profile"

        # Simulate a RequestError containing the secret token
        # This simulates a situation where the exception message might contain the URL with token
        error_message = "Connection error to https://api.controld.com?token=SECRET_TOKEN_123"
        client.get.side_effect = httpx.RequestError(error_message, request=MagicMock())

        # Action
        main.check_api_access(client, profile_id)

        # Assertion
        # We expect log.error to be called
        self.assertTrue(mock_log.error.called, "log.error should have been called")

        # Check the arguments passed to log.error
        # The code is: log.error(f"Network Error during access check: {e}")
        # So the first argument should contain the redacted message
        # Since it is an f-string, the redaction must happen BEFORE formatting or inside the f-string expression
        args = mock_log.error.call_args[0]
        logged_message = args[0]

        # Verify secret is NOT present
        self.assertNotIn("SECRET_TOKEN_123", logged_message, "Secret token leaked in logs!")

        # Verify redaction placeholder IS present
        self.assertIn("[REDACTED]", logged_message, "Redaction placeholder missing!")

if __name__ == '__main__':
    unittest.main()
