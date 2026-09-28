import os
import socket
import sys
import unittest
from unittest.mock import patch

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


class TestSSRF(unittest.TestCase):
    def test_domain_resolving_to_private_ip(self):
        """
        Test that a domain resolving to a private IP is blocked.
        This simulates a DNS Rebinding attack or SSRF attempt against internal infrastructure.
        """
        # Use an allowlisted host so we test the DNS-resolved IP safety
        # rather than the domain allowlist.

        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            # Simulate resolving to 192.168.1.1
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.1", 443))
            ]

            url = "https://internal.raw.githubusercontent.com/config.json"

            # This calls the function in main.py
            result = main.validate_folder_url(url)

            # We expect this to be False (Blocked)
            self.assertFalse(result, "Should block domain resolving to private IP")

    def test_domain_resolving_to_public_ip(self):
        """
        Test that a domain resolving to a public IP is allowed.
        """
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            # Simulate resolving to 8.8.8.8
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))
            ]

            url = "https://public.raw.githubusercontent.com/config.json"

            result = main.validate_folder_url(url)

            self.assertTrue(result, "Should allow domain resolving to public IP")


if __name__ == "__main__":
    unittest.main()
