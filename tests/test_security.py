import unittest
from unittest.mock import patch
import socket
import logging
import sys
import os

# Add parent directory to path so we can import main
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configure logging to avoid polluting output
logging.basicConfig(level=logging.CRITICAL)

import main

class TestSecurity(unittest.TestCase):
    def test_validate_folder_url_prevents_dns_rebinding(self):
        """
        Verify that the implementation prevents domains that resolve to private IPs.
        """
        suspicious_url = "https://internal.example.com/list.json"

        # Mock socket.getaddrinfo to return 127.0.0.1
        with patch("socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))
            ]

            result = main.validate_folder_url(suspicious_url)

            # Should be False (Secure)
            self.assertFalse(result, "validate_folder_url should return False for domains resolving to private IPs")

if __name__ == "__main__":
    unittest.main()
