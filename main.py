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
import os
import logging
import sys
import time
import re
import concurrent.futures
import threading
from typing import Dict, List, Optional, Any, Set, Sequence

import httpx
from dotenv import load_dotenv

# --------------------------------------------------------------------------- #
# 0. Bootstrap – load secrets and configure logging
# --------------------------------------------------------------------------- #
load_dotenv()

# Determine if we should use colors
USE_COLORS = sys.stderr.isatty() and sys.stdout.isatty()

class Colors:
    if USE_COLORS:
        HEADER = '\033[95m'
        BLUE = '\033[94m'
        CYAN = '\033[96m'
        GREEN = '\033[92m'
        WARNING = '\033[93m'
        FAIL = '\033[91m'
        ENDC = '\033[0m'
        BOLD = '\033[1m'
        UNDERLINE = '\033[4m'
    else:
        HEADER = ''
        BLUE = ''
        CYAN = ''
        GREEN = ''
        WARNING = ''
        FAIL = ''
        ENDC = ''
        BOLD = ''
        UNDERLINE = ''

class ColoredFormatter(logging.Formatter):
    """Custom formatter to add colors to log levels."""
    LEVEL_COLORS = {
        logging.DEBUG: Colors.BLUE,
        logging.INFO: Colors.CYAN,
        logging.WARNING: Colors.WARNING,
        logging.ERROR: Colors.FAIL,
        logging.CRITICAL: Colors.FAIL + Colors.BOLD,
    }

    def __init__(self, fmt=None, datefmt=None, style='%', validate=True):
        super().__init__(fmt, datefmt, style, validate)
        self.delegate_formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S")

    def format(self, record):
        original_levelname = record.levelname
        color = self.LEVEL_COLORS.get(record.levelno, Colors.ENDC)
        padded_level = f"{original_levelname:<8}"
        record.levelname = f"{color}{padded_level}{Colors.ENDC}"
        result = self.delegate_formatter.format(record)
        record.levelname = original_levelname
        return result

# Setup logging
handler = logging.StreamHandler()
handler.setFormatter(ColoredFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("control-d-sync")

# --------------------------------------------------------------------------- #
# 1. Constants – tweak only here
# --------------------------------------------------------------------------- #
API_BASE = "https://api.controld.com/profiles"


def sanitize_for_log(text: Any) -> str:
    """Sanitize text for logging."""
    safe = repr(str(text))
    if len(safe) >= 2 and safe[0] == safe[-1] and safe[0] in ("'", '"'):
        return safe[1:-1]
    return safe


def _clean_env_kv(value: Optional[str], key: str) -> Optional[str]:
    """Allow TOKEN/PROFILE values to be provided as either raw values or KEY=value."""
    if not value:
        return value
    v = value.strip()
    m = re.match(rf"^{re.escape(key)}\s*=\s*(.+)$", v)
    if m:
        return m.group(1).strip()
    return v


TOKEN = _clean_env_kv(os.getenv("TOKEN"), "TOKEN")

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
MAX_RETRIES = 10
RETRY_DELAY = 1            
FOLDER_CREATION_DELAY = 5  # <--- CHANGED: Increased from 2 to 5 for patience

# --------------------------------------------------------------------------- #
# 2. Clients
# --------------------------------------------------------------------------- #
def _api_client() -> httpx.Client:
    return httpx.Client(
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {TOKEN}",
        },
        timeout=30,
    )

_gh = httpx.Client(timeout=30)
MAX_RESPONSE_SIZE = 10 * 1024 * 1024  # 10 MB limit for external resources

# --------------------------------------------------------------------------- #
# 3. Helpers
# --------------------------------------------------------------------------- #
_cache: Dict[str, Dict] = {}

def validate_folder_url(url: str) -> bool:
    if not url.startswith("https://"):
        log.warning(f"Skipping unsafe or invalid URL: {sanitize_for_log(url)}")
        return False
    return True

def validate_profile_id(profile_id: str) -> bool:
    if not re.match(r"^[a-zA-Z0-9_-]+$", profile_id):
        log.error("Invalid profile ID format (contains unsafe characters)")
        return False
    return True

def validate_folder_data(data: Dict[str, Any], url: str) -> bool:
    if not isinstance(data, dict):
        log.error(f"Invalid data from {sanitize_for_log(url)}: Root must be a JSON object.")
        return False
    if "group" not in data:
        log.error(f"Invalid data from {sanitize_for_log(url)}: Missing 'group' key.")
        return False
    if not isinstance(data["group"], dict):
        log.error(f"Invalid data from {sanitize_for_log(url)}: 'group' must be an object.")
        return False
    if "group" not in data["group"]:
        log.error(f"Invalid data from {sanitize_for_log(url)}: Missing 'group.group' (folder name).")
        return False
    return True

def _api_get(client: httpx.Client, url: str) -> httpx.Response:
    return _retry_request(lambda: client.get(url))

def _api_delete(client: httpx.Client, url: str) -> httpx.Response:
    return _retry_request(lambda: client.delete(url))

def _api_post(client: httpx.Client, url: str, data: Dict) -> httpx.Response:
    return _retry_request(lambda: client.post(url, data=data))

def _api_post_form(client: httpx.Client, url: str, data: Dict) -> httpx.Response:
    return _retry_request(lambda: client.post(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"}))

def _retry_request(request_func, max_retries=MAX_RETRIES, delay=RETRY_DELAY):
    for attempt in range(max_retries):
        try:
            response = request_func()
            response.raise_for_status()
            return response
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            if attempt == max_retries - 1:
                if hasattr(e, 'response') and e.response is not None:
                    log.debug(f"Response content: {e.response.text}")
                raise
            wait_time = delay * (2 ** attempt)
            log.warning(f"Request failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {wait_time}s...")
            time.sleep(wait_time)

def _gh_get(url: str) -> Dict:
    if url not in _cache:
        try:
            with _gh.stream("GET", url) as r:
                r.raise_for_status()

                # 1. Content-Length header check
                cl = r.headers.get("Content-Length")
                if cl and int(cl) > MAX_RESPONSE_SIZE:
                    raise ValueError(f"Response too large ({cl} bytes)")

                # 2. Streaming read with size check
                content_chunks = []
                total_size = 0
                for chunk in r.iter_bytes():
                    total_size += len(chunk)
                    if total_size > MAX_RESPONSE_SIZE:
                        raise ValueError(f"Response too large (> {MAX_RESPONSE_SIZE} bytes)")
                    content_chunks.append(chunk)

                full_content = b"".join(content_chunks)
                _cache[url] = json.loads(full_content)
        except ValueError as e:
            # Re-raise size errors or JSON errors
            raise ValueError(f"Failed to fetch {sanitize_for_log(url)}: {e}") from e
    return _cache[url]

def list_existing_folders(client: httpx.Client, profile_id: str) -> Dict[str, str]:
    try:
        data = _api_get(client, f"{API_BASE}/{profile_id}/groups").json()
        folders = data.get("body", {}).get("groups", [])
        return {
            f["group"].strip(): f["PK"]
            for f in folders
            if f.get("group") and f.get("PK")
        }
    except (httpx.HTTPError, KeyError) as e:
        log.error(f"Failed to list existing folders: {sanitize_for_log(e)}")
        return {}

def get_all_existing_rules(client: httpx.Client, profile_id: str) -> Set[str]:
    all_rules = set()
    try:
        # Get rules from root
        try:
            data = _api_get(client, f"{API_BASE}/{profile_id}/rules").json()
            root_rules = data.get("body", {}).get("rules", [])
            for rule in root_rules:
                if rule.get("PK"):
                    all_rules.add(rule["PK"])
        except httpx.HTTPError:
            pass

        # Get rules from folders
        folders = list_existing_folders(client, profile_id)
        for folder_name, folder_id in folders.items():
            try:
                data = _api_get(client, f"{API_BASE}/{profile_id}/rules/{folder_id}").json()
                folder_rules = data.get("body", {}).get("rules", [])
                for rule in folder_rules:
                    if rule.get("PK"):
                        all_rules.add(rule["PK"])
            except httpx.HTTPError:
                continue

        log.info(f"Total existing rules across all folders: {len(all_rules)}")
        return all_rules
    except Exception as e:
        log.error(f"Failed to get existing rules: {sanitize_for_log(e)}")
        return set()

def fetch_folder_data(url: str) -> Dict[str, Any]:
    js = _gh_get(url)
    if not validate_folder_data(js, url):
        raise KeyError(f"Invalid folder data from {sanitize_for_log(url)}")
    return js

def warm_up_cache(urls: Sequence[str]) -> None:
    urls = list(set(urls))
    urls_to_fetch = [u for u in urls if u not in _cache and validate_folder_url(u)]
    if not urls_to_fetch:
        return
    log.info(f"Warming up cache for {len(urls_to_fetch)} URLs...")
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(_gh_get, url): url for url in urls_to_fetch}
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as e:
                log.warning(f"Failed to pre-fetch {sanitize_for_log(futures[future])}: {e}")

def delete_folder(client: httpx.Client, profile_id: str, name: str, folder_id: str) -> bool:
    try:
        _api_delete(client, f"{API_BASE}/{profile_id}/groups/{folder_id}")
        log.info("Deleted folder %s (ID %s)", sanitize_for_log(name), folder_id)
        return True
    except httpx.HTTPError as e:
        log.error(f"Failed to delete folder {sanitize_for_log(name)} (ID {folder_id}): {sanitize_for_log(e)}")
        return False

def create_folder(client: httpx.Client, profile_id: str, name: str, do: int, status: int) -> Optional[str]:
    """
    Create a new folder and return its ID.
    Attempts to read ID from response first, then falls back to polling.
    """
    try:
        # 1. Send the Create Request
        response = _api_post(
            client,
            f"{API_BASE}/{profile_id}/groups",
            data={"name": name, "do": do, "status": status},
        )
        
        # OPTIMIZATION: Try to grab ID directly from response to avoid the wait loop
        try:
            resp_data = response.json()
            body = resp_data.get("body", {})
            
            # Check if it returned a single group object
            if isinstance(body, dict) and "group" in body and "PK" in body["group"]:
                 pk = body["group"]["PK"]
                 log.info("Created folder %s (ID %s) [Direct]", sanitize_for_log(name), pk)
                 return str(pk)
                 
            # Check if it returned a list containing our group
            if isinstance(body, dict) and "groups" in body:
                for grp in body["groups"]:
                    if grp.get("group") == name:
                        log.info("Created folder %s (ID %s) [Direct]", sanitize_for_log(name), grp["PK"])
                        return str(grp["PK"])
        except Exception as e:
            log.debug(f"Could not extract ID from POST response: {e}")

        # 2. Fallback: Poll for the new folder (The Robust Retry Logic)
        for attempt in range(MAX_RETRIES + 1):
            try:
                data = _api_get(client, f"{API_BASE}/{profile_id}/groups").json()
                groups = data.get("body", {}).get("groups", [])
                
                for grp in groups:
                    if grp["group"].strip() == name.strip():
                        log.info("Created folder %s (ID %s) [Polled]", sanitize_for_log(name), grp["PK"])
                        return str(grp["PK"])
            except Exception as e:
                log.warning(f"Error fetching groups on attempt {attempt}: {e}")

            if attempt < MAX_RETRIES:
                wait_time = FOLDER_CREATION_DELAY * (attempt + 1)
                log.info(f"Folder '{name}' not found yet. Retrying in {wait_time}s...")
                time.sleep(wait_time)

        log.error(f"Folder {sanitize_for_log(name)} was not found after creation and retries.")
        return None

    except (httpx.HTTPError, KeyError) as e:
        log.error(f"Failed to create folder {sanitize_for_log(name)}: {sanitize_for_log(e)}")
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
    existing_rules_lock: Optional[threading.Lock] = None,
) -> bool:
    if not hostnames:
        log.info("Folder %s - no rules to push", sanitize_for_log(folder_name))
        return True

    original_count = len(hostnames)

    if existing_rules_lock is not None:
        with existing_rules_lock:
            rules_snapshot = set(existing_rules)
    else:
        rules_snapshot = existing_rules

    filtered_hostnames = [h for h in hostnames if h not in rules_snapshot]
    duplicates_count = original_count - len(filtered_hostnames)

    if duplicates_count > 0:
        log.info(f"Folder {sanitize_for_log(folder_name)}: skipping {duplicates_count} duplicate rules")

    if not filtered_hostnames:
        log.info(f"Folder {sanitize_for_log(folder_name)} - no new rules to push after filtering duplicates")
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
            _api_post_form(client, f"{API_BASE}/{profile_id}/rules", data=data)
            log.info(
                "Folder %s – batch %d: added %d rules",
                sanitize_for_log(folder_name), i, len(batch)
            )
            successful_batches += 1
            if existing_rules_lock:
                with existing_rules_lock:
                    existing_rules.update(batch)
            else:
                existing_rules.update(batch)
        except httpx.HTTPError as e:
            log.error(f"Failed to push batch {i} for folder {sanitize_for_log(folder_name)}: {sanitize_for_log(e)}")
            if hasattr(e, 'response') and e.response is not None:
                log.debug(f"Response content: {e.response.text}")

    if successful_batches == total_batches:
        log.info("Folder %s – finished (%d new rules added)", sanitize_for_log(folder_name), len(filtered_hostnames))
        return True
    else:
        log.error("Folder %s – only %d/%d batches succeeded", sanitize_for_log(folder_name), successful_batches, total_batches)
        return False

def _process_single_folder(
    folder_data: Dict[str, Any],
    profile_id: str,
    existing_rules: Set[str],
    existing_rules_lock: threading.Lock,
    client: httpx.Client,
) -> bool:
    grp = folder_data["group"]
    name = grp["group"].strip()

    # Client is now passed in, reusing the connection
    main_do = grp.get("action", {}).get("do", 0)
    main_status = grp.get("action", {}).get("status", 1)

    folder_id = create_folder(client, profile_id, name, main_do, main_status)
    if not folder_id:
        return False

    folder_success = True
    if "rule_groups" in folder_data:
        for rule_group in folder_data["rule_groups"]:
            action = rule_group.get("action", {})
            do = action.get("do", 0)
            status = action.get("status", 1)
            hostnames = [r["PK"] for r in rule_group.get("rules", []) if r.get("PK")]
            if not push_rules(profile_id, name, folder_id, do, status, hostnames, existing_rules, client, existing_rules_lock):
                folder_success = False
    else:
        hostnames = [r["PK"] for r in folder_data.get("rules", []) if r.get("PK")]
        if not push_rules(profile_id, name, folder_id, main_do, main_status, hostnames, existing_rules, client, existing_rules_lock):
            folder_success = False

    return folder_success

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
    try:
        # Fetch all folder data first
        folder_data_list = []
        valid_urls = [url for url in folder_urls if validate_folder_url(url)]

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_url = {executor.submit(fetch_folder_data, url): url for url in valid_urls}

            for future in concurrent.futures.as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    folder_data_list.append(future.result())
                except (httpx.HTTPError, KeyError) as e:
                    log.error(f"Failed to fetch folder data from {sanitize_for_log(url)}: {sanitize_for_log(e)}")
                    continue

        if not folder_data_list:
            log.error("No valid folder data found")
            return False

        # Build plan entries
        plan_entry = {"profile": profile_id, "folders": []}
        for folder_data in folder_data_list:
            grp = folder_data["group"]
            name = grp["group"].strip()
            
            if "rule_groups" in folder_data:
                # Multi-action format
                total_rules = sum(len(rg.get("rules", [])) for rg in folder_data["rule_groups"])
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
                hostnames = [r["PK"] for r in folder_data.get("rules", []) if r.get("PK")]
                plan_entry["folders"].append(
                    {
                        "name": name,
                        "rules": len(hostnames),
                        "action": grp.get("action", {}).get("do"),
                        "status": grp.get("action", {}).get("status"),
                    }
                )

        if plan_accumulator is not None:
            plan_accumulator.append(plan_entry)

        if dry_run:
            log.info("Dry-run complete: no API calls were made.")
            return True

        # Create new folders and push rules
        success_count = 0
        existing_rules_lock = threading.Lock()

        # CRITICAL FIX: Switch to Serial Processing (1 worker)
        # This prevents API rate limits and ensures stability for large folders.
        max_workers = 1

        # Initial client for getting existing state AND processing folders
        # Optimization: Reuse the same client session to keep TCP connections alive
        with _api_client() as client:
            existing_folders = list_existing_folders(client, profile_id)
            if not no_delete:
                deletion_occurred = False
                for folder_data in folder_data_list:
                    name = folder_data["group"]["group"].strip()
                    if name in existing_folders:
                        delete_folder(client, profile_id, name, existing_folders[name])
                        deletion_occurred = True
                
                # CRITICAL FIX: Increased wait time for massive folders to clear
                if deletion_occurred:
                    log.info("Waiting 60s for deletions to propagate (prevents 'Badware Hoster' zombie state)...")
                    time.sleep(60)

            existing_rules = get_all_existing_rules(client, profile_id)

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_folder = {
                    executor.submit(
                        _process_single_folder,
                        folder_data,
                        profile_id,
                        existing_rules,
                        existing_rules_lock,
                        client  # Pass the persistent client
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
                        log.error(f"Failed to process folder '{folder_name}': {e}")

        log.info(f"Sync complete: {success_count}/{len(folder_data_list)} folders processed successfully")
        return success_count == len(folder_data_list)

    except Exception as e:
        log.error(f"Unexpected error during sync for profile {profile_id}: {sanitize_for_log(e)}")
        return False
        
# --------------------------------------------------------------------------- #
# 5. Entry-point
# --------------------------------------------------------------------------- #
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Control D folder sync")
    parser.add_argument("--profiles", help="Comma-separated list of profile IDs", default=None)
    parser.add_argument("--folder-url", action="append", help="Folder JSON URL(s)", default=None)
    parser.add_argument("--dry-run", action="store_true", help="Plan only")
    parser.add_argument("--no-delete", action="store_true", help="Do not delete existing folders")
    parser.add_argument("--plan-json", help="Write plan to JSON file", default=None)
    return parser.parse_args()

def main():
    args = parse_args()
    profiles_arg = _clean_env_kv(args.profiles or os.getenv("PROFILE", ""), "PROFILE") or ""
    profile_ids = [p.strip() for p in profiles_arg.split(",") if p.strip()]
    folder_urls = args.folder_url if args.folder_url else DEFAULT_FOLDER_URLS

    if not profile_ids and not args.dry_run:
        log.error("PROFILE missing and --dry-run not set. Provide --profiles or set PROFILE env.")
        exit(1)

    if not TOKEN and not args.dry_run:
        log.error("TOKEN missing and --dry-run not set. Set TOKEN env for live sync.")
        exit(1)

    warm_up_cache(folder_urls)

    plan: List[Dict[str, Any]] = []
    success_count = 0
    sync_results = []

    for profile_id in (profile_ids or ["dry-run-placeholder"]):
        start_time = time.time()
        # Skip validation for dry-run placeholder
        if profile_id != "dry-run-placeholder" and not validate_profile_id(profile_id):
            sync_results.append({
                "profile": profile_id,
                "folders": 0,
                "rules": 0,
                "status_label": "❌ Invalid Profile ID",
                "success": False,
                "duration": 0.0,
            })
            continue

        log.info("Starting sync for profile %s", profile_id)
        status = sync_profile(
            profile_id,
            folder_urls,
            dry_run=args.dry_run,
            no_delete=args.no_delete,
            plan_accumulator=plan,
        )
        end_time = time.time()
        duration = end_time - start_time

        if status:
            success_count += 1

        # RESTORED STATS LOGIC: Calculate actual counts from the plan
        entry = next((p for p in plan if p["profile"] == profile_id), None)
        folder_count = len(entry["folders"]) if entry else 0
        rule_count = sum(f["rules"] for f in entry["folders"]) if entry else 0

        if args.dry_run:
            status_text = "✅ Planned" if status else "❌ Failed (Dry)"
        else:
            status_text = "✅ Success" if status else "❌ Failed"

        sync_results.append({
            "profile": profile_id,
            "folders": folder_count,
            "rules": rule_count,
            "status_label": status_text,
            "success": status,
            "duration": duration,
        })

    if args.plan_json:
        with open(args.plan_json, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2)
        log.info("Plan written to %s", args.plan_json)

    # ... (The rest of your table printing logic in the screenshot looks correct) ...
    # You can keep the code from "Print Summary Table" downwards as it appears in your edit.
    
    # Just ensure you include the summary table printing code here if you haven't already!
    # (Based on your screenshot, you already have the correct table printing code below this point)
    
    # Print Summary Table
    # Determine the width for the Profile ID column (min 25)
    max_profile_len = max((len(r["profile"]) for r in sync_results), default=25)
    profile_col_width = max(25, max_profile_len)

    # Calculate total width for the table
    # Profile ID + " | " + Folders + " | " + Rules + " | " + Duration + " | " + Status
    # Widths: profile_col_width + 3 + 10 + 3 + 10 + 3 + 10 + 3 + 15 = profile_col_width + 57
    table_width = profile_col_width + 57

    title_text = "DRY RUN SUMMARY" if args.dry_run else "SYNC SUMMARY"
    title_color = Colors.CYAN if args.dry_run else Colors.HEADER

    print("\n" + "=" * table_width)
    print(f"{title_color}{title_text:^{table_width}}{Colors.ENDC}")
    print("=" * table_width)

    # Header
    print(
        f"{Colors.BOLD}"
        f"{'Profile ID':<{profile_col_width}} | {'Folders':>10} | {'Rules':>10} | {'Duration':>10} | {'Status':<15}"
        f"{Colors.ENDC}"
    )
    print("-" * table_width)

    # Rows
    total_folders = 0
    total_rules = 0
    total_duration = 0.0

    for res in sync_results:
        # Use boolean success field for color logic
        status_color = Colors.GREEN if res['success'] else Colors.FAIL

        print(
            f"{res['profile']:<{profile_col_width}} | "
            f"{res['folders']:>10} | "
            f"{res['rules']:>10,} | "
            f"{res['duration']:>9.1f}s | "
            f"{status_color}{res['status_label']:<15}{Colors.ENDC}"
        )
        total_folders += res['folders']
        total_rules += res['rules']
        total_duration += res['duration']

    print("-" * table_width)

    # Total Row
    total = len(profile_ids or ["dry-run-placeholder"])
    all_success = (success_count == total)

    if args.dry_run:
        if all_success:
            total_status_text = "✅ Ready"
        else:
            total_status_text = "❌ Errors"
    else:
        if all_success:
            total_status_text = "✅ All Good"
        else:
            total_status_text = "❌ Errors"

    total_status_color = Colors.GREEN if all_success else Colors.FAIL

    print(
        f"{Colors.BOLD}"
        f"{'TOTAL':<{profile_col_width}} | "
        f"{total_folders:>10} | "
        f"{total_rules:>10,} | "
        f"{total_duration:>9.1f}s | "
        f"{total_status_color}{total_status_text:<15}{Colors.ENDC}"
    )
    print("=" * table_width + "\n")

    total = len(profile_ids or ["dry-run-placeholder"])
    log.info(f"All profiles processed: {success_count}/{total} successful")
    exit(0 if success_count == total else 1)

if __name__ == "__main__":
    main()
