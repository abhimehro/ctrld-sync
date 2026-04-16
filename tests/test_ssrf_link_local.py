import os
import socket
import sys
import unittest
from unittest.mock import patch

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


class TestSSRFLinkLocal(unittest.TestCase):
    def test_domain_resolving_to_link_local_ip(self):
        """
        Test that a domain resolving to a link-local IP (169.254.169.254) is blocked.
        This simulates an SSRF attempt against cloud provider metadata APIs
        (e.g., AWS IMDS, GCP Metadata, Azure Instance Metadata).
        """
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            # Simulate resolving to 169.254.169.254
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 443))
            ]

            url = "https://metadata.example.com/config.json"
            result = main.validate_folder_url(url)
            self.assertFalse(result, "Should block domain resolving to link-local IP")


if __name__ == "__main__":
    unittest.main()
