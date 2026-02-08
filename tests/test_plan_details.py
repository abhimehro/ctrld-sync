import sys
import os
from unittest.mock import MagicMock, patch
import pytest
import main

def test_print_plan_details_no_colors():
    """Test print_plan_details when USE_COLORS is False."""
    # We need to mock os.write because main.py uses it to bypass CodeQL
    mock_os_write = MagicMock()

    with patch("main.USE_COLORS", False), \
         patch("os.write", mock_os_write), \
         patch("sys.stdout.fileno", return_value=1):

        plan_entry = {
            "profile": "test_profile",
            "folders": [
                {"label": "Folder A", "rules": 10},
                {"label": "Folder B", "rules": 5},
            ]
        }
        main.print_plan_details(plan_entry)

        # Collect all bytes written via os.write
        written_bytes = b"".join(call.args[1] for call in mock_os_write.call_args_list)
        output = written_bytes.decode("utf-8")

        # Verify the structure
        assert "  - Folder A: 10 rules" in output
        assert "  - Folder B: 5 rules" in output
        assert "\033[" not in output  # No escape codes

def test_print_plan_details_with_colors(capsys):
    """Test print_plan_details when USE_COLORS is True."""
    class MockColors:
        HEADER = "<HEADER>"
        BOLD = "<BOLD>"
        WARNING = "<WARNING>"
        ENDC = "<ENDC>"

    mock_os_write = MagicMock()

    with patch("main.USE_COLORS", True), \
         patch("main.Colors", MockColors), \
         patch("os.write", mock_os_write), \
         patch("sys.stdout.fileno", return_value=1):

        plan_entry = {
            "profile": "test_profile",
            "folders": [
                {"label": "Folder A", "rules": 10},
            ]
        }
        main.print_plan_details(plan_entry)

        # Collect output (header is printed via print(), body via os.write())
        # The print() calls are captured by capsys
        captured = capsys.readouterr()
        stdout_output = captured.out

        # The os.write calls are captured by our mock
        written_bytes = b"".join(call.args[1] for call in mock_os_write.call_args_list)
        os_output = written_bytes.decode("utf-8")

        # Verify header (from print)
        assert "<HEADER>📝 Plan Details for test_profile:<ENDC>" in stdout_output

        # Verify body (from os.write)
        assert "  • <BOLD>Folder A<ENDC>: 10 rules" in os_output

def test_print_plan_details_empty(capsys):
    """Test print_plan_details with no folders."""
    with patch("main.USE_COLORS", False):
        plan_entry = {
            "profile": "test_profile",
            "folders": []
        }
        main.print_plan_details(plan_entry)

        captured = capsys.readouterr()
        output = captured.out

        assert "Plan Details for test_profile:" in output
        assert "  No folders to sync." in output
