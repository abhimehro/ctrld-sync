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


# Case 7: verify_access_and_get_folders handles success and errors correctly
def test_verify_access_and_get_folders_success(monkeypatch):
    m = reload_main_with_env(monkeypatch)
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "body": {
            "groups": [
                {"group": "Folder A", "PK": "id_a"},
                {"group": "Folder B", "PK": "id_b"}
            ]
        }
    }
    mock_client.get.return_value = mock_response
    mock_response.raise_for_status.return_value = None

    result = m.verify_access_and_get_folders(mock_client, "valid_profile")
    assert result == {"Folder A": "id_a", "Folder B": "id_b"}


def test_verify_access_and_get_folders_401(monkeypatch):
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

    assert m.verify_access_and_get_folders(mock_client, "invalid_token") is None
    assert mock_log.critical.call_count >= 1
    # Check for authentication failed message
    args = str(mock_log.critical.call_args_list)
    assert "Authentication Failed" in args


def test_verify_access_and_get_folders_403(monkeypatch):
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

    assert m.verify_access_and_get_folders(mock_client, "forbidden_profile") is None
    assert mock_log.critical.call_count == 1
    assert "Access Denied" in str(mock_log.critical.call_args)


def test_verify_access_and_get_folders_404(monkeypatch):
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

    assert m.verify_access_and_get_folders(mock_client, "missing_profile") is None
    assert mock_log.critical.call_count >= 1
    assert "Profile Not Found" in str(mock_log.critical.call_args_list)


def test_verify_access_and_get_folders_500_retry(monkeypatch):
    """Test that verify_access_and_get_folders retries on 500 errors."""
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
    monkeypatch.setattr(m, "RETRY_DELAY", 0.001)
    monkeypatch.setattr("time.sleep", lambda x: None)
    monkeypatch.setattr(m, "MAX_RETRIES", 2)

    assert m.verify_access_and_get_folders(mock_client, "profile") is None
    assert mock_client.get.call_count == 2
    assert mock_log.error.called
    assert "500" in str(mock_log.error.call_args)


def test_verify_access_and_get_folders_network_error(monkeypatch):
    """Test that verify_access_and_get_folders handles network errors."""
    m = reload_main_with_env(monkeypatch)
    mock_client = MagicMock()

    # Simulate network error
    error = httpx.RequestError("Network failure", request=MagicMock())
    mock_client.get.side_effect = error

    mock_log = MagicMock()
    monkeypatch.setattr(m, "log", mock_log)
    monkeypatch.setattr(m, "RETRY_DELAY", 0.001)
    monkeypatch.setattr("time.sleep", lambda x: None)
    monkeypatch.setattr(m, "MAX_RETRIES", 2)

    assert m.verify_access_and_get_folders(mock_client, "profile") is None
    assert mock_client.get.call_count == 2
    assert mock_log.error.called
    error_msg = str(mock_log.error.call_args)
    assert "Network error" in error_msg or "access verification" in error_msg


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


# Case 14: get_validated_input handles KeyboardInterrupt gracefully
def test_get_validated_input_interrupt(monkeypatch, capsys):
    m = reload_main_with_env(monkeypatch)

    # Mock input to raise KeyboardInterrupt
    monkeypatch.setattr("builtins.input", MagicMock(side_effect=KeyboardInterrupt))

    with pytest.raises(SystemExit) as e:
        m.get_validated_input("Prompt: ", lambda x: True, "Error")

    # Check exit code is 130
    assert e.value.code == 130

    # Check friendly message
    captured = capsys.readouterr()
    assert "Input cancelled" in captured.out


# Case 15: get_validated_input handles both KeyboardInterrupt and EOFError for regular and password inputs
@pytest.mark.parametrize("exception", [KeyboardInterrupt, EOFError])
@pytest.mark.parametrize(
    "is_password,mock_path",
    [(False, "builtins.input"), (True, "getpass.getpass")],
)
def test_get_validated_input_graceful_exit_comprehensive(
    monkeypatch, capsys, exception, is_password, mock_path
):
    """Test graceful exit on user cancellation (Ctrl+C/Ctrl+D) for both regular and password inputs."""
    m = reload_main_with_env(monkeypatch)

    # Mock input to raise the specified exception
    monkeypatch.setattr(mock_path, MagicMock(side_effect=exception))

    with pytest.raises(SystemExit) as e:
        m.get_validated_input(
            "Prompt: ", lambda x: True, "Error", is_password=is_password
        )

    # Check exit code is 130 (standard for SIGINT)
    assert e.value.code == 130

    # Check friendly cancellation message is displayed
    captured = capsys.readouterr()
    assert "Input cancelled" in captured.out


# Case 16: _get_progress_bar_width returns correct values based on terminal size
def test_get_progress_bar_width(monkeypatch):
    """Test dynamic progress bar width calculation with various terminal sizes."""
    m = reload_main_with_env(monkeypatch)

    # Test very narrow terminal (30 cols) -> min clamp at 15
    monkeypatch.setattr("shutil.get_terminal_size", lambda fallback: (30, 24))
    width = m._get_progress_bar_width()
    assert width == 15  # 30 * 0.4 = 12, clamped to min 15

    # Test narrow terminal (50 cols) -> 40% = 20
    monkeypatch.setattr("shutil.get_terminal_size", lambda fallback: (50, 24))
    width = m._get_progress_bar_width()
    assert width == 20  # 50 * 0.4 = 20

    # Test standard terminal (80 cols) -> 40% = 32
    monkeypatch.setattr("shutil.get_terminal_size", lambda fallback: (80, 24))
    width = m._get_progress_bar_width()
    assert width == 32  # 80 * 0.4 = 32

    # Test medium terminal (100 cols) -> 40% = 40
    monkeypatch.setattr("shutil.get_terminal_size", lambda fallback: (100, 24))
    width = m._get_progress_bar_width()
    assert width == 40  # 100 * 0.4 = 40

    # Test wide terminal (200 cols) -> max clamp at 50
    monkeypatch.setattr("shutil.get_terminal_size", lambda fallback: (200, 24))
    width = m._get_progress_bar_width()
    assert width == 50  # 200 * 0.4 = 80, clamped to max 50


# Case 17: countdown_timer and render_progress_bar use dynamic width helper
def test_progress_functions_use_dynamic_width(monkeypatch):
    """Verify that progress functions call the width helper."""
    m = reload_main_with_env(monkeypatch, no_color=None, isatty=True)
    mock_stderr = MagicMock()
    monkeypatch.setattr(sys, "stderr", mock_stderr)

    # Mock terminal size to verify it's being used
    monkeypatch.setattr("shutil.get_terminal_size", lambda fallback: (120, 24))

    # Test render_progress_bar uses dynamic width
    m.render_progress_bar(5, 10, "Test")
    width_120 = m._get_progress_bar_width()  # Should be 48 (120 * 0.4)
    assert width_120 == 48

    # Check that the progress bar output reflects the dynamic width
    writes = [args[0] for args, _ in mock_stderr.write.call_args_list]
    combined = "".join(writes)
    # With width 48, at 50% progress we should have 24 filled chars
    assert "█" * 24 in combined or len([c for c in combined if c == "█"]) == 24


# Case 18: check_env_permissions uses secure file operations
def test_check_env_permissions_secure(monkeypatch):
    m = reload_main_with_env(monkeypatch)

    # Mock os.path.exists and os.path.islink
    monkeypatch.setattr("os.path.exists", lambda x: True)
    monkeypatch.setattr("os.path.islink", lambda x: False)
    monkeypatch.setattr("os.name", "posix")

    # Mock low-level file operations
    mock_open = MagicMock(return_value=123)
    mock_close = MagicMock()
    mock_fstat = MagicMock()
    mock_fchmod = MagicMock()

    monkeypatch.setattr("os.open", mock_open)
    monkeypatch.setattr("os.close", mock_close)
    monkeypatch.setattr("os.fstat", mock_fstat)
    monkeypatch.setattr("os.fchmod", mock_fchmod)

    # Mock stat result: world readable (needs fix)
    # 0o666 = rw-rw-rw-
    mock_stat_result = MagicMock()
    mock_stat_result.st_mode = 0o100666 # Regular file, rw-rw-rw-
    mock_fstat.return_value = mock_stat_result

    # Capture stderr
    mock_stderr = MagicMock()
    monkeypatch.setattr(sys, "stderr", mock_stderr)

    # Run
    m.check_env_permissions(".env")

    # Verify os.open called with O_NOFOLLOW
    assert mock_open.called
    args, _ = mock_open.call_args
    # Check flags
    expected_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    assert args[1] == expected_flags

    # Verify fchmod called
    mock_fchmod.assert_called_with(123, 0o600)

    # Verify close called
    mock_close.assert_called_with(123)

    # Verify success message
    writes = [args[0] for args, _ in mock_stderr.write.call_args_list]
    combined = "".join(writes)
    assert "Fixed .env permissions" in combined

    # Test case where permissions are already fine
    mock_open.reset_mock()
    mock_fchmod.reset_mock()
    mock_stat_result.st_mode = 0o100600 # rw-------

    m.check_env_permissions(".env")

    assert mock_open.called
    assert not mock_fchmod.called
