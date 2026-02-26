# AGENTS.md

## Cursor Cloud specific instructions

### Overview

This is **ctrld-sync**, a single-file Python CLI tool (`main.py`) that syncs Control D DNS folders with remote block-lists via the Control D API. No external services (databases, caches, Docker) are needed.

### Prerequisites

- **Python 3.13+** (required by `pyproject.toml`). The VM update script installs `uv`, which manages the Python version automatically.
- **uv** is the preferred package manager (`uv.lock` present). Run `uv sync --all-extras` to install runtime + dev deps.

### Common commands

- **Install deps**: `uv sync --all-extras`
- **Run tests**: `uv run pytest tests/ -v`
- **Lint (ruff)**: `ruff check .` and `ruff format --check .` (ruff is installed as a uv tool, not a project dep)
- **Run app**: `uv run python main.py --help` / `uv run python main.py --dry-run`
- **Run benchmark**: `uv run python benchmark_retry_jitter.py`

### Known issues

- **Pre-existing syntax error in `main.py` line 1141**: `for j, rule in enumerate (rgi"rules"1):` is corrupted code. This exists on the `main` branch as well and prevents `import main` from working, which blocks most tests and the CLI itself. Only `tests/test_fix_env.py` (which imports `fix_env` instead) passes.

### Environment variables

For live runs (not `--dry-run`), set `TOKEN` and `PROFILE` in a `.env` file (see `.env.example`). These are Control D API credentials and are **not** needed for running tests or `--dry-run`.

### Trunk

The project uses Trunk for linting (`.trunk/trunk.yaml`) with ruff, bandit, black, isort, etc. Trunk actions (pre-commit/pre-push) are disabled in the config.
