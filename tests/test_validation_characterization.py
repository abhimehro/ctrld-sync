"""Characterization tests for validation.py behavior preservation.

These tests pin the exact log messages and edge-case behavior of
validate_folder_data and sanitize_for_log so future refactors cannot silently
change them.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from typing import Any, cast

import pytest

import validation


@pytest.fixture(autouse=True)
def _restore_token():
    old = validation._token
    yield
    validation.set_token_for_redaction(old)


@pytest.mark.parametrize(
    "data,url,expected_log",
    [
        (cast(Any, []), "https://x.test", "Root must be a JSON object."),
        ({"group": 1}, "https://x.test", "'group' must be an object."),
        ({"group": {}}, "https://x.test", "Missing 'group.group' (folder name)."),
        (
            {"group": {"group": 123}},
            "https://x.test",
            "Folder name must be a string.",
        ),
        (
            {"group": {"group": ""}},
            "https://x.test",
            "Invalid folder name (empty, unsafe characters, or non-printable).",
        ),
        (
            {"group": {"group": "   "}},
            "https://x.test",
            "Invalid folder name (empty, unsafe characters, or non-printable).",
        ),
        (
            {"group": {"group": "<script>"}},
            "https://x.test",
            "Invalid folder name (empty, unsafe characters, or non-printable).",
        ),
        (
            {"group": {"group": "ok"}, "rules": "x"},
            "https://x.test",
            "'rules' must be a list.",
        ),
        (
            {"group": {"group": "ok"}, "rules": ["x"]},
            "https://x.test",
            "rules[0] must be an object.",
        ),
        (
            {"group": {"group": "ok"}, "rules": [{"PK": 123}]},
            "https://x.test",
            "rules[0].PK must be a string.",
        ),
        (
            {"group": {"group": "ok"}, "rule_groups": "x"},
            "https://x.test",
            "'rule_groups' must be a list.",
        ),
        (
            {"group": {"group": "ok"}, "rule_groups": ["x"]},
            "https://x.test",
            "rule_groups[0] must be an object.",
        ),
        (
            {"group": {"group": "ok"}, "rule_groups": [{"rules": "x"}]},
            "https://x.test",
            "rule_groups[0].rules must be a list.",
        ),
        (
            {
                "group": {"group": "ok"},
                "rule_groups": [{"rules": [{"PK": 123}]}],
            },
            "https://x.test",
            "rule_groups[0].rules[0].PK must be a string.",
        ),
        # Group with no 'rules' key is valid; URL should be sanitized in logs.
        (
            {"group": {"group": "ok"}, "rule_groups": [{}]},
            "https://user:pass@x.test/path?token=secret",
            "",  # valid, no error log
        ),
        (
            {"group": {"group": "ok"}, "rules": []},
            "https://x.test",
            "",
        ),
        (
            {"group": {"group": "ok"}, "rule_groups": [{"rules": []}]},
            "https://x.test",
            "",
        ),
    ],
)
def test_validate_folder_data_exact_logs(data, url, expected_log, caplog):
    caplog.set_level(logging.ERROR, logger="validation")
    result = validation.validate_folder_data(data, url)
    if expected_log:
        assert result is False
        assert expected_log in caplog.text
    else:
        assert result is True
        assert caplog.text == ""


def test_validate_folder_data_group_is_list(caplog):
    caplog.set_level(logging.ERROR, logger="validation")
    data: dict[str, Any] = {"group": []}
    assert validation.validate_folder_data(data, "https://x.test") is False
    assert "'group' must be an object." in caplog.text


def test_validate_folder_data_dict_subclass_rule_is_rejected_silently(caplog):
    """OrderedDict fails the fast path and matches no isinstance branch."""
    caplog.set_level(logging.ERROR, logger="validation")
    data = {
        "group": {"group": "F"},
        "rules": [OrderedDict([("PK", "a.com")])],
    }
    assert validation.validate_folder_data(data, "https://x.test") is False
    assert caplog.text == ""


def test_set_token_for_redaction_after_import():
    validation.set_token_for_redaction("SEKRET")
    sanitized = validation.sanitize_for_log("prefix SEKRET suffix")
    assert "SEKRET" not in sanitized
    assert "[REDACTED]" in sanitized


def test_sanitize_redaction_before_repr_escaping():
    """repr() must run after token redaction, or a token with newlines leaks."""
    validation.set_token_for_redaction("tok\nen")
    sanitized = validation.sanitize_for_log("prefix tok\nen suffix")
    assert "tok" not in sanitized


def test_sanitize_redacts_token_in_nested_containers():
    validation.set_token_for_redaction("NESTED_SECRET")
    sanitized = validation.sanitize_for_log({"api_token": "NESTED_SECRET"})
    assert "NESTED_SECRET" not in sanitized
    assert "[REDACTED]" in sanitized
