"""Tests for the print_plan_details dry-run output function."""

from unittest.mock import patch


def test_print_plan_details_no_colors(capsys):
    """Test print_plan_details output when colors are disabled."""
    import main
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
    import main
    with patch("main.USE_COLORS", False):
        plan_entry = {"profile": "test_profile", "folders": []}
        main.print_plan_details(plan_entry)

    captured = capsys.readouterr()
    output = captured.out

    assert "Plan Details for test_profile:" in output
    assert "No folders to sync." in output


def test_print_plan_details_with_colors(capsys):
    """Test print_plan_details output when colors are enabled."""
    import main
    with patch("main.USE_COLORS", True):
        plan_entry = {
            "profile": "test_profile",
            "folders": [{"name": "Folder A", "rules": 10}],
        }
        main.print_plan_details(plan_entry)

    captured = capsys.readouterr()
    output = captured.out

    assert "📝 Plan Details for test_profile:" in output
    assert "Folder A" in output
    assert "10 rules" in output
