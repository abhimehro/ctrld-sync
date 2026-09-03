# AGENTS.md

## Cursor Cloud specific instructions

### Project overview

Python CLI tool that syncs Control D DNS folders with remote JSON block-lists
via the Control D REST API. The codebase is split into focused modules;
`main.py` is only the CLI/bootstrap/wiring entry point. No frontend or database.
Docker is optional (`Dockerfile` / `docker-compose.yml`); local CLI use does not
require it.

### Runtime

- Requires **Python >= 3.13** (uses modern language features). The VM's system
  Python is 3.12; `uv python install 3.13` provides the right version and
  `uv sync` picks it up automatically via `requires-python` in `pyproject.toml`.
- Trunk's Python runtime may be newer than 3.13 (lint-only). App, CI, and mypy
  stay on 3.13 — do not treat a Trunk interpreter bump as an app upgrade.
- Package manager: **uv** (`uv sync --all-extras` installs runtime + dev deps
  into `.venv`).

### Common commands

| Task                       | Command                                                            |
| -------------------------- | ------------------------------------------------------------------ |
| Install/update deps        | `uv sync --all-extras`                                             |
| Run linter                 | `ruff check .` (install via `uv tool install ruff` if not on PATH) |
| Run all tests              | `uv run pytest tests/ test_main.py -v`                             |
| Run specific test file     | `uv run pytest tests/test_fix_env.py -v`                           |
| Run app (dry-run)          | `uv run python main.py --dry-run`                                  |
| Run app (live)             | `TOKEN=xxx PROFILE=yyy uv run python main.py`                      |
| Install pre-commit hooks   | `uv run pre-commit install`                                        |
| Run pre-commit (all files) | `uv run pre-commit run --all-files`                                |

### Current status

All modules compile cleanly
(`uv run python -m compileall -q main.py models.py
validation.py config.py display/ gh_client.py sync/ api_client.py cache.py
fix_env.py`).
The full test suite is `uv run pytest tests/ test_main.py -v`.

`main.py` is now only CLI/bootstrap/wiring; helpers live in `models.py`,
`validation.py`, `config.py`, `display/`, `gh_client.py`, and `sync/`.

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
