"""Grouplookupstate cluster."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum, auto

import api_client
import config
import httpx
import sync

from api_client import _CONNECT_ERROR_HINT, _TIMEOUT_HINT
from display import Colors
from models import RuleAction, SyncContext
from validation import sanitize_for_log, validate_folder_id


class _GroupLookupState(Enum):
    ABSENT = auto()
    INVALID = auto()
    VALID = auto()


@dataclass(frozen=True, slots=True)
class _GroupLookupResult:
    state: _GroupLookupState
    folder_id: str | None = None


def list_existing_folders(client: httpx.Client, profile_id: str) -> dict[str, str]:
    """
    Retrieves all existing folders (groups) for a given profile.

    Returns a dictionary mapping folder names to their IDs.
    Returns empty dict on error.
    """
    try:
        data = sync._api_get(client, f"{config.API_BASE}/{profile_id}/groups").json()
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
        sync.log.error(f"Failed to list existing folders{hint}: {sanitize_for_log(e)}")
        return {}


def _parse_folders_response(data: dict) -> dict[str, str] | None:
    """Parse folders response."""
    if not isinstance(data, dict):
        sync.log.error("Failed to parse folders data: response is not a JSON object")
        return None
    body = data.get("body")
    if not isinstance(body, dict):
        sync.log.error("Failed to parse folders data: 'body' is not a JSON object")
        return None
    folders = body.get("groups", [])
    if not isinstance(folders, list):
        sync.log.error("Failed to parse folders data: 'body[\"groups\"]' is not a list")
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
                    sync.log.critical(f"{Colors.FAIL}{line}{Colors.ENDC}")
                return None

            if attempt == api_client.MAX_RETRIES - 1:
                sync.log.error(f"API Request Failed ({code}): {sanitize_for_log(e)}")
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
                sync.log.error(
                    "Network error during access verification: %s%s",
                    sanitize_for_log(err),
                    hint,
                )
                return None

        wait_time = api_client.RETRY_DELAY * (2**attempt)
        sync.log.warning(
            "Request failed (attempt %d/%d). Retrying in %ds...",
            attempt + 1,
            api_client.MAX_RETRIES,
            wait_time,
        )
        time.sleep(wait_time)

    return None


def delete_folder(
    client: httpx.Client, profile_id: str, name: str, folder_id: str
) -> bool:
    """
    Deletes a folder (group) from a Control D profile.

    Returns True on success, False on failure. Logs detailed error information.
    """
    try:
        sync._api_delete(client, f"{config.API_BASE}/{profile_id}/groups/{folder_id}")
        sync.log.info(
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
        sync.log.error(
            f"Failed to delete folder {sanitize_for_log(name)} (ID {sanitize_for_log(folder_id)}){hint}: {sanitize_for_log(e)}"
        )
        return False


def _process_new_folder_pk(pk: str, name: str, source: str) -> str | None:
    if not validate_folder_id(pk, log_errors=False):
        sync.log.error(f"API returned invalid folder ID: {sanitize_for_log(pk)}")
        return None
    sync.log.info(
        "Created folder %s (ID %s) [%s]",
        sanitize_for_log(name),
        sanitize_for_log(pk),
        source,
    )
    return pk


def _find_folder_in_groups(
    groups: list, name: str, *, source: str, stop_on_invalid: bool
) -> _GroupLookupResult:
    for grp in groups:
        if not isinstance(grp, dict):
            continue
        if grp.get("group", "").strip() != name.strip():
            continue
        if "PK" in grp:
            pk = _process_new_folder_pk(str(grp["PK"]), name, source)
            if pk:
                return _GroupLookupResult(_GroupLookupState.VALID, pk)
            if stop_on_invalid:
                return _GroupLookupResult(_GroupLookupState.INVALID)
    return _GroupLookupResult(_GroupLookupState.ABSENT)


def _extract_from_groups_list(groups: list, name: str) -> str | None:
    """Extract folder ID from groups list."""
    result = _find_folder_in_groups(
        groups, name, source="Direct", stop_on_invalid=False
    )
    return result.folder_id if result.state is _GroupLookupState.VALID else None


def _extract_folder_id_from_response(response: httpx.Response, name: str) -> str | None:
    try:
        body = response.json().get("body")
    except Exception as e:
        if sync.log.isEnabledFor(logging.DEBUG):
            sync.log.debug(
                f"Could not extract ID from POST response: {sanitize_for_log(e)}"
            )
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
            result = _poll_folder_attempt(ctx, name)
        except Exception as e:
            sync.log.warning(
                f"Error fetching groups on attempt {attempt}: {sanitize_for_log(e)}"
            )
            result = _GroupLookupResult(_GroupLookupState.ABSENT)

        if result.state is _GroupLookupState.VALID:
            return result.folder_id
        if result.state is _GroupLookupState.INVALID:
            return None

        if attempt < api_client.MAX_RETRIES:
            wait_time = config.FOLDER_CREATION_DELAY * (attempt + 1)
            sync.countdown_timer(
                wait_time, f"Waiting for folder '{sanitize_for_log(name)}' to appear"
            )

    sync.log.error(
        f"Folder {sanitize_for_log(name)} was not found after creation and retries."
    )
    return None


def _poll_folder_attempt(ctx: SyncContext, name: str) -> _GroupLookupResult:
    """Fetch and inspect one folder-poll response."""
    data = sync._api_get(
        ctx.client, f"{config.API_BASE}/{ctx.profile_id}/groups"
    ).json()
    groups = data.get("body", {}).get("groups", [])
    return _find_folder_in_groups(groups, name, source="Polled", stop_on_invalid=True)


def create_folder(ctx: SyncContext, name: str, action: RuleAction) -> str | None:
    """
    Create a new folder and return its ID.
    Attempts to read ID from response first, then falls back to polling.
    """
    sync.log.info(f"Creating folder {sanitize_for_log(name)}")
    try:
        # 1. Send the Create Request
        response = sync._api_post(
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
        sync.log.error(
            f"Failed to create folder {sanitize_for_log(name)}{hint}: {sanitize_for_log(e)}"
        )
        return None
