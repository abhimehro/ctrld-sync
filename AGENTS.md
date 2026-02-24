# AGENTS.md

## Project Overview

**ctrld-sync** is a Python CLI tool that syncs Control D DNS filtering folders
with remote block-lists. It downloads JSON block-lists, deletes existing folders
with matching names, recreates them, and pushes rules in batches to the
Control D API.

## Language & Runtime

- Python 3.13+
- Runtime dependencies: `httpx`, `python-dotenv`
- Dependency metadata lives in `pyproject.toml` (source of truth);
  `requirements.txt` is kept in sync for CI pip-caching.

## Repository Layout

```text
main.py                  # Single-file CLI application (~2900 lines)
fix_env.py               # Utility for .env file permission repair
pyproject.toml           # Project metadata & dependency declarations
requirements.txt         # Pinned runtime deps (mirrors pyproject.toml)
tests/                   # pytest test suite (27 test files)
.github/workflows/       # 18 GitHub Actions workflows
.trunk/                  # Trunk linter/formatter configuration
  configs/               # Per-tool config (ruff, isort, markdownlint, yamllint)
```

## Building & Running

No build step is required. Install dependencies and run directly:

```bash
pip install -r requirements.txt
python main.py --dry-run           # safe preview, no API calls
python main.py --profiles <id>     # live sync against Control D
```

The project also supports `uv sync` for local development.

## Testing

Tests use **pytest** with `pytest-mock`, `pytest-xdist`, and `pytest-benchmark`.

```bash
pytest tests/ -v              # run all tests
pytest tests/ -n auto         # parallel execution
pytest tests/ -k "security"  # run a subset by keyword
```

All test files live under `tests/` and follow the `test_*.py` naming convention.
Test categories include security (SSRF, CSV injection, log sanitization),
validation (folders, hostnames, IDs), performance regression, UX, and caching.

## Linting & Formatting

The project uses [Trunk](https://trunk.io) to orchestrate linters. Key tools:

| Tool          | Purpose                     |
|---------------|-----------------------------|
| ruff          | Python linting              |
| black         | Python formatting           |
| isort         | Import sorting (black profile) |
| bandit        | Security linting            |
| markdownlint  | Markdown linting            |
| yamllint      | YAML linting                |
| actionlint    | GitHub Actions linting      |
| prettier      | General formatting          |

Ruff is configured to select rule sets `B`, `D3`, `E`, `F` and ignore `E501`
(line length is left to the formatter). See `.trunk/configs/ruff.toml`.

## Coding Conventions

- **Formatting**: Black style. Imports sorted with isort (black profile).
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes,
  `UPPER_SNAKE_CASE` for module-level constants. Private helpers use a leading
  underscore (e.g. `_retry_request()`).
- **Type hints**: Use `typing` annotations on function signatures.
- **Error handling**: Wrap external calls in try/except, log errors, and degrade
  gracefully rather than crashing.
- **Security**: Validate all external inputs. Sanitize log output. Guard against
  SSRF. Check `.env` file permissions before loading secrets.
- **Constants**: Defined at module top-level (e.g. `MAX_RETRIES`, `BATCH_SIZE`).
- **Comments**: Explain *why*, not *what*. Do not add redundant narrative
  comments.

## CI / GitHub Actions

The primary workflow is `.github/workflows/sync.yml` (runs daily at 02:00 UTC).
Security scans (Bandit, Codacy) and performance regression tests run on push and
PR events. Workflows require `TOKEN` and `PROFILE` repository secrets.

## Environment Variables

| Variable  | Purpose                              |
|-----------|--------------------------------------|
| `TOKEN`   | Control D API token                  |
| `PROFILE` | Default Control D profile ID         |
| `NO_COLOR`| Disable colored terminal output      |

A `.env.example` template is provided. The real `.env` file is git-ignored.
