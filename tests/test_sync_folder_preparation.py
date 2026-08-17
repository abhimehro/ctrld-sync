"""Characterization tests for folder lookup, polling, and preparation."""

from __future__ import annotations

import concurrent.futures
from collections.abc import Callable
from typing import Any

import pytest

import api_client
import config
import sync
from models import SyncContext


class _Response:
    def __init__(self, payload: Any = None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error

    def json(self) -> Any:
        if self.error is not None:
            raise self.error
        return self.payload


class _ImmediateExecutor:
    def __init__(self) -> None:
        self.submissions: list[str] = []

    def submit(self, fn: Callable[..., Any], *args: Any) -> concurrent.futures.Future:
        self.submissions.append(fn.__name__)
        future: concurrent.futures.Future = concurrent.futures.Future()
        try:
            future.set_result(fn(*args))
        except Exception as exc:
            future.set_exception(exc)
        return future


def _preparation(executor: _ImmediateExecutor, no_delete: bool) -> Any:
    return sync._FolderPreparationContext(
        client=object(),  # type: ignore[arg-type]
        profile_id="profile",
        shared_executor=executor,  # type: ignore[arg-type]
        no_delete=no_delete,
    )


def _folder_data(name: str) -> Any:
    return {"group": {"group": name}, "rules": []}


def _poll_context() -> SyncContext:
    return SyncContext(
        profile_id="profile",
        client=object(),  # type: ignore[arg-type]
        existing_rules=set(),
    )


def test_extracts_folder_from_direct_response_and_logs_source(caplog):
    with caplog.at_level("INFO", logger=sync.log.name):
        result = sync._extract_from_groups_list(
            [{"group": " New Folder ", "PK": "folder-1"}], "New Folder"
        )

    assert result == "folder-1"
    assert "Created folder New Folder (ID folder-1) [Direct]" in caplog.text


def test_extract_scans_past_invalid_duplicate_for_valid_id(caplog):
    with caplog.at_level("INFO", logger=sync.log.name):
        result = sync._extract_from_groups_list(
            [
                {"group": "Folder", "PK": "../invalid"},
                {"group": "Folder", "PK": "valid-id"},
            ],
            "Folder",
        )

    assert result == "valid-id"
    assert "API returned invalid folder ID: ../invalid" in caplog.text
    assert "[Direct]" in caplog.text


def test_extract_ignores_non_dict_entries_and_missing_pk():
    assert (
        sync._extract_from_groups_list(
            ["not-a-group", {"group": "Folder"}, {"group": "Other", "PK": "id"}],
            "Folder",
        )
        is None
    )


def test_extract_non_string_group_propagates():
    with pytest.raises(AttributeError):
        sync._extract_from_groups_list([{"group": 42, "PK": "id"}], "Folder")


@pytest.mark.parametrize(
    ("payload", "warns"),
    [
        (None, True),
        ({"body": None}, True),
        ({"body": {"groups": None}}, True),
        ({"body": {"groups": {}}}, False),
        ({"body": {"groups": [1, "not-a-group"]}}, False),
    ],
)
def test_poll_malformed_response_is_retryable(monkeypatch, payload, warns, caplog):
    responses = [_Response(payload)] * (api_client.MAX_RETRIES + 1)
    monkeypatch.setattr(sync, "_api_get", lambda *args: responses.pop(0))
    waits: list[tuple[int, str]] = []
    monkeypatch.setattr(sync, "countdown_timer", lambda *args: waits.append(args))

    with caplog.at_level("WARNING", logger=sync.log.name):
        result = sync._poll_for_folder_id(_poll_context(), "Folder")

    assert result is None
    assert len(waits) == api_client.MAX_RETRIES
    assert caplog.text.count("Error fetching groups on attempt") == (
        api_client.MAX_RETRIES + 1 if warns else 0
    )
    if warns:
        assert f"attempt {api_client.MAX_RETRIES}" in caplog.text


def test_poll_finds_folder_on_first_attempt(monkeypatch, caplog):
    monkeypatch.setattr(
        sync,
        "_api_get",
        lambda *args: _Response(
            {"body": {"groups": [{"group": "Folder", "PK": "id"}]}}
        ),
    )
    waits: list[tuple[int, str]] = []
    monkeypatch.setattr(sync, "countdown_timer", lambda *args: waits.append(args))

    with caplog.at_level("INFO", logger=sync.log.name):
        result = sync._poll_for_folder_id(_poll_context(), "Folder")

    assert result == "id"
    assert waits == []
    assert "[Polled]" in caplog.text


def test_poll_finds_folder_after_misses(monkeypatch):
    responses = [
        _Response({"body": {"groups": []}}),
        _Response({"body": {"groups": [{"group": "Folder", "PK": "id"}]}}),
    ]
    monkeypatch.setattr(sync, "_api_get", lambda *args: responses.pop(0))
    waits: list[tuple[int, str]] = []
    monkeypatch.setattr(sync, "countdown_timer", lambda *args: waits.append(args))

    assert sync._poll_for_folder_id(_poll_context(), "Folder") == "id"
    assert waits == [
        (
            config.FOLDER_CREATION_DELAY,
            "Waiting for folder 'Folder' to appear",
        )
    ]


def test_poll_retry_exhaustion_has_exact_calls_waits_and_final_error(
    monkeypatch, caplog
):
    responses = [_Response({"body": {"groups": []}})] * (api_client.MAX_RETRIES + 1)
    get_calls: list[int] = []
    def side_effect(*args):
        get_calls.append(1)
        return responses.pop(0)
    monkeypatch.setattr(
        sync, "_api_get", side_effect
    )
    waits: list[tuple[int, str]] = []
    monkeypatch.setattr(sync, "countdown_timer", lambda *args: waits.append(args))

    with caplog.at_level("ERROR", logger=sync.log.name):
        result = sync._poll_for_folder_id(_poll_context(), "Folder")

    assert result is None
    assert len(get_calls) == api_client.MAX_RETRIES + 1
    assert len(waits) == api_client.MAX_RETRIES
    assert [delay for delay, _ in waits] == [
        config.FOLDER_CREATION_DELAY * (attempt + 1)
        for attempt in range(api_client.MAX_RETRIES)
    ]
    assert (
        caplog.text.count("Folder Folder was not found after creation and retries.")
        == 1
    )


def test_poll_fetch_exception_then_success_logs_zero_based_attempt(monkeypatch, caplog):
    responses = [
        _Response(error=ValueError("bad response")),
        _Response({"body": {"groups": [{"group": "Folder", "PK": "id"}]}}),
    ]
    monkeypatch.setattr(sync, "_api_get", lambda *args: responses.pop(0))
    waits: list[tuple[int, str]] = []
    monkeypatch.setattr(sync, "countdown_timer", lambda *args: waits.append(args))

    with caplog.at_level("WARNING", logger=sync.log.name):
        result = sync._poll_for_folder_id(_poll_context(), "Folder")

    assert result == "id"
    assert "Error fetching groups on attempt 0: bad response" in caplog.text
    assert waits == [
        (
            config.FOLDER_CREATION_DELAY,
            "Waiting for folder 'Folder' to appear",
        )
    ]


def test_poll_non_string_group_is_swallowed_and_warned(monkeypatch, caplog):
    responses = [
        _Response({"body": {"groups": [{"group": 42}]}}),
        _Response({"body": {"groups": [{"group": "Folder", "PK": "id"}]}}),
    ]
    monkeypatch.setattr(sync, "_api_get", lambda *args: responses.pop(0))
    monkeypatch.setattr(sync, "countdown_timer", lambda *args: None)

    with caplog.at_level("WARNING", logger=sync.log.name):
        result = sync._poll_for_folder_id(_poll_context(), "Folder")

    assert result == "id"
    assert "Error fetching groups on attempt 0" in caplog.text


def test_poll_matching_group_without_pk_continues(monkeypatch):
    responses = [
        _Response({"body": {"groups": [{"group": "Folder"}]}}),
        _Response({"body": {"groups": [{"group": "Folder", "PK": "id"}]}}),
    ]
    monkeypatch.setattr(sync, "_api_get", lambda *args: responses.pop(0))
    monkeypatch.setattr(sync, "countdown_timer", lambda *args: None)

    assert sync._poll_for_folder_id(_poll_context(), "Folder") == "id"


def test_poll_invalid_pk_returns_without_wait_or_final_error(monkeypatch, caplog):
    monkeypatch.setattr(
        sync,
        "_api_get",
        lambda *args: _Response(
            {"body": {"groups": [{"group": "Folder", "PK": "../invalid"}]}}
        ),
    )
    waits: list[tuple[int, str]] = []
    monkeypatch.setattr(sync, "countdown_timer", lambda *args: waits.append(args))

    with caplog.at_level("ERROR", logger=sync.log.name):
        result = sync._poll_for_folder_id(_poll_context(), "Folder")

    assert result is None
    assert waits == []
    assert "API returned invalid folder ID: ../invalid" in caplog.text
    assert "was not found after creation and retries" not in caplog.text
    assert "[Polled]" not in caplog.text


def test_poll_stops_on_first_invalid_duplicate_before_valid(monkeypatch, caplog):
    monkeypatch.setattr(
        sync,
        "_api_get",
        lambda *args: _Response(
            {
                "body": {
                    "groups": [
                        {"group": "Folder", "PK": "../invalid"},
                        {"group": "Folder", "PK": "valid-id"},
                    ]
                }
            }
        ),
    )
    monkeypatch.setattr(sync, "countdown_timer", lambda *args: None)

    with caplog.at_level("ERROR", logger=sync.log.name):
        result = sync._poll_for_folder_id(_poll_context(), "Folder")

    assert result is None
    assert "Created folder Folder (ID valid-id)" not in caplog.text


def test_prepare_access_failure_submits_nothing(monkeypatch):
    executor = _ImmediateExecutor()
    monkeypatch.setattr(sync, "verify_access_and_get_folders", lambda *args: None)

    result = sync._prepare_folders_and_rules(
        _preparation(executor, False), [_folder_data("Folder")]
    )

    assert result == (None, set())
    assert executor.submissions == []


def test_prepare_no_delete_scans_all_folders_without_wait_or_deletes(monkeypatch):
    executor = _ImmediateExecutor()
    existing = {"Keep": "keep-id", "Replace": "replace-id"}
    scanned: list[dict[str, str]] = []
    monkeypatch.setattr(sync, "verify_access_and_get_folders", lambda *args: existing)
    def side_effect(client, profile, folders):
        scanned.append(folders.copy())
        return {"rule"}
    monkeypatch.setattr(
        sync,
        "get_all_existing_rules",
        side_effect,
    )
    monkeypatch.setattr(sync, "delete_folder", lambda *args: pytest.fail("deleted"))
    waits: list[tuple[int, str]] = []
    monkeypatch.setattr(sync, "countdown_timer", lambda *args: waits.append(args))

    result = sync._prepare_folders_and_rules(
        _preparation(executor, True), [_folder_data("Replace")]
    )

    assert result == (existing, {"rule"})
    assert scanned == [existing]
    assert waits == []


def test_prepare_removes_replacements_from_scan_before_failed_deletion(monkeypatch):
    executor = _ImmediateExecutor()
    existing = {"Replace": "replace-id", "Keep": "keep-id"}
    scanned: list[dict[str, str]] = []
    monkeypatch.setattr(sync, "verify_access_and_get_folders", lambda *args: existing)
    def side_effect(client, profile, folders):
        scanned.append(folders.copy())
        return set()
    monkeypatch.setattr(
        sync,
        "get_all_existing_rules",
        side_effect,
    )
    monkeypatch.setattr(sync, "delete_folder", lambda *args: False)
    monkeypatch.setattr(sync, "countdown_timer", lambda *args: None)

    result = sync._prepare_folders_and_rules(
        _preparation(executor, False), [_folder_data("Replace")]
    )

    assert scanned == [{"Keep": "keep-id"}]
    assert result[0] == existing


@pytest.mark.parametrize(
    ("outcomes", "expected_folders", "waits"),
    [
        ({"A": True, "B": True}, {}, 1),
        ({"A": True, "B": False}, {"B": "b-id"}, 1),
        ({"A": False, "B": False}, {"A": "a-id", "B": "b-id"}, 0),
        ({"A": "raise", "B": False}, {"A": "a-id", "B": "b-id"}, 0),
    ],
)
def test_prepare_deletion_outcomes(monkeypatch, outcomes, expected_folders, waits):
    executor = _ImmediateExecutor()
    existing = {"A": "a-id", "B": "b-id"}
    monkeypatch.setattr(sync, "verify_access_and_get_folders", lambda *args: existing)
    monkeypatch.setattr(sync, "get_all_existing_rules", lambda *args: set())

    def delete(_client, _profile, name, _folder_id):
        if outcomes[name] == "raise":
            raise RuntimeError("delete failed")
        return outcomes[name]

    monkeypatch.setattr(sync, "delete_folder", delete)
    waits_seen: list[tuple[int, str]] = []
    monkeypatch.setattr(sync, "countdown_timer", lambda *args: waits_seen.append(args))

    result = sync._prepare_folders_and_rules(
        _preparation(executor, False),
        [_folder_data("A"), _folder_data("B")],
    )

    assert result[0] == expected_folders
    assert len(waits_seen) == waits
    if waits:
        assert waits_seen == [(60, "Waiting for deletions to propagate")]


def test_prepare_rules_future_success(monkeypatch):
    executor = _ImmediateExecutor()
    monkeypatch.setattr(
        sync, "verify_access_and_get_folders", lambda *args: {"Folder": "id"}
    )
    monkeypatch.setattr(sync, "get_all_existing_rules", lambda *args: {"rule"})
    monkeypatch.setattr(sync, "delete_folder", lambda *args: True)
    monkeypatch.setattr(sync, "countdown_timer", lambda *args: None)

    assert sync._prepare_folders_and_rules(
        _preparation(executor, False), [_folder_data("Folder")]
    ) == ({}, {"rule"})


def test_prepare_rules_future_failure_returns_empty_set(monkeypatch, caplog):
    executor = _ImmediateExecutor()
    monkeypatch.setattr(
        sync, "verify_access_and_get_folders", lambda *args: {"Folder": "id"}
    )
    monkeypatch.setattr(
        sync,
        "get_all_existing_rules",
        lambda *args: (_ for _ in ()).throw(RuntimeError("rules failed")),
    )

    with caplog.at_level("ERROR", logger=sync.log.name):
        result = sync._prepare_folders_and_rules(
            _preparation(executor, True), [_folder_data("Folder")]
        )

    assert result == ({"Folder": "id"}, set())
    assert "Failed to fetch existing rules in background: rules failed" in caplog.text


def test_prepare_submits_rules_before_delete_and_preserves_duplicate_targets(
    monkeypatch,
):
    executor = _ImmediateExecutor()

    def verify(*args):
        return {"Folder": "id"}

    def rules(*args):
        return set()

    monkeypatch.setattr(sync, "verify_access_and_get_folders", verify)
    monkeypatch.setattr(sync, "get_all_existing_rules", rules)
    delete_calls: list[str] = []

    def delete(_client, _profile, name, _folder_id):
        delete_calls.append(name)
        return True

    monkeypatch.setattr(sync, "delete_folder", delete)
    monkeypatch.setattr(sync, "countdown_timer", lambda *args: None)

    sync._prepare_folders_and_rules(
        _preparation(executor, False),
        [_folder_data("Folder"), _folder_data("Folder")],
    )

    assert executor.submissions[:3] == ["rules", "delete", "delete"]
    assert delete_calls == ["Folder", "Folder"]
