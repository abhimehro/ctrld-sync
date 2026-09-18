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

<!-- gitnexus:start -->

# GitNexus — Code Intelligence

This project is indexed by GitNexus as **ctrld-sync** (1503 symbols, 2943
relationships, 114 execution flows).

> Index stale? Run `node .gitnexus/run.cjs analyze --index-only` from the
> project root — it auto-selects an available runner. No `.gitnexus/run.cjs`
> yet? Bootstrap with `npx`, `bunx`, or `pnpm dlx` — e.g.
> `bunx gitnexus@latest analyze` (npm 11 npx crash; #1939).

## Always Do

- **MUST run impact before editing.** Use
  `impact({target: "symbolName", direction: "upstream"})` or
  `node .gitnexus/run.cjs impact "symbolName" --direction upstream --repo .`;
  report callers, processes, and risk. Never substitute grep for graph analysis.
- **MUST analyze graph changes before committing.** Use
  `detect_changes({scope: "all"})` (MCP) or
  `node .gitnexus/run.cjs detect-changes --scope all --repo .` (CLI fallback).
  `partial: true` or `truncated: true` is not a clean check — a zero means
  unseen, not unaffected; re-run it. For regression review:
  `detect_changes({scope: "compare", base_ref: "main"})` or
  `node .gitnexus/run.cjs detect-changes --scope compare --base-ref "main" --repo .`.
- MUST warn on HIGH/CRITICAL `risk` pre-edit; never use `riskSharedAxes` to
  waive a HIGH/CRITICAL `risk` warning. Compare File/symbol: MCP File omits
  axes; Graph-RAG expands File.
- **MUST treat `risk: UNKNOWN` as unresolved, not as low.** An empty caller set
  is not evidence the symbol is unused — it can also mean the callers are not
  resolvable by the index (plain-object property access, dynamic dispatch,
  cross-language calls). `impact` pairs `UNKNOWN` with a `riskNote` saying so.
  Confirm with a text search before treating the symbol as safe to change or
  delete; do not proceed on the strength of a zero.
- **MUST use `query({search_query: "concept"})` for concepts/flows,
  `context({name: "symbolName"})` for a named symbol, or `impact` for blast
  radius, on read-only callers, dependencies, imports, or execution flow.**
  Graph first; text search only for empty/`UNKNOWN`/literals.
- For security review, `explain({target: "fileOrSymbol"})` lists taint findings
  (source→sink flows; needs `analyze --pdg`).

## Never Do

- NEVER edit a function, class, or method before MCP/CLI impact analysis.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis, and never
  read `UNKNOWN` as an all-clear — it means the walk could not answer, which is
  the one verdict that requires confirming by other means.
- NEVER rename symbols with find-and-replace — use `rename` which understands
  the call graph.
- NEVER commit before MCP/CLI graph change analysis.

## Resources

| Resource                                    | Use for                                  |
| ------------------------------------------- | ---------------------------------------- |
| `gitnexus://repo/ctrld-sync/context`        | Codebase overview, check index freshness |
| `gitnexus://repo/ctrld-sync/clusters`       | All functional areas                     |
| `gitnexus://repo/ctrld-sync/processes`      | All execution flows                      |
| `gitnexus://repo/ctrld-sync/process/{name}` | Step-by-step execution trace             |

## CLI

| Task                                         | Read this skill file                               |
| -------------------------------------------- | -------------------------------------------------- |
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus-exploring/SKILL.md`       |
| Blast radius / "What breaks if I change X?"  | `.claude/skills/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?"             | `.claude/skills/gitnexus-debugging/SKILL.md`       |
| Rename / extract / split / refactor          | `.claude/skills/gitnexus-refactoring/SKILL.md`     |
| Tools, resources, schema reference           | `.claude/skills/gitnexus-guide/SKILL.md`           |
| Index, status, clean, wiki CLI commands      | `.claude/skills/gitnexus-cli/SKILL.md`             |
| Work in the Tests area (227 symbols)         | `.claude/skills/gitnexus-area-tests/SKILL.md`      |
| Work in the Display area (59 symbols)        | `.claude/skills/gitnexus-area-display/SKILL.md`    |
| Work in the Sync area (37 symbols)           | `.claude/skills/gitnexus-area-sync/SKILL.md`       |
| Work in the Cluster_30 area (30 symbols)     | `.claude/skills/gitnexus-area-cluster-30/SKILL.md` |
| Work in the Cluster_7 area (8 symbols)       | `.claude/skills/gitnexus-area-cluster-7/SKILL.md`  |
| Work in the Cluster_2 area (6 symbols)       | `.claude/skills/gitnexus-area-cluster-2/SKILL.md`  |
| Work in the Cluster_15 area (6 symbols)      | `.claude/skills/gitnexus-area-cluster-15/SKILL.md` |
| Work in the Cluster_5 area (4 symbols)       | `.claude/skills/gitnexus-area-cluster-5/SKILL.md`  |
| Work in the Cluster_20 area (4 symbols)      | `.claude/skills/gitnexus-area-cluster-20/SKILL.md` |
| Work in the Cluster_52 area (4 symbols)      | `.claude/skills/gitnexus-area-cluster-52/SKILL.md` |
| Work in the Cluster_53 area (4 symbols)      | `.claude/skills/gitnexus-area-cluster-53/SKILL.md` |
| Work in the Cluster_3 area (3 symbols)       | `.claude/skills/gitnexus-area-cluster-3/SKILL.md`  |

<!-- gitnexus:end -->
