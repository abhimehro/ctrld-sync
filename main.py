#!/usr/bin/env python3
"""
Control D Sync
----------------------
A tiny helper that keeps your Control D folders in sync with a set of
remote block-lists.

It does three things:
1. Reads the folder names from the JSON files.
2. Deletes any existing folders with those names (so we start fresh).
3. Re-creates the folders and pushes all rules in batches.

Nothing fancy, just works.
"""

from __future__ import annotations

import argparse
import concurrent.futures  # noqa: F401
import ipaddress  # noqa: F401
import json
import logging
import os
import shutil  # noqa: F401
import socket  # noqa: F401
import stat
import sys
import time
import types
from typing import Any

import httpx

from dotenv import load_dotenv

import api_client
import cache
import config
import display  # noqa: F401
import gh_client  # noqa: F401
import models  # noqa: F401
import sync  # noqa: F401
import validation
from api_client import (  # noqa: F401
    ALLOWED_API_HOSTS,
    MAX_RETRIES,
    MAX_RETRY_DELAY,
    RETRY_DELAY,
    _CONNECT_ERROR_HINT,
    _SERVER_ERROR_HINT,
    _TIMEOUT_HINT,
    _api_delete,
    _api_get,
    _api_post,
    _api_post_form,
    _api_stats,
    _rate_limit_info,
    _rate_limit_lock,
    _retry_request,
    retry_with_jitter,
)
from cache import (  # noqa: F401
    CACHE_TTL_SECONDS,
    _cache_stats,
    _disk_cache,
    get_cache_dir,
    load_disk_cache,
    save_disk_cache,
)
from config import (  # noqa: F401
    API_BASE,
    BATCH_KEYS,
    BATCH_SIZE,
    DEFAULT_FOLDER_URLS,
    DELETE_WORKERS,
    FOLDER_CREATION_DELAY,
    MAX_RESPONSE_SIZE,
    USER_AGENT,
    _DEFAULT_CONFIG_PATHS,
    _STATUS_HINTS,
    _clean_env_kv,
    _resolve_folder_urls,
    _validate_config,
    get_default_config,
    load_config,
)
from display import (  # noqa: F401
    EMPTY_INPUT_HINT,
    INVALID_INPUT_HINT,
    USE_COLORS,
    AlertSystem,
    Box,
    ColoredFormatter,
    Colors,
    JsonFormatter,
    _clear_current_line,
    _display_len,
    _get_progress_bar_width,
    _pad_string,
    _print_bold_header,
    _print_completion,
    _print_hint,
    countdown_timer,
    display_api_statistics,
    display_cache_statistics,
    display_rate_limit_status,
    display_statistics,
    get_password,
    get_validated_input,
    make_col_separator,
    pluralize,
    print_line,
    print_plan_details,
    print_row,
    print_success_message,
    print_summary_table,
    render_progress_bar,
)
from gh_client import (  # noqa: F401
    _cache,
    _cache_lock,
    _gh,
    _gh_get,
    fetch_folder_data,
    warm_up_cache,
)
from models import (  # noqa: F401
    FolderAction,
    FolderData,
    FolderGroup,
    PlanEntry,
    PlanFolderEntry,
    PlanRuleGroup,
    RuleAction,
    RuleEntry,
    RuleGroup,
    SyncContext,
    SyncResult,
)
from sync import (  # noqa: F401
    _process_single_folder,
    check_api_access,
    create_client,
    create_folder,
    delete_folder,
    get_all_existing_rules,
    list_existing_folders,
    push_rules,
    sync_profile,
    verify_access_and_get_folders,
)
from validation import (  # noqa: F401
    DEFAULT_ALLOWED_BLOCKLIST_DOMAINS,
    MAX_FOLDER_ID_LENGTH,
    MAX_FOLDER_NAME_LENGTH,
    MAX_HOSTNAME_LENGTH,
    MAX_PROFILE_ID_LENGTH,
    MAX_RULE_LENGTH,
    MAX_URL_LENGTH,
    _ALLOWED_RULE_CHARS,
    _is_safe_ip,
    extract_profile_id,
    is_valid_folder_name,
    is_valid_profile_id_format,
    is_valid_rule,
    sanitize_for_log,
    set_allowed_blocklist_domains,
    set_token_for_redaction,
    validate_folder_data,
    validate_folder_id,
    validate_folder_url,
    validate_hostname,
    validate_profile_id,
)

# SECURITY: Check .env permissions will be called in main() to avoid side effects at import time


class _MainModule(types.ModuleType):
    """Custom module class so test patches on main.* update canonical module state."""

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "TOKEN":
            # Keep the canonical token redaction state in validation in sync
            # with this module-level variable (used by tests and main()).
            set_token_for_redaction(value or "")
        elif name == "USE_COLORS":
            # main.USE_COLORS is a re-export of display.USE_COLORS; tests patch
            # main.USE_COLORS expecting the display (and sync) colour gate to follow.
            if "display" in sys.modules:
                sys.modules["display"].USE_COLORS = value  # type: ignore[attr-defined]
            if "sync" in sys.modules:
                sys.modules["sync"].USE_COLORS = value  # type: ignore[attr-defined]
        elif name == "log":
            # Many tests patch main.log; helper modules were extracted with per-module
            # loggers, so keep them pointing at the same logger object for compatibility.
            for mod in (
                "api_client",
                "cache",
                "config",
                "display",
                "gh_client",
                "sync",
                "validation",
            ):
                if mod in sys.modules:
                    sys.modules[mod].log = value  # type: ignore[attr-defined]
        super().__setattr__(name, value)

    def __getattr__(self, name: str) -> Any:
        # Mirror the mutable allowlist state from validation so tests that read
        # main._ALLOWED_BLOCKLIST_DOMAINS see updates made via set_allowed_blocklist_domains.
        if name in ("_ALLOWED_BLOCKLIST_DOMAINS", "ALLOWED_BLOCKLIST_DOMAINS"):
            return validation._ALLOWED_BLOCKLIST_DOMAINS
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


sys.modules[__name__].__class__ = _MainModule

# Module logger must be created *after* the custom __setattr__ is installed so
# helper module loggers can be unified at import time.
log = logging.getLogger("control-d-sync")

# Module body assignments do not trigger __setattr__, so unify loggers explicitly.
for _mod in (
    "api_client",
    "cache",
    "config",
    "display",
    "gh_client",
    "sync",
    "validation",
):
    if _mod in sys.modules:
        sys.modules[_mod].log = log  # type: ignore[attr-defined]

# Configure coloured/JSON output and silence noisy library loggers.
display.configure_logging()

TOKEN: str | None = _clean_env_kv(os.getenv("TOKEN"), "TOKEN")

# Keep the canonical token redaction state in validation in sync with this module
# variable (module body assignments do not trigger __setattr__).
set_token_for_redaction(TOKEN or "")

# Inject token-aware sanitizer into helper modules at import time so tests
# and direct imports see the same redaction behaviour.
api_client._sanitize_fn = sanitize_for_log
cache._sanitize_fn = sanitize_for_log


def _api_client() -> httpx.Client:
    """Backwards-compatible test helper: build a Control D client from main.TOKEN."""
    return create_client(TOKEN or "")


def check_env_permissions(env_path: str = ".env") -> None:
    """
    Check .env file permissions and auto-fix if readable by others.

    Security: Automatically sets permissions to 600 (owner read/write only)
    if the file is world-readable. This prevents other users on the system
    from stealing secrets stored in .env files.

    Args:
        env_path: Path to the .env file to check (default: ".env")
    """
    if not os.path.exists(env_path):
        return

    # Security: Don't follow symlinks when checking/fixing permissions
    # This prevents attacks where .env is symlinked to a system file (e.g., /etc/passwd)
    if os.path.islink(env_path):
        sys.stderr.write(
            f"{Colors.WARNING}⚠️  Security Warning: {env_path} is a symlink. "
            f"Skipping permission fix to avoid damaging target file.{Colors.ENDC}\n"
        )
        return

    # Windows doesn't have Unix permissions
    if os.name == "nt":
        # Just warn on Windows, can't auto-fix
        sys.stderr.write(
            f"{Colors.WARNING}⚠️  Security Warning: "
            f"Please ensure {env_path} is only readable by you.{Colors.ENDC}\n"
        )
        return

    try:
        # Security: Use low-level file descriptor operations to avoid TOCTOU (Time-of-Check Time-of-Use)
        # race conditions. We open the file with O_NOFOLLOW to ensure we don't follow symlinks.
        fd = os.open(env_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            file_stat = os.fstat(fd)
            # Check if group or others have any permission
            if file_stat.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
                perms = format(stat.S_IMODE(file_stat.st_mode), "03o")

                # Auto-fix: Set to 600 (owner read/write only) using fchmod on the open descriptor
                try:
                    os.fchmod(fd, 0o600)
                    sys.stderr.write(
                        f"{Colors.GREEN}✓ Fixed {env_path} permissions "
                        f"(was {perms}, now set to 600){Colors.ENDC}\n"
                    )
                except OSError as fix_error:
                    # Auto-fix failed, show warning with instructions
                    sys.stderr.write(
                        f"{Colors.WARNING}⚠️  Security Warning: {env_path} is "
                        f"readable by others ({perms})! Auto-fix failed: {fix_error}. "
                        f"Please run: chmod 600 {env_path}{Colors.ENDC}\n"
                    )
        finally:
            os.close(fd)
    except OSError as error:
        # More specific exception type as suggested by bot review
        exception_type = type(error).__name__
        sys.stderr.write(
            f"{Colors.WARNING}⚠️  Security Warning: Could not check {env_path} "
            f"permissions ({exception_type}: {error}){Colors.ENDC}\n"
        )


def _get_interactive_restart_confirmation() -> bool:
    """Helper to prompt for and validate interactive restart confirmation."""
    prompt_initial = f"{Colors.BOLD}🚀 Ready to launch? {Colors.ENDC}Press [Enter] to run now {Colors.DIM}(or type 'n' / Ctrl+C to cancel)...{Colors.ENDC} "
    prompt_reprompt = f"{Colors.BOLD}🚀 Ready to launch? {Colors.ENDC}Press [Enter] to run now {Colors.DIM}(or type 'n' / Ctrl+C to cancel)...{Colors.ENDC} "
    cancel_msg = f"{Colors.WARNING}⚠️  Cancelled.{Colors.ENDC}"
    err_msg = f"{Colors.FAIL}❌ Unrecognized input. Please press Enter to continue, or 'n' to cancel.{Colors.ENDC}"

    print()  # Add vertical space structurally to avoid terminal clearing issues on KeyboardInterrupt
    prompt = prompt_initial

    while True:
        # Flush stdout (and stderr) so the prompt is visible even if output is buffered or redirected
        sys.stdout.flush()
        sys.stderr.flush()
        try:
            user_response = input(prompt).strip().lower()
        except (KeyboardInterrupt, EOFError):
            _clear_current_line()
            print(cancel_msg, file=sys.stderr)
            return False

        if user_response in ("", "y", "yes"):
            return True

        if user_response in ("n", "no", "q", "quit", "exit", "cancel"):
            print(cancel_msg, file=sys.stderr)
            return False

        print(err_msg, file=sys.stderr)
        print(file=sys.stderr)
        prompt = prompt_reprompt


def prompt_for_interactive_restart(profile_ids: list[str]) -> bool:
    """
    Prompts the user to restart the script in live mode (after a successful dry run).

    If the user confirms, the function returns True, and sys.argv is modified in-place
    to remove --dry-run so the next loop iteration performs a live sync.

    This function only runs if sys.stdin is a TTY (interactive session).
    """
    if not sys.stdin.isatty():
        return False

    if not _get_interactive_restart_confirmation():
        return False

    # Prepare environment for the new process
    # Pass the current token to avoid re-prompting if it was entered interactively
    if TOKEN:
        os.environ["TOKEN"] = TOKEN

    # Construct command arguments
    # Use sys.argv filtering to preserve all user-provided flags (even future ones)
    # while removing --dry-run to switch to live mode.
    clean_argv = [arg for arg in sys.argv[1:] if arg != "--dry-run"]
    new_argv = [sys.executable, sys.argv[0]] + clean_argv

    # If --profiles wasn't in original args (meaning it came from env/input),
    # inject it explicitly so the user doesn't have to re-enter it.
    if "--profiles" not in sys.argv and profile_ids:
        new_argv.extend(["--profiles", ",".join(profile_ids)])

    print(f"\n{Colors.GREEN}🔄 Restarting in live mode...{Colors.ENDC}")
    # Modifying sys.argv in-place allows the main loop to pick up the new arguments
    # without invoking os.execv, eliminating command injection risks entirely.
    sys.argv.clear()
    sys.argv.extend(new_argv)
    return True


def _handle_clear_cache() -> None:
    """Handles the --clear-cache flag by deleting the cache file and exiting."""
    cache_file = get_cache_dir() / "blocklists.json"
    if cache_file.exists():
        try:
            size_bytes = cache_file.stat().st_size
            size_str = (
                f"{size_bytes / (1024 * 1024):.1f} MB"
                if size_bytes >= 1024 * 1024
                else f"{size_bytes / 1024:.1f} KB"
            )
            cache_file.unlink()
            print(
                f"{Colors.GREEN}✓ Cleared blocklist cache: {cache_file} ({size_str} freed){Colors.ENDC}"
            )
        except OSError as e:
            print(f"{Colors.FAIL}✗ Failed to clear cache: {e}{Colors.ENDC}")
            exit(1)
    else:
        print(f"{Colors.CYAN}ℹ No cache file found, nothing to clear{Colors.ENDC}")
        _print_hint(
            "💡 Hint: The cache file will be created or updated after a successful sync run without --dry-run"
        )
    _disk_cache.clear()
    exit(0)


def _prompt_for_missing_config(profile_ids: list[str]) -> None:
    """Prompts for missing profile ID and API token interactively."""
    global TOKEN

    if not profile_ids:
        print(f"{Colors.CYAN}ℹ Profile ID is missing.{Colors.ENDC}")
        _print_hint(
            "  💡 Hint: You can find this in the URL of your profile in the Control D Dashboard (or just paste the URL)."
        )

        def validate_profile_input(value: str) -> bool:
            """Validates one or more profile IDs from comma-separated input."""
            ids = [extract_profile_id(p) for p in value.split(",") if p.strip()]
            return bool(ids) and all(
                validate_profile_id(pid, log_errors=False) for pid in ids
            )

        print()
        p_input = get_validated_input(
            f"{Colors.BOLD}👤 Enter Control D Profile ID {Colors.DIM}(comma-separated for multiple){Colors.ENDC}: ",
            validate_profile_input,
            "Invalid ID(s) or URL(s). Must be a valid Profile ID or a Control D Profile URL. Comma-separate for multiple.",
        )
        profile_ids.extend(
            [extract_profile_id(p) for p in p_input.split(",") if p.strip()]
        )

    if not TOKEN:
        print(f"{Colors.CYAN}ℹ API Token is missing.{Colors.ENDC}")
        _print_hint(
            "  💡 Hint: You can generate one at: https://controld.com/account/manage-account"
        )

        print()
        t_input = get_password(
            f"{Colors.BOLD}🔑 Enter Control D API Token {Colors.DIM}(typing will be hidden){Colors.ENDC}: ",
            lambda x: len(x) > 8,
            "Token seems too short. Please check your API token.",
        )
        TOKEN = t_input


def _build_dry_run_command_str(args: argparse.Namespace, profile_ids: list[str]) -> str:
    """Builds suggested CLI command string for live sync after dry run."""
    cmd_parts = ["python", "main.py"]
    if profile_ids and profile_ids[0] != "dry-run-placeholder":
        p_str = ",".join(profile_ids)
    else:
        p_str = "<your-profile-id>"
    cmd_parts.append(f"--profiles {p_str}")

    if args.folder_url:
        cmd_parts.extend(f"--folder-url {url}" for url in args.folder_url)
    if args.config:
        cmd_parts.append(f"--config {args.config}")
    if args.no_delete:
        cmd_parts.append("--no-delete")

    return " ".join(cmd_parts)


def _print_dry_run_success(cmd_str: str) -> None:
    """Prints suggested command after a dry run."""
    if USE_COLORS:
        print(f"{Colors.BOLD}👉 Ready to sync? Run the following command:{Colors.ENDC}")
        print(f"   {Colors.CYAN}{cmd_str}{Colors.ENDC}")
    else:
        print("👉 Ready to sync? Run the following command:")
        print(f"   {cmd_str}")


def _print_dry_run_failure() -> None:
    """Prints dry run error message."""
    if USE_COLORS:
        print(
            f"{Colors.FAIL}⚠️  Dry run encountered errors. Please check the logs above.{Colors.ENDC}"
        )
    else:
        print("⚠️  Dry run encountered errors. Please check the logs above.")


def _print_dry_run_next_steps(
    args: argparse.Namespace, profile_ids: list[str], all_success: bool
) -> bool:
    """Prints suggested next steps after a dry run and handles interactive restart."""
    print()  # Spacer
    if not all_success:
        _print_dry_run_failure()
        return False

    cmd_str = _build_dry_run_command_str(args, profile_ids)
    _print_dry_run_success(cmd_str)
    return prompt_for_interactive_restart(profile_ids)


def parse_args() -> argparse.Namespace:
    """
    Parses command-line arguments for the Control D sync tool.

    Supports profile IDs, folder URLs, dry-run mode, no-delete flag,
    plan JSON output file path, and an optional config file path.
    """
    parser = argparse.ArgumentParser(
        description="✨ Control D Sync: Keep your folders in sync with remote blocklists.",
        epilog="Run with --dry-run first to preview changes safely. Made with ❤️  for Control D users.",
    )
    parser.add_argument(
        "--profiles", help="Comma-separated list of profile IDs", default=None
    )
    parser.add_argument(
        "--folder-url", action="append", help="Folder JSON URL(s)", default=None
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan only")
    parser.add_argument(
        "--no-delete", action="store_true", help="Do not delete existing folders"
    )
    parser.add_argument("--plan-json", help="Write plan to JSON file", default=None)
    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear the persistent blocklist cache and exit",
    )
    parser.add_argument(
        "--config",
        "-c",
        metavar="FILE",
        help=(
            "Path to a YAML configuration file. "
            "Defaults to config.yaml / config.yml in the current directory "
            "or ~/.ctrld-sync/config.yaml / config.yml."
        ),
        default=None,
    )
    return parser.parse_args()


def _apply_runtime_settings(cfg: dict[str, Any] | None) -> None:
    """Apply optional runtime tuning from config["settings"], if present."""
    if not cfg:
        return
    settings = cfg.get("settings") or {}
    if not isinstance(settings, dict):
        return

    batch_size = settings.get("batch_size")
    if isinstance(batch_size, int) and batch_size > 0:
        config.BATCH_SIZE = batch_size
        # Regenerate BATCH_KEYS since BATCH_SIZE changed
        config.BATCH_KEYS = [f"hostnames[{i}]" for i in range(batch_size)]

    delete_workers = settings.get("delete_workers")
    if isinstance(delete_workers, int) and delete_workers > 0:
        config.DELETE_WORKERS = delete_workers

    max_retries = settings.get("max_retries")
    if isinstance(max_retries, int) and max_retries >= 0:
        api_client.MAX_RETRIES = max_retries


def main() -> bool:
    """
    Main entry point for Control D Sync.

    Loads environment configuration, validates inputs, warms up cache,
    and syncs profiles. Supports interactive prompts for missing credentials
    when running in a TTY. Prints summary statistics and exits with appropriate
    status code.
    """
    # SECURITY: Check .env permissions (after Colors is defined for NO_COLOR support)
    # This must happen BEFORE load_dotenv() to prevent reading secrets from world-readable files
    check_env_permissions()
    load_dotenv()

    global TOKEN
    # Re-initialize TOKEN to pick up values from .env (since load_dotenv was delayed)
    TOKEN = _clean_env_kv(os.getenv("TOKEN"), "TOKEN")

    # Inject token-aware sanitizer into modules that must not log secrets.
    api_client._sanitize_fn = validation.sanitize_for_log
    cache._sanitize_fn = validation.sanitize_for_log
    set_token_for_redaction(TOKEN or "")

    args = parse_args()

    # Load persistent cache from disk (graceful degradation on any error)
    # NOTE: Called only after successful argument parsing so that `--help` or
    #       argument errors do not perform unnecessary filesystem I/O or logging.
    load_disk_cache()

    # Handle --clear-cache: delete cache file and exit immediately
    if args.clear_cache:
        _handle_clear_cache()

    profiles_arg = (
        _clean_env_kv(args.profiles or os.getenv("PROFILE", ""), "PROFILE") or ""
    )
    profile_ids = [extract_profile_id(p) for p in profiles_arg.split(",") if p.strip()]

    # --folder-url flags take highest precedence; otherwise use config file or defaults
    folder_urls, cfg = _resolve_folder_urls(args)

    if cfg is not None:
        _apply_runtime_settings(cfg)

    # Interactive prompts for missing config
    if not args.dry_run and sys.stdin.isatty():
        _prompt_for_missing_config(profile_ids)

    # Re-apply token redaction in case the interactive prompt changed TOKEN.
    set_token_for_redaction(TOKEN or "")

    if not profile_ids and not args.dry_run:
        log.error(
            "PROFILE missing and --dry-run not set. Provide --profiles or set PROFILE env."
        )
        exit(1)

    if not TOKEN and not args.dry_run:
        log.error("TOKEN missing and --dry-run not set. Set TOKEN env for live sync.")
        exit(1)

    warm_up_cache(folder_urls)

    plan: list[PlanEntry] = []
    success_count = 0
    sync_results: list[SyncResult] = []

    profile_id = "unknown"
    start_time = time.time()

    try:
        for profile_id in profile_ids or ["dry-run-placeholder"]:
            start_time = time.time()
            # Skip validation for dry-run placeholder
            if profile_id != "dry-run-placeholder" and not validate_profile_id(
                profile_id
            ):
                sync_results.append(
                    {
                        "profile": profile_id,
                        "folders": 0,
                        "rules": 0,
                        "status_label": "❌ Invalid Profile ID",
                        "success": False,
                        "duration": 0.0,
                    }
                )
                continue

            display_profile = (
                "(Unspecified)" if profile_id == "dry-run-placeholder" else profile_id
            )
            log.info("Starting sync for profile %s", display_profile)
            status = sync_profile(
                profile_id,
                folder_urls,
                token=TOKEN or "",
                dry_run=args.dry_run,
                no_delete=args.no_delete,
                plan_accumulator=plan,
            )
            end_time = time.time()
            duration = end_time - start_time

            if status:
                success_count += 1

            entry = next((p for p in plan if p["profile"] == profile_id), None)
            folder_count = len(entry["folders"]) if entry else 0
            rule_count = sum([f["rules"] for f in entry["folders"]]) if entry else 0

            if args.dry_run:
                status_text = "✅ Planned" if status else "❌ Failed (Dry)"
            else:
                status_text = "✅ Success" if status else "❌ Failed"

            sync_results.append(
                {
                    "profile": profile_id,
                    "folders": folder_count,
                    "rules": rule_count,
                    "status_label": status_text,
                    "success": status,
                    "duration": duration,
                }
            )
    except KeyboardInterrupt:
        duration = time.time() - start_time
        _clear_current_line()
        print(
            f"{Colors.WARNING}⚠️  Sync cancelled by user. Finishing current task...{Colors.ENDC}",
            file=sys.stderr,
        )

        entry = next((p for p in plan if p["profile"] == profile_id), None)
        folder_count = len(entry["folders"]) if entry else 0
        rule_count = sum([f["rules"] for f in entry["folders"]]) if entry else 0

        sync_results.append(
            {
                "profile": profile_id,
                "folders": folder_count,
                "rules": rule_count,
                "status_label": "⛔ Cancelled",
                "success": False,
                "duration": duration,
            }
        )

    if args.plan_json:
        with open(args.plan_json, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)
        log.info("Plan written to %s", args.plan_json)

    total = len(profile_ids or ["dry-run-placeholder"])
    all_success = success_count == total

    print_summary_table(
        sync_results=sync_results,
        success_count=success_count,
        total=total,
        dry_run=args.dry_run,
    )

    # Success Delight
    if success_count > 0 and not args.dry_run:
        print_success_message(profile_ids, success_count, total)

    # Dry Run Next Steps
    if args.dry_run and _print_dry_run_next_steps(args, profile_ids, all_success):
        return True

    # Display execution statistics and rate limit status
    display_statistics()

    # Save cache to disk after successful sync (non-fatal if it fails)
    if not args.dry_run:
        save_disk_cache()

    total = len(profile_ids or ["dry-run-placeholder"])
    log.info(f"All profiles processed: {success_count}/{total} successful")
    if success_count != total:
        exit(1)
    return False


if __name__ == "__main__":
    try:
        while main():
            pass
    except KeyboardInterrupt:
        _clear_current_line()
        print(f"{Colors.WARNING}⚠️  Cancelled by user.{Colors.ENDC}", file=sys.stderr)
        sys.exit(130)
