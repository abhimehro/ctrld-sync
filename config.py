"""Configuration loading and runtime constants."""

from __future__ import annotations

import logging
import argparse
import sys
from pathlib import Path
from typing import cast

import yaml
from api_client import _4XX_HINTS, _SERVER_ERROR_HINT, MAX_RETRIES
from display import Colors
from validation import (
    DEFAULT_ALLOWED_BLOCKLIST_DOMAINS,
    set_allowed_blocklist_domains,
)

log = logging.getLogger(__name__)

API_BASE = "https://api.controld.com/profiles"
USER_AGENT = "Control-D-Sync/0.1.0"

DELETE_WORKERS = 3  # Conservative for DELETE operations due to rate limits


def _clean_env_kv(value: str | None, key: str) -> str | None:
    """Allow TOKEN/PROFILE values to be provided as either raw values or KEY=value."""
    if not value:
        return value
    v = value.strip()
    if "=" in v:
        k, val = v.split("=", 1)
        if k.strip() == key:
            # String splitting is used here as it's significantly faster than regex for basic KV parsing
            # Emulate regex behavior: only return if value is not empty (.+ match)
            val_stripped = val.strip()
            if val_stripped:
                return val_stripped
    return v


DEFAULT_FOLDER_URLS = [
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/apple-private-relay-allow-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/badware-hoster-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/meta-tracker-allow-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/microsoft-allow-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-amazon-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-apple-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-huawei-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-lgwebos-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-microsoft-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-oppo-realme-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-samsung-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-tiktok-aggressive-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-tiktok-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-vivo-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-xiaomi-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/nosafesearch-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/referral-allow-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/spam-idns-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/spam-tlds-allow-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/spam-tlds-combined-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/spam-tlds-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/ultimate-known_issues-allow-folder.json",
    "https://raw.githubusercontent.com/yokoffing/Control-D-Config/main/folders/potentially-malicious-ips.json",
]

BATCH_SIZE = 500
BATCH_KEYS = [f"hostnames[{i}]" for i in range(BATCH_SIZE)]

FOLDER_CREATION_DELAY = 5  # <--- CHANGED: Increased from 2 to 5 for patience

_STATUS_HINTS: dict[int, str] = {
    **_4XX_HINTS,  # single source of truth for 401, 403, 404
    429: "Rate limited — the sync will retry automatically with backoff.",
    500: _SERVER_ERROR_HINT,
}

_DEFAULT_CONFIG_PATHS = [
    "config.yaml",
    "config.yml",
    "~/.ctrld-sync/config.yaml",
    "~/.ctrld-sync/config.yml",
]


def get_default_config() -> dict:
    """Return the built-in default configuration (mirrors DEFAULT_FOLDER_URLS)."""
    return {
        "folders": [{"url": u} for u in DEFAULT_FOLDER_URLS],
        "allowed_blocklist_domains": list(DEFAULT_ALLOWED_BLOCKLIST_DOMAINS),
        "settings": {
            "batch_size": BATCH_SIZE,
            "delete_workers": 3,
            "max_retries": MAX_RETRIES,
        },
    }


def _validate_config(config: dict) -> None:
    """
    Validate a loaded configuration dict and raise ValueError on the first problem.

    Checks:
    - 'folders' key exists and is a non-empty list
    - Each folder entry has a 'url' string (name and action are optional)
    - All URLs are https://
    - 'action' values, if present, are 'block' or 'allow'
    - Settings values, if present, are positive integers
    """
    if "folders" not in config:
        raise ValueError("Configuration is missing the required 'folders' key.")

    folders = config["folders"]
    if not isinstance(folders, list) or not folders:
        raise ValueError("'folders' must be a non-empty list.")

    for i, entry in enumerate(folders):
        if not isinstance(entry, dict):
            raise ValueError(
                f"folders[{i}] must be a mapping, got {type(entry).__name__}."
            )
        url = entry.get("url", "")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ValueError(
                f"folders[{i}]: 'url' must be an https:// string (got {url!r})."
            )
        name = entry.get("name", "")
        if name and (not isinstance(name, str) or not name.strip()):
            raise ValueError(f"folders[{i}]: 'name' must be a non-empty string.")
        action = entry.get("action")
        if action is not None and action not in ("block", "allow"):
            raise ValueError(
                f"folders[{i}]: 'action' must be 'block' or 'allow' (got {action!r})."
            )

    _validate_allowed_blocklist_domains(config.get("allowed_blocklist_domains"))

    settings = config.get("settings", {})
    if not isinstance(settings, dict):
        raise ValueError("'settings' must be a mapping.")
    for key in ("batch_size", "delete_workers", "max_retries"):
        val = settings.get(key)
        if val is not None and (not isinstance(val, int) or val <= 0):
            raise ValueError(
                f"settings.{key} must be a positive integer (got {val!r})."
            )


def _read_config_yaml(
    config_path: str | None = None,
) -> tuple[Path, dict] | None:
    paths_to_try: list[str] = (
        [config_path] if config_path else list(_DEFAULT_CONFIG_PATHS)
    )

    for raw_path in paths_to_try:
        p = Path(raw_path).expanduser()
        if not p.exists():
            continue
        try:
            # Opening the file can fail with OSError (e.g. permission denied, is a directory),
            # so we handle it here to avoid an unhelpful traceback.
            with open(p, encoding="utf-8") as fh:
                # Parsing YAML can raise yaml.YAMLError for malformed configuration.
                loaded = yaml.safe_load(fh)
        except OSError as exc:
            print(
                f"{Colors.FAIL}✗ Failed to read configuration file {p}: {exc}{Colors.ENDC}",
                file=sys.stderr,
            )
            sys.exit(1)
        except yaml.YAMLError as exc:
            print(
                f"{Colors.FAIL}✗ Invalid YAML in {p}: {exc}{Colors.ENDC}",
                file=sys.stderr,
            )
            sys.exit(1)

        if loaded is None:
            print(
                f"{Colors.FAIL}✗ Configuration file {p} is empty.{Colors.ENDC}",
                file=sys.stderr,
            )
            sys.exit(1)

        if not isinstance(loaded, dict):
            print(
                f"{Colors.FAIL}✗ Configuration file {p} is not a YAML mapping.{Colors.ENDC}",
                file=sys.stderr,
            )
            sys.exit(1)

        return p, cast(dict, loaded)

    if config_path:
        print(
            f"{Colors.FAIL}✗ Config file not found: {config_path}{Colors.ENDC}",
            file=sys.stderr,
        )
        sys.exit(1)

    return None


def load_config(config_path: str | None = None) -> dict:
    """
    Load and validate configuration from a YAML file.

    Resolution order (first found wins):
    1. Explicit *config_path* argument (e.g. from --config CLI flag)
    2. config.yaml / config.yml in the current working directory
    3. ~/.ctrld-sync/config.yaml / ~/.ctrld-sync/config.yml
    4. Built-in defaults (get_default_config())

    Raises SystemExit on invalid YAML or schema violations so the operator
    sees a clear error message rather than a cryptic traceback.
    """

    loaded_config = _read_config_yaml(config_path)
    if loaded_config is None:
        # No config file found; use built-in defaults silently
        set_allowed_blocklist_domains(None)
        return get_default_config()

    p, loaded = loaded_config

    try:
        _validate_config(loaded)
    except ValueError as exc:
        print(
            f"{Colors.FAIL}✗ Configuration error in {p}: {exc}{Colors.ENDC}",
            file=sys.stderr,
        )
        sys.exit(1)

    log.info("Loaded configuration from %s", p)
    set_allowed_blocklist_domains(loaded.get("allowed_blocklist_domains"))
    return loaded


def _load_allowed_blocklist_domains(config_path: str | None = None) -> None:
    loaded_config = _read_config_yaml(config_path)
    if loaded_config is None:
        set_allowed_blocklist_domains(None)
        return

    p, loaded = loaded_config
    try:
        _validate_allowed_blocklist_domains(loaded.get("allowed_blocklist_domains"))
    except ValueError as exc:
        print(
            f"{Colors.FAIL}✗ Configuration error in {p}: {exc}{Colors.ENDC}",
            file=sys.stderr,
        )
        sys.exit(1)

    set_allowed_blocklist_domains(loaded.get("allowed_blocklist_domains"))


def _validate_allowed_blocklist_domains(allowed_domains: list[str] | None) -> None:
    if allowed_domains is None:
        return
    if not isinstance(allowed_domains, list):
        raise ValueError("'allowed_blocklist_domains' must be a list.")
    for i, domain in enumerate(allowed_domains):
        if not isinstance(domain, str) or not domain.strip():
            raise ValueError(
                f"allowed_blocklist_domains[{i}]: must be a non-empty string (got {domain!r})."
            )


MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10 MB limit for external resources


def _resolve_folder_urls(args: argparse.Namespace) -> tuple[list[str], dict | None]:
    if args.folder_url:
        # When explicit URLs are given, only the blocklist allowlist is needed.
        # A broken auto-discovered config.yaml must not block --folder-url usage,
        # so we warn and fall back to the default allowlist instead of exiting.
        # An explicit --config path that is missing/invalid stays fatal.
        try:
            _load_allowed_blocklist_domains(args.config)
        except SystemExit:
            if args.config:
                raise
            log.warning(
                "Could not load allowed_blocklist_domains from a discovered config; "
                "falling back to default allowlisted domains."
            )
            set_allowed_blocklist_domains(None)
        return args.folder_url, None

    cfg = load_config(args.config)
    return [entry["url"] for entry in cfg["folders"]], cfg


__all__ = [
    "API_BASE",
    "USER_AGENT",
    "BATCH_SIZE",
    "BATCH_KEYS",
    "DELETE_WORKERS",
    "FOLDER_CREATION_DELAY",
    "MAX_RESPONSE_SIZE",
    "_STATUS_HINTS",
    "DEFAULT_FOLDER_URLS",
    "_DEFAULT_CONFIG_PATHS",
    "_clean_env_kv",
    "get_default_config",
    "load_config",
    "_resolve_folder_urls",
]
