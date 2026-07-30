# AGENTS.md

## Cursor Cloud specific instructions

### Project overview

Python CLI that syncs Control D DNS folders with remote JSON block-lists via the
Control D REST API. Core modules:

- `main.py` — CLI entrypoint and sync orchestration
- `api_client.py` — Control D REST client helpers
- `cache.py` — local cache helpers
- `fix_env.py` — `.env` / environment loading

Optional Docker packaging lives in `Dockerfile` / `docker-compose.yml` (not
required for local `uv` development). No frontend or database.

### Runtime

- Requires **Python >= 3.13** (uses modern language features). The VM's system
  Python is 3.12; `uv python install 3.13` provides the right version and
  `uv sync` picks it up automatically via `requires-python` in `pyproject.toml`.
- Package manager: **uv** (`uv sync --all-extras` installs runtime + dev deps
  into `.venv`).

### Common commands

| Task                       | Command                                                            |
| -------------------------- | ------------------------------------------------------------------ |
| Install/update deps        | `uv sync --all-extras`                                             |
| Run linter                 | `ruff check .` (install via `uv tool install ruff` if not on PATH) |
| Run all tests              | `uv run pytest -v`                                                 |
| Run package tests only     | `uv run pytest tests/ -v`                                          |
| Run specific test file     | `uv run pytest tests/test_fix_env.py -v`                           |
| Run app (dry-run)          | `uv run python main.py --dry-run`                                  |
| Run app (live)             | `TOKEN=xxx PROFILE=yyy uv run python main.py`                      |
| Install pre-commit hooks   | `uv run pre-commit install`                                        |
| Run pre-commit (all files) | `uv run pre-commit run --all-files`                                |

### Current status

`main.py` compiles cleanly when checked with the project interpreter
(`uv run python -m py_compile main.py`). Pytest `testpaths` cover `tests/` plus
root `test_main.py`. Prefer `uv run pytest -v` for the full suite.

### Secrets for live runs

A live sync run requires `TOKEN` (Control D API token) and `PROFILE` (profile
ID) as environment variables or in a `.env` file. All tests use mocks and do not
need these secrets.

### CodeScene review/salvage trigger

During automated PR review or salvage sessions, if CodeScene is red on a PR,
post:

```bash
/cs-agent skill:fix-code-health-degradations
```

Then wait for that run to complete before final defer/salvage disposition.
