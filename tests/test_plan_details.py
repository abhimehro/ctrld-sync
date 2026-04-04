"""Tests for the print_plan_details dry-run output function."""

import importlib
import os
from unittest.mock import patch

# NOTE: Avoid importing `main` at module import time.
# Some tests delete `sys.modules["main"]` to force a clean import under different env/TTY
# settings; holding a stale module reference can cause patches to target the wrong module.


def test_print_plan_details_no_colors(capsys):
    """Test print_plan_details output when colors are disabled."""
    import main as m

    with patch.object(m, "USE_COLORS", False):
        plan_entry: m.PlanEntry = {
            "profile": "test_profile",
            "folders": [
                {"name": "Folder B", "rules": 5, "action": 0},
                {"name": "Folder A", "rules": 10, "action": 1},
                {
                    "name": "Folder C",
                    "rules": 3,
                    "rule_groups": [
                        {"action": 0, "rules": 1, "status": 1},
                        {"action": 1, "rules": 2, "status": 1},
                    ],
                },
            ],
        }
        m.print_plan_details(plan_entry)

    captured = capsys.readouterr()
    output = captured.out

    assert "Plan Details for test_profile:" in output
    # Match exact output including alignment spaces
    assert "  - Folder A : 10 rules [Allow]" in output
    assert "  - Folder B :  5 rules [Block]" in output
    assert "  - Folder C :  3 rules [Mixed]" in output
    # Verify alphabetical ordering (A before B before C)
    assert output.index("Folder A") < output.index("Folder B")
    assert output.index("Folder B") < output.index("Folder C")


def test_print_plan_details_empty_folders(capsys):
    """Test print_plan_details with no folders."""
    import main as m

    with patch.object(m, "USE_COLORS", False):
        plan_entry: m.PlanEntry = {"profile": "test_profile", "folders": []}
        m.print_plan_details(plan_entry)

    captured = capsys.readouterr()
    output = captured.out

    assert "Plan Details for test_profile:" in output
    assert "No folders to sync." in output
    assert "Hint: Add folder URLs using --folder-url or in your config.yaml" in output


def test_print_plan_details_with_colors(capsys):
    """Test print_plan_details output when colors are enabled."""
    # Force USE_COLORS=True for this test, and reload `main` so the `Colors` class is
    # created with non-empty ANSI codes.

    with patch.dict(os.environ, {"NO_COLOR": ""}, clear=False):
        with (
            patch("sys.stderr.isatty", return_value=True),
            patch("sys.stdout.isatty", return_value=True),
        ):
            import main as m

            m = importlib.reload(m)

            plan_entry: m.PlanEntry = {
                "profile": "test_profile",
                "folders": [{"name": "Folder A", "rules": 10, "action": 1}],
            }
            m.print_plan_details(plan_entry)

            captured = capsys.readouterr()
            output = captured.out

            assert "📝 Plan Details for test_profile:" in output
            assert "Folder A" in output
            assert "10 rules" in output
            assert "✅ Allow" in output
