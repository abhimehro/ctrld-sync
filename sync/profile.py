"""Per-profile orchestration: plan, delete, create folders and push rules."""

from __future__ import annotations

import concurrent.futures
from dataclasses import dataclass

import config
import httpx
import sync

from display import pluralize, print_plan_details
from models import FolderData, RuleAction, SyncContext, SyncProfileOptions
from validation import sanitize_for_log


@dataclass(frozen=True, slots=True)
class _FolderPreparationContext:
    """Shared state for preparing folders and collecting existing rules."""

    client: httpx.Client
    profile_id: str
    shared_executor: concurrent.futures.ThreadPoolExecutor
    no_delete: bool


def _partition_folders_for_deletion(
    prep: _FolderPreparationContext,
    folder_data_list: list[FolderData],
    existing_folders: dict[str, str],
) -> tuple[list[tuple[str, str]], dict[str, str]]:
    """Partition replacement folders while preserving target order."""
    folders_to_delete: list[tuple[str, str]] = []
    folders_to_scan = existing_folders.copy()

    if prep.no_delete:
        return folders_to_delete, folders_to_scan

    for folder_data in folder_data_list:
        name = folder_data["group"]["group"].strip()
        if name in existing_folders:
            folders_to_delete.append((name, existing_folders[name]))
            folders_to_scan.pop(name, None)

    return folders_to_delete, folders_to_scan


def _delete_folders(
    prep: _FolderPreparationContext,
    folders_to_delete: list[tuple[str, str]],
    existing_folders: dict[str, str],
) -> bool:
    """Delete replacement folders and return whether any deletion succeeded."""
    future_to_name = {
        prep.shared_executor.submit(
            sync.delete_folder, prep.client, prep.profile_id, name, folder_id
        ): name
        for name, folder_id in folders_to_delete
    }
    deletion_occurred = False

    for future in concurrent.futures.as_completed(future_to_name):
        name = future_to_name[future]
        try:
            if future.result():
                del existing_folders[name]
                deletion_occurred = True
        except Exception as exc:
            sync.log.error(
                "Failed to delete folder %s: %s",
                sanitize_for_log(name),
                sanitize_for_log(exc),
            )

    return deletion_occurred


def _wait_for_deletions(deletion_occurred: bool) -> None:
    """Wait for successfully deleted folders to leave the API."""
    if not deletion_occurred:
        return
    if not sync.USE_COLORS:
        sync.log.info(
            "Waiting 60s for deletions to propagate (prevents 'Badware Hoster' zombie state)..."
        )
    sync.countdown_timer(60, "Waiting for deletions to propagate")


def _resolve_rules_future(
    existing_rules_future: concurrent.futures.Future[set[str]],
) -> set[str]:
    """Resolve the background rules scan using its current error boundary."""
    try:
        return existing_rules_future.result()
    except Exception as e:
        sync.log.error(
            f"Failed to fetch existing rules in background: {sanitize_for_log(e)}"
        )
        return set()


def _prepare_folders_and_rules(
    prep: _FolderPreparationContext,
    folder_data_list: list[FolderData],
) -> tuple[dict[str, str] | None, set[str]]:
    """
    Verifies access, deletes old folders, and fetches existing rules in background.
    """
    existing_folders = sync.verify_access_and_get_folders(prep.client, prep.profile_id)
    if existing_folders is None:
        return None, set()

    folders_to_delete, folders_to_scan = _partition_folders_for_deletion(
        prep, folder_data_list, existing_folders
    )
    existing_rules_future = prep.shared_executor.submit(
        sync.get_all_existing_rules, prep.client, prep.profile_id, folders_to_scan
    )

    if not prep.no_delete and folders_to_delete:
        deletion_occurred = _delete_folders(prep, folders_to_delete, existing_folders)
        _wait_for_deletions(deletion_occurred)

    existing_rules = _resolve_rules_future(existing_rules_future)
    return existing_folders, existing_rules


def _sync_profile_live(
    options: SyncProfileOptions,
    folder_data_list: list[FolderData],
) -> bool:
    """Execute the live (non-dry-run) portion of a profile sync."""
    with (
        concurrent.futures.ThreadPoolExecutor(
            max_workers=config.DELETE_WORKERS
        ) as shared_executor,
        sync.create_client(options.token) as client,
    ):
        prep = _FolderPreparationContext(
            client=client,
            profile_id=options.profile_id,
            shared_executor=shared_executor,
            no_delete=options.no_delete,
        )
        existing_folders_and_rules = _prepare_folders_and_rules(prep, folder_data_list)
        if existing_folders_and_rules[0] is None:
            return False
        existing_folders, existing_rules = existing_folders_and_rules

        ctx = SyncContext(
            profile_id=options.profile_id,
            client=client,
            existing_rules=existing_rules,
            batch_executor=shared_executor,
        )

        success_count = _process_folders(ctx, folder_data_list)

    sync.log.info(
        f"Sync complete: {success_count}/{len(folder_data_list)} {pluralize(len(folder_data_list), 'folder')} processed successfully"
    )
    return success_count == len(folder_data_list)


def _process_single_folder(
    ctx: SyncContext,
    folder_data: FolderData,
) -> bool:
    grp = folder_data["group"]
    name = grp["group"].strip()

    # Client is now passed in, reusing the connection
    main_do = grp.get("action", {}).get("do", 0)
    main_status = grp.get("action", {}).get("status", 1)
    main_action = RuleAction(do=main_do, status=main_status)

    folder_id = sync.create_folder(ctx, name, main_action)
    if not folder_id:
        return False

    folder_success = True
    if "rule_groups" in folder_data:
        for rule_group in folder_data["rule_groups"]:
            action_data = rule_group.get("action", {})
            action = RuleAction(
                do=action_data.get("do", 0),
                status=action_data.get("status", 1),
            )
            hostnames = [pk for r in rule_group.get("rules", []) if (pk := r.get("PK"))]
            if not sync.push_rules(
                ctx,
                name,
                folder_id,
                action,
                hostnames,
            ):
                folder_success = False
    else:
        hostnames = [pk for r in folder_data.get("rules", []) if (pk := r.get("PK"))]
        if not sync.push_rules(
            ctx,
            name,
            folder_id,
            main_action,
            hostnames,
        ):
            folder_success = False

    return folder_success


def _process_folders(
    ctx: SyncContext,
    folder_data_list: list[FolderData],
) -> int:
    """Process folders serially (max_workers=1) and return the success count."""
    success_count = 0
    # CRITICAL FIX: Switch to Serial Processing (1 worker)
    # This prevents API rate limits and ensures stability for large folders.
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future_to_folder = {
            executor.submit(sync._process_single_folder, ctx, folder_data): folder_data
            for folder_data in folder_data_list
        }

        for future in concurrent.futures.as_completed(future_to_folder):
            folder_data = future_to_folder[future]
            folder_name = folder_data["group"]["group"].strip()
            try:
                if future.result():
                    success_count += 1
            except Exception as e:
                sync.log.error(
                    f"Failed to process folder '{sanitize_for_log(folder_name)}': {sanitize_for_log(e)}"
                )

    return success_count


def sync_profile(options: SyncProfileOptions) -> bool:
    """
    Synchronizes Control D folders from remote blocklist URLs.

    Fetches folder data, optionally deletes existing folders with same names,
    creates new folders, and pushes rules in batches. In dry-run mode, only
    generates a plan without making API changes. Returns True if all folders
    sync successfully.
    """
    # SECURITY: Clear cached DNS validations at the start of each sync run.
    # This prevents TOCTOU issues where a domain's IP could change between runs.
    sync.validate_folder_url.cache_clear()
    sync.validate_hostname.cache_clear()

    try:
        folder_data_list = sync._fetch_all_folder_data(options.folder_urls)
        if folder_data_list is None:
            return False

        # Build plan entries
        plan_entry = sync._build_plan_entry(options.profile_id, folder_data_list)

        if options.plan_accumulator is not None:
            options.plan_accumulator.append(plan_entry)

        if options.dry_run:
            print_plan_details(plan_entry)
            sync.log.info("Dry-run complete: no API calls were made.")
            return True

        return _sync_profile_live(options, folder_data_list)

    except Exception as e:
        sync.log.error(
            f"Unexpected error during sync for profile {options.profile_id}: {sanitize_for_log(e)}"
        )
        return False
