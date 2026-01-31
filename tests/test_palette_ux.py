import sys
from unittest.mock import MagicMock
import main

def test_print_dry_run_plan_with_colors(monkeypatch):
    """Verify print_dry_run_plan output with colors enabled."""
    # Force colors on
    monkeypatch.setattr(main, "USE_COLORS", True)

    # Since Colors class is evaluated at import time, we need to manually set color codes
    # if the module was imported in a non-TTY environment
    for attr, code in {
        "HEADER": "\033[95m",
        "BLUE": "\033[94m",
        "CYAN": "\033[96m",
        "GREEN": "\033[92m",
        "WARNING": "\033[93m",
        "FAIL": "\033[91m",
        "ENDC": "\033[0m",
        "BOLD": "\033[1m",
        "UNDERLINE": "\033[4m",
    }.items():
        monkeypatch.setattr(main.Colors, attr, code)

    # Mock stdout to capture print output
    mock_stdout = MagicMock()
    monkeypatch.setattr(sys, "stdout", mock_stdout)

    plan = {
        "profile": "test_profile",
        "folders": [
            {"name": "Test Folder 1", "rules": 10},
            {"name": "Test Folder 2", "rules": 20},
        ]
    }

    main.print_dry_run_plan(plan)

    # Aggregate all writes
    # print() typically calls write(string) and write('\n')
    combined_output = "".join([str(args[0]) for args, _ in mock_stdout.write.call_args_list])

    assert "📝 Dry Run Plan for Profile:" in combined_output
    assert "test_profile" in combined_output
    assert "Test Folder 1" in combined_output
    assert "10 rules" in combined_output
    # ANSI codes should be present (main.Colors.HEADER starts with \033[95m)
    assert "\033[" in combined_output

def test_print_dry_run_plan_no_colors(monkeypatch):
    """Verify print_dry_run_plan output without colors."""
    monkeypatch.setattr(main, "USE_COLORS", False)

    mock_stdout = MagicMock()
    monkeypatch.setattr(sys, "stdout", mock_stdout)

    plan = {
        "profile": "test_profile",
        "folders": [
            {"name": "Test Folder 1", "rules": 10},
        ]
    }

    main.print_dry_run_plan(plan)

    combined_output = "".join([str(args[0]) for args, _ in mock_stdout.write.call_args_list])

    assert "📝 Dry Run Plan for Profile:" in combined_output
    assert "test_profile" in combined_output
    assert "Test Folder 1" in combined_output
    assert "10 rules" in combined_output
    # No ANSI codes
    assert "\033[" not in combined_output

def test_print_dry_run_plan_empty_folders(monkeypatch):
    """Verify output when no folders are present."""
    monkeypatch.setattr(main, "USE_COLORS", False)
    mock_stdout = MagicMock()
    monkeypatch.setattr(sys, "stdout", mock_stdout)

    plan = {
        "profile": "test_profile",
        "folders": []
    }

    main.print_dry_run_plan(plan)

    combined_output = "".join([str(args[0]) for args, _ in mock_stdout.write.call_args_list])
    assert "(No folders found to sync)" in combined_output
