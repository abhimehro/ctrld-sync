import importlib
import os
import sys
from unittest.mock import MagicMock, call, patch

import httpx
import pytest

import main


# Helper to reload main with specific env/tty settings
def reload_main_with_env(monkeypatch, no_color=None, isatty=True):
    if no_color is not None:
        monkeypatch.setenv("NO_COLOR", no_color)
    else:
        monkeypatch.delenv("NO_COLOR", raising=False)

    with patch("sys.stderr") as mock_stderr, patch("sys.stdout") as mock_stdout:
        mock_stderr.isatty.return_value = isatty
        mock_stdout.isatty.return_value = isatty
        importlib.reload(main)
        return main


# Case 1: USE_COLORS respects NO_COLOR environment variable and terminal isatty status
def test_use_colors_respects_no_color(monkeypatch):
    m = reload_main_with_env(monkeypatch, no_color="1", isatty=True)
    assert m.USE_COLORS is False


def test_use_colors_respects_isatty_true(monkeypatch):
    m = reload_main_with_env(monkeypatch, no_color=None, isatty=True)
    assert m.USE_COLORS is True


def test_use_colors_respects_isatty_false(monkeypatch):
    m = reload_main_with_env(monkeypatch, no_color=None, isatty=False)
    assert m.USE_COLORS is False


# Case 2: get_all_existing_rules updates all_rules set correctly without locking
def test_get_all_existing_rules_updates_correctly(monkeypatch):
    # Setup
    m = reload_main_with_env(monkeypatch, no_color="1")  # Disable colors for simplicity
    mock_client = MagicMock()
    profile_id = "test_profile"

    # Mock helpers
    mock_list_folders = MagicMock(return_value={"FolderA": "id_A", "FolderB": "id_B"})
    monkeypatch.setattr(m, "list_existing_folders", mock_list_folders)

    # Mock _api_get to return different rules for root vs folders
    def side_effect(client, url):
        mock_resp = MagicMock()
        if url.endswith("/rules"):  # Root rules
            mock_resp.json.return_value = {"body": {"rules": [{"PK": "rule_root"}]}}
        elif "id_A" in url:
            mock_resp.json.return_value = {
                "body": {"rules": [{"PK": "rule_A1"}, {"PK": "rule_A2"}]}
            }
        elif "id_B" in url:
            mock_resp.json.return_value = {"body": {"rules": [{"PK": "rule_B1"}]}}
        return mock_resp

    monkeypatch.setattr(m, "_api_get", side_effect)

    # Execution
    rules = m.get_all_existing_rules(mock_client, profile_id)

    # Verification
    expected_rules = {"rule_root", "rule_A1", "rule_A2", "rule_B1"}
    assert rules == expected_rules


# Case 3: push_rules updates data dictionary with pre-calculated batch keys correctly
def test_push_rules_updates_data_with_batch_keys(monkeypatch):
    m = reload_main_with_env(monkeypatch)
    mock_client = MagicMock()
    mock_post_form = MagicMock()
    monkeypatch.setattr(m, "_api_post_form", mock_post_form)

    # Create enough hostnames for one batch
    batch_size = m.BATCH_SIZE
    hostnames = [f"host{i}" for i in range(batch_size)]

    m.push_rules(
        profile_id="p1",
        folder_name="f1",
        folder_id="fid1",
        do=1,
        status=1,
        hostnames=hostnames,
        existing_rules=set(),
        client=mock_client,
    )

    assert mock_post_form.called
    args, kwargs = mock_post_form.call_args
    data_sent = kwargs["data"]

    # Check if hostnames[0], hostnames[1]... are in data
    assert "hostnames[0]" in data_sent
    assert data_sent["hostnames[0]"] == "host0"
    assert f"hostnames[{batch_size-1}]" in data_sent
    assert data_sent[f"hostnames[{batch_size-1}]"] == f"host{batch_size-1}"
    assert data_sent["do"] == "1"
    assert data_sent["group"] == "fid1"


# Case 3b: push_rules updates existing_rules set correctly
def test_push_rules_updates_existing_rules(monkeypatch):
    m = reload_main_with_env(monkeypatch)
    mock_client = MagicMock()
    monkeypatch.setattr(m, "_api_post_form", MagicMock())

    hostnames = ["h1", "h2"]
    existing_rules = set()

    m.push_rules(
        profile_id="p1",
        folder_name="f1",
        folder_id="fid1",
        do=1,
        status=1,
        hostnames=hostnames,
        existing_rules=existing_rules,
        client=mock_client,
    )

    assert "h1" in existing_rules
    assert "h2" in existing_rules


# Case 4: push_rules logs info conditionally based on USE_COLORS flag
def test_push_rules_logs_conditionally_use_colors(monkeypatch):
    # Test when USE_COLORS is False
    m_no_color = reload_main_with_env(monkeypatch, no_color="1")
    monkeypatch.setattr(m_no_color, "_api_post_form", MagicMock())
    mock_log = MagicMock()
    monkeypatch.setattr(m_no_color, "log", mock_log)

    hostnames = ["h1"]
    m_no_color.push_rules("p", "f", "fid", 1, 1, hostnames, set(), MagicMock())

    # Should log info when USE_COLORS is False (lines 567-571)
    # log.info("Folder %s – batch %d: added %d rules", ...)
    assert mock_log.info.called

    found_batch_log = False
    for call_obj in mock_log.info.call_args_list:
        args, _ = call_obj
        if "batch" in str(args) and "added" in str(args):
            found_batch_log = True
            break
    assert found_batch_log, "Batch log message not found in log.info calls"

    # Test when USE_COLORS is True
    m_color = reload_main_with_env(monkeypatch, no_color=None, isatty=True)
    monkeypatch.setattr(m_color, "_api_post_form", MagicMock())
    monkeypatch.setattr(m_color, "log", mock_log)
    mock_log.reset_mock()

    m_color.push_rules("p", "f", "fid", 1, 1, hostnames, set(), MagicMock())

    # Should NOT log info for batch success when USE_COLORS is True
    # It might log other things, but not the batch success message handled by stderr
    # Check that the specific batch message is NOT logged
    for call_args in mock_log.info.call_args_list:
        args = call_args[0]
        if "batch" in str(args) and "added" in str(args):
            pytest.fail("Should not log batch info when USE_COLORS is True")


# Case 5: push_rules writes colored progress and completion messages to stderr when USE_COLORS is True
def test_push_rules_writes_colored_stderr(monkeypatch):
    m = reload_main_with_env(monkeypatch, no_color=None, isatty=True)
    monkeypatch.setattr(m, "_api_post_form", MagicMock())

    mock_stderr = MagicMock()
    monkeypatch.setattr(sys, "stderr", mock_stderr)

    hostnames = ["h1"]
    m.push_rules("p", "f", "fid", 1, 1, hostnames, set(), MagicMock())

    # Check for color codes in stderr writes
    # Look for CYAN (progress) and GREEN (completion)
    # Colors.CYAN defined in main might vary depending on reload, but since we reloaded with isatty=True
    # Colors class should have values.

    # We can check for calls containing specific substrings
    writes = [args[0] for args, _ in mock_stderr.write.call_args_list]
    combined_output = "".join(writes)

    # Verify progress message
    assert "🚀 Folder" in combined_output
    # Verify completion message
    assert "✅ Folder" in combined_output

    # Verify colors are present (checking for escape sequence intro \033)
    assert "\033[" in combined_output


# Case 6: Interactive prompts show helpful hints
def test_interactive_prompts_show_hints(monkeypatch, capsys):
    # Ensure environment is clean
    monkeypatch.delenv("PROFILE", raising=False)
    monkeypatch.delenv("TOKEN", raising=False)

    # Prevent dotenv from loading .env file which would restore the variables
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda: None)

    # Reload main with isatty=True to trigger interactive mode logic
    m = reload_main_with_env(monkeypatch, isatty=True)

    # Mock sys.stdin.isatty to return True
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    # Mock inputs to provide values immediately
    monkeypatch.setattr("builtins.input", lambda prompt="": "test_profile")
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "test_token")

    # Mock parse_args
    mock_args = MagicMock()
    mock_args.profiles = None
    mock_args.folder_url = None
    mock_args.dry_run = False
    mock_args.no_delete = False
    mock_args.plan_json = None
    monkeypatch.setattr(m, "parse_args", lambda: mock_args)

    # Mock internal functions to abort execution safely after prompts
    monkeypatch.setattr(
        m, "warm_up_cache", MagicMock(side_effect=RuntimeError("AbortTest"))
    )

    # Run main
    with pytest.raises(RuntimeError, match="AbortTest"):
        m.main()

    # Check output
    captured = capsys.readouterr()
    stdout = captured.out

    assert "You can find this in the URL of your profile" in stdout
    assert "https://controld.com/account/manage-account" in stdout


# Case 7: check_api_access handles success and errors correctly
def test_check_api_access_success(monkeypatch):
    m = reload_main_with_env(monkeypatch)
    mock_client = MagicMock()
    mock_client.get.return_value.raise_for_status.return_value = None

    assert m.check_api_access(mock_client, "valid_profile") is True


def test_check_api_access_401(monkeypatch):
    m = reload_main_with_env(monkeypatch)
    mock_client = MagicMock()

    # Simulate 401 response
    mock_response = MagicMock()
    mock_response.status_code = 401
    error = httpx.HTTPStatusError(
        "401 Unauthorized", request=MagicMock(), response=mock_response
    )
    mock_client.get.return_value.raise_for_status.side_effect = error

    # Mock log to verify output
    mock_log = MagicMock()
    monkeypatch.setattr(m, "log", mock_log)

    assert m.check_api_access(mock_client, "invalid_token") is False
    assert mock_log.critical.call_count >= 1
    # Check for authentication failed message
    args = str(mock_log.critical.call_args_list)
    assert "Authentication Failed" in args


def test_check_api_access_403(monkeypatch):
    m = reload_main_with_env(monkeypatch)
    mock_client = MagicMock()

    # Simulate 403 response
    mock_response = MagicMock()
    mock_response.status_code = 403
    error = httpx.HTTPStatusError(
        "403 Forbidden", request=MagicMock(), response=mock_response
    )
    mock_client.get.return_value.raise_for_status.side_effect = error

    mock_log = MagicMock()
    monkeypatch.setattr(m, "log", mock_log)

    assert m.check_api_access(mock_client, "forbidden_profile") is False
    assert mock_log.critical.call_count == 1
    assert "Access Denied" in str(mock_log.critical.call_args)


def test_check_api_access_404(monkeypatch):
    m = reload_main_with_env(monkeypatch)
    mock_client = MagicMock()

    # Simulate 404 response
    mock_response = MagicMock()
    mock_response.status_code = 404
    error = httpx.HTTPStatusError(
        "404 Not Found", request=MagicMock(), response=mock_response
    )
    mock_client.get.return_value.raise_for_status.side_effect = error

    mock_log = MagicMock()
    monkeypatch.setattr(m, "log", mock_log)

    assert m.check_api_access(mock_client, "missing_profile") is False
    assert mock_log.critical.call_count >= 1
    assert "Profile Not Found" in str(mock_log.critical.call_args_list)


def test_check_api_access_generic_http_error(monkeypatch):
    m = reload_main_with_env(monkeypatch)
    mock_client = MagicMock()

    # Simulate 500 response
    mock_response = MagicMock()
    mock_response.status_code = 500
    error = httpx.HTTPStatusError(
        "500 Server Error", request=MagicMock(), response=mock_response
    )
    mock_client.get.return_value.raise_for_status.side_effect = error

    mock_log = MagicMock()
    monkeypatch.setattr(m, "log", mock_log)

    assert m.check_api_access(mock_client, "profile") is False
    assert mock_log.error.called
    assert "500" in str(mock_log.error.call_args)


def test_check_api_access_network_error(monkeypatch):
    m = reload_main_with_env(monkeypatch)
    mock_client = MagicMock()

    # Simulate network error
    error = httpx.RequestError("Network failure", request=MagicMock())
    mock_client.get.side_effect = error

    mock_log = MagicMock()
    monkeypatch.setattr(m, "log", mock_log)

    assert m.check_api_access(mock_client, "profile") is False
    assert mock_log.error.called
    assert "Network failure" in str(mock_log.error.call_args)


# Case 8: extract_profile_id correctly extracts ID from URL or returns input
def test_extract_profile_id():
    # Regular ID
    assert main.extract_profile_id("12345") == "12345"
    # URL with /filters
    assert (
        main.extract_profile_id("https://controld.com/dashboard/profiles/12345/filters")
        == "12345"
    )
    # URL without /filters
    assert (
        main.extract_profile_id("https://controld.com/dashboard/profiles/12345")
        == "12345"
    )
    # URL with params
    assert (
        main.extract_profile_id("https://controld.com/dashboard/profiles/12345?foo=bar")
        == "12345"
    )
    # Clean up whitespace
    assert main.extract_profile_id("  12345  ") == "12345"
    # Invalid input returns as is (cleaned)
    assert main.extract_profile_id("random-string") == "random-string"
    # Empty input
    assert main.extract_profile_id("") == ""
    assert main.extract_profile_id(None) == ""


# Mock load_dotenv globally to prevent local .env from polluting tests
import dotenv

dotenv.load_dotenv = lambda **kwargs: None


# Case 9: Interactive input handles URL pasting
def test_interactive_input_extracts_id(monkeypatch, capsys):
    # Ensure environment is clean
    monkeypatch.delenv("PROFILE", raising=False)
    monkeypatch.delenv("TOKEN", raising=False)

    # Reload main with isatty=True
    m = reload_main_with_env(monkeypatch, isatty=True)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)

    # Provide URL as input
    url_input = "https://controld.com/dashboard/profiles/extracted_id/filters"
    monkeypatch.setattr("builtins.input", lambda prompt="": url_input)
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "test_token")

    # Mock parse_args
    mock_args = MagicMock()
    mock_args.profiles = None
    mock_args.folder_url = None
    mock_args.dry_run = False
    mock_args.no_delete = False
    mock_args.plan_json = None
    monkeypatch.setattr(m, "parse_args", lambda: mock_args)

    # Mock sync_profile to catch the call
    mock_sync = MagicMock(return_value=True)
    monkeypatch.setattr(m, "sync_profile", mock_sync)
    monkeypatch.setattr(m, "warm_up_cache", MagicMock())

    # Run main, expect clean exit
    with pytest.raises(SystemExit):
        m.main()

    # Verify sync_profile called with extracted ID
    args, _ = mock_sync.call_args
    assert args[0] == "extracted_id"

    # Verify prompt text update
    captured = capsys.readouterr()
    assert "(or just paste the URL)" in captured.out


# Case 10: validate_profile_id respects log_errors flag
def test_validate_profile_id_log_errors(monkeypatch):
    m = reload_main_with_env(monkeypatch)
    mock_log = MagicMock()
    monkeypatch.setattr(m, "log", mock_log)

    # Invalid ID with logging enabled (default)
    assert m.validate_profile_id("invalid spaces") is False
    assert mock_log.error.called

    mock_log.reset_mock()

    # Invalid ID with logging disabled
    assert m.validate_profile_id("invalid spaces", log_errors=False) is False
    assert not mock_log.error.called


# Case 11: get_validated_input retries on invalid input and returns valid input
def test_get_validated_input_retry(monkeypatch, capsys):
    m = reload_main_with_env(monkeypatch)

    # Mock input to return invalid first, then valid
    # First call: empty string -> "Value cannot be empty"
    # Second call: "invalid" -> Validator fails -> Error message
    # Third call: "valid" -> Validator passes
    input_mock = MagicMock(side_effect=["", "invalid", "valid"])
    monkeypatch.setattr("builtins.input", input_mock)

    validator = lambda x: x == "valid"

    result = m.get_validated_input("Prompt: ", validator, "Error message")

    assert result == "valid"
    assert input_mock.call_count == 3

    # Check output for error messages
    captured = capsys.readouterr()
    assert "Value cannot be empty" in captured.out
    assert "Error message" in captured.out


# Case 12: get_validated_input works with getpass
def test_get_validated_input_password(monkeypatch):
    m = reload_main_with_env(monkeypatch)

    getpass_mock = MagicMock(return_value="secret")
    monkeypatch.setattr("getpass.getpass", getpass_mock)

    validator = lambda x: True

    result = m.get_validated_input("Password: ", validator, "Error", is_password=True)

    assert result == "secret"
    getpass_mock.assert_called_once()


# Case 13: render_progress_bar renders correctly
def test_render_progress_bar(monkeypatch):
    m = reload_main_with_env(monkeypatch, no_color=None, isatty=True)
    mock_stderr = MagicMock()
    monkeypatch.setattr(sys, "stderr", mock_stderr)

    m.render_progress_bar(5, 10, "Test", prefix="T")

    # Check output
    writes = [args[0] for args, _ in mock_stderr.write.call_args_list]
    combined = "".join(writes)

    # \033[K clear line
    assert "\033[K" in combined
    # Prefix and Label
    assert "T Test" in combined
    # Progress bar and percentage
    assert "50%" in combined
    assert "5/10" in combined
    # Color codes (accessing instance Colors or m.Colors)
    assert m.Colors.CYAN in combined
    assert m.Colors.ENDC in combined


# Case 14: is_valid_rule logic correctness
def test_is_valid_rule_logic(monkeypatch):
    m = reload_main_with_env(monkeypatch)

    # Valid rules
    assert m.is_valid_rule("example.com")
    assert m.is_valid_rule("sub.example.com")
    assert m.is_valid_rule("1.2.3.4")
    assert m.is_valid_rule("2001:db8::1")
    assert m.is_valid_rule("192.168.1.0/24")
    assert m.is_valid_rule("example-domain.com")
    assert m.is_valid_rule("example_domain.com")
    assert m.is_valid_rule("*.example.com")

    # Invalid rules
    assert not m.is_valid_rule("")
    assert not m.is_valid_rule(" ")
    assert not m.is_valid_rule("example.com; rm -rf /")  # Injection attempt
    assert not m.is_valid_rule("<script>alert(1)</script>")  # XSS
    assert not m.is_valid_rule("example.com|cat /etc/passwd")  # Shell pipe
    assert not m.is_valid_rule("example.com&")
    assert not m.is_valid_rule("$variable")
