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

import argparse
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Sequence, Set

import httpx
from dotenv import load_dotenv

# --------------------------------------------------------------------------- #
# 0. Bootstrap – load secrets and configure logging
# --------------------------------------------------------------------------- #
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("control-d-sync")

# --------------------------------------------------------------------------- #
# 1. Constants – tweak only here
# --------------------------------------------------------------------------- #
API_BASE = "https://api.controld.com/profiles"
TOKEN = os.getenv("TOKEN")

# Default folder sources
DEFAULT_FOLDER_URLS = [
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/apple-private-relay-allow-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/badware-hoster-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/meta-tracker-allow-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/microsoft-allow-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-amazon-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-apple-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-huawei-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-lgwebos-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-microsoft-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-oppo-realme-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-samsung-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-tiktok-aggressive-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-tiktok-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-vivo-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-xiaomi-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/nosafesearch-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/referral-allow-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/spam-idns-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/spam-tlds-allow-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/spam-tlds-combined-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/spam-tlds-folder.json",
    "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/ultimate-known_issues-allow-folder.json",
    "https://raw.githubusercontent.com/yokoffing/Control-D-Config/main/folders/potentially-malicious-ips.json",
]

BATCH_SIZE = 500
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds
FOLDER_CREATION_DELAY = 2  # seconds to wait after creating a folder
MAX_WORKERS = 10  # Parallel threads for fetching data

# --------------------------------------------------------------------------- #
# 2. Clients
# --------------------------------------------------------------------------- #
def _api_client() -> httpx.Client:
    """Lazily build Control D API client."""
    return httpx.Client(
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {TOKEN}",
        },
        timeout=30,
    )

# GitHub raw client (no auth, no headers) – single instance
_gh = httpx.Client(timeout=30)

# --------------------------------------------------------------------------- #
# 3. Helpers
# --------------------------------------------------------------------------- #
# simple in-memory cache: url -> decoded JSON
_cache: Dict[str, Dict] = {}


def _api_get(client: httpx.Client, url: str) -> httpx.Response:
    """GET helper for Control-D API with retries."""
    return _retry_request(lambda: client.get(url))


def _api_delete(client: httpx.Client, url: str) -> httpx.Response:
    """DELETE helper for Control-D API with retries."""
    return _retry_request(lambda: client.delete(url))


def _api_post(client: httpx.Client, url: str, data: Dict) -> httpx.Response:
    """POST helper for Control-D API with retries."""
    return _retry_request(lambda: client.post(url, data=data))


def _api_post_form(client: httpx.Client, url: str, data: Dict) -> httpx.Response:
    """POST helper for form data with retries."""
    return _retry_request(lambda: client.post(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}))


def _retry_request(request_func, max_retries=MAX_RETRIES, delay=RETRY_DELAY):
    """Retry a request function with exponential backoff."""
    for attempt in range(max_retries):
        try:
            response = request_func()
            response.raise_for_status()
            return response
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            if attempt == max_retries - 1:
                # Log the response content if available
                if hasattr(e, 'response') and e.response is not None:
                    log.error(f"Response content: {e.response.text}")
                raise
            wait_time = delay * (2 ** attempt)
            log.warning(f"Request failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time}s...")
            time.sleep(wait_time)


def _gh_get(url: str) -> Dict:
    """Fetch JSON from GitHub (cached)."""
    if url not in _cache:
        r = _gh.get(url)
        r.raise_for_status()
        _cache[url] = r.json()
    return _cache[url]


def list_existing_folders(client: httpx.Client, profile_id: str) -> Dict[str, str]:
    """Return folder-name -> folder-id mapping."""
    try:
        data = _api_get(client, f"{API_BASE}/{profile_id}/groups").json()
        folders = data.get("body", {}).get("groups", [])
        return {
            f["group"].strip(): f["PK"]
            for f in folders
            if f.get("group") and f.get("PK")
        }
    except (httpx.HTTPError, KeyError) as e:
        log.error(f"Failed to list existing folders: {e}")
        return {}


def get_all_existing_rules(client: httpx.Client, profile_id: str) -> Set[str]:
    """Get all existing rules from all folders in the profile."""
    all_rules = set()

    try:
        # Get rules from root folder (no folder_id)
        try:
            data = _api_get(client, f"{API_BASE}/{profile_id}/rules").json()
            root_rules = data.get("body", {}).get("rules", [])
            for rule in root_rules:
                if rule.get("PK"):
                    all_rules.add(rule["PK"])

            log.debug(f"Found {len(root_rules)} rules in root folder")

        except httpx.HTTPError as e:
            log.warning(f"Failed to get root folder rules: {e}")

        # Get all folders (including ones we're not managing)
        folders = list_existing_folders(client, profile_id)

        # Helper for parallel execution
        def fetch_folder_rules(item):
            folder_name, folder_id = item
            local_rules = set()
            try:
                data = _api_get(client, f"{API_BASE}/{profile_id}/rules/{folder_id}").json()
                folder_rules = data.get("body", {}).get("rules", [])
                for rule in folder_rules:
                    if rule.get("PK"):
                        local_rules.add(rule["PK"])

                log.debug(f"Found {len(folder_rules)} rules in folder '{folder_name}'")
                return local_rules
            except httpx.HTTPError as e:
                log.warning(f"Failed to get rules from folder '{folder_name}': {e}")
                return set()

        # Get rules from each folder in parallel
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # We map the fetch function over the items
            results = executor.map(fetch_folder_rules, folders.items())

            for rules in results:
                all_rules.update(rules)

        log.info(f"Total existing rules across all folders: {len(all_rules)}")
        return all_rules

    except Exception as e:
        log.error(f"Failed to get existing rules: {e}")
        return set()


def fetch_folder_data(url: str) -> Dict[str, Any]:
    """Return folder data from GitHub JSON."""
    js = _gh_get(url)
    return js


def delete_folder(client: httpx.Client, profile_id: str, name: str, folder_id: str) -> bool:
    """Delete a single folder by its ID. Returns True if successful."""
    try:
        _api_delete(client, f"{API_BASE}/{profile_id}/groups/{folder_id}")
        log.info("Deleted folder '%s' (ID %s)", name, folder_id)
        return True
    except httpx.HTTPError as e:
        log.error(f"Failed to delete folder '{name}' (ID {folder_id}): {e}")
        return False


def create_folder(client: httpx.Client, profile_id: str, name: str, do: int, status: int) -> Optional[str]:
    """
    Create a new folder and return its ID.
    The API returns the full list of groups, so we look for the one we just added.
    """
    try:
        _api_post(
            client,
            f"{API_BASE}/{profile_id}/groups",
            data={"name": name, "do": do, "status": status},
        )

        # Re-fetch the list and pick the folder we just created
        data = _api_get(client, f"{API_BASE}/{profile_id}/groups").json()
        for grp in data["body"]["groups"]:
            if grp["group"].strip() == name.strip():
                log.info("Created folder '%s' (ID %s)", name, grp["PK"])
                time.sleep(FOLDER_CREATION_DELAY)
                return str(grp["PK"])

        log.error(f"Folder '{name}' was not found after creation")
        return None
    except (httpx.HTTPError, KeyError) as e:
        log.error(f"Failed to create folder '{name}': {e}")
        return None


def push_rules(
    profile_id: str,
    folder_name: str,
    folder_id: str,
    do: int,
    status: int,
    hostnames: List[str],
    existing_rules: Set[str],
    client: httpx.Client,
) -> bool:
    """Push hostnames in batches to the given folder, skipping duplicates. Returns True if successful."""
    if not hostnames:
        log.info("Folder '%s' - no rules to push", folder_name)
        return True

    # Filter out duplicates
    original_count = len(hostnames)
    filtered_hostnames = [h for h in hostnames if h not in existing_rules]
    duplicates_count = original_count - len(filtered_hostnames)

    if duplicates_count > 0:
        log.info(f"Folder '{folder_name}': skipping {duplicates_count} duplicate rules")

    if not filtered_hostnames:
        log.info(f"Folder '{folder_name}' - no new rules to push after filtering duplicates")
        return True

    successful_batches = 0
    total_batches = len(range(0, len(filtered_hostnames), BATCH_SIZE))

    for i, start in enumerate(range(0, len(filtered_hostnames), BATCH_SIZE), 1):
        batch = filtered_hostnames[start : start + BATCH_SIZE]

        data = {
            "do": str(do),
            "status": str(status),
            "group": str(folder_id),
        }

        for j, hostname in enumerate(batch):
            data[f"hostnames[{j}]"] = hostname

        try:
            _api_post_form(
                client,
                f"{API_BASE}/{profile_id}/rules",
                data=data,
            )
            log.info(
                "Folder '%s' – batch %d: added %d rules",
                folder_name,
                i,
                len(batch),
            )
            successful_batches += 1

            # Update existing_rules set with the newly added rules
            existing_rules.update(batch)

        except httpx.HTTPError as e:
            log.error(f"Failed to push batch {i} for folder '{folder_name}': {e}")
            if hasattr(e, 'response') and e.response is not None:
                log.error(f"Response content: {e.response.text}")

    if successful_batches == total_batches:
        log.info("Folder '%s' – finished (%d new rules added)", folder_name, len(filtered_hostnames))
        return True
    else:
        log.error(f"Folder '%s' – only {successful_batches}/{total_batches} batches succeeded")
        return False


# --------------------------------------------------------------------------- #
# 4. Main workflow
# --------------------------------------------------------------------------- #
def sync_profile(
    profile_id: str,
    folder_urls: Sequence[str],
    dry_run: bool = False,
    no_delete: bool = False,
    plan_accumulator: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """One-shot sync: delete old, create new, push rules. Returns True if successful."""
    try:
        # Fetch all folder data first
        folder_data_list = []

        # Parallel fetch to speed up startup
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # We want to preserve order, although technically not strictly required,
            # it's good practice.
            futures = [executor.submit(fetch_folder_data, url) for url in folder_urls]

            for i, future in enumerate(futures):
                try:
                    folder_data_list.append(future.result())
                except Exception as e:
                    # Log which URL failed
                    log.error(f"Failed to fetch folder data from {folder_urls[i]}: {e}")
                    continue

        if not folder_data_list:
            log.error("No valid folder data found")
            return False

        # Build plan entries
        plan_entry = {"profile": profile_id, "folders": []}
        for folder_data in folder_data_list:
            grp = folder_data["group"]
            name = grp["group"].strip()
            hostnames = [r["PK"] for r in folder_data.get("rules", []) if r.get("PK")]
            plan_entry["folders"].append(
                {
                    "name": name,
                    "rules": len(hostnames),
                    "action": grp["action"].get("do"),
                    "status": grp["action"].get("status"),
                }
            )

        if plan_accumulator is not None:
            plan_accumulator.append(plan_entry)

        if dry_run:
            for folder_data in folder_data_list:
                grp = folder_data["group"]
                name = grp["group"].strip()
                hostnames = [r["PK"] for r in folder_data.get("rules", []) if r.get("PK")]
                log.info("DRY-RUN plan for '%s': action=%s status=%s rules=%d", name, grp["action"].get("do"), grp["action"].get("status"), len(hostnames))
            log.info("Dry-run complete: no API calls were made.")
            return True

        client = _api_client()

        # Get existing folders and delete target folders
        existing_folders = list_existing_folders(client, profile_id)
        if not no_delete:
            for folder_data in folder_data_list:
                name = folder_data["group"]["group"].strip()
                if name in existing_folders:
                    delete_folder(client, profile_id, name, existing_folders[name])

        # Get all existing rules AFTER deleting target folders
        existing_rules = get_all_existing_rules(client, profile_id)

        # Create new folders and push rules
        success_count = 0
        for folder_data in folder_data_list:
            grp = folder_data["group"]
            name = grp["group"].strip()
            do = grp["action"].get("do", 0)  # Default to 0 (block) if not specified
            status = grp["action"].get("status", 1)  # Default to 1 (enabled) if not specified
            hostnames = [r["PK"] for r in folder_data.get("rules", []) if r.get("PK")]

            folder_id = create_folder(client, profile_id, name, do, status)
            if folder_id and push_rules(profile_id, name, folder_id, do, status, hostnames, existing_rules, client):
                success_count += 1
                # Note: existing_rules is updated within push_rules function

        log.info(f"Sync complete: {success_count}/{len(folder_data_list)} folders processed successfully")
        return success_count == len(folder_data_list)

    except Exception as e:
        log.error(f"Unexpected error during sync for profile {profile_id}: {e}")
        return False


# --------------------------------------------------------------------------- #
# 5. Entry-point
# --------------------------------------------------------------------------- #
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Control D folder sync")
    parser.add_argument(
        "--profiles",
        help="Comma-separated list of profile IDs (overrides PROFILE env)",
        default=None,
    )
    parser.add_argument(
        "--folder-url",
        action="append",
        help="Folder JSON URL(s) to sync (can be used multiple times; overrides defaults)",
        default=None,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan only: fetch folder JSON and print intended actions; no API calls",
    )
    parser.add_argument(
        "--no-delete",
        action="store_true",
        help="Safety: do not delete existing folders; only add new/overwriting content",
    )
    parser.add_argument(
        "--plan-json",
        help="Write plan (per profile/folder/rule counts) to JSON file",
        default=None,
    )
    return parser.parse_args()


def main():
    args = parse_args()

    profiles_arg = args.profiles or os.getenv("PROFILE", "")
    profile_ids = [p.strip() for p in profiles_arg.split(",") if p.strip()]

    folder_urls = args.folder_url if args.folder_url else DEFAULT_FOLDER_URLS

    if not profile_ids and not args.dry_run:
        log.error("PROFILE missing and --dry-run not set. Provide --profiles or set PROFILE env.")
        exit(1)

    if not TOKEN and not args.dry_run:
        log.error("TOKEN missing and --dry-run not set. Set TOKEN env for live sync.")
        exit(1)

    plan: List[Dict[str, Any]] = []
    success_count = 0
    for profile_id in (profile_ids or ["dry-run-placeholder"]):
        log.info("Starting sync for profile %s", profile_id)
        if sync_profile(profile_id, folder_urls, dry_run=args.dry_run, no_delete=args.no_delete, plan_accumulator=plan):
            success_count += 1

    if args.plan_json:
        with open(args.plan_json, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)
        log.info("Plan written to %s", args.plan_json)

    total = len(profile_ids or ["dry-run-placeholder"])
    log.info(f"All profiles processed: {success_count}/{total} successful")
    exit(0 if success_count == total else 1)


if __name__ == "__main__":
    main()
