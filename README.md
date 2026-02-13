# Control D Sync

[![Sync](https://github.com/abhimehro/ctrld-sync/actions/workflows/sync.yml/badge.svg)](https://github.com/abhimehro/ctrld-sync/actions/workflows/sync.yml)
[![Bandit](https://github.com/abhimehro/ctrld-sync/actions/workflows/bandit.yml/badge.svg)](https://github.com/abhimehro/ctrld-sync/actions/workflows/bandit.yml)
[![Codacy Security Scan](https://github.com/abhimehro/ctrld-sync/actions/workflows/codacy.yml/badge.svg)](https://github.com/abhimehro/ctrld-sync/actions/workflows/codacy.yml)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A tiny Python script that keeps your Control D Folders in sync with a set of
remote block-lists.

## What it does
1. Downloads the current JSON block-lists.
2. Deletes any existing folders with the same names.
3. Re-creates the folders and pushes all rules in batches.

## Quick start

### Obtain Control D API token

1. Log in to your Control D account.
2. Navigate to the "Preferences > API" section.
3. Click the "+" button to create a new API token.
4. Copy the token value.

### Obtain Control D profile ID

1. Log in to your Control D account.
2. Open the Profile you want to sync.
3. Copy the profile ID from the URL.
```
https://controld.com/dashboard/profiles/741861frakbm/filters
                                        ^^^^^^^^^^^^
```

### Configure the script

1. **Clone & install**
   ```bash
   git clone https://github.com/your-username/ctrld-sync.git
   cd ctrld-sync
   uv sync
   ```

2. **Configure secrets**
   Create a `.env` file (or set GitHub secrets) with:
   ```py
   TOKEN=your_control_d_api_token
   PROFILE=your_profile_id  # or comma-separated list of profile ids (e.g. your_id_1,your_id_2)
   ```
   For GitHub Actions, set `TOKEN` and `PROFILE` secrets to the raw values (not the full `TOKEN=...` / `PROFILE=...` lines).

3. **Configure Folders**
   Edit the `FOLDER_URLS` list in `main.py` to include the URLs of the JSON block-lists you want to sync.
   
   **Example configuration:**
   ```python
   DEFAULT_FOLDER_URLS = [
       # Allow lists
       "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/apple-private-relay-allow-folder.json",
       "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/microsoft-allow-folder.json",
       
       # Block lists
       "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/badware-hoster-folder.json",
       "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-amazon-folder.json",
       
       # Custom block lists
       "https://raw.githubusercontent.com/yokoffing/Control-D-Config/main/folders/potentially-malicious-ips.json",
   ]
   ```
   
   The script includes 23 default folder URLs from [hagezi's dns-blocklists](https://github.com/hagezi/dns-blocklists) covering:
   - Native tracker blocking (Amazon, Apple, Samsung, etc.)
   - Badware and spam protection
   - Allow lists for common services
   
   You can add your own JSON block-list URLs or use command-line arguments:
   ```bash
   uv run python main.py --folder-url https://example.com/my-blocklist.json
   ```

> [!NOTE]
> Currently only Folders with one action are supported.
> Either "Block" or "Allow" actions are supported.

4. **Run locally**
   ```bash
   uv run python main.py --dry-run            # plan only, no API calls
   uv run python main.py --profiles your_id   # live run (requires TOKEN)
   ```

5. **Run in CI**
The included GitHub Actions workflow (`.github/workflows/ci.yml`) runs a dry-run daily at 02:00 UTC and on PRs, writes `plan.json`, and uploads it as an artifact for review.

### Configure GitHub Actions

1. Fork this repo.
2. Go to the "Actions" Tab and enable actions.
3. Go to the Repo Settings.
4. Under "Secrets and variables > Actions" create the following secrets like above, under "Repository secrets":
   - `TOKEN`: your Control D API token
   - `PROFILE`: your Control D profile ID(s)

## Requirements
- Python 3.13+
- `uv` (for dependency management)

## Release Process

This project uses manual releases via GitHub Releases. To create a new release:

1. **Ensure all changes are tested and merged to `main`**
   ```bash
   # Verify tests pass
   pytest tests/
   
   # Verify security scans pass
   bandit -r main.py -ll
   ```

2. **Update version in `pyproject.toml`**
   ```toml
   [project]
   version = "0.2.0"  # Increment appropriately
   ```

3. **Create and push a version tag**
   ```bash
   git tag -a v0.2.0 -m "Release v0.2.0: Description of changes"
   git push origin v0.2.0
   ```

4. **Create GitHub Release**
   - Go to [Releases](https://github.com/abhimehro/ctrld-sync/releases)
   - Click "Draft a new release"
   - Select the tag you just created
   - Add release notes highlighting:
     - New features
     - Bug fixes
     - Breaking changes (if any)
     - Security updates
   - Publish the release

**Release Checklist:**
- [ ] All tests passing
- [ ] Security scans clean (Bandit, Codacy)
- [ ] Version updated in `pyproject.toml`
- [ ] Git tag created and pushed
- [ ] GitHub Release created with notes
- [ ] Release announcement (optional)
