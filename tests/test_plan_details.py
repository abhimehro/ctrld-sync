"""Tests for the print_plan_details dry-run output function."""

import importlib
import os
from unittest.mock import patch

import pytest

# NOTE: Avoid importing `main` at module import time.
# Some tests delete `sys.modules["main"]` to force a clean import under different env/TTY
# settings; holding a stale module reference can cause patches to target the wrong module.


def _mark_color(monkeypatch, main_module):
    """Patch display globals to deterministic markers for color output tests."""
    monkeypatch.setattr(main_module.display, "USE_COLORS", True)
    for attr, value in {
        "HEADER": "<H>",
        "BOLD": "<B>",
        "FAIL": "<F>",
        "GREEN": "<G>",
        "WARNING": "<W>",
        "ENDC": "<E>",
        "DIM": "<D>",
    }.items():
        monkeypatch.setattr(main_module.display.Colors, attr, value)


def _mark_no_color(monkeypatch, main_module):
    """Patch display globals to empty values for no-color output tests."""
    monkeypatch.setattr(main_module.display, "USE_COLORS", False)
    for attr in ("HEADER", "BOLD", "FAIL", "GREEN", "WARNING", "ENDC", "DIM"):
        monkeypatch.setattr(main_module.display.Colors, attr, "")


def test_print_plan_details_no_colors(capsys):
    """Test print_plan_details output when colors are disabled."""
    import main as m

    with patch.object(m, "USE_COLORS", False):
        plan_entry = m.PlanEntry(
            profile="test_profile",
            folders=[
                m.PlanFolderEntry(name="Folder B", rules=5, action=0),
                m.PlanFolderEntry(name="Folder A", rules=10, action=1),
                m.PlanFolderEntry(
                    name="Folder C",
                    rules=3,
                    rule_groups=[
                        {"action": 0, "rules": 0, "status": 0},
                        {"action": 1, "rules": 0, "status": 1},
                    ],
                ),
            ],
        )
        m.print_plan_details(plan_entry)

    captured = capsys.readouterr()
    output = captured.out

    assert "📝 Plan Details for test_profile:" in output
    # Match exact output including alignment spaces
    assert "  - Folder A : 10 rules (✅ Allow)" in output
    assert "  - Folder B :  5 rules (⛔ Block)" in output
    assert "  - Folder C :  3 rules (⚠️  Mixed)" in output
    # Verify alphabetical ordering (A before B before C)
    assert output.index("Folder A") < output.index("Folder B")
    assert output.index("Folder B") < output.index("Folder C")


def test_print_plan_details_empty_folders(capsys):
    """Test print_plan_details with no folders."""
    import main as m

    with patch.object(m, "USE_COLORS", False):
        plan_entry = m.PlanEntry(profile="test_profile", folders=[])
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

            plan_entry = m.PlanEntry(
                profile="test_profile",
                folders=[m.PlanFolderEntry(name="Folder A", rules=10, action=1)],
            )
            m.print_plan_details(plan_entry)

            captured = capsys.readouterr()
            output = captured.out

            assert "📝 Plan Details for test_profile:" in output
            assert "Folder A" in output
            assert "10 rules" in output
            assert "✅ Allow" in output


@pytest.mark.parametrize(
    "case",
    [
        # No action / rule_groups -> "Block (Default)"
        (
            False,
            {"profile": "p", "folders": [{"name": "Default", "rules": 7}]},
            "\n📝 Plan Details for p:\n  - Default : 7 rules (⛔ Block (Default))\n\n",
        ),
        (
            True,
            {"profile": "p", "folders": [{"name": "Default", "rules": 7}]},
            "\n<H>📝 Plan Details for p:<E>\n  • <B>Default<E> : 7 rules (<F>⛔ Block (Default)<E>)\n\n",
        ),
        # Single rule_groups with unrecognized action -> double fallback to default
        (
            False,
            {
                "profile": "p",
                "folders": [
                    {
                        "name": "Bad",
                        "rules": 2,
                        "rule_groups": [{"rules": 2, "action": 5, "status": 1}],
                    }
                ],
            },
            "\n📝 Plan Details for p:\n  - Bad : 2 rules (⛔ Block (Default))\n\n",
        ),
        (
            True,
            {
                "profile": "p",
                "folders": [
                    {
                        "name": "Bad",
                        "rules": 2,
                        "rule_groups": [{"rules": 2, "action": 5, "status": 1}],
                    }
                ],
            },
            "\n<H>📝 Plan Details for p:<E>\n  • <B>Bad<E> : 2 rules (<F>⛔ Block (Default)<E>)\n\n",
        ),
        # Single rule_groups with action: None -> double fallback to default
        (
            False,
            {
                "profile": "p",
                "folders": [
                    {
                        "name": "None",
                        "rules": 2,
                        "rule_groups": [{"rules": 2, "action": None, "status": 1}],
                    }
                ],
            },
            "\n📝 Plan Details for p:\n  - None : 2 rules (⛔ Block (Default))\n\n",
        ),
        (
            True,
            {
                "profile": "p",
                "folders": [
                    {
                        "name": "None",
                        "rules": 2,
                        "rule_groups": [{"rules": 2, "action": None, "status": 1}],
                    }
                ],
            },
            "\n<H>📝 Plan Details for p:<E>\n  • <B>None<E> : 2 rules (<F>⛔ Block (Default)<E>)\n\n",
        ),
        # {0, None} in rule_groups -> Mixed (icon has a load-bearing trailing space)
        (
            False,
            {
                "profile": "p",
                "folders": [
                    {
                        "name": "Mix",
                        "rules": 2,
                        "rule_groups": [
                            {"rules": 1, "action": 0, "status": 1},
                            {"rules": 1, "action": None, "status": 1},
                        ],
                    }
                ],
            },
            "\n📝 Plan Details for p:\n  - Mix : 2 rules (⚠️  Mixed)\n\n",
        ),
        (
            True,
            {
                "profile": "p",
                "folders": [
                    {
                        "name": "Mix",
                        "rules": 2,
                        "rule_groups": [
                            {"rules": 1, "action": 0, "status": 1},
                            {"rules": 1, "action": None, "status": 1},
                        ],
                    }
                ],
            },
            "\n<H>📝 Plan Details for p:<E>\n  • <B>Mix<E> : 2 rules (<W>⚠️  Mixed<E>)\n\n",
        ),
        # Empty rule_groups with top-level action -> use top-level action
        (
            False,
            {
                "profile": "p",
                "folders": [
                    {"name": "Empty", "rules": 4, "action": 0, "rule_groups": []}
                ],
            },
            "\n📝 Plan Details for p:\n  - Empty : 4 rules (⛔ Block)\n\n",
        ),
        (
            True,
            {
                "profile": "p",
                "folders": [
                    {"name": "Empty", "rules": 4, "action": 0, "rule_groups": []}
                ],
            },
            "\n<H>📝 Plan Details for p:<E>\n  • <B>Empty<E> : 4 rules (<F>⛔ Block<E>)\n\n",
        ),
        # Pluralization and thousands separator alignment
        (
            False,
            {
                "profile": "p",
                "folders": [
                    {"name": "Small", "rules": 1, "action": 0},
                    {"name": "Large", "rules": 1234, "action": 0},
                ],
            },
            "\n📝 Plan Details for p:\n  - Large : 1,234 rules (⛔ Block)\n  - Small :     1 rule  (⛔ Block)\n\n",
        ),
        (
            True,
            {
                "profile": "p",
                "folders": [
                    {"name": "Small", "rules": 1, "action": 0},
                    {"name": "Large", "rules": 1234, "action": 0},
                ],
            },
            "\n<H>📝 Plan Details for p:<E>\n  • <B>Large<E> : 1,234 rules (<F>⛔ Block<E>)\n  • <B>Small<E> :     1 rule  (<F>⛔ Block<E>)\n\n",
        ),
        # Wide/emoji folder names exercise _display_len/_pad_string
        (
            False,
            {
                "profile": "p",
                "folders": [
                    {"name": "テスト", "rules": 3, "action": 0},
                    {"name": "abc", "rules": 3, "action": 0},
                ],
            },
            "\n📝 Plan Details for p:\n  - abc    : 3 rules (⛔ Block)\n  - テスト : 3 rules (⛔ Block)\n\n",
        ),
        (
            True,
            {
                "profile": "p",
                "folders": [
                    {"name": "テスト", "rules": 3, "action": 0},
                    {"name": "abc", "rules": 3, "action": 0},
                ],
            },
            "\n<H>📝 Plan Details for p:<E>\n  • <B>abc   <E> : 3 rules (<F>⛔ Block<E>)\n  • <B>テスト<E> : 3 rules (<F>⛔ Block<E>)\n\n",
        ),
    ],
)
def test_print_plan_details_characterization(monkeypatch, capsys, case):
    """Full-output characterization matrix for edge cases and both color modes."""
    use_colors, plan_entry, expected = case
    import main as m

    if use_colors:
        _mark_color(monkeypatch, m)
    else:
        _mark_no_color(monkeypatch, m)

    m.print_plan_details(plan_entry)
    assert capsys.readouterr().out == expected


def test_resolve_folder_action_fallbacks():
    """Direct unit coverage for the action-resolution lookup and fallbacks."""
    import display

    # No action / no rule_groups -> default
    assert display._resolve_folder_action({"name": "x", "rules": 1}) == (
        "Block (Default)",
        "⛔",
        "FAIL",
    )

    # Single top-level action
    assert display._resolve_folder_action({"name": "x", "rules": 1, "action": 0}) == (
        "Block",
        "⛔",
        "FAIL",
    )
    assert display._resolve_folder_action({"name": "x", "rules": 1, "action": 1}) == (
        "Allow",
        "✅",
        "GREEN",
    )

    # Single rule_groups action
    rg = {"rules": 1, "action": 0, "status": 1}
    assert display._resolve_folder_action(
        {"name": "x", "rules": 1, "rule_groups": [rg]}
    ) == (
        "Block",
        "⛔",
        "FAIL",
    )

    # Mixed rule_groups actions
    assert display._resolve_folder_action(
        {
            "name": "x",
            "rules": 2,
            "rule_groups": [
                {"rules": 1, "action": 0, "status": 1},
                {"rules": 1, "action": 1, "status": 1},
            ],
        }
    ) == ("Mixed", "⚠️ ", "WARNING")

    # Unrecognized single rule_groups action falls back to top-level action
    assert display._resolve_folder_action(
        {
            "name": "x",
            "rules": 2,
            "action": 0,
            "rule_groups": [{"rules": 2, "action": 5, "status": 1}],
        }
    ) == ("Block", "⛔", "FAIL")

    # Unrecognized single rule_groups action with no top-level action -> default
    assert display._resolve_folder_action(
        {
            "name": "x",
            "rules": 2,
            "rule_groups": [{"rules": 2, "action": 5, "status": 1}],
        }
    ) == ("Block (Default)", "⛔", "FAIL")
