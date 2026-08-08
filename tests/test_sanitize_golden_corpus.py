"""Differential golden-file test for sanitize_for_log."""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest

import validation


def _load_corpus_and_golden() -> tuple[str, list[Any], list[str]]:
    data_dir = pathlib.Path(__file__).resolve().parent / "data"
    with open(data_dir / "sanitize_corpus.json", encoding="utf-8") as f:
        corpus = json.load(f)
    with open(data_dir / "sanitize_golden.json", encoding="utf-8") as f:
        golden = json.load(f)
    assert corpus["token"] == golden["token"]
    return corpus["token"], corpus["inputs"], golden["outputs"]


def _decode_input(obj: Any) -> Any:
    if isinstance(obj, dict) and obj.get("__type__") == "exception":
        return Exception(obj["message"])
    return obj


@pytest.fixture(autouse=True)
def _restore_token():
    old = validation._token
    yield
    validation._token = old


def test_sanitize_golden_corpus():
    token, inputs, expected_outputs = _load_corpus_and_golden()
    validation.set_token_for_redaction(token)
    for raw_input, expected in zip(inputs, expected_outputs, strict=True):
        inp = _decode_input(raw_input)
        assert validation.sanitize_for_log(inp) == expected
