import unittest
from unittest.mock import patch
import socket
import ipaddress
import logging

# We import the module to test its logic.
# We need to be careful about side effects from top-level code in main.py.
# However, standard unittest discovery or running this file directly is the standard way.
# We will mock environmental variables if needed, but the main.py logic handles defaults.

# Import validate_folder_url from main
# Note: This will execute the top-level code in main.py.
import main

class TestSSRFProtection(unittest.TestCase):

    @patch('socket.getaddrinfo')
    def test_domain_resolving_to_localhost(self, mock_getaddrinfo):
        # Simulate localtest.me resolving to 127.0.0.1
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443))
        ]

        url = "https://localtest.me/config.json"
        is_valid = main.validate_folder_url(url)

        self.assertFalse(is_valid, "Should reject domain resolving to localhost")

    @patch('socket.getaddrinfo')
    def test_domain_resolving_to_private_ip(self, mock_getaddrinfo):
        # Simulate internal.corp resolving to 192.168.1.5
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.168.1.5', 443))
        ]

        url = "https://internal.corp/secret.json"
        is_valid = main.validate_folder_url(url)

        self.assertFalse(is_valid, "Should reject domain resolving to private IP")

    def test_ip_literal_link_local(self):
        # Test explicit link-local IP (169.254.x.x)
        # This hits the first check (IP literal), not the DNS resolution path.
        url = "https://169.254.169.254/latest/meta-data/"
        is_valid = main.validate_folder_url(url)
        self.assertFalse(is_valid, "Should reject link-local IP literal")

    @patch('socket.getaddrinfo')
    def test_domain_resolving_to_link_local(self, mock_getaddrinfo):
        # Simulate aws-metadata resolving to 169.254.169.254
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('169.254.169.254', 80))
        ]

        url = "https://169.254.169.254.nip.io/latest/meta-data/"
        is_valid = main.validate_folder_url(url)

        self.assertFalse(is_valid, "Should reject domain resolving to link-local IP")

    @patch('socket.getaddrinfo')
    def test_domain_resolving_to_public_ip(self, mock_getaddrinfo):
        # Simulate google.com resolving to 8.8.8.8 (public)
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 443))
        ]

        url = "https://google.com/config.json"
        is_valid = main.validate_folder_url(url)

        self.assertTrue(is_valid, "Should accept domain resolving to public IP")

    @patch('socket.getaddrinfo')
    def test_dns_resolution_failure(self, mock_getaddrinfo):
        # Simulate DNS failure
        mock_getaddrinfo.side_effect = socket.gaierror("Name or service not known")

        url = "https://nonexistent.domain/config.json"
        is_valid = main.validate_folder_url(url)

        self.assertFalse(is_valid, "Should reject URL if DNS resolution fails")

if __name__ == '__main__':
    # Suppress logging during tests
    logging.getLogger('control-d-sync').setLevel(logging.CRITICAL)
    unittest.main()
