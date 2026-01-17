import unittest
from unittest.mock import patch, MagicMock
import sys
import os
import socket

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main

class TestSSRF(unittest.TestCase):
    def test_domain_resolving_to_private_ip(self):
        """
        Test that a domain resolving to a private IP is blocked.
        This simulates a DNS Rebinding attack or SSRF attempt against internal infrastructure.
        """
        # We need to mock socket.getaddrinfo because the fix will use it.
        # For the current code, this mock is unused, but the test ensures
        # that 'internal.example.com' (which is not an IP literal) passes validation currently
        # and will fail validation (be blocked) after the fix.

        with patch('socket.getaddrinfo') as mock_getaddrinfo:
            # Simulate resolving to 192.168.1.1
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.168.1.1', 443))
            ]

            url = "https://internal.example.com/config.json"

            # This calls the function in main.py
            result = main.validate_folder_url(url)

            # We expect this to be False (Blocked)
            self.assertFalse(result, "Should block domain resolving to private IP")

    def test_domain_resolving_to_public_ip(self):
        """
        Test that a domain resolving to a public IP is allowed.
        """
        with patch('socket.getaddrinfo') as mock_getaddrinfo:
            # Simulate resolving to 8.8.8.8
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443))
            ]

            url = "https://public.example.com/config.json"

            result = main.validate_folder_url(url)

            self.assertTrue(result, "Should allow domain resolving to public IP")

if __name__ == '__main__':
    unittest.main()
