import sys
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Optional


logger = logging.getLogger(__name__)

# Default config search paths (highest to lowest precedence after CLI flag)
_DEFAULT_CONFIG_PATHS = [
    "config.yaml",
    "config.yml",
    "~/.ctrld-sync/config.yaml",
    "~/.ctrld-sync/config.yml",
]


def get_default_config() -> Dict:
    from main import DEFAULT_FOLDER_URLS, BATCH_SIZE, MAX_RETRIES
    """Return the built-in default configuration (mirrors DEFAULT_FOLDER_URLS)."""
    return {
        "folders": [{"url": u} for u in DEFAULT_FOLDER_URLS],
        "settings": {
            "batch_size": BATCH_SIZE,
            "delete_workers": 3,
            "max_retries": MAX_RETRIES,
        },
    }


def validate_config(config: Dict) -> None:
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
            raise ValueError(f"folders[{i}] must be a mapping, got {type(entry).__name__}.")
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

    settings = config.get("settings", {})
    if not isinstance(settings, dict):
        raise ValueError("'settings' must be a mapping.")
    for key in ("batch_size", "delete_workers", "max_retries"):
        val = settings.get(key)
        if val is not None and (not isinstance(val, int) or val <= 0):
            raise ValueError(f"settings.{key} must be a positive integer (got {val!r}).")


def load_config(config_path: Optional[str] = None) -> Dict:
    from main import Colors
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
    paths_to_try: List[str] = []
    if config_path:
        paths_to_try = [config_path]
    else:
        paths_to_try = list(_DEFAULT_CONFIG_PATHS)

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

        try:
            validate_config(loaded)
        except ValueError as exc:
            print(
                f"{Colors.FAIL}✗ Configuration error in {p}: {exc}{Colors.ENDC}",
                file=sys.stderr,
            )
            sys.exit(1)

        logger.info("Loaded configuration from %s", p)
        return loaded

    if config_path:
        # Explicit path was given but not found — this is always an error
        print(
            f"{Colors.FAIL}✗ Config file not found: {config_path}{Colors.ENDC}",
            file=sys.stderr,
        )
        sys.exit(1)

    # No config file found; use built-in defaults silently
    return get_default_config()
