import sys
from unittest.mock import MagicMock, patch
import pytest
import main

def test_print_plan_details_no_colors(capsys):
    """Test print_plan_details when USE_COLORS is False."""
    with patch("main.USE_COLORS", False):
        plan_entry = {
            "profile": "test_profile",
            "folders": [
                {"name": "Folder A", "rules": 10},
                {"name": "Folder B", "rules": 5},
            ]
        }
        main.print_plan_details(plan_entry)

        captured = capsys.readouterr()
        output = captured.out

        assert "Plan Details for test_profile:" in output
        assert "  - Folder A: 10 rules" in output
        assert "  - Folder B: 5 rules" in output
        assert "\033[" not in output  # No escape codes

def test_print_plan_details_with_colors(capsys):
    """Test print_plan_details when USE_COLORS is True."""
    # We need to ensure Colors has values. Since main.Colors is initialized based on environment,
    # we might need to patch it or reload main with mocked environment.
    # However, main.Colors values are constant strings if USE_COLORS was true during import,
    # or empty strings if false.

    # Let's mock Colors class to ensure it has color codes for this test
    class MockColors:
        HEADER = "<HEADER>"
        BOLD = "<BOLD>"
        WARNING = "<WARNING>"
        ENDC = "<ENDC>"

    with patch("main.USE_COLORS", True), patch("main.Colors", MockColors):
        plan_entry = {
            "profile": "test_profile",
            "folders": [
                {"name": "Folder A", "rules": 10},
            ]
        }
        main.print_plan_details(plan_entry)

        captured = capsys.readouterr()
        output = captured.out

        assert "<HEADER>📝 Plan Details for test_profile:<ENDC>" in output
        assert "  • <BOLD>Folder A<ENDC>: 10 rules" in output

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
