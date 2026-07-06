"""Tests for SSRF protection via the blocklist domain allowlist."""

import argparse
import socket
from unittest.mock import patch

import main


def test_default_allowed_blocklist_domains_pass():
    main.set_allowed_blocklist_domains(None)
    assert (
        main.validate_folder_url(
            "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-amazon-folder.json"
        )
        is True
    )
    assert (
        main.validate_folder_url(
            "https://github.com/abhimehro/ctrld-sync/blob/main/config.yaml.example"
        )
        is True
    )


def test_non_allowlisted_domain_rejected():
    main.set_allowed_blocklist_domains(None)
    assert main.validate_folder_url("https://evil.com/file.json") is False


def test_custom_allowlist_overrides_defaults():
    main.set_allowed_blocklist_domains(["custom.example.com", "trusted.org"])
    with patch("socket.getaddrinfo") as mock_getaddrinfo:
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ]
        assert main.validate_folder_url("https://custom.example.com/file.json") is True
        assert main.validate_folder_url("https://trusted.org/file.json") is True
    assert (
        main.validate_folder_url("https://raw.githubusercontent.com/test/file.json")
        is False
    )


def test_folder_url_uses_config_allowlist(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text(
        "allowed_blocklist_domains:\n  - custom.example.com\n"
    )
    monkeypatch.chdir(tmp_path)
    main.set_allowed_blocklist_domains(None)

    urls, cfg = main._resolve_folder_urls(
        argparse.Namespace(folder_url=["https://custom.example.com/file.json"], config=None)
    )

    assert urls == ["https://custom.example.com/file.json"]
    assert cfg is None
    assert main.validate_folder_url("https://custom.example.com/file.json") is True
