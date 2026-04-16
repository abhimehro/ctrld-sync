import os
import socket
import sys
import unittest
from unittest.mock import patch

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


class TestSSRFLoopback(unittest.TestCase):
    def test_domain_resolving_to_loopback_ip(self):
        """
        Test that a domain resolving to a loopback IP (127.0.0.2) is blocked.
        """
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            # Simulate resolving to 127.0.0.2
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.2", 443))
            ]

            url = "https://loopback.example.com/config.json"
            result = main.validate_folder_url(url)
            self.assertFalse(result, "Should block domain resolving to loopback IP")


if __name__ == "__main__":
    unittest.main()
