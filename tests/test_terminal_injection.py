
import importlib
import sys
from unittest.mock import MagicMock, patch
import pytest
import main

# Helper to reload main with specific env/tty settings (copied from test_main.py)
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

def test_terminal_injection_in_summary_table(monkeypatch, capsys, caplog):
    """
    Test that malicious ANSI codes in profile IDs are sanitized in the summary table.
    """
    # Ensure INFO logs are captured
    import logging
    caplog.set_level(logging.INFO)

    # 1. Setup environment
    monkeypatch.setenv("TOKEN", "valid_token")
    monkeypatch.setenv("PROFILE", "valid_profile")

    # Reload main to pick up env
    m = reload_main_with_env(monkeypatch)

    # 2. Mock external dependencies
    monkeypatch.setattr(m, "warm_up_cache", MagicMock())
    monkeypatch.setattr(m, "sync_profile", MagicMock(return_value=False)) # Fail sync

    # 3. Patch validate_profile_id to allow our "malicious" ID to pass through the initial validation check?
    # Actually, main.py checks: if not validate_profile_id(pid): sync_results.append(...)
    # So if we want it to end up in the table, we can just let it fail validation.
    # The vulnerability is that INVALID profiles are printed RAW.

    malicious_id = "test\033[31mINJECTION"

    # Mock parse_args
    mock_args = MagicMock()
    mock_args.profiles = malicious_id
    mock_args.folder_url = None
    mock_args.dry_run = True
    mock_args.no_delete = False
    mock_args.plan_json = None
    monkeypatch.setattr(m, "parse_args", lambda: mock_args)

    # 4. Run main
    # We need to catch SystemExit
    with pytest.raises(SystemExit):
        m.main()

    # 5. Check output
    captured = capsys.readouterr()
    # Check caplog for logs (since we use log.info)
    log_text = caplog.text
    all_output = captured.out + captured.err + log_text

    # If vulnerable, output contains the raw ANSI code \033
    # We assert that the raw ESC character is NOT present
    assert "\033[31m" not in all_output, "Terminal injection detected: ANSI codes printed raw!"

    # We assert that the output is masked because it is long/sensitive
    # The new masking logic replaces the entire ID with "********" for Profile IDs from env var.
    # We look for this string in the logs.
    assert "********" in log_text, "Redacted output not found in logs!"
