"""Tests for the print_plan_details dry-run output function."""

import importlib
import os
import sys
from unittest.mock import patch

import main


def test_print_plan_details_no_colors(capsys):
    """Test print_plan_details output when colors are disabled."""
    with patch("main.USE_COLORS", False):
        plan_entry = {
            "profile": "test_profile",
            "folders": [
                {"name": "Folder B", "rules": 5},
                {"name": "Folder A", "rules": 10},
            ],
        }
        main.print_plan_details(plan_entry)

    captured = capsys.readouterr()
    output = captured.out

    assert "Plan Details for test_profile:" in output
    assert "  - Folder A: 10 rules" in output
    assert "  - Folder B: 5 rules" in output
    # Verify alphabetical ordering (A before B)
    assert output.index("Folder A") < output.index("Folder B")


def test_print_plan_details_empty_folders(capsys):
    """Test print_plan_details with no folders."""
    with patch("main.USE_COLORS", False):
        plan_entry = {"profile": "test_profile", "folders": []}
        main.print_plan_details(plan_entry)

    captured = capsys.readouterr()
    output = captured.out

    assert "Plan Details for test_profile:" in output
    assert "No folders to sync." in output


def test_print_plan_details_with_colors(capsys):
    """Test print_plan_details output when colors are enabled."""
    # Force USE_COLORS=True for this test, but also ensure Colors class is populated
    # The Colors class is defined at import time based on USE_COLORS.
    # If main was imported previously with USE_COLORS=False, Colors attributes are empty strings.
    # We must reload main with an environment that forces USE_COLORS=True, or mock Colors.

    with patch.dict(os.environ, {"NO_COLOR": ""}):
        with patch("sys.stderr.isatty", return_value=True), patch("sys.stdout.isatty", return_value=True):
            # Robust reload: handle case where main module reference is stale
            if "main" in sys.modules:
                importlib.reload(sys.modules["main"])
            else:
                import main
                importlib.reload(main)

            # Now verify output with colors
            plan_entry = {
                "profile": "test_profile",
                "folders": [{"name": "Folder A", "rules": 10}],
            }
            # Use the module from sys.modules to ensure we use the reloaded one
            sys.modules["main"].print_plan_details(plan_entry)

            captured = capsys.readouterr()
            output = captured.out

            assert "📝 Plan Details for test_profile:" in output
            assert "Folder A" in output
            assert "10 rules" in output
