"""Dry-run plan details rendering."""

from __future__ import annotations

from models import PlanEntry, PlanFolderEntry
from validation import sanitize_for_log

from .colors import USE_COLORS, Colors
from .text import _display_len, _pad_string, pluralize


def _resolve_folder_action(folder: PlanFolderEntry) -> tuple[str, str, str]:
    """Return (label, icon, color_attr_name) for a folder.

    Does not evaluate ``USE_COLORS`` or touch ``Colors`` values; the color
    attribute name is resolved at presentation time so tests that patch
    ``Colors`` after import continue to work.
    """
    actions = {rg.get("action") for rg in folder.get("rule_groups") or []}
    if len(actions) > 1:
        # "⚠️ " intentionally ends with a space; the caller format adds one
        # more, producing the two spaces before "Mixed" asserted in tests.
        return "Mixed", "⚠️ ", "WARNING"

    action_val = next(iter(actions)) if actions else folder.get("action")
    if action_val not in (0, 1):
        action_val = folder.get("action")

    if action_val == 0:
        return "Block", "⛔", "FAIL"
    if action_val == 1:
        return "Allow", "✅", "GREEN"
    return "Block (Default)", "⛔", "FAIL"


def _get_action_text(folder: PlanFolderEntry) -> str:
    """Determine the rendered action label (Block/Allow/Mixed) for a folder."""
    label, icon, color_attr = _resolve_folder_action(folder)
    if USE_COLORS:
        return f"({getattr(Colors, color_attr)}{icon} {label}{Colors.ENDC})"
    return f"({icon} {label})"


def _format_plan_header(profile: str) -> str:
    """Return the header line for a plan details block."""
    if USE_COLORS:
        return f"\n{Colors.HEADER}📝 Plan Details for {profile}:{Colors.ENDC}"
    return f"\n📝 Plan Details for {profile}:"


def _format_empty_warning() -> str:
    """Return the warning shown when a plan has no folders."""
    if USE_COLORS:
        return f"  {Colors.WARNING}⚠️  No folders to sync.{Colors.ENDC}"
    return "  ⚠️  No folders to sync."


def _format_dimmed_hint(hint: str) -> str:
    """Return a hint string, dimmed when colors are enabled."""
    if USE_COLORS:
        return f"{Colors.DIM}{hint}{Colors.ENDC}"
    return hint


def _format_folder_line(
    folder: PlanFolderEntry, max_name_len: int, max_rules_len: int
) -> str:
    """Return a single formatted folder line for the plan details table."""
    name = sanitize_for_log(folder.get("name", "Unknown"))
    rules_count = folder.get("rules", 0)
    formatted_rules = f"{rules_count:,}"
    padded_name = _pad_string(name, max_name_len, "<")
    action_text = _get_action_text(folder)

    if USE_COLORS:
        return (
            f"  • {Colors.BOLD}{padded_name}{Colors.ENDC} : "
            f"{formatted_rules:>{max_rules_len}} {pluralize(rules_count, 'rule'):<5} {action_text}"
        )
    return (
        f"  - {padded_name} : "
        f"{formatted_rules:>{max_rules_len}} {pluralize(rules_count, 'rule'):<5} {action_text}"
    )


def print_plan_details(plan_entry: PlanEntry) -> None:
    """Pretty-print the folder-level breakdown during a dry-run."""
    profile = sanitize_for_log(plan_entry.get("profile", "unknown"))
    if profile == "dry-run-placeholder":
        profile = "(Unspecified)"
    folders = plan_entry.get("folders", [])

    print(_format_plan_header(profile))

    if not folders:
        print(_format_empty_warning())
        print(
            _format_dimmed_hint(
                "  💡 Hint: Add folder URLs using --folder-url or in your config.yaml"
            )
        )
        return

    # Calculate max width for alignment
    max_name_len = max(
        # Use the same default ("Unknown") as when printing, so alignment is accurate
        (_display_len(sanitize_for_log(f.get("name", "Unknown"))) for f in folders),
        default=0,
    )
    max_rules_len = max((len(f"{f.get('rules', 0):,}") for f in folders), default=0)

    for folder in sorted(folders, key=lambda f: f.get("name", "Unknown")):
        print(_format_folder_line(folder, max_name_len, max_rules_len))

    print("")


__all__ = [
    "print_plan_details",
    "_resolve_folder_action",
    "_get_action_text",
    "_format_plan_header",
    "_format_empty_warning",
    "_format_dimmed_hint",
    "_format_folder_line",
]
