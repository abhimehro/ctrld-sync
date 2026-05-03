import ipaddress
import os
import socket
import sys
import unittest
from collections.abc import Iterable
from typing import NamedTuple
from unittest.mock import patch

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


class ResolvedIpCase(NamedTuple):
    hostname: str
    address: str
    family: socket.AddressFamily
    expected: bool
    description: str


class TestSSRFEnhanced(unittest.TestCase):
    def setUp(self):
        main.validate_hostname.cache_clear()
        main.validate_folder_url.cache_clear()

    def tearDown(self):
        main.validate_hostname.cache_clear()
        main.validate_folder_url.cache_clear()

    def assert_resolution_cases(self, cases: Iterable[ResolvedIpCase]) -> None:
        for case in cases:
            with self.subTest(address=case.address):
                with patch("socket.getaddrinfo") as mock_getaddrinfo:
                    mock_getaddrinfo.return_value = [
                        (
                            case.family,
                            socket.SOCK_STREAM,
                            6,
                            "",
                            (case.address, 443),
                        )
                    ]

                    url = f"https://{case.hostname}/config.json"
                    result = main.validate_folder_url(url)

                self.assertIs(result, case.expected, case.description)

    def test_domain_resolving_to_unsafe_ip(self):
        """
        Test that domains resolving to various unsafe IPs are blocked.
        """
        self.assert_resolution_cases(
            [
                ResolvedIpCase(
                    "cgnat.example.com",
                    "100.64.0.1",
                    socket.AF_INET,
                    False,
                    "Should block domain resolving to CGNAT IP",
                ),
                ResolvedIpCase(
                    "multicast.example.com",
                    "224.0.0.1",
                    socket.AF_INET,
                    False,
                    "Should block domain resolving to Multicast IP",
                ),
                ResolvedIpCase(
                    "zero.example.com",
                    str(ipaddress.IPv4Address(0)),
                    socket.AF_INET,
                    False,
                    "Should block domain resolving to unspecified IPv4",
                ),
                ResolvedIpCase(
                    "reserved.example.com",
                    "240.0.0.1",
                    socket.AF_INET,
                    False,
                    "Should block domain resolving to reserved IP",
                ),
                ResolvedIpCase(
                    "mapped-global.example.com",
                    "::ffff:8.8.8.8",
                    socket.AF_INET6,
                    True,
                    "Should allow global IPv4-mapped IPv6 addresses",
                ),
                ResolvedIpCase(
                    "mapped-reserved.example.com",
                    "::ffff:240.0.0.1",
                    socket.AF_INET6,
                    False,
                    "Should block reserved IPv4-mapped IPv6 addresses",
                ),
            ]
        )


if __name__ == "__main__":
    unittest.main()
