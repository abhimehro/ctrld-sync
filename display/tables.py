"""Summary and success message table rendering."""

from __future__ import annotations

import secrets
from dataclasses import dataclass

from models import SyncResult

from .colors import USE_COLORS, Box, Colors
from .output import _print_hint
from .text import _display_len, _pad_string, pluralize


@dataclass
class _SummaryStats:
    t_f: int
    t_r: int
    t_d: float
    t_status: str
    t_col: str


def _get_display_profile(profile: str) -> str:
    return "(Unspecified)" if profile == "dry-run-placeholder" else profile


def _print_hint_if_no_folders(t_f: int) -> None:
    if t_f == 0:
        _print_hint(
            "  💡 Hint: Add folder URLs using --folder-url or in your config.yaml"
        )


def print_line(left_char: str, mid_char: str, right_char: str, w: list[int]) -> str:
    """Format a horizontal table separator line."""
    return f"{Colors.BOLD}{make_col_separator(left_char, mid_char, right_char, Box.H, w)}{Colors.ENDC}"


def print_row(cols: list[str], w: list[int]) -> str:
    """Format a row of table data."""
    col0 = _pad_string(cols[0], w[0], "<")
    col1 = _pad_string(cols[1], w[1], ">")
    col2 = _pad_string(cols[2], w[2], ">")
    col3 = _pad_string(cols[3], w[3], ">")
    col4 = _pad_string(cols[4], w[4], "<")
    return f"{Colors.BOLD}│{Colors.ENDC} {col0} {Colors.BOLD}│{Colors.ENDC} {col1} {Colors.BOLD}│{Colors.ENDC} {col2} {Colors.BOLD}│{Colors.ENDC} {col3} {Colors.BOLD}│{Colors.ENDC} {col4} {Colors.BOLD}│{Colors.ENDC}"


def _render_ascii_table(
    sync_results: list[SyncResult], w: list[int], stats: _SummaryStats, dry_run: bool
) -> None:
    header = f"{'Profile ID':<{w[0]}} | {'Folders':>{w[1]}} | {'Rules':>{w[2]}} | {'Duration':>{w[3]}} | {'Status':<{w[4]}}"
    sep = "-" * len(header)
    title = f"📋 {'DRY RUN' if dry_run else 'SYNC'} SUMMARY"
    padded_title = _pad_string(title, len(header), align="^")
    print(f"\n{padded_title}\n{sep}\n{header}\n{sep}")
    for r in sync_results:
        display_profile = _get_display_profile(r["profile"])
        print(
            f"{display_profile:<{w[0]}} | {r['folders']:>{w[1]}} | {r['rules']:>{w[2]},} | {r['duration']:>{w[3] - 1}.1f}s | {_pad_string(r['status_label'], w[4], align='<')}"
        )
    print(
        f"{sep}\n{'TOTAL':<{w[0]}} | {stats.t_f:>{w[1]}} | {stats.t_r:>{w[2]},} | {stats.t_d:>{w[3] - 1}.1f}s | {_pad_string(stats.t_status, w[4], align='<')}\n{sep}\n"
    )
    print()


def _render_unicode_table(
    sync_results: list[SyncResult], w: list[int], stats: _SummaryStats, dry_run: bool
) -> None:
    print(f"\n{print_line('┌', '─', '┐', w)}")
    title = f"📋 {'DRY RUN' if dry_run else 'SYNC'} SUMMARY"
    padded_title = _pad_string(title, sum(w) + 14, align="^")
    print(
        f"{Colors.BOLD}│{Colors.CYAN if dry_run else Colors.HEADER}{padded_title}{Colors.ENDC}{Colors.BOLD}│{Colors.ENDC}"
    )
    print(
        f"{print_line('├', '┬', '┤', w)}\n{print_row([f'{Colors.HEADER}Profile ID{Colors.ENDC}', f'{Colors.HEADER}Folders{Colors.ENDC}', f'{Colors.HEADER}Rules{Colors.ENDC}', f'{Colors.HEADER}Duration{Colors.ENDC}', f'{Colors.HEADER}Status{Colors.ENDC}'], w)}"
    )
    print(print_line("├", "┼", "┤", w))

    for r in sync_results:
        sc = Colors.GREEN if r["success"] else Colors.FAIL
        display_profile = _get_display_profile(r["profile"])
        print(
            print_row(
                [
                    display_profile,
                    str(r["folders"]),
                    f"{r['rules']:,}",
                    f"{r['duration']:.1f}s",
                    f"{sc}{r['status_label']}{Colors.ENDC}",
                ],
                w,
            )
        )

    print(
        f"{print_line('├', '┼', '┤', w)}\n{print_row(['TOTAL', str(stats.t_f), f'{stats.t_r:,}', f'{stats.t_d:.1f}s', f'{stats.t_col}{stats.t_status}{Colors.ENDC}'], w)}"
    )
    print(f"{print_line('└', '┴', '┘', w)}\n")


def print_summary_table(
    sync_results: list[SyncResult], success_count: int, total: int, dry_run: bool
) -> None:
    max_p = max((_display_len(r["profile"]) for r in sync_results), default=25)
    w = [max(25, max_p), 10, 12, 10, 15]

    t_f, t_r, t_d = (
        sum(r["folders"] for r in sync_results),
        sum(r["rules"] for r in sync_results),
        sum(r["duration"] for r in sync_results),
    )
    all_ok = success_count == total
    if all_ok:
        t_status = "✅ Ready" if dry_run else "✅ All Good"
        t_col = Colors.GREEN
    elif success_count > 0:
        t_status = "⚠️ Partial"
        t_col = Colors.WARNING
    else:
        t_status = "❌ Errors"
        t_col = Colors.FAIL
    stats = _SummaryStats(t_f, t_r, t_d, t_status, t_col)

    if not USE_COLORS:
        _render_ascii_table(sync_results, w, stats, dry_run)
        _print_hint_if_no_folders(t_f)
        return

    _render_unicode_table(sync_results, w, stats, dry_run)
    _print_hint_if_no_folders(t_f)


def _print_success_text(all_success: bool, success_count: int, total: int) -> None:
    """Helper to print the success or partial success message."""
    if all_success:
        success_msgs = [
            "✨ All synced!",
            "🚀 Ready for liftoff!",
            "🎨 Beautifully done!",
            "💎 Smooth operation!",
            "🌈 Perfect harmony!",
        ]
        chosen_msg = secrets.choice(success_msgs)
    else:
        profile_word = pluralize(total, "profile")
        chosen_msg = f"⚠️  Synced {success_count} out of {total} {profile_word}. Check errors above."

    if USE_COLORS:
        color = Colors.GREEN if all_success else Colors.WARNING
        print(f"\n{color}{chosen_msg}{Colors.ENDC}")
    else:
        print(f"\n{chosen_msg}")


def _print_dashboard_url(profile_ids: list[str]) -> None:
    """Helper to print the dashboard URL."""
    is_single_profile = (
        profile_ids
        and len(profile_ids) == 1
        and profile_ids[0] != "dry-run-placeholder"
    )
    is_multi_profile = len(profile_ids) > 1

    if not is_single_profile and not is_multi_profile:
        return

    dashboard_url = (
        f"https://controld.com/dashboard/profiles/{profile_ids[0]}/filters"
        if is_single_profile
        else "https://controld.com/dashboard/profiles"
    )

    if USE_COLORS:
        print(
            f"{Colors.CYAN}👀 View your changes: {Colors.UNDERLINE}{dashboard_url}{Colors.ENDC}"
        )
    else:
        print(f"👀 View your changes: {dashboard_url}")


def print_success_message(
    profile_ids: list[str], success_count: int, total: int
) -> None:
    """Prints a random success message and a link to the Control D dashboard."""
    all_success = success_count == total
    _print_success_text(all_success, success_count, total)
    _print_dashboard_url(profile_ids)


def make_col_separator(
    left: str, mid: str, right: str, horiz: str, col_widths: list[int]
) -> str:
    """Generates a table row separator with given box drawing characters and column widths."""
    parts = [horiz * (w + 2) for w in col_widths]
    return left + mid.join(parts) + right


__all__ = [
    "print_summary_table",
    "print_success_message",
    "print_line",
    "print_row",
    "make_col_separator",
    "_SummaryStats",
    "_get_display_profile",
    "_print_hint_if_no_folders",
    "_render_ascii_table",
    "_render_unicode_table",
    "_print_success_text",
    "_print_dashboard_url",
]
