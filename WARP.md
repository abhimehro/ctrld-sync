# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview
Control D Sync - A Python script that synchronizes Control D DNS folders with remote blocklists from GitHub (primarily from hagezi/dns-blocklists). The script:
1. Downloads JSON blocklists from configured URLs
2. Deletes existing folders with matching names
3. Recreates folders and pushes rules in batches (500 rules/batch)

## Development Commands

```bash
# Install dependencies
uv sync

# Run the sync script
uv run python main.py

# Run with explicit env vars (for testing)
TOKEN=xxx PROFILE=yyy uv run python main.py
```

## Required Environment Variables
Configure in `.env` (copy from `.env.example`):
- `TOKEN` - Control D API token (from Preferences > API)
- `PROFILE` - Profile ID(s), comma-separated for multiple profiles

## Architecture
Single-file application (`main.py`) with these key components:

1. **HTTP Clients** (lines 82-91)
   - `_api` - Authenticated Control D API client
   - `_gh` - GitHub raw content client (with in-memory caching)

2. **API Helpers** (lines 100-144)
   - Retry logic with exponential backoff (`MAX_RETRIES=3`)
   - `_api_get`, `_api_delete`, `_api_post`, `_api_post_form`

3. **Core Functions**
   - `list_existing_folders()` - Get folder-name → folder-id mapping
   - `get_all_existing_rules()` - Collect all rule PKs to prevent duplicates
   - `create_folder()` / `delete_folder()` - Folder CRUD with 2s creation delay
   - `push_rules()` - Batch upload with duplicate filtering

4. **Entry Point**
   - `sync_profile()` - Full sync workflow per profile
   - `main()` - Iterates over all profile IDs

## Control D API
- Base URL: `https://api.controld.com/profiles`
- Auth: Bearer token in Authorization header
- Key endpoints:
  - `GET /profiles/{id}/groups` - List folders
  - `DELETE /profiles/{id}/groups/{folder_id}` - Delete folder
  - `POST /profiles/{id}/groups` - Create folder
  - `POST /profiles/{id}/rules` - Create rules (form-urlencoded)

## Adding New Blocklists
Edit `FOLDER_URLS` list in `main.py` (lines 47-71). JSON format must include:
- `group.group` - Folder name
- `group.action.do` - Action type (block/allow)
- `group.action.status` - Status flag
- `rules[].PK` - Hostname entries

## CI/CD
GitHub Actions workflow (`.github/workflows/sync.yml`):
- Runs daily at 02:00 UTC
- Manual trigger via `workflow_dispatch`
- Requires `TOKEN` and `PROFILE` repository secrets
