"""Control D folder/rule synchronization orchestration."""

from __future__ import annotations

import concurrent.futures
import contextlib
import itertools
import logging
import sys
import time
from collections.abc import Sequence


import httpx

import api_client
import config
from api_client import (
    _CONNECT_ERROR_HINT,
    _TIMEOUT_HINT,
    _api_delete,
    _api_get,
    _api_post,
    _api_post_form,
)
from display import (
    Colors,
    USE_COLORS,
    _clear_current_line,
    _print_completion,
    countdown_timer,
    pluralize,
    print_plan_details,
    render_progress_bar,
)
from gh_client import _cache, _cache_lock, fetch_folder_data  # noqa: F401
from models import FolderData, PlanEntry, RuleAction, SyncContext
from validation import (
    _ALLOWED_RULE_CHARS,
    MAX_RULE_LENGTH,
    is_valid_rule,
    sanitize_for_log,
    set_token_for_redaction,
    validate_folder_id,
    validate_folder_url,
    validate_hostname,
)

log = logging.getLogger(__name__)


def create_client(token: str) -> httpx.Client:
    set_token_for_redaction(token)
    return httpx.Client(
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": config.USER_AGENT,
        },
        # SECURITY: Explicit timeouts prevent resource exhaustion/DoS via Slowloris
        timeout=httpx.Timeout(10.0, connect=5.0),
        follow_redirects=False,
    )


def check_api_access(client: httpx.Client, profile_id: str) -> bool:
    """
    Verifies API access and Profile existence before starting heavy work.
    Returns True if access is good, False otherwise (with helpful logs).
    """
    url = f"{config.API_BASE}/{profile_id}/groups"
    try:
        # We use a raw request here to avoid the automatic retries of _retry_request
        # for auth errors, which are permanent.
        resp = client.get(url)
        resp.raise_for_status()
        return True
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 401:
            log.critical(
                f"{Colors.FAIL}❌ Authentication Failed: The API Token is invalid.{Colors.ENDC}"
            )
            log.critical(
                f"{Colors.FAIL}   Please check your token at: https://controld.com/account/manage-account{Colors.ENDC}"
            )
        elif code == 403:
            log.critical(
                f"{Colors.FAIL}🚫 Access Denied: Token lacks permission for Profile {profile_id}.{Colors.ENDC}"
            )
        elif code == 404:
            log.critical(
                f"{Colors.FAIL}🔍 Profile Not Found: The ID '{sanitize_for_log(profile_id)}' does not exist.{Colors.ENDC}"
            )
            log.critical(
                f"{Colors.FAIL}   Please verify the Profile ID from your Control D Dashboard URL.{Colors.ENDC}"
            )
        else:
            log.error(f"API Access Check Failed ({code}): {sanitize_for_log(e)}")
        return False
    except httpx.RequestError as e:
        hint = ""
        if isinstance(e, httpx.TimeoutException):
            hint = f" | hint: {_TIMEOUT_HINT}"
        elif isinstance(e, httpx.ConnectError):
            hint = f" | hint: {_CONNECT_ERROR_HINT}"
        log.error(f"Network Error during access check: {sanitize_for_log(e)}{hint}")
        return False


def list_existing_folders(client: httpx.Client, profile_id: str) -> dict[str, str]:
    """
    Retrieves all existing folders (groups) for a given profile.

    Returns a dictionary mapping folder names to their IDs.
    Returns empty dict on error.
    """
    try:
        data = _api_get(client, f"{config.API_BASE}/{profile_id}/groups").json()
        folders = data.get("body", {}).get("groups", [])
        result = {}
        for f in folders:
            if not f.get("group") or not f.get("PK"):
                continue
            pk = str(f["PK"])
            if validate_folder_id(pk):
                result[f["group"].strip()] = pk
        return result
    except (httpx.HTTPError, KeyError) as e:
        hint = ""
        if isinstance(e, httpx.HTTPStatusError):
            hint = f" | hint: {config._STATUS_HINTS.get(e.response.status_code, f'HTTP {e.response.status_code}')}"
        elif isinstance(e, httpx.TimeoutException):
            hint = f" | hint: {_TIMEOUT_HINT}"
        elif isinstance(e, httpx.ConnectError):
            hint = f" | hint: {_CONNECT_ERROR_HINT}"
        log.error(f"Failed to list existing folders{hint}: {sanitize_for_log(e)}")
        return {}


def _parse_folders_response(data: dict) -> dict[str, str] | None:
    """Parse folders response."""
    if not isinstance(data, dict):
        log.error("Failed to parse folders data: response is not a JSON object")
        return None
    body = data.get("body")
    if not isinstance(body, dict):
        log.error("Failed to parse folders data: 'body' is not a JSON object")
        return None
    folders = body.get("groups", [])
    if not isinstance(folders, list):
        log.error("Failed to parse folders data: 'body[\"groups\"]' is not a list")
        return None

    result: dict[str, str] = {}
    for f in folders:
        if not isinstance(f, dict):
            continue
        name = f.get("group")
        pk = f.get("PK")
        if not name or not pk:
            continue
        pk_str = str(pk)
        if validate_folder_id(pk_str):
            result[str(name).strip()] = pk_str

    return result


def verify_access_and_get_folders(
    client: httpx.Client, profile_id: str
) -> dict[str, str] | None:
    """Combine access check and folder listing into a single API request.

    Returns:
        Dict of {folder_name: folder_id} on success.
        None if access is denied or the request fails after retries.
    """
    url = f"{config.API_BASE}/{profile_id}/groups"

    for attempt in range(api_client.MAX_RETRIES):
        try:
            resp = client.get(url)
            resp.raise_for_status()
            return _parse_folders_response(resp.json())

        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code in (401, 403, 404):
                error_messages = {
                    401: [
                        "❌ Authentication Failed: The API Token is invalid.",
                        "   Please check your token at: https://controld.com/account/manage-account",
                    ],
                    403: [
                        f"🚫 Access Denied: Token lacks permission for Profile {sanitize_for_log(profile_id)}."
                    ],
                    404: [
                        f"🔍 Profile Not Found: The ID '{sanitize_for_log(profile_id)}' does not exist.",
                        "   Please verify the Profile ID from your Control D Dashboard URL.",
                    ],
                }
                for line in error_messages.get(code, []):
                    log.critical(f"{Colors.FAIL}{line}{Colors.ENDC}")
                return None

            if attempt == api_client.MAX_RETRIES - 1:
                log.error(f"API Request Failed ({code}): {sanitize_for_log(e)}")
                return None

        except httpx.RequestError as err:
            if attempt == api_client.MAX_RETRIES - 1:
                hint = (
                    f" | hint: {_TIMEOUT_HINT}"
                    if isinstance(err, httpx.TimeoutException)
                    else (
                        f" | hint: {_CONNECT_ERROR_HINT}"
                        if isinstance(err, httpx.ConnectError)
                        else ""
                    )
                )
                log.error(
                    "Network error during access verification: %s%s",
                    sanitize_for_log(err),
                    hint,
                )
                return None

        wait_time = api_client.RETRY_DELAY * (2**attempt)
        log.warning(
            "Request failed (attempt %d/%d). Retrying in %ds...",
            attempt + 1,
            api_client.MAX_RETRIES,
            wait_time,
        )
        time.sleep(wait_time)

    return None


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
            data = _api_get(
                client, f"{config.API_BASE}/{profile_id}/rules/{folder_id}"
            ).json()
            folder_rules = data.get("body", {}).get("rules", [])
            return [pk for rule in folder_rules if (pk := rule.get("PK"))]
        except httpx.HTTPError as e:
            log.debug(
                "Could not fetch rules for folder %s (will skip): %s",
                folder_id,
                sanitize_for_log(e),
            )
            return []
        except Exception as e:
            # We log error but don't stop the whole process;
            # individual folder failure shouldn't crash the sync
            log.warning(
                f"Error fetching rules for folder {folder_id}: {sanitize_for_log(e)}"
            )
            return []

    try:
        # Get rules from root
        try:
            data = _api_get(client, f"{config.API_BASE}/{profile_id}/rules").json()
            root_rules = data.get("body", {}).get("rules", [])
            # OPTIMIZATION: C-speed list comprehension with bulk update is faster than Python for-loop
            all_rules.update([pk for rule in root_rules if (pk := rule.get("PK"))])
        except httpx.HTTPError as e:
            log.debug(
                "Could not fetch root-level rules (will proceed with folder rules only): %s",
                sanitize_for_log(e),
            )

        # Get rules from folders in parallel
        # Optimization: Use known_folders if provided to avoid redundant API call
        if known_folders is not None:
            folders = known_folders
        else:
            folders = list_existing_folders(client, profile_id)

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
                    log.warning(
                        f"Failed to fetch rules for folder ID {folder_id}: {sanitize_for_log(e)}"
                    )

        log.info(f"Total existing rules across all folders: {len(all_rules):,}")
        return all_rules
    except Exception as e:
        log.error(f"Failed to get existing rules: {sanitize_for_log(e)}")
        return set()


def delete_folder(
    client: httpx.Client, profile_id: str, name: str, folder_id: str
) -> bool:
    """
    Deletes a folder (group) from a Control D profile.

    Returns True on success, False on failure. Logs detailed error information.
    """
    try:
        _api_delete(client, f"{config.API_BASE}/{profile_id}/groups/{folder_id}")
        log.info(
            "Deleted folder %s (ID %s)",
            sanitize_for_log(name),
            sanitize_for_log(folder_id),
        )
        return True
    except httpx.HTTPError as e:
        hint = ""
        if isinstance(e, httpx.HTTPStatusError):
            hint = f" | hint: {config._STATUS_HINTS.get(e.response.status_code, f'HTTP {e.response.status_code}')}"
        elif isinstance(e, httpx.TimeoutException):
            hint = f" | hint: {_TIMEOUT_HINT}"
        elif isinstance(e, httpx.ConnectError):
            hint = f" | hint: {_CONNECT_ERROR_HINT}"
        log.error(
            f"Failed to delete folder {sanitize_for_log(name)} (ID {sanitize_for_log(folder_id)}){hint}: {sanitize_for_log(e)}"
        )
        return False


def _process_new_folder_pk(pk: str, name: str, source: str) -> str | None:
    if not validate_folder_id(pk, log_errors=False):
        log.error(f"API returned invalid folder ID: {sanitize_for_log(pk)}")
        return None
    log.info(
        "Created folder %s (ID %s) [%s]",
        sanitize_for_log(name),
        sanitize_for_log(pk),
        source,
    )
    return pk


def _extract_from_groups_list(groups: list, name: str) -> str | None:
    """Extract folder ID from groups list."""
    for grp in groups:
        if not isinstance(grp, dict):
            continue
        if grp.get("group", "").strip() != name.strip():
            continue
        if "PK" in grp:
            pk = _process_new_folder_pk(str(grp["PK"]), name, "Direct")
            if pk:
                return pk
    return None


def _extract_folder_id_from_response(response: httpx.Response, name: str) -> str | None:
    try:
        body = response.json().get("body")
    except Exception as e:
        if log.isEnabledFor(logging.DEBUG):
            log.debug(f"Could not extract ID from POST response: {sanitize_for_log(e)}")
        return None

    if not isinstance(body, dict):
        return None

    group = body.get("group")
    if isinstance(group, dict) and "PK" in group:
        return _process_new_folder_pk(str(group["PK"]), name, "Direct")

    groups = body.get("groups")
    if isinstance(groups, list):
        return _extract_from_groups_list(groups, name)

    return None


def _poll_for_folder_id(ctx: SyncContext, name: str) -> str | None:
    for attempt in range(api_client.MAX_RETRIES + 1):
        try:
            data = _api_get(
                ctx.client, f"{config.API_BASE}/{ctx.profile_id}/groups"
            ).json()
            groups = data.get("body", {}).get("groups", [])

            for grp in groups:
                if not isinstance(grp, dict):
                    continue
                if grp.get("group", "").strip() != name.strip():
                    continue
                if "PK" in grp:
                    pk = _process_new_folder_pk(str(grp["PK"]), name, "Polled")
                    if pk:
                        return pk
                    return None  # Invalid PK found, stop polling
        except Exception as e:
            log.warning(
                f"Error fetching groups on attempt {attempt}: {sanitize_for_log(e)}"
            )

        if attempt < api_client.MAX_RETRIES:
            wait_time = config.FOLDER_CREATION_DELAY * (attempt + 1)
            countdown_timer(
                wait_time, f"Waiting for folder '{sanitize_for_log(name)}' to appear"
            )

    log.error(
        f"Folder {sanitize_for_log(name)} was not found after creation and retries."
    )
    return None


def create_folder(ctx: SyncContext, name: str, action: RuleAction) -> str | None:
    """
    Create a new folder and return its ID.
    Attempts to read ID from response first, then falls back to polling.
    """
    log.info(f"Creating folder {sanitize_for_log(name)}")
    try:
        # 1. Send the Create Request
        response = _api_post(
            ctx.client,
            f"{config.API_BASE}/{ctx.profile_id}/groups",
            data={"name": name, "do": action.do, "status": action.status},
        )

        # OPTIMIZATION: Try to grab ID directly from response to avoid the wait loop
        pk = _extract_folder_id_from_response(response, name)
        if pk:
            return pk

        # 2. Fallback: Poll for the new folder (The Robust Retry Logic)
        return _poll_for_folder_id(ctx, name)

    except (httpx.HTTPError, KeyError) as e:
        hint = ""
        if isinstance(e, httpx.HTTPStatusError):
            hint = f" | hint: {config._STATUS_HINTS.get(e.response.status_code, f'HTTP {e.response.status_code}')}"
        log.error(
            f"Failed to create folder {sanitize_for_log(name)}{hint}: {sanitize_for_log(e)}"
        )
        return None


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
                log.warning(
                    f"Skipping unsafe rule in {sanitized_folder}: {sanitize_for_log(h)}"
                )
        log.warning(
            f"Folder {sanitized_folder}: skipped {skipped_unsafe} unsafe {pluralize(skipped_unsafe, 'rule')}"
        )

    duplicates_count = original_count - len(filtered_hostnames) - skipped_unsafe

    if duplicates_count > 0:
        log.info(
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
    allowed = _ALLOWED_RULE_CHARS
    max_len = MAX_RULE_LENGTH

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


def _push_single_batch(
    client: httpx.Client,
    profile_id: str,
    sanitized_folder_name: str,
    str_do: str,
    str_status: str,
    str_group: str,
    batch_idx: int,
    batch_data: list[str],
) -> list[str] | None:
    """Processes a single batch of rules by sending API request."""
    data = {
        "do": str_do,
        "status": str_status,
        "group": str_group,
    }
    # Optimization: Use pre-calculated keys and zip for faster dict update
    # strict=False is intentional: batch_data may be shorter than BATCH_KEYS for final batch
    data.update(zip(config.BATCH_KEYS, batch_data, strict=False))

    try:
        _api_post_form(client, f"{config.API_BASE}/{profile_id}/rules", data=data)
        if not USE_COLORS:
            log.info(
                "Folder %s – batch %d: added %d %s",
                sanitized_folder_name,
                batch_idx,
                len(batch_data),
                pluralize(len(batch_data), "rule"),
            )
        return batch_data
    except httpx.HTTPError as e:
        _clear_current_line()
        hint = ""
        if isinstance(e, httpx.HTTPStatusError):
            # Use a more specific name to avoid confusion with the rule "status" payload
            status_code = e.response.status_code
            hint = f" ({config._STATUS_HINTS.get(status_code, f'HTTP {status_code}')})"
        log.error(
            f"Failed to push batch {batch_idx} for folder {sanitized_folder_name}{hint}: {sanitize_for_log(e)}"
        )
        response = getattr(e, "response", None)
        if response is not None and log.isEnabledFor(logging.DEBUG):
            log.debug(f"Response content: {sanitize_for_log(response.text)}")
        return None


def _process_batches_with_executor(
    executor: concurrent.futures.Executor,
    ctx: SyncContext,
    batch_config: tuple[tuple[str, str, str, str], list[list[str]], str],
) -> int:
    """Process batches using the provided executor and return successful batch count."""
    batch_params, batches, progress_label = batch_config
    str_do, str_status, str_group, sanitized_folder_name = batch_params
    successful_batches = 0
    futures = {
        executor.submit(
            _push_single_batch,
            ctx.client,
            ctx.profile_id,
            sanitized_folder_name,
            str_do,
            str_status,
            str_group,
            i,
            batch,
        ): i
        for i, batch in enumerate(batches, 1)
    }

    for future in concurrent.futures.as_completed(futures):
        result = future.result()
        if result:
            successful_batches += 1
            ctx.existing_rules.update(result)

        render_progress_bar(successful_batches, len(batches), progress_label)

    return successful_batches


def _log_batch_result(
    sanitized_folder_name: str,
    successful_batches: int,
    total_batches: int,
    total_rules: int,
) -> bool:
    """Helper to evaluate and log the result of a batch rule push."""
    if successful_batches == total_batches:
        _print_completion(
            f"Folder {sanitized_folder_name}: Finished ({total_rules:,} {pluralize(total_rules, 'rule')})"
        )
        return True

    _clear_current_line()
    if successful_batches > 0:
        log.warning(
            "Folder %s – only %d/%d batches succeeded (Partial)",
            sanitized_folder_name,
            successful_batches,
            total_batches,
        )
    else:
        log.error(
            "Folder %s – 0/%d batches succeeded",
            sanitized_folder_name,
            total_batches,
        )
    return False


def _push_rule_batches(
    ctx: SyncContext,
    folder_name: str,
    folder_id: str,
    action: RuleAction,
    filtered_hostnames: list[str],
) -> bool:
    """
    Splits rules into batches and pushes them to the API in parallel.
    """
    batches = [
        filtered_hostnames[start : start + config.BATCH_SIZE]
        for start in range(0, len(filtered_hostnames), config.BATCH_SIZE)
    ]
    total_batches = len(batches)

    # Optimization: Hoist loop invariants to avoid redundant computations
    str_do = str(action.do)
    str_status = str(action.status)
    str_group = str(folder_id)
    sanitized_folder_name = sanitize_for_log(folder_name)
    progress_label = f"Folder {sanitized_folder_name}"

    # Optimization 3: Parallelize batch processing
    batch_params = (str_do, str_status, str_group, sanitized_folder_name)
    batch_config = (batch_params, batches, progress_label)

    if total_batches == 1:
        result = _push_single_batch(
            ctx.client,
            ctx.profile_id,
            sanitized_folder_name,
            str_do,
            str_status,
            str_group,
            1,
            batches[0],
        )
        successful_batches = 1 if result else 0
        if result:
            ctx.existing_rules.update(result)
        render_progress_bar(successful_batches, 1, progress_label)
    else:
        if ctx.batch_executor:
            with contextlib.nullcontext(ctx.batch_executor) as executor:
                successful_batches = _process_batches_with_executor(
                    executor, ctx, batch_config
                )
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                successful_batches = _process_batches_with_executor(
                    executor, ctx, batch_config
                )

    return _log_batch_result(
        sanitized_folder_name,
        successful_batches,
        total_batches,
        len(filtered_hostnames),
    )


def push_rules(
    ctx: SyncContext,
    folder_name: str,
    folder_id: str,
    action: RuleAction,
    hostnames: list[str],
) -> bool:
    """
    Pushes rules to a folder in batches, filtering duplicates and invalid rules.

    Deduplicates input, validates rules against _ALLOWED_RULE_CHARS, and sends batches
    in parallel for optimal performance. Updates ctx.existing_rules set with newly
    added rules. Returns True if all batches succeed.
    """
    if not hostnames:
        log.info("Folder %s - no rules to push", sanitize_for_log(folder_name))
        return True

    filtered_hostnames = _filter_rules_for_folder(
        ctx.existing_rules, hostnames, folder_name
    )

    if not filtered_hostnames:
        log.info(
            f"Folder {sanitize_for_log(folder_name)} - no new rules to push after filtering duplicates"
        )
        return True

    return _push_rule_batches(
        ctx,
        folder_name,
        folder_id,
        action,
        filtered_hostnames,
    )


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

    folder_id = create_folder(ctx, name, main_action)
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
            if not push_rules(
                ctx,
                name,
                folder_id,
                action,
                hostnames,
            ):
                folder_success = False
    else:
        hostnames = [pk for r in folder_data.get("rules", []) if (pk := r.get("PK"))]
        if not push_rules(
            ctx,
            name,
            folder_id,
            main_action,
            hostnames,
        ):
            folder_success = False

    return folder_success


def _fetch_all_folder_data(folder_urls: Sequence[str]) -> list[FolderData] | None:
    """Fetches folder data for all URLs in parallel."""
    folder_data_list: list[FolderData] = []

    # OPTIMIZATION: Move validation inside the thread pool to parallelize DNS lookups.
    # Previously, sequential validation blocked the main thread.
    def _fetch_if_valid(url: str):
        # Optimization: If we already have the content in cache, return it directly.
        # The content was validated at the time of fetch (warm_up_cache).
        # Read directly from cache to avoid calling fetch_folder_data while holding lock.
        with _cache_lock:
            if (cached := _cache.get(url)) is not None:
                return cached

        if validate_folder_url(url):
            # Use sys.modules[__name__] so tests can monkeypatch sync.fetch_folder_data.
            return sys.modules[__name__].fetch_folder_data(url)
        return None

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_url = {
            executor.submit(_fetch_if_valid, url): url for url in folder_urls
        }

        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                result = future.result()
                if result:
                    folder_data_list.append(result)
            except (httpx.HTTPError, KeyError, ValueError) as e:
                log.error(
                    f"Failed to fetch folder data from {sanitize_for_log(url)}: {sanitize_for_log(e)}"
                )
                continue

    if not folder_data_list:
        log.error("No valid folder data found")
        hint_message = (
            "💡 Hint: Check your --folder-url flags or your config file "
            "(see --config, config.yaml, or config.yml) for typos or unreachable URLs"
        )
        if USE_COLORS:
            log.warning(f"{Colors.DIM}{hint_message}{Colors.ENDC}")
        else:
            log.warning(hint_message)
        return None

    return folder_data_list


def _build_plan_entry(profile_id: str, folder_data_list: list[FolderData]) -> PlanEntry:
    """Builds the plan entry for a given profile."""
    plan_entry: PlanEntry = {"profile": profile_id, "folders": []}
    for folder_data in folder_data_list:
        grp = folder_data["group"]
        name = grp["group"].strip()

        if "rule_groups" in folder_data:
            # Multi-action format
            # OPTIMIZATION: C-speed list comprehension avoids Python loop overhead, benchmarking ~20% faster than sum(generator)
            total_rules = sum(
                [len(rg.get("rules", [])) for rg in folder_data["rule_groups"]]
            )
            plan_entry["folders"].append(
                {
                    "name": name,
                    "rules": total_rules,
                    "rule_groups": [
                        {
                            "rules": len(rg.get("rules", [])),
                            "action": rg.get("action", {}).get("do"),
                            "status": rg.get("action", {}).get("status"),
                        }
                        for rg in folder_data["rule_groups"]
                    ],
                }
            )
        else:
            # Legacy single-action format
            # OPTIMIZATION: C-speed list comprehension avoids Python loop overhead, benchmarking ~20% faster than sum(generator)
            rules_count = len([1 for r in folder_data.get("rules", []) if r.get("PK")])
            plan_entry["folders"].append(
                {
                    "name": name,
                    "rules": rules_count,
                    "action": grp.get("action", {}).get("do"),
                    "status": grp.get("action", {}).get("status"),
                }
            )
    return plan_entry


def _prepare_folders_and_rules(
    client: httpx.Client,
    profile_id: str,
    folder_data_list: list[FolderData],
    no_delete: bool,
    shared_executor: concurrent.futures.ThreadPoolExecutor,
) -> tuple[dict[str, str] | None, set[str]]:
    """
    Verifies access, deletes old folders, and fetches existing rules in background.
    """
    # Verify access and list existing folders in one request
    existing_folders = verify_access_and_get_folders(client, profile_id)
    if existing_folders is None:
        return None, set()

    # Identify folders to delete and folders to keep (scan)
    folders_to_delete = []
    folders_to_scan = existing_folders.copy()

    if not no_delete:
        for folder_data in folder_data_list:
            name = folder_data["group"]["group"].strip()
            if name in existing_folders:
                folders_to_delete.append((name, existing_folders[name]))
                # OPTIMIZATION: Use dict.pop() to avoid a redundant dictionary lookup.
                folders_to_scan.pop(name, None)

    # Start fetching rules from kept folders in background (parallel to deletions)
    existing_rules_future = shared_executor.submit(
        get_all_existing_rules, client, profile_id, folders_to_scan
    )

    if not no_delete:
        deletion_occurred = False
        if folders_to_delete:
            # Parallel delete to speed up the "clean slate" phase
            # Use shared_executor (3 workers)
            future_to_name = {
                shared_executor.submit(
                    delete_folder, client, profile_id, name, folder_id
                ): name
                for name, folder_id in folders_to_delete
            }

            for future in concurrent.futures.as_completed(future_to_name):
                name = future_to_name[future]
                try:
                    if future.result():
                        del existing_folders[name]
                        deletion_occurred = True
                except Exception as exc:
                    # Sanitize both name and exception to prevent log injection
                    log.error(
                        "Failed to delete folder %s: %s",
                        sanitize_for_log(name),
                        sanitize_for_log(exc),
                    )

        # CRITICAL FIX: Increased wait time for massive folders to clear
        if deletion_occurred:
            if not USE_COLORS:
                log.info(
                    "Waiting 60s for deletions to propagate (prevents 'Badware Hoster' zombie state)..."
                )
            countdown_timer(60, "Waiting for deletions to propagate")

    # Retrieve result from background task
    # If deletion occurred, we effectively used the wait time to fetch rules!
    try:
        existing_rules = existing_rules_future.result()
    except Exception as e:
        log.error(
            f"Failed to fetch existing rules in background: {sanitize_for_log(e)}"
        )
        existing_rules = set()

    return existing_folders, existing_rules


def sync_profile(
    profile_id: str,
    folder_urls: Sequence[str],
    token: str,
    dry_run: bool = False,
    no_delete: bool = False,
    plan_accumulator: list[PlanEntry] | None = None,
) -> bool:
    """
    Synchronizes Control D folders from remote blocklist URLs.

    Fetches folder data, optionally deletes existing folders with same names,
    creates new folders, and pushes rules in batches. In dry-run mode, only
    generates a plan without making API changes. Returns True if all folders
    sync successfully.
    """
    # SECURITY: Clear cached DNS validations at the start of each sync run.
    # This prevents TOCTOU issues where a domain's IP could change between runs.
    validate_folder_url.cache_clear()
    validate_hostname.cache_clear()

    try:
        folder_data_list = _fetch_all_folder_data(folder_urls)
        if folder_data_list is None:
            return False

        # Build plan entries
        plan_entry = _build_plan_entry(profile_id, folder_data_list)

        if plan_accumulator is not None:
            plan_accumulator.append(plan_entry)

        if dry_run:
            print_plan_details(plan_entry)
            log.info("Dry-run complete: no API calls were made.")
            return True

        # Create new folders and push rules
        success_count = 0

        # CRITICAL FIX: Switch to Serial Processing (1 worker)
        # This prevents API rate limits and ensures stability for large folders.
        max_workers = 1

        # Shared executor for rate-limited operations (DELETE, push_rules batches)
        # Reusing this executor prevents thread churn and enforces global rate limits.
        with (
            concurrent.futures.ThreadPoolExecutor(
                max_workers=config.DELETE_WORKERS
            ) as shared_executor,
            create_client(token) as client,
        ):
            existing_folders_and_rules = _prepare_folders_and_rules(
                client, profile_id, folder_data_list, no_delete, shared_executor
            )
            if existing_folders_and_rules[0] is None:
                return False
            existing_folders, existing_rules = existing_folders_and_rules

            ctx = SyncContext(
                profile_id=profile_id,
                client=client,
                existing_rules=existing_rules,
                batch_executor=shared_executor,
            )

            with concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers
            ) as executor:
                future_to_folder = {
                    executor.submit(
                        _process_single_folder,
                        ctx,
                        folder_data,
                    ): folder_data
                    for folder_data in folder_data_list
                }

                for future in concurrent.futures.as_completed(future_to_folder):
                    folder_data = future_to_folder[future]
                    folder_name = folder_data["group"]["group"].strip()
                    try:
                        if future.result():
                            success_count += 1
                    except Exception as e:
                        log.error(
                            f"Failed to process folder '{sanitize_for_log(folder_name)}': {sanitize_for_log(e)}"
                        )

        log.info(
            f"Sync complete: {success_count}/{len(folder_data_list)} {pluralize(len(folder_data_list), 'folder')} processed successfully"
        )
        return success_count == len(folder_data_list)

    except Exception as e:
        log.error(
            f"Unexpected error during sync for profile {profile_id}: {sanitize_for_log(e)}"
        )
        return False


__all__ = [
    "create_client",
    "sync_profile",
    "push_rules",
    "get_all_existing_rules",
    "check_api_access",
    "list_existing_folders",
    "verify_access_and_get_folders",
    "delete_folder",
    "create_folder",
]
