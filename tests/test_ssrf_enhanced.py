import ipaddress
import os
import socket
import sys
from unittest.mock import patch

import pytest

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main


@pytest.fixture(autouse=True)
def clear_ssrf_validation_caches():
    main.validate_hostname.cache_clear()
    main.validate_folder_url.cache_clear()
    yield
    main.validate_hostname.cache_clear()
    main.validate_folder_url.cache_clear()


@pytest.mark.parametrize(
    "ip,url,test_desc",
    [
        ("100.64.0.1", "https://cgnat.example.com/config.json", "CGNAT IP"),
        ("224.0.0.1", "https://multicast.example.com/config.json", "Multicast IP"),
        (
            str(ipaddress.IPv4Address(0)),
            "https://zero.example.com/config.json",
            "unspecified IPv4",
        ),
        ("240.0.0.1", "https://reserved.example.com/config.json", "reserved IP"),
    ],
)
def test_domain_resolving_to_unsafe_ip(ip, url, test_desc):
    """
    Test that a domain resolving to various unsafe IPs is blocked.
    """
    with patch("socket.getaddrinfo") as mock_getaddrinfo:
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))
        ]

        result = main.validate_folder_url(url)
        assert not result, f"Should block domain resolving to {test_desc}"


def test_ipv4_mapped_ipv6_global_ip_is_allowed():
    """
    Test that a global IPv4 address mapped to IPv6 is validated by its IPv4 value.
    """
    with patch("socket.getaddrinfo") as mock_getaddrinfo:
        mock_getaddrinfo.return_value = [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:8.8.8.8", 443))
        ]

        result = main.validate_folder_url(
            "https://mapped-global.example.com/config.json"
        )
        assert result, "Should allow global IPv4-mapped IPv6 addresses"


def test_ipv4_mapped_ipv6_reserved_ip_is_blocked():
    """
    Test that a reserved IPv4 address mapped to IPv6 is validated by its IPv4 value.
    """
    with patch("socket.getaddrinfo") as mock_getaddrinfo:
        mock_getaddrinfo.return_value = [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:240.0.0.1", 443))
        ]

        result = main.validate_folder_url(
            "https://mapped-reserved.example.com/config.json"
        )
        assert not result, "Should block reserved IPv4-mapped IPv6 addresses"
