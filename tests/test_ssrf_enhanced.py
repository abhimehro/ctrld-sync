
import unittest
from unittest.mock import patch
import sys
import os
import socket

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main

class TestSSRFEnhanced(unittest.TestCase):
    def test_domain_resolving_to_cgnat_ip(self):
        """
        Test that a domain resolving to a Carrier Grade NAT IP (100.64.x.x) is blocked.
        Current code allows this, but security best practice is to block it.
        """
        with patch('socket.getaddrinfo') as mock_getaddrinfo:
            # Simulate resolving to 100.64.0.1
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('100.64.0.1', 443))
            ]

            url = "https://cgnat.example.com/config.json"
            result = main.validate_folder_url(url)
            self.assertFalse(result, "Should block domain resolving to CGNAT IP")

    def test_domain_resolving_to_multicast_ip(self):
        """
        Test that a domain resolving to a Multicast IP is blocked.
        """
        with patch('socket.getaddrinfo') as mock_getaddrinfo:
            # Simulate resolving to 224.0.0.1
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('224.0.0.1', 443))
            ]

            url = "https://multicast.example.com/config.json"
            result = main.validate_folder_url(url)
            self.assertFalse(result, "Should block domain resolving to Multicast IP")

    def test_domain_resolving_to_unspecified_ip(self):
        """
        Test that a domain resolving to 0.0.0.0 is blocked.
        """
        with patch('socket.getaddrinfo') as mock_getaddrinfo:
            # Simulate resolving to 0.0.0.0
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('0.0.0.0', 443))
            ]

            url = "https://zero.example.com/config.json"
            result = main.validate_folder_url(url)
            self.assertFalse(result, "Should block domain resolving to 0.0.0.0")

if __name__ == '__main__':
    unittest.main()
