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
   ```

2. **Install dependencies**
   
   Choose one of the following methods:
   
   **Using pip (recommended for CI/production):**
   ```bash
   pip install -r requirements.txt
   ```
   
   **Using uv (faster for local development):**
   ```bash
   uv sync
   ```
   
   Both methods are fully supported. Our main sync CI workflow uses `pip` for consistency with caching, while other workflows use `uv`; `uv` is generally faster for local development.

3. **Configure secrets**
   Create a `.env` file (or set GitHub secrets) with:
   ```py
   TOKEN=your_control_d_api_token
   PROFILE=your_profile_id  # or comma-separated list of profile ids (e.g. your_id_1,your_id_2)
   ```
   For GitHub Actions, set `TOKEN` and `PROFILE` secrets to the raw values (not the full `TOKEN=...` / `PROFILE=...` lines).

4. **Configure Folders**
   
   You can configure which folders to sync using a YAML configuration file instead of editing `main.py`:
   
   ```bash
   cp config.yaml.example config.yaml
   # Edit config.yaml to add, remove, or change folder URLs
   ```
   
   **Configuration file locations** (checked in order):
   1. `--config FILE` CLI flag
   2. `config.yaml` or `config.yml` in the current directory
   3. `~/.ctrld-sync/config.yaml` or `~/.ctrld-sync/config.yml`
   4. Built-in defaults (the `DEFAULT_FOLDER_URLS` list in `main.py`)
   
   **Example `config.yaml`:**
   ```yaml
   folders:
     - name: "Native Tracker – Amazon"
       url: "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/native-tracker-amazon-folder.json"
       action: "block"
   
     - name: "Apple Private Relay – Allow"
       url: "https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/apple-private-relay-allow-folder.json"
       action: "allow"
   
   settings:
     batch_size: 500
     delete_workers: 3
     max_retries: 10
   ```
   
   - `name` and `action` are optional labels; the actual folder name and rule action come from the remote JSON file.
   - All `url` values must use `https://`.
   - `action` must be `"block"` or `"allow"` when provided.
   
   Alternatively, you can still pass folder URLs directly on the command line (these override any config file):
   ```bash
   python main.py --folder-url https://example.com/my-blocklist.json
   ```
   
   Or point to a specific config file:
   ```bash
   python main.py --config /path/to/my-config.yaml
   ```
   
   The script includes 23 default folder URLs from [hagezi's dns-blocklists](https://github.com/hagezi/dns-blocklists) covering:
   - Native tracker blocking (Amazon, Apple, Samsung, etc.)
   - Badware and spam protection
   - Allow lists for common services

> [!NOTE]
> Currently only Folders with one action are supported.
> Either "Block" or "Allow" actions are supported.

5. **Run locally**
   ```bash
   python main.py --dry-run            # plan only, no API calls
   python main.py --profiles your_id   # live run (requires TOKEN)
   ```

6. **Run in CI**
   The included GitHub Actions workflow (`.github/workflows/sync.yml`) runs the sync script daily at 02:00 UTC and can also be triggered manually via workflow dispatch.

### Configure GitHub Actions

1. Fork this repo.
2. Go to the "Actions" Tab and enable actions.
3. Go to the Repo Settings.
4. Under "Secrets and variables > Actions" create the following secrets like above, under "Repository secrets":
   - `TOKEN`: your Control D API token
   - `PROFILE`: your Control D profile ID(s)

## Requirements
- Python 3.13+
- Runtime dependencies (install with `pip install -r requirements.txt` or `uv sync`):
  - `httpx` – HTTP client
  - `python-dotenv` – `.env` file support
  - `pyyaml` – YAML configuration file support

## Testing

This project includes a comprehensive test suite to ensure code quality and correctness.

### Running Tests

**Basic test execution:**
```bash
# Install dev dependencies first
pip install pytest pytest-mock pytest-xdist

# Run all tests
pytest tests/
```

**Parallel test execution (recommended):**
```bash
# Run tests in parallel using all available CPU cores
pytest tests/ -n auto

# Run with specific number of workers
pytest tests/ -n 4
```

**Note on parallel execution:** The test suite is currently small (~78 tests, <1s execution time), so parallel execution overhead may result in longer wall-clock time compared to sequential execution. However, pytest-xdist is included for:
- **Test isolation verification** - Ensures tests don't share state
- **Future scalability** - As the test suite grows, parallel execution will provide significant speedups
- **CI optimization** - May benefit from parallelization in CI environments with different characteristics

### Development Workflow

For active development with frequent test runs:
```bash
# Run tests sequentially (faster for small test suites)
pytest tests/ -v

# Run specific test file
pytest tests/test_security.py -v

# Run tests matching pattern
pytest tests/ -k "test_validation" -v
```

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

## CI/CD & Dependency Caching

### How Caching Works

The GitHub Actions workflows use automatic dependency caching to speed up CI runs:

- **Cache Key**: Includes the SHA-256 hash of `requirements.txt` along with the runner OS, Python version, and other factors (managed by `actions/setup-python@v5`)
- **Cache Location**: `~/.cache/pip` (managed by `actions/setup-python@v5`)
- **Invalidation**: Automatic when `requirements.txt` changes, or when environment details like Python version or runner OS change (per `actions/setup-python` caching behavior)

### Expected Performance

- **First run** (cold cache): ~30-40 seconds for dependency installation
- **Subsequent runs** (warm cache): ~5-10 seconds for cache restoration
- **Cache hit rate**: Expected >80% for typical PR/commit workflows

### Maintaining Dependencies

**Important**: `requirements.txt` must stay synchronized with `pyproject.toml`

When updating dependencies:

1. **Update `pyproject.toml`**
   ```toml
   [project]
   dependencies = [
       "httpx>=0.28.1",
       "python-dotenv>=1.1.1",
   ]
   ```

2. **Update `requirements.txt`** (manual sync required)
   ```bash
   # Extract runtime dependencies from pyproject.toml
   python3 -c "
   import sys
   try:
       import tomllib  # Python 3.11+
   except ModuleNotFoundError:
       try:
           import tomli as tomllib  # Fallback for older Python versions (requires 'tomli' package)
       except ModuleNotFoundError:
           sys.stderr.write('Error: No TOML parser available. Install the \"tomli\" package for Python <3.11.\n')
           sys.exit(1)
   
   with open('pyproject.toml', 'rb') as f:
       data = tomllib.load(f)
   
   deps = data.get('project', {}).get('dependencies') or []
   for dep in deps:
       print(dep)
   " > requirements.txt.tmp
   
   # Add header and move into place
   cat > requirements.txt << 'EOF'
# Runtime dependencies - manually synchronized with pyproject.toml
# This file is maintained for CI caching purposes only
# Source of truth: pyproject.toml [project.dependencies]
EOF
   cat requirements.txt.tmp >> requirements.txt
   rm requirements.txt.tmp
   ```

3. **Verify locally**
   ```bash
   pip install -r requirements.txt
   python main.py --help  # Smoke test
   ```

### Why requirements.txt?

The project uses a flat layout (scripts in root directory), which doesn't support `pip install -e .` without additional configuration. Using `requirements.txt` for CI is a minimal-change approach that:

- ✅ Enables effective pip caching via `actions/setup-python@v5`
- ✅ Provides explicit cache key for reproducible builds
- ✅ Maintains simplicity (no src/ layout migration required)
- ✅ Keeps `pyproject.toml` as single source of truth for version declarations

### Cache Debugging

If you suspect cache issues:

1. **Check cache hit/miss** in workflow logs:
   ```
   Run actions/setup-python@v5
   Cache restored successfully: true
   ```

2. **Manually clear cache** (if needed):
   - Go to Actions → Caches
   - Delete relevant pip cache entries
   - Re-run workflow to rebuild cache

3. **Verify dependencies match**:
   ```bash
   # Compare runtime dependencies (excluding dev dependencies)
   # This checks that requirements.txt matches pyproject.toml
   python3 -c "
   import tomllib
   
   # Parse pyproject.toml dependencies using a real TOML parser
   with open('pyproject.toml', 'rb') as f:
       data = tomllib.load(f)
   project = data.get('project', {})
   deps = project.get('dependencies', []) or []
   deps = [d.strip() for d in deps if isinstance(d, str) and d.strip()]
   
   # Parse requirements.txt (skip comments)
   with open('requirements.txt') as f:
       reqs = [line.strip() for line in f if line.strip() and not line.startswith('#')]
   
   # Compare
   deps_set = set(deps)
   reqs_set = set(reqs)
   if deps_set == reqs_set:
       print('✓ Dependencies match')
   else:
       print('✗ Dependencies mismatch!')
       print(f'  In pyproject.toml only: {deps_set - reqs_set}')
       print(f'  In requirements.txt only: {reqs_set - deps_set}')
   "
   ```
