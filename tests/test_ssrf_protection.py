"""Tests for SSRF protection via the blocklist domain allowlist."""

import argparse
import socket
from unittest.mock import patch

import pytest

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
        argparse.Namespace(
            folder_url=["https://custom.example.com/file.json"], config=None
        )
    )

    assert urls == ["https://custom.example.com/file.json"]
    assert cfg is None
    with patch("main.socket.getaddrinfo") as mock_getaddrinfo:
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ]
        assert main.validate_folder_url("https://custom.example.com/file.json") is True


def test_folder_url_explicit_missing_config_path_exits(tmp_path):
    with pytest.raises(SystemExit):
        main._resolve_folder_urls(
            argparse.Namespace(
                folder_url=["https://custom.example.com/file.json"],
                config=str(tmp_path / "missing.yaml"),
            )
        )


def test_folder_url_broken_discovered_config_falls_back(tmp_path, monkeypatch):
    # A broken auto-discovered config.yaml must not block --folder-url usage:
    # it should warn and fall back to the default allowlist rather than exit.
    (tmp_path / "config.yaml").write_text("just a bare string, not a mapping\n")
    monkeypatch.chdir(tmp_path)
    main.set_allowed_blocklist_domains(None)

    urls, cfg = main._resolve_folder_urls(
        argparse.Namespace(
            folder_url=["https://raw.githubusercontent.com/test/file.json"],
            config=None,
        )
    )

    assert urls == ["https://raw.githubusercontent.com/test/file.json"]
    assert cfg is None
    # Fallback to defaults means the GitHub-only allowlist is active again.
    assert main._ALLOWED_BLOCKLIST_DOMAINS == main.DEFAULT_ALLOWED_BLOCKLIST_DOMAINS
