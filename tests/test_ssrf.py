import unittest
from unittest.mock import patch
import sys
import os
import socket

# Add parent directory to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import validate_folder_url

class TestSSRF(unittest.TestCase):
    def test_localhost_literal(self):
        """Test that explicit localhost strings are rejected."""
        self.assertFalse(validate_folder_url("https://localhost/config.json"))
        self.assertFalse(validate_folder_url("https://127.0.0.1/config.json"))
        self.assertFalse(validate_folder_url("https://[::1]/config.json"))

    @patch('socket.getaddrinfo')
    def test_private_ipv4_resolution(self, mock_getaddrinfo):
        """Test that domains resolving to private IPv4 are rejected."""
        # mock returns list of (family, type, proto, canonname, sockaddr)
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.168.1.1', 0))
        ]
        url = "https://internal.private/config.json"

        self.assertFalse(validate_folder_url(url), "Should reject domain resolving to private IPv4")

    @patch('socket.getaddrinfo')
    def test_private_ipv6_resolution(self, mock_getaddrinfo):
        """Test that domains resolving to private IPv6 are rejected."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, '', ('fd00::1', 0, 0, 0))
        ]
        url = "https://internal6.private/config.json"

        self.assertFalse(validate_folder_url(url), "Should reject domain resolving to private IPv6")

    @patch('socket.getaddrinfo')
    def test_mixed_resolution_unsafe(self, mock_getaddrinfo):
        """Test that if ANY resolved IP is private, it is rejected."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.168.1.1', 0))
        ]
        url = "https://mixed.private/config.json"

        self.assertFalse(validate_folder_url(url), "Should reject if any IP is private")

    @patch('socket.getaddrinfo')
    def test_public_resolution(self, mock_getaddrinfo):
        """Test that domains resolving to only public IPs are accepted."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 0))
        ]
        url = "https://google.com/config.json"

        self.assertTrue(validate_folder_url(url), "Should accept domain resolving to public IP")

    @patch('socket.getaddrinfo')
    def test_dns_resolution_failure(self, mock_getaddrinfo):
        """Test that domains failing resolution are rejected."""
        mock_getaddrinfo.side_effect = Exception("DNS lookup failed")
        url = "https://nonexistent.domain/config.json"

        self.assertFalse(validate_folder_url(url), "Should reject domain that fails resolution")

if __name__ == '__main__':
    unittest.main()
