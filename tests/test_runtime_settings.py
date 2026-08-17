"""Tests for main._apply_runtime_settings."""

import pytest

import api_client
import config
import main


@pytest.fixture(autouse=True)
def defaults():
    """Set and restore a known baseline for runtime constants."""
    batch_size = 500
    batch_keys = [f"hostnames[{i}]" for i in range(batch_size)]
    delete_workers = 3
    max_retries = 10
    config.BATCH_SIZE = batch_size
    config.BATCH_KEYS = batch_keys[:]
    config.DELETE_WORKERS = delete_workers
    api_client.MAX_RETRIES = max_retries
    yield {
        "batch_size": batch_size,
        "batch_keys": batch_keys,
        "delete_workers": delete_workers,
        "max_retries": max_retries,
    }
    config.BATCH_SIZE = batch_size
    config.BATCH_KEYS = batch_keys[:]
    config.DELETE_WORKERS = delete_workers
    api_client.MAX_RETRIES = max_retries


@pytest.mark.parametrize(
    "key, value",
    [
        ("batch_size", 0),
        ("batch_size", -1),
        ("batch_size", True),
        ("batch_size", False),
        ("batch_size", 1.5),
        ("batch_size", "10"),
        ("delete_workers", 0),
        ("delete_workers", -1),
        ("delete_workers", True),
        ("delete_workers", False),
        ("delete_workers", 1.5),
        ("delete_workers", "10"),
        ("max_retries", 0),
        ("max_retries", -1),
        ("max_retries", True),
        ("max_retries", False),
        ("max_retries", 1.5),
        ("max_retries", "10"),
    ],
)
def test_apply_runtime_settings_ignores_invalid_values(defaults, key, value):
    """Invalid settings values must not mutate runtime constants."""
    main._apply_runtime_settings({"settings": {key: value}})
    assert defaults["batch_size"] == config.BATCH_SIZE
    assert defaults["batch_keys"] == config.BATCH_KEYS
    assert defaults["delete_workers"] == config.DELETE_WORKERS
    assert defaults["max_retries"] == api_client.MAX_RETRIES


@pytest.mark.parametrize(
    "key, value",
    [
        ("batch_size", None),
        ("delete_workers", None),
        ("max_retries", None),
    ],
)
def test_apply_runtime_settings_none_uses_defaults(defaults, key, value):
    """Explicit null/None settings must not mutate runtime constants."""
    main._apply_runtime_settings({"settings": {key: value}})
    assert defaults["batch_size"] == config.BATCH_SIZE
    assert defaults["batch_keys"] == config.BATCH_KEYS
    assert defaults["delete_workers"] == config.DELETE_WORKERS
    assert defaults["max_retries"] == api_client.MAX_RETRIES


@pytest.mark.parametrize(
    "key, value, expected_module, expected_attr, expected",
    [
        ("batch_size", 1, config, "BATCH_SIZE", 1),
        ("batch_size", 3, config, "BATCH_SIZE", 3),
        ("batch_size", 10, config, "BATCH_SIZE", 10),
        ("delete_workers", 1, config, "DELETE_WORKERS", 1),
        ("delete_workers", 3, config, "DELETE_WORKERS", 3),
        ("delete_workers", 10, config, "DELETE_WORKERS", 10),
        ("max_retries", 1, api_client, "MAX_RETRIES", 1),
        ("max_retries", 3, api_client, "MAX_RETRIES", 3),
        ("max_retries", 10, api_client, "MAX_RETRIES", 10),
    ],
)
def test_apply_runtime_settings_applies_valid_values(
    key, value, expected_module, expected_attr, expected
):
    """Valid positive int settings are applied to the matching runtime constant."""
    main._apply_runtime_settings({"settings": {key: value}})
    assert getattr(expected_module, expected_attr) == expected


def test_apply_runtime_settings_batch_size_regenerates_keys():
    """Changing batch_size also regenerates config.BATCH_KEYS."""
    main._apply_runtime_settings({"settings": {"batch_size": 2}})
    assert config.BATCH_SIZE == 2
    assert config.BATCH_KEYS == ["hostnames[0]", "hostnames[1]"]
