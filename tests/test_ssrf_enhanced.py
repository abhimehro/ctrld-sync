import os
import ipaddress
import socket
import sys
import unittest
from unittest.mock import patch

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


class TestSSRFEnhanced(unittest.TestCase):
    def setUp(self):
        main.validate_hostname.cache_clear()
        main.validate_folder_url.cache_clear()

    def tearDown(self):
        main.validate_hostname.cache_clear()
        main.validate_folder_url.cache_clear()

    def test_unsafe_domain_resolutions_are_blocked(self):
        """Test that domains resolving to unsafe IP ranges are blocked."""
        cases = [
            ("cgnat.example.com", "100.64.0.1", "CGNAT IP"),
            ("multicast.example.com", "224.0.0.1", "Multicast IP"),
            ("zero.example.com", str(ipaddress.IPv4Address(0)), "unspecified IPv4"),
            ("reserved.example.com", "240.0.0.1", "reserved IP"),
        ]
        for hostname, address, description in cases:
            with self.subTest(address=address):
                with patch("socket.getaddrinfo") as mock_getaddrinfo:
                    mock_getaddrinfo.return_value = [
                        (socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))
                    ]

                    url = f"https://{hostname}/config.json"
                    result = main.validate_folder_url(url)
                    self.assertFalse(
                        result, f"Should block domain resolving to {description}"
                    )

    def test_ipv4_mapped_ipv6_global_ip_is_allowed(self):
        """
        Test that a global IPv4 address mapped to IPv6 is validated by its IPv4 value.
        """
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:8.8.8.8", 443))
            ]

            url = "https://mapped-global.example.com/config.json"
            result = main.validate_folder_url(url)
            self.assertTrue(result, "Should allow global IPv4-mapped IPv6 addresses")


if __name__ == "__main__":
    unittest.main()
