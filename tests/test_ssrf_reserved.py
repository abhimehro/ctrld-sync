import os
import socket
import sys
import unittest
from unittest.mock import patch

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


class TestSSRFReserved(unittest.TestCase):
    def test_domain_resolving_to_reserved_ip(self):
        """
        Test that a domain resolving to a reserved IP (e.g., 240.0.0.1) is blocked.
        """
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            # Simulate resolving to 240.0.0.1
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("240.0.0.1", 443))
            ]

            url = "https://reserved.example.com/config.json"
            result = main.validate_folder_url(url)
            self.assertFalse(result, "Should block domain resolving to a reserved IP")


if __name__ == "__main__":
    unittest.main()
