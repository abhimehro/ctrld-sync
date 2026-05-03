---
name: testing-ctrld-sync
description: Test the ctrld-sync Python CLI end-to-end. Use when verifying dry-run behavior, folder URL validation, SSRF defenses, or cache-related sync changes.
---

# Testing ctrld-sync

ctrld-sync is a Python CLI (`main.py`) with no frontend. Prefer shell/exec evidence over browser screenshots or recordings unless a future UI is added.

## Devin Secrets Needed

- `TOKEN`: Control D API token. Required only for live sync runs.
- `PROFILE`: Control D profile ID. Required only for live sync runs.

Dry-run and mocked unit/regression tests do not need secrets and should be preferred for security-sensitive validation.

## Setup

1. Work from the repo root.
2. If dependencies are missing, run `uv sync --all-extras`.
3. Use `NO_COLOR=1` for test commands when capturing terminal evidence.

## Core Commands

- Run the CLI dry-run path: `NO_COLOR=1 uv run python main.py --dry-run`
- Run with an explicit folder URL: `NO_COLOR=1 uv run python main.py --dry-run --folder-url https://example.com/folder.json`
- Run all tests: `uv run pytest tests/ -v`
- Run focused SSRF tests: `uv run pytest tests/test_ssrf.py tests/test_ssrf_enhanced.py tests/test_ssrf_link_local.py tests/test_ssrf_loopback.py -q`
- Lint: `uv run ruff check .`
- Typecheck: `uv run mypy .`

## SSRF / URL Validation Testing

For URL validation changes, include at least one user-facing CLI dry-run assertion and one focused runtime/unit assertion.

Useful dry-run literal IP check:

```bash
NO_COLOR=1 uv run python main.py --dry-run --folder-url https://10.0.0.1/config.json
```

Expected behavior for reserved or unsafe IPs:

- Logs include `Skipping unsafe IP` or `Skipping unsafe hostname`.
- Dry-run summary reports `Failed (Dry)` / `Errors`.
- Process exits non-zero.

For DNS cache or TOCTOU-sensitive changes, use a small Python harness that imports `main`, clears validation caches before the scenario starts, patches `socket.getaddrinfo`, and calls `sync_profile(..., dry_run=True)` more than once without clearing caches between calls. If the branch claims to clear both URL and hostname validation caches at sync start, assert DNS is re-read on later sync runs and unsafe DNS results are rejected. If the current production code only clears the URL cache, record the stale-hostname-cache result as a bug candidate instead of treating it as a passing test.

## Reporting

- Do not record an idle desktop for shell-only CLI tests.
- Save command output under a persistent artifact directory such as `~/test-artifacts/`.
- Include limits clearly, especially when live `TOKEN`/`PROFILE` secrets are unavailable and tests use dry-run/mocked runtime paths instead of live API mutation.
- When testing a PR, post one concise PR comment with runtime assertions and attach or link command-output evidence.
