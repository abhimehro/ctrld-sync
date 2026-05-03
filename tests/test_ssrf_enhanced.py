import os
import socket
import sys
from unittest.mock import patch

import pytest

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


@pytest.mark.parametrize(
    "ip,url,test_desc",
    [
        ("100.64.0.1", "https://cgnat.example.com/config.json", "CGNAT IP"),
        ("224.0.0.1", "https://multicast.example.com/config.json", "Multicast IP"),
        ("0.0.0.0", "https://zero.example.com/config.json", "0.0.0.0"),
        ("240.0.0.1", "https://reserved.example.com/config.json", "reserved IP"),
    ],
)
def test_domain_resolving_to_unsafe_ip(ip, url, test_desc):
    """
    Test that a domain resolving to various unsafe IPs is blocked.
    """
    with patch("socket.getaddrinfo") as mock_getaddrinfo:
        # Simulate resolving to the test IP
        # nosec: B104 (Possible binding to all interfaces) - mocking bad IP for SSRF testing
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))  # noqa: S104
        ]

        result = main.validate_folder_url(url)
        assert not result, f"Should block domain resolving to {test_desc}"
