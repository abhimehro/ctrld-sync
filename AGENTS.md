# AGENTS.md

## Cursor Cloud specific instructions

### Project overview

Single-file Python CLI tool (`main.py`) that syncs Control D DNS folders with remote JSON block-lists via the Control D REST API. No frontend, no database, no Docker required.

### Runtime

- Requires **Python >= 3.13** (uses modern language features). The VM's system Python is 3.12; `uv python install 3.13` provides the right version and `uv sync` picks it up automatically via `requires-python` in `pyproject.toml`.
- Package manager: **uv** (`uv sync --all-extras` installs runtime + dev deps into `.venv`).

### Common commands

| Task | Command |
|---|---|
| Install/update deps | `uv sync --all-extras` |
| Run linter | `ruff check .` (install via `uv tool install ruff` if not on PATH) |
| Run all tests | `uv run pytest tests/ -v` |
| Run specific test file | `uv run pytest tests/test_fix_env.py -v` |
| Run app (dry-run) | `uv run python main.py --dry-run` |
| Run app (live) | `TOKEN=xxx PROFILE=yyy uv run python main.py` |

### Known issue (as of main branch)

`main.py` has a **pre-existing syntax error at line 1141** (corrupted text: `rgi"rules"1` instead of `rg["rules"]`, plus broken indentation and Unicode characters in nearby f-strings). This blocks:
- Importing the `main` module (and therefore 20 of 22 tests)
- Running `python main.py` at all

Only `tests/test_fix_env.py` (2 tests) currently passes because it imports `fix_env` instead of `main`. This is a codebase bug, not an environment issue.

### Secrets for live runs

A live sync run requires `TOKEN` (Control D API token) and `PROFILE` (profile ID) as environment variables or in a `.env` file. All tests use mocks and do not need these secrets.
