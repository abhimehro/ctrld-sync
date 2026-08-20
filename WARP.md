# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this
repository.

## Project Overview

Control D Sync is a Python CLI tool that keeps one or more Control D profiles'
Folders in sync with a set of remote JSON blocklists (primarily from
hagezi/dns-blocklists plus a small number of curated extras). The code is split
into focused modules; `main.py` is only the CLI/bootstrap/wiring entry point.
For each profile it:

1. Downloads and validates the configured JSON folder definitions.
2. Plans the changes (including rule counts per folder) and optionally writes a
   `plan.json` file.
3. Optionally deletes any existing folders with matching names.
4. Recreates folders and pushes rules in batches (with duplicate-rule filtering)
   while printing a colored summary table.

## Development & Run Commands

Use `uv` for local dependency management (Python 3.13+ is required).

```bash
# Install dependencies (local dev)
uv sync --all-extras

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

- `--dry-run` never hits the Control D API; it only fetches and validates the
  remote JSON and builds the plan/summary.
- When run in a TTY without `TOKEN` / `PROFILE`, `main()` will interactively
  prompt for missing values (unless `--dry-run` is set).

## Configuration & Environment

Secrets can be provided via a `.env` file (loaded automatically by
`python-dotenv`) or through real environment variables:

- `TOKEN` – Control D API token (from the "Preferences > API" page).
- `PROFILE` – Single profile ID or a comma-separated list of profile IDs.

`_clean_env_kv()` allows both raw values and `KEY=value` style strings. This
means `PROFILE` or `TOKEN` may accidentally be set as `PROFILE=abc123`; the
helper strips the `KEY=` prefix so both forms work. This is especially relevant
for GitHub Actions and `.env` files.

Folder sources are controlled by:

- `DEFAULT_FOLDER_URLS` – The built-in list of HTTPS JSON folder definitions
  (primarily Hagezi Control D folders plus a few curated extras).
- `--folder-url` – One or more CLI overrides; when provided, these replace
  `DEFAULT_FOLDER_URLS` for that run.

Safety/validation helpers:

- `validate_folder_url()` – Enforces HTTPS, rejects localhost/private IPs, and
  ensures URLs are structurally sound before fetching.
- `validate_folder_data()` – Ensures each JSON payload has a `group.group`
  folder name and basic structure before it is used.
- `validate_profile_id()` – Guards against obviously malformed or dangerous
  profile IDs.

## Module Map

| Module          | Purpose                                                                 | Key exports                                                                                                                                                                                          |
| --------------- | ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `main.py`       | CLI, argument parsing, environment bootstrap, and wiring                | `main()`, `parse_args()`, `run_main()`                                                                                                                                                               |
| `models.py`     | Pure data types (TypedDicts / dataclasses)                              | `RuleAction`, `SyncContext`, `FolderData`, `PlanEntry`, `SyncResult`                                                                                                                                 |
| `validation.py` | Sanitization, hostname/URL/profile/folder validators, allowlist helpers | `sanitize_for_log`, `validate_hostname`, `validate_folder_url`, `validate_profile_id`, `is_valid_rule`, `is_valid_folder_name`, `DEFAULT_ALLOWED_BLOCKLIST_DOMAINS`, `set_allowed_blocklist_domains` |
| `config.py`     | Defaults, config loading/validation, runtime constants                  | `DEFAULT_FOLDER_URLS`, `load_config`, `get_default_config`, `_resolve_folder_urls`, `_validate_config`, `BATCH_SIZE`, `MAX_RESPONSE_SIZE`                                                            |
| `display/`      | Colors, prompts, progress bars, tables, logging formatters              | `Colors`, `USE_COLORS`, `AlertSystem`, `JsonFormatter`, `ColoredFormatter`, `render_progress_bar`, `countdown_timer`, `print_summary_table`                                                          |
| `gh_client.py`  | `httpx` client for fetching blocklist JSON, in-memory cache             | `_gh_get`, `fetch_folder_data`, `warm_up_cache`                                                                                                                                                      |
| `sync/`         | Folder/rule orchestration package                                       | `sync_profile`, `create_client`, `push_rules`, `create_folder`, `delete_folder`, `verify_access_and_get_folders`                                                                                     |
| `api_client.py` | Low-level Control D API helpers (HTTP + retries)                        | `_api_get`, `_api_post`, `_api_post_form`, `_api_delete`, `_retry_request`, `retry_with_jitter`                                                                                                      |
| `cache.py`      | Persistent disk cache for blocklist JSON                                | `load_disk_cache`, `save_disk_cache`, `_disk_cache`                                                                                                                                                  |
| `fix_env.py`    | Legacy `.env` fix helper                                                | `fix_env`                                                                                                                                                                                            |

Dependencies between the new modules are one-way:

```text
models
^
validation <- config <- display
^         ^
gh_client <- sync <- main
^
api_client, cache
```

No helper module imports `main.py`.

## High-Level Architecture

`main()` drives the sync in phases:

1. **Bootstrap & logging**
   - Loads `.env` with `load_dotenv()`.
   - Configures color-aware logging via `display.ColoredFormatter` and the
     shared `control-d-sync` logger.
   - `display.Colors` / `USE_COLORS` disable ANSI codes when not attached to a
     TTY.

2. **Configuration & constants**
   - `config.API_BASE` – Base URL for Control D API operations.
   - `config.DEFAULT_FOLDER_URLS` – Default set of remote JSON folder
     definitions.
   - Tunables such as `BATCH_SIZE`, `MAX_RETRIES`, `RETRY_DELAY`,
     `FOLDER_CREATION_DELAY`, and `MAX_RESPONSE_SIZE` live in `config.py` and
     control batching, retry behavior, and size limits.

3. **HTTP clients & low-level helpers**
   - `sync.create_client(token)` – Creates an authenticated `httpx.Client` for
     talking to Control D, with bearer-token auth.
   - `gh_client._gh` – Long-lived `httpx.Client` for fetching remote JSON over
     HTTPS.
   - `api_client._retry_request()` – Wraps Control D API calls with exponential
     backoff and debug logging on failure.
   - `gh_client._gh_get()` – Streams remote JSON responses with strict size
     checks (`MAX_RESPONSE_SIZE`), then parses and memoizes them in
     `gh_client._cache`.
   - `validation.sanitize_for_log()` – Redacts `TOKEN` values from any log
     messages.

4. **Control D sync package (`sync/`)**
   - `sync.verify_access_and_get_folders()` – Combines the API access check and
     fetching existing folders into a single request. Returns
     `{folder_name -> folder_id}` on success.
   - `sync.list_existing_folders()` – Helper that returns a
     `{folder_name -> folder_id}` mapping (used as fallback).
   - `sync.get_all_existing_rules()` – Collects all existing rule PKs from both
     the root and each folder, using a `ThreadPoolExecutor` to parallelize
     per-folder fetches while accumulating into a shared `set` guarded by a
     lock.
   - `sync.delete_folder()` – Deletes a folder by ID with error-logged failures.
   - `sync.create_folder()` – Creates a folder and tries to read its ID directly
     from the response; if that fails, it polls `GET /groups` with increasing
     waits (using `FOLDER_CREATION_DELAY`) until the new folder appears. Uses
     `models.SyncContext` and `models.RuleAction`.
   - `sync.push_rules()` – Sends hostname rules in batches (`BATCH_SIZE`) to
     `POST /rules`, de-duplicating against the global `ctx.existing_rules` set
     and updating it as batches succeed. Uses `models.SyncContext` and
     `models.RuleAction`.

5. **Folder data processing (`gh_client.py`)**
   - `gh_client.fetch_folder_data()` – Fetches and validates a single folder
     JSON document.
   - `gh_client.warm_up_cache()` – Pre-fetches and caches folder JSON
     definitions in parallel, so subsequent parsing is cheap.
   - `sync._process_single_folder()` – Given one parsed folder JSON and a
     `models.SyncContext`, it:
     - Determines the main folder attributes (name, default action/status).
     - Creates the folder via `sync.create_folder()`.
     - Handles either legacy single-action JSON (flat `rules`) or the newer
       multi-action `rule_groups` format, dispatching batched
       `sync.push_rules()` calls for each group.

6. **Per-profile orchestration (`sync.sync_profile`)**
   - For one `profile_id` and a list of folder URLs, it:
     1. Validates URLs and fetches all folder JSON documents in parallel.
     2. Builds a `models.PlanEntry` summarizing folder names, rule counts, and
        per-action breakdown (for `rule_groups`), appending it to the shared
        `plan_accumulator`.
     3. If `dry_run=True`, stops here after logging a summary message.
     4. Otherwise, reuses a single `httpx.Client` to:
        - Verify access and list existing folders in one request
          (`sync.verify_access_and_get_folders`).
        - Optionally delete existing folders with matching names (`--no-delete`
          skips this step).
        - If any deletions occurred, waits ~60 seconds
          (`display.countdown_timer`) to let Control D fully process the
          removals.
        - Build the global `existing_rules` set.
        - Sequentially process each folder (executor with `max_workers=1` to
          avoid rate-limit and ordering issues), calling
          `sync._process_single_folder()` for each.
     5. Returns a boolean indicating whether all folders for that profile were
        processed successfully.

7. **CLI & entry point (`main.py`)**
   - `main.parse_args()` defines the public CLI surface:
     - `--profiles` – Comma-separated profile IDs.
     - `--folder-url` – One or more custom folder JSON URLs.
     - `--dry-run` – Plan only, no Control D API calls.
     - `--no-delete` – Do not delete existing folders before pushing new rules.
     - `--plan-json` – Path to write the aggregated plan as JSON.
   - `main()` resolves `TOKEN` and `PROFILE` from CLI and environment
     (`config._clean_env_kv` aware), optionally prompts interactively, then
     loops over each profile to:
     - Call `sync.sync_profile()`.
     - Track per-profile stats (folders, rules, duration, status).
     - Handle `KeyboardInterrupt` by marking the current profile as cancelled
       but still printing a summary.
   - At the end, it optionally writes `plan.json` (or a custom path from
     `--plan-json`) and prints a colorized summary table with per-profile and
     total aggregates before exiting with a non-zero status if any profile
     failed.

The test suite lives under `tests/` and `test_main.py` at the repo root. Keep
commands in sync with `pyproject.toml` and update this file when module
boundaries change.

## Control D API Surface

All Control D interactions are scoped under
`API_BASE = "https://api.controld.com/profiles"` with bearer-token
authentication. The tool uses these endpoints:

- `GET /{profile_id}/groups` – List folders for a profile.
- `DELETE /{profile_id}/groups/{folder_id}` – Delete a specific folder.
- `POST /{profile_id}/groups` – Create a folder.
- `GET /{profile_id}/rules` and `GET /{profile_id}/rules/{folder_id}` – Discover
  existing rules to avoid duplicates.
- `POST /{profile_id}/rules` – Create rules in batches via form-encoded fields
  (`hostnames[0]`, `hostnames[1]`, ...).

## Adding or Changing Blocklists

Folder definitions are expected to be JSON documents with at least:

- `group.group` – The folder name as it will appear in Control D.
- Either a flat `rules` array (`rules[].PK` hostnames) or a `rule_groups` array,
  where each group contains its own `rules` and optional `action`/`status`.

To change what gets synced:

- Edit `DEFAULT_FOLDER_URLS` in `main.py` to adjust the built-in set of remote
  JSON definitions; or
- Pass one or more `--folder-url` arguments on the CLI for ad-hoc runs without
  modifying the code.

## CI/CD

GitHub Actions workflow: `.github/workflows/sync.yml`

- Triggers:
  - Scheduled run daily at `02:00 UTC`.
  - Manual run via `workflow_dispatch`.
- Job:
  - Checks out the repo and sets up uv + Python 3.13.
  - Installs dependencies with `uv sync --all-extras` (from `pyproject.toml` /
    `uv.lock`).
  - Runs `uv run python main.py` with:
    - `TOKEN` – Provided via `secrets.TOKEN`.
    - `PROFILE` – Provided via `secrets.PROFILE` (can be a comma-separated list
      for multiple profiles).

The workflow uses the same CLI and environment semantics as local runs; if you
change `main.py`'s arguments or environment handling, keep this workflow in
sync.
