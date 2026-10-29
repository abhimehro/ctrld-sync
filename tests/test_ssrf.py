import os
import socket
import sys
import unittest
from unittest.mock import PropertyMock, patch

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main

# Allowlisted host so DNS-resolved IP safety is exercised (not domain allowlist).
_ALLOWLIST_HOST = "raw.githubusercontent.com"


class TestSSRF(unittest.TestCase):
    def setUp(self):
        main.validate_folder_url.cache_clear()
        main.validate_hostname.cache_clear()

    def tearDown(self):
        main.validate_folder_url.cache_clear()
        main.validate_hostname.cache_clear()

    def _assert_resolved_ip(self, ip: str, expected: bool, label: str) -> None:
        with patch("socket.getaddrinfo") as mock_getaddrinfo:
            mock_getaddrinfo.return_value = [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))
            ]
            url = f"https://{label}.{_ALLOWLIST_HOST}/config.json"
            result = main.validate_folder_url(url)
            self.assertEqual(
                result,
                expected,
                f"IP {ip}: expected {expected}, got {result}",
            )

    def test_domain_resolving_to_ip_cases(self):
        cases = [
            ("192.168.1.1", False, "private"),
            ("8.8.8.8", True, "public"),
            ("100.64.0.1", False, "cgnat"),
            ("224.0.0.1", False, "multicast"),
            ("0.0.0.0", False, "unspecified"),  # nosec B104
            ("169.254.169.254", False, "linklocal"),
            ("127.0.0.2", False, "loopback"),
            ("240.0.0.1", False, "reserved"),
        ]
        for ip, expected, label in cases:
            with self.subTest(ip=ip):
                self._assert_resolved_ip(ip, expected, label)

    def test_reserved_ip_guard_blocks_when_other_flags_allow(self):
        """Explicit is_reserved guard must block even if other flags would allow."""
        with (
            patch.object(
                main.ipaddress.IPv4Address, "is_private", new_callable=PropertyMock
            ) as mock_private,
            patch.object(
                main.ipaddress.IPv4Address, "is_global", new_callable=PropertyMock
            ) as mock_global,
        ):
            mock_private.return_value = False
            mock_global.return_value = True

            self.assertFalse(
                main._is_safe_ip(main.ipaddress.IPv4Address("240.0.0.1")),
                "Should block reserved IPs even when other flags would allow them",
            )


if __name__ == "__main__":
    unittest.main()
