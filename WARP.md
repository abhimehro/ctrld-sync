# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview
Control D Sync is a single-file Python tool (`main.py`) that keeps one or more Control D profiles' Folders in sync with a set of remote JSON blocklists (primarily from hagezi/dns-blocklists plus a small number of curated extras). For each profile it:
1. Downloads and validates the configured JSON folder definitions.
2. Plans the changes (including rule counts per folder) and optionally writes a `plan.json` file.
3. Optionally deletes any existing folders with matching names.
4. Recreates folders and pushes rules in batches (with duplicate-rule filtering) while printing a colored summary table.

## Development & Run Commands

Use `uv` for local dependency management (Python 3.13+ is required).

```bash
# Install dependencies (local dev)
uv sync

# Dry-run against default blocklists (no TOKEN required)
uv run python main.py --dry-run

# Dry-run and inspect the computed plan
uv run python main.py \
  --dry-run \
  --plan-json plan.json

# Live sync a single profile using env vars (recommended)
# TOKEN / PROFILE can come from .env or the environment
TOKEN=your_api_token PROFILE=your_profile_id \
  uv run python main.py

# Live sync multiple profiles (comma-separated PROFILE or --profiles)
TOKEN=your_api_token PROFILE="id1,id2" \
  uv run python main.py
# or
TOKEN=your_api_token \
  uv run python main.py --profiles "id1,id2"

# Override the default blocklists with explicit JSON URLs
uv run python main.py \
  --dry-run \
  --folder-url https://example.com/folder-a.json \
  --folder-url https://example.com/folder-b.json

# Skip deletion of existing folders (only add new rules)
TOKEN=your_api_token PROFILE=your_profile_id \
  uv run python main.py --no-delete
```

Notes:
- `--dry-run` never hits the Control D API; it only fetches and validates the remote JSON and builds the plan/summary.
- When run in a TTY without `TOKEN` / `PROFILE`, `main()` will interactively prompt for missing values (unless `--dry-run` is set).

## Configuration & Environment

Secrets can be provided via a `.env` file (loaded automatically by `python-dotenv`) or through real environment variables:
- `TOKEN` – Control D API token (from the "Preferences > API" page).
- `PROFILE` – Single profile ID or a comma-separated list of profile IDs.

`_clean_env_kv()` allows both raw values and `KEY=value` style strings. This means `PROFILE` or `TOKEN` may accidentally be set as `PROFILE=abc123`; the helper strips the `KEY=` prefix so both forms work. This is especially relevant for GitHub Actions and `.env` files.

Folder sources are controlled by:
- `DEFAULT_FOLDER_URLS` – The built-in list of HTTPS JSON folder definitions (primarily Hagezi Control D folders plus a few curated extras).
- `--folder-url` – One or more CLI overrides; when provided, these replace `DEFAULT_FOLDER_URLS` for that run.

Safety/validation helpers:
- `validate_folder_url()` – Enforces HTTPS, rejects localhost/private IPs, and ensures URLs are structurally sound before fetching.
- `validate_folder_data()` – Ensures each JSON payload has a `group.group` folder name and basic structure before it is used.
- `validate_profile_id()` – Guards against obviously malformed or dangerous profile IDs.

## High-Level Architecture (`main.py`)

The entire tool lives in `main.py` and is structured into clear phases:

1. **Bootstrap & logging**
   - Loads `.env` with `load_dotenv()`.
   - Configures color-aware logging via `ColoredFormatter` and a `log` logger.
   - Defines a `Colors` helper class that disables ANSI codes when not attached to a TTY.

2. **Configuration & constants**
   - `API_BASE` – Base URL for Control D API operations.
   - `DEFAULT_FOLDER_URLS` – Default set of remote JSON folder definitions.
   - Tunables such as `BATCH_SIZE`, `MAX_RETRIES`, `RETRY_DELAY`, `FOLDER_CREATION_DELAY`, and `MAX_RESPONSE_SIZE` control batching, retry behavior, and size limits.

3. **HTTP clients & low-level helpers**
   - `_api_client()` – Creates an authenticated `httpx.Client` for talking to Control D, with bearer-token auth from `TOKEN`.
   - `_gh` – Long-lived `httpx.Client` for fetching remote JSON over HTTPS.
   - `_retry_request()` – Wraps Control D API calls with exponential backoff and debug logging on failure.
   - `_gh_get()` – Streams remote JSON responses with strict size checks (`MAX_RESPONSE_SIZE`), then parses and memoizes them in `_cache`.
   - `sanitize_for_log()` – Redacts `TOKEN` values from any log messages.

4. **Control D API helpers**
   - `verify_access_and_get_folders()` – Combines the API access check and fetching existing folders into a single request. Returns `{folder_name -> folder_id}` on success.
   - `list_existing_folders()` – Helper that returns a `{folder_name -> folder_id}` mapping (used as fallback).
   - `get_all_existing_rules()` – Collects all existing rule PKs from both the root and each folder, using a `ThreadPoolExecutor` to parallelize per-folder fetches while accumulating into a shared `set` guarded by a lock.
   - `delete_folder()` – Deletes a folder by ID with error-logged failures.
   - `create_folder()` – Creates a folder and tries to read its ID directly from the response; if that fails, it polls `GET /groups` with increasing waits (using `FOLDER_CREATION_DELAY`) until the new folder appears.
   - `push_rules()` – Sends hostname rules in batches (`BATCH_SIZE`) to `POST /rules`, de-duplicating against the global `existing_rules` set and updating it as batches succeed.

5. **Folder data processing**
   - `fetch_folder_data()` – Fetches and validates a single folder JSON document.
   - `warm_up_cache()` – Pre-fetches and caches folder JSON definitions in parallel, so subsequent parsing is cheap.
   - `_process_single_folder()` – Given one parsed folder JSON, it:
     - Determines the main folder attributes (name, default action/status).
     - Creates the folder via `create_folder()`.
     - Handles either legacy single-action JSON (flat `rules`) or the newer multi-action `rule_groups` format, dispatching batched `push_rules()` calls for each group.

6. **Per-profile orchestration (`sync_profile`)**
   - For one `profile_id` and a list of folder URLs, it:
     1. Validates URLs and fetches all folder JSON documents in parallel.
     2. Builds a `plan_entry` summarizing folder names, rule counts, and per-action breakdown (for `rule_groups`), appending it to the shared `plan_accumulator`.
     3. If `dry_run=True`, stops here after logging a summary message.
     4. Otherwise, reuses a single `_api_client()` instance to:
        - Verify access and list existing folders in one request (`verify_access_and_get_folders`).
        - Optionally delete existing folders with matching names (`--no-delete` skips this step).
        - If any deletions occurred, waits ~60 seconds (`countdown_timer`) to let Control D fully process the removals.
        - Build the global `existing_rules` set.
        - Sequentially process each folder (executor with `max_workers=1` to avoid rate-limit and ordering issues), calling `_process_single_folder()` for each.
     5. Returns a boolean indicating whether all folders for that profile were processed successfully.

7. **CLI & entry point (`main`)**
   - `parse_args()` defines the public CLI surface:
     - `--profiles` – Comma-separated profile IDs.
     - `--folder-url` – One or more custom folder JSON URLs.
     - `--dry-run` – Plan only, no Control D API calls.
     - `--no-delete` – Do not delete existing folders before pushing new rules.
     - `--plan-json` – Path to write the aggregated plan as JSON.
   - `main()` resolves `TOKEN` and `PROFILE` from CLI and environment (`_clean_env_kv` aware), optionally prompts interactively, then loops over each profile to:
     - Call `sync_profile()`.
     - Track per-profile stats (folders, rules, duration, status).
     - Handle `KeyboardInterrupt` by marking the current profile as cancelled but still printing a summary.
   - At the end, it optionally writes `plan.json` (or a custom path from `--plan-json`) and prints a colorized summary table with per-profile and total aggregates before exiting with a non-zero status if any profile failed.

There is currently no dedicated test suite or linter configuration in this repository; if you add one (e.g. `pytest`, `ruff`), prefer to keep commands and configuration in sync with `pyproject.toml` and update this file accordingly.

## Control D API Surface

All Control D interactions are scoped under `API_BASE = "https://api.controld.com/profiles"` with bearer-token authentication. The tool uses these endpoints:
- `GET /{profile_id}/groups` – List folders for a profile.
- `DELETE /{profile_id}/groups/{folder_id}` – Delete a specific folder.
- `POST /{profile_id}/groups` – Create a folder.
- `GET /{profile_id}/rules` and `GET /{profile_id}/rules/{folder_id}` – Discover existing rules to avoid duplicates.
- `POST /{profile_id}/rules` – Create rules in batches via form-encoded fields (`hostnames[0]`, `hostnames[1]`, ...).

## Adding or Changing Blocklists

Folder definitions are expected to be JSON documents with at least:
- `group.group` – The folder name as it will appear in Control D.
- Either a flat `rules` array (`rules[].PK` hostnames) or a `rule_groups` array, where each group contains its own `rules` and optional `action`/`status`.

To change what gets synced:
- Edit `DEFAULT_FOLDER_URLS` in `main.py` to adjust the built-in set of remote JSON definitions; or
- Pass one or more `--folder-url` arguments on the CLI for ad-hoc runs without modifying the code.

## CI/CD

GitHub Actions workflow: `.github/workflows/sync.yml`
- Triggers:
  - Scheduled run daily at `02:00 UTC`.
  - Manual run via `workflow_dispatch`.
- Job:
  - Checks out the repo and sets up Python 3.13.
  - Installs `httpx` and `python-dotenv` with `pip`.
  - Runs `python main.py` with:
    - `TOKEN` – Provided via `secrets.TOKEN`.
    - `PROFILE` – Provided via `secrets.PROFILE` (can be a comma-separated list for multiple profiles).

The workflow uses the same CLI and environment semantics as local runs; if you change `main.py`'s arguments or environment handling, keep this workflow in sync.
