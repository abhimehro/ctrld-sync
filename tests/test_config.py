"""Tests for YAML configuration file support (load_config, get_default_config, _validate_config)."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

import main


# ─────────────────────────────────────────────────────────────────────────────
# get_default_config
# ─────────────────────────────────────────────────────────────────────────────

def test_get_default_config_returns_dict():
    cfg = main.get_default_config()
    assert isinstance(cfg, dict)
    assert "folders" in cfg
    assert "settings" in cfg


def test_get_default_config_folders_match_default_urls():
    cfg = main.get_default_config()
    urls = [entry["url"] for entry in cfg["folders"]]
    assert urls == main.DEFAULT_FOLDER_URLS


def test_get_default_config_settings_are_positive_ints():
    settings = main.get_default_config()["settings"]
    for key in ("batch_size", "delete_workers", "max_retries"):
        assert isinstance(settings[key], int)
        assert settings[key] > 0


# ─────────────────────────────────────────────────────────────────────────────
# _validate_config
# ─────────────────────────────────────────────────────────────────────────────

def test_validate_config_valid_minimal():
    cfg = {"folders": [{"url": "https://example.com/folder.json"}]}
    main._validate_config(cfg)  # must not raise


def test_validate_config_valid_full():
    cfg = {
        "folders": [
            {"name": "Test", "url": "https://example.com/f.json", "action": "block"},
            {"url": "https://example.com/f2.json", "action": "allow"},
        ],
        "settings": {"batch_size": 100, "delete_workers": 2, "max_retries": 5},
    }
    main._validate_config(cfg)  # must not raise


def test_validate_config_missing_folders_key():
    with pytest.raises(ValueError, match="missing the required 'folders'"):
        main._validate_config({})


def test_validate_config_empty_folders_list():
    with pytest.raises(ValueError, match="non-empty list"):
        main._validate_config({"folders": []})


def test_validate_config_folders_not_a_list():
    with pytest.raises(ValueError, match="non-empty list"):
        main._validate_config({"folders": "not-a-list"})


def test_validate_config_folder_entry_not_a_dict():
    with pytest.raises(ValueError, match="must be a mapping"):
        main._validate_config({"folders": ["https://example.com/f.json"]})


def test_validate_config_url_missing():
    with pytest.raises(ValueError, match="'url' must be an https://"):
        main._validate_config({"folders": [{}]})


def test_validate_config_url_not_https():
    with pytest.raises(ValueError, match="'url' must be an https://"):
        main._validate_config({"folders": [{"url": "http://example.com/f.json"}]})


def test_validate_config_invalid_action():
    cfg = {"folders": [{"url": "https://example.com/f.json", "action": "deny"}]}
    with pytest.raises(ValueError, match="'action' must be 'block' or 'allow'"):
        main._validate_config(cfg)


def test_validate_config_blank_name():
    cfg = {"folders": [{"url": "https://example.com/f.json", "name": "   "}]}
    with pytest.raises(ValueError, match="'name' must not be blank"):
        main._validate_config(cfg)


def test_validate_config_settings_zero_value():
    cfg = {
        "folders": [{"url": "https://example.com/f.json"}],
        "settings": {"batch_size": 0},
    }
    with pytest.raises(ValueError, match="positive integer"):
        main._validate_config(cfg)


def test_validate_config_settings_negative_value():
    cfg = {
        "folders": [{"url": "https://example.com/f.json"}],
        "settings": {"max_retries": -1},
    }
    with pytest.raises(ValueError, match="positive integer"):
        main._validate_config(cfg)


def test_validate_config_settings_not_a_dict():
    cfg = {
        "folders": [{"url": "https://example.com/f.json"}],
        "settings": "bad",
    }
    with pytest.raises(ValueError, match="'settings' must be a mapping"):
        main._validate_config(cfg)


# ─────────────────────────────────────────────────────────────────────────────
# load_config – happy paths
# ─────────────────────────────────────────────────────────────────────────────

def _write_config(tmp_path: Path, data: dict, filename: str = "config.yaml") -> Path:
    p = tmp_path / filename
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


def test_load_config_returns_defaults_when_no_file(tmp_path, monkeypatch):
    """No config file anywhere → built-in defaults are returned."""
    monkeypatch.chdir(tmp_path)
    cfg = main.load_config()
    assert cfg == main.get_default_config()


def test_load_config_reads_config_yaml(tmp_path, monkeypatch):
    """config.yaml in cwd is picked up automatically."""
    monkeypatch.chdir(tmp_path)
    data = {"folders": [{"url": "https://example.com/f.json"}]}
    _write_config(tmp_path, data)
    cfg = main.load_config()
    assert cfg["folders"][0]["url"] == "https://example.com/f.json"


def test_load_config_reads_config_yml(tmp_path, monkeypatch):
    """config.yml (alternative extension) is also recognised."""
    monkeypatch.chdir(tmp_path)
    data = {"folders": [{"url": "https://example.com/f.json"}]}
    _write_config(tmp_path, data, filename="config.yml")
    cfg = main.load_config()
    assert cfg["folders"][0]["url"] == "https://example.com/f.json"


def test_load_config_explicit_path(tmp_path):
    """Explicit --config path is used when given."""
    data = {"folders": [{"url": "https://example.com/explicit.json"}]}
    p = _write_config(tmp_path, data, filename="my-config.yaml")
    cfg = main.load_config(config_path=str(p))
    assert cfg["folders"][0]["url"] == "https://example.com/explicit.json"


def test_load_config_explicit_path_takes_precedence_over_cwd(tmp_path, monkeypatch):
    """Explicit path wins over auto-discovered cwd config."""
    monkeypatch.chdir(tmp_path)
    cwd_data = {"folders": [{"url": "https://example.com/cwd.json"}]}
    _write_config(tmp_path, cwd_data)

    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()
    explicit_data = {"folders": [{"url": "https://example.com/explicit.json"}]}
    explicit_p = explicit_dir / "cfg.yaml"
    explicit_p.write_text(yaml.dump(explicit_data), encoding="utf-8")

    cfg = main.load_config(config_path=str(explicit_p))
    assert cfg["folders"][0]["url"] == "https://example.com/explicit.json"


# ─────────────────────────────────────────────────────────────────────────────
# load_config – error paths
# ─────────────────────────────────────────────────────────────────────────────

def test_load_config_invalid_yaml_exits(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("folders: [bad: yaml: \x00", encoding="utf-8")
    with pytest.raises(SystemExit):
        main.load_config()


def test_load_config_invalid_schema_exits(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    data = {"folders": [{"url": "http://not-https.com/f.json"}]}
    _write_config(tmp_path, data)
    with pytest.raises(SystemExit):
        main.load_config()


def test_load_config_explicit_missing_path_exits(tmp_path):
    with pytest.raises(SystemExit):
        main.load_config(config_path=str(tmp_path / "nonexistent.yaml"))


def test_load_config_empty_file_exits(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("", encoding="utf-8")
    with pytest.raises(SystemExit):
        main.load_config()


# ─────────────────────────────────────────────────────────────────────────────
# parse_args – --config flag
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_args_config_default_is_none(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "--dry-run"])
    args = main.parse_args()
    assert args.config is None


def test_parse_args_config_long_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "--config", "/tmp/cfg.yaml", "--dry-run"])
    args = main.parse_args()
    assert args.config == "/tmp/cfg.yaml"


def test_parse_args_config_short_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "-c", "/tmp/cfg.yaml", "--dry-run"])
    args = main.parse_args()
    assert args.config == "/tmp/cfg.yaml"


# ─────────────────────────────────────────────────────────────────────────────
# config.yaml.example can be parsed and validated
# ─────────────────────────────────────────────────────────────────────────────

def test_config_yaml_example_is_valid():
    """The shipped example file must parse cleanly and pass validation."""
    example = Path(__file__).parent.parent / "config.yaml.example"
    assert example.exists(), "config.yaml.example not found in repo root"
    cfg = main.load_config(config_path=str(example))
    assert "folders" in cfg
    assert len(cfg["folders"]) > 0
