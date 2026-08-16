"""Get All Existing Rules cluster."""

from __future__ import annotations

import concurrent.futures
import itertools

import config
import httpx
import sync

from display import pluralize
from validation import is_valid_rule, sanitize_for_log


def get_all_existing_rules(
    client: httpx.Client,
    profile_id: str,
    known_folders: dict[str, str] | None = None,
) -> set[str]:
    """
    Fetches all existing rules across root and all folders.

    Retrieves rules from the root level and all folders in parallel.
    Uses known_folders to avoid redundant API calls when provided.
    Returns set of rule IDs.
    """
    all_rules = set()

    def _fetch_folder_rules(folder_id: str) -> list[str]:
        try:
            data = sync._api_get(
                client, f"{config.API_BASE}/{profile_id}/rules/{folder_id}"
            ).json()
            folder_rules = data.get("body", {}).get("rules", [])
            return [pk for rule in folder_rules if (pk := rule.get("PK"))]
        except httpx.HTTPError as e:
            sync.log.debug(
                "Could not fetch rules for folder %s (will skip): %s",
                folder_id,
                sanitize_for_log(e),
            )
            return []
        except Exception as e:
            # We log error but don't stop the whole process;
            # individual folder failure shouldn't crash the sync
            sync.log.warning(
                f"Error fetching rules for folder {folder_id}: {sanitize_for_log(e)}"
            )
            return []

    try:
        # Get rules from root
        try:
            data = sync._api_get(client, f"{config.API_BASE}/{profile_id}/rules").json()
            root_rules = data.get("body", {}).get("rules", [])
            # OPTIMIZATION: C-speed list comprehension with bulk update is faster than Python for-loop
            all_rules.update([pk for rule in root_rules if (pk := rule.get("PK"))])
        except httpx.HTTPError as e:
            sync.log.debug(
                "Could not fetch root-level rules (will proceed with folder rules only): %s",
                sanitize_for_log(e),
            )

        # Get rules from folders in parallel
        # Optimization: Use known_folders if provided to avoid redundant API call
        if known_folders is not None:
            folders = known_folders
        else:
            folders = sync.list_existing_folders(client, profile_id)

        # Parallelize fetching rules from folders.
        # Using 5 workers to be safe with rate limits, though GETs are usually cheaper.
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_folder = {
                executor.submit(_fetch_folder_rules, folder_id): folder_id
                for folder_name, folder_id in folders.items()
            }

            for future in concurrent.futures.as_completed(future_to_folder):
                try:
                    result = future.result()
                    if result:
                        all_rules.update(result)
                except Exception as e:
                    folder_id = future_to_folder[future]
                    sync.log.warning(
                        f"Failed to fetch rules for folder ID {folder_id}: {sanitize_for_log(e)}"
                    )

        sync.log.info(f"Total existing rules across all folders: {len(all_rules):,}")
        return all_rules
    except Exception as e:
        sync.log.error(f"Failed to get existing rules: {sanitize_for_log(e)}")
        return set()


def _deduplicate_hostnames(
    existing_rules: set[str], hostnames: list[str]
) -> dict[str, None]:
    """Optimization 1: Deduplicate and filter existing rules efficiently."""
    if not existing_rules:
        return dict.fromkeys(hostnames)

    # Filter first using itertools.filterfalse (C-speed), then deduplicate with dict.fromkeys.
    # This prevents redundant dictionary insertions for rules already in existing_rules,
    # and avoids materializing a large intermediate list before deduplication.
    return dict.fromkeys(itertools.filterfalse(existing_rules.__contains__, hostnames))


def _log_filtering_results(
    original_count: int,
    unique_hostnames_dict: dict[str, None],
    filtered_hostnames: list[str],
    folder_name: str,
) -> None:
    """Logs statistics for dropped entries and duplicated rules."""
    skipped_unsafe = len(unique_hostnames_dict) - len(filtered_hostnames)

    if skipped_unsafe > 0:
        # SLOW PATH: Only iterate again to log if we actually found unsafe rules
        is_safe = is_valid_rule
        sanitized_folder = sanitize_for_log(folder_name)
        for h in unique_hostnames_dict:
            if not is_safe(h):
                sync.log.warning(
                    f"Skipping unsafe rule in {sanitized_folder}: {sanitize_for_log(h)}"
                )
        sync.log.warning(
            f"Folder {sanitized_folder}: skipped {skipped_unsafe} unsafe {pluralize(skipped_unsafe, 'rule')}"
        )

    duplicates_count = original_count - len(filtered_hostnames) - skipped_unsafe

    if duplicates_count > 0:
        sync.log.info(
            f"Folder {sanitize_for_log(folder_name)}: skipping {duplicates_count} duplicate {pluralize(duplicates_count, 'rule')}"
        )


def _filter_rules_for_folder(
    existing_rules: set[str],
    hostnames: list[str],
    folder_name: str,
) -> list[str]:
    """
    Deduplicates and filters hostnames, logging dropped entries.
    """
    unique_hostnames_dict = _deduplicate_hostnames(existing_rules, hostnames)

    # Optimization 2: Inline method references for hot loop performance
    allowed = sync._ALLOWED_RULE_CHARS
    max_len = sync.MAX_RULE_LENGTH

    # Second pass: Strict safety validation
    # FAST PATH: C-speed list comprehension for the 99.9% case where rules are safe
    filtered_hostnames = [
        h
        for h in unique_hostnames_dict
        if h and len(h) <= max_len and allowed.issuperset(h)
    ]

    _log_filtering_results(
        len(hostnames), unique_hostnames_dict, filtered_hostnames, folder_name
    )

    return filtered_hostnames
