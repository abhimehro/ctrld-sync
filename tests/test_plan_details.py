"""Tests for the print_plan_details dry-run output function."""

import importlib
import os
import sys
from unittest.mock import patch


# NOTE: Avoid importing `main` at module import time.
# Some tests delete `sys.modules["main"]` to force a clean import under different env/TTY
# settings; holding a stale module reference can cause patches to target the wrong module.

def test_print_plan_details_no_colors(capsys):
    """Test print_plan_details output when colors are disabled."""
    import main as m

    with patch.object(m, "USE_COLORS", False):
        plan_entry = {
            "profile": "test_profile",
            "folders": [
                {"name": "Folder B", "rules": 5},
                {"name": "Folder A", "rules": 10},
            ],
        }
        m.print_plan_details(plan_entry)

    captured = capsys.readouterr()
    output = captured.out

    assert "Plan Details for test_profile:" in output
    # Match exact output including alignment spaces
    assert "  - Folder A : 10 rules" in output
    assert "  - Folder B :  5 rules" in output
    # Verify alphabetical ordering (A before B)
    assert output.index("Folder A") < output.index("Folder B")


def test_print_plan_details_empty_folders(capsys):
    """Test print_plan_details with no folders."""
    import main as m

    with patch.object(m, "USE_COLORS", False):
        plan_entry = {"profile": "test_profile", "folders": []}
        m.print_plan_details(plan_entry)

    captured = capsys.readouterr()
    output = captured.out

    assert "Plan Details for test_profile:" in output
    assert "No folders to sync." in output


def test_print_plan_details_with_colors(capsys):
    """Test print_plan_details output when colors are enabled."""
    # Force USE_COLORS=True for this test, and reload `main` so the `Colors` class is
    # created with non-empty ANSI codes.

    with patch.dict(os.environ, {"NO_COLOR": ""}, clear=False):
        with patch("sys.stderr.isatty", return_value=True), patch(
            "sys.stdout.isatty", return_value=True
        ):
            import main as m

            m = importlib.reload(m)

            plan_entry = {
                "profile": "test_profile",
                "folders": [{"name": "Folder A", "rules": 10}],
            }
            m.print_plan_details(plan_entry)

            captured = capsys.readouterr()
            output = captured.out

            assert "📝 Plan Details for test_profile:" in output
            assert "Folder A" in output
            assert "10 rules" in output
