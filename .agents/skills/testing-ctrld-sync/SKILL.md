---
name: testing-ctrld-sync
description: Test the ctrld-sync Python CLI end-to-end. Use when verifying dry-run behavior, SSRF/URL validation, DNS cache safety, or Control D sync flows.
---

# Testing ctrld-sync

## App shape

- `ctrld-sync` is a single-file Python CLI app (`main.py`), not a browser UI.
- Prefer shell evidence over screen recordings unless a future task introduces an actual GUI.
- Use `uv` for all Python commands so the project interpreter and dependencies are selected correctly.

## Devin Secrets Needed

- No secrets are needed for dry-run validation, mocked network tests, unit tests, linting, or pre-commit.
- `TOKEN`: Control D API token. Required only for live sync runs.
- `PROFILE`: Control D profile ID. Required only for live sync runs.

## Baseline checks

Run these before reporting a code-change task as ready:

```bash
uv run pytest tests/ -v
uv run ruff check .
uv run mypy main.py
uv run pre-commit run --all-files
```

Check PR CI with the git PR checks tool after pushing code.

## Dry-run CLI smoke test

Use dry-run when testing behavior that does not require Control D writes:

```bash
NO_COLOR=1 uv run python main.py --dry-run --folder-url https://example.com/config.json --plan-json /home/ubuntu/ctrld-sync-plan.json
```

For negative URL/SSRF validation tests, expect a safe failure: nonzero exit code, warnings explaining the rejected URL or IP, `No valid folder data found`, and an empty plan file (`[]`). Do not treat the nonzero exit code as a failure when the test intentionally supplies only unsafe inputs.

## SSRF and DNS cache validation pattern

When validating DNS or SSRF protections, use a local Python harness with mocks instead of making real outbound requests:

1. Import `main` under `uv run python`.
2. Clear in-memory validation and fetch caches before the scenario:
   - `main.validate_folder_url.cache_clear()`
   - `main.validate_hostname.cache_clear()`
   - clear `main._cache` under `main._cache_lock`
   - `main._disk_cache.clear()` if disk cache effects matter
3. Patch `socket.getaddrinfo` to control DNS answers.
4. Patch `main.fetch_folder_data` to return a minimal valid payload for safe cases and count whether fetching was attempted.
5. Call `main.sync_profile(..., dry_run=True, plan_accumulator=...)`.

For DNS rebind/cache tests, run two syncs in the same Python process for the same URL:

- First DNS answer: safe global IP such as `8.8.8.8`; expected `sync_profile` returns `True` and fetch is called once.
- Second DNS answer: unsafe/reserved IP such as `240.0.0.1`; expected DNS is consulted again, `sync_profile` returns `False`, fetch count remains unchanged, and the second plan is empty.

This specifically proves both `validate_folder_url` and `validate_hostname` caches are cleared at the start of each sync run.

## Reporting

For shell-only testing, attach a markdown test report containing command outputs and clear pass/fail assertions. Mention explicitly that no browser recording was created because the app has no UI and the test evidence is CLI output.
