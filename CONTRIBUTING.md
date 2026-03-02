# Contributing to ctrld-sync

Thank you for your interest in contributing! This guide covers everything you need to get started.

## Prerequisites

- **Python ≥ 3.13** — the project uses modern language features not available in earlier versions.
  ```bash
  uv python install 3.13   # install via uv if your system Python is older
  ```
- **[uv](https://github.com/astral-sh/uv)** — the project's package manager.
  ```bash
  pip install uv            # or follow the official uv installation guide
  ```

## Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/abhimehro/ctrld-sync.git
   cd ctrld-sync
   ```

2. **Install all dependencies** (runtime + dev extras)
   ```bash
   uv sync --all-extras
   ```
   This creates a `.venv` in the project root and installs everything declared in `pyproject.toml`.

3. **Configure secrets** — copy the example env file and fill in your values:
   ```bash
   cp .env.example .env
   # Edit .env and set TOKEN and PROFILE
   ```
   See the [Secrets](#secrets) section below for details.

## Running Tests

```bash
uv run pytest tests/ -v
```

Run a specific test file:
```bash
uv run pytest tests/test_fix_env.py -v
```

Run tests matching a pattern:
```bash
uv run pytest tests/ -k "test_validation" -v
```

All tests use mocks — no live API credentials are required.

## Running the Linter

```bash
uv tool install ruff   # install once if ruff is not already on your PATH
ruff check .
```

Or run through uv without a global install:
```bash
uv run ruff check .
```

## Running Pre-commit Hooks

Install the hooks once:
```bash
uv run pre-commit install
```

Run against all files manually:
```bash
uv run pre-commit run --all-files
```

The pre-commit configuration (`.pre-commit-config.yaml`) runs ruff (lint + format), trailing-whitespace, end-of-file-fixer, YAML check, and merge-conflict check.

## Dry-run Mode

Verify your changes without making any live API calls:
```bash
uv run python main.py --dry-run
```

## Submitting a Pull Request

1. **Branch naming** — use a short, descriptive name:
   - `fix/<short-description>` for bug fixes
   - `feat/<short-description>` for new features
   - `docs/<short-description>` for documentation changes
   - `chore/<short-description>` for maintenance tasks

2. **Before opening a PR**
   - Run the full test suite: `uv run pytest tests/ -v`
   - Run the linter: `ruff check .`
   - Run pre-commit: `uv run pre-commit run --all-files`

3. **PR description** — include:
   - A summary of what changed and why
   - How to test or verify the change
   - Any relevant issue numbers (e.g., `Closes #123`)

## Secrets

`TOKEN` (Control D API token) and `PROFILE` (profile ID) are required only for live runs against the API.

- **Never commit these values to source control.**
- Store them in a `.env` file at the project root (this file is listed in `.gitignore`):
  ```
  TOKEN=your_control_d_api_token
  PROFILE=your_profile_id
  ```
- For GitHub Actions, add them as repository secrets under **Settings → Secrets and variables → Actions**.

## Getting Help

If you run into problems, open a [GitHub Discussion](https://github.com/abhimehro/ctrld-sync/discussions) or check the existing [issues](https://github.com/abhimehro/ctrld-sync/issues).
