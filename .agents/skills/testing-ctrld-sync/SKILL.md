---
name: testing-ctrld-sync
description: Test the ctrld-sync Python CLI end-to-end, including dry-run planning, SSRF harnesses, and batching regression checks.
---

# ctrld-sync CLI Testing

## App shape

- Single-file Python CLI app in `main.py`; no browser UI, database, or Docker
  service is required.
- Use shell-based testing evidence. Do not record the desktop unless a future
  change adds a GUI.
- Python >= 3.13 is required; use `uv` so the repo interpreter is selected.

## Setup

```bash
uv sync --all-extras
```

Repo environment config usually already runs this as maintenance. Re-run only if
dependencies are missing or stale.

## Devin Secrets Needed

- `TOKEN`: Control D API token, required only for live sync runs.
- `PROFILE`: Control D profile ID, required only for live sync runs.

Dry-run and mocked SSRF validation tests do not require Control D secrets.

## Standard verification commands

```bash
uv run pytest tests/ test_main.py -v
uv run ruff check .
uv run mypy main.py
uv run pre-commit run --all-files
```

For SSRF-only changes, the focused checks are usually sufficient before broader
CI:

```bash
uv run pytest tests/test_ssrf_enhanced.py -v
uv run ruff check main.py tests/test_ssrf_enhanced.py
uv run mypy main.py
```

## Runtime dry-run testing

The simplest dry-run sanity command is:

```bash
uv run python main.py --dry-run --folder-url https://example.com/config.json
```

`--dry-run` does not require `TOKEN` or `PROFILE`; `main.py` uses a
`dry-run-placeholder` profile and avoids Control D API writes.

Important: `example.com` is **not** in the default `allowed_blocklist_domains`
(`raw.githubusercontent.com`, `github.com`, `yokoffing.github.io`), so the
command above will print a `DRY RUN SUMMARY` but exit `1` with
`Failed (Dry)`. It does not crash, but it does not produce a `Ready` status.
To obtain a passing `Planned` / `Ready` dry-run, either:

- use a URL whose host is in the default allowlist, or
- create a temporary `config.yaml` with `allowed_blocklist_domains: [example.com]`
  and pass `--config /path/to/config.yaml`.

## SSRF harness for mocked end-to-end dry-run

For deterministic SSRF tests, use a temporary Python harness that:

1. Calls `main.main()` with `--dry-run` and explicit `--folder-url` values.
2. Patches `socket.getaddrinfo` to return controlled IP addresses.
3. Patches **`gh_client._gh_get`** (not `main._gh_get`) so unsafe URLs fail
   immediately if fetched and safe URLs return minimal valid folder JSON.
   `main._gh_get` is just an alias; the actual fetch path goes through
   `gh_client.fetch_folder_data` -> `gh_client._gh_get`.
4. Does not patch `main.main()`, `sync_profile()`, `validate_folder_url()`,
   `validate_hostname()`, or `_is_safe_ip()`.
5. Attaches an explicit in-memory handler to logger `control-d-sync`; the
   module-level logging handler is created at import time, so
   `contextlib.redirect_stderr()` alone might not capture warnings.
6. Patches `main.prompt_for_interactive_restart` to a no-op when running in a
   PTY so dry-run success does not block on the restart prompt.
7. Patches `main.load_disk_cache` and `main.load_dotenv` to no-ops so the
   harness starts from a clean, reproducible state.
8. Clears `main.validate_folder_url.cache_clear()`,
   `main.validate_hostname.cache_clear()`, `gh_client._cache`, and
   `gh_client._disk_cache` before the run.

Useful SSRF cases:

- `240.0.0.1` should be rejected as unsafe/reserved IPv4.
- `::ffff:8.8.8.8` should be allowed after IPv4-mapped IPv6 unwrapping.
- `::ffff:240.0.0.1` should be rejected.
- `64:ff9b::1` should be rejected and is useful for proving the explicit
  `is_reserved` guard blocks a reserved IPv6 address that may otherwise report
  `is_global=True`.

Expected dry-run evidence for a passing safe case:

- Output contains `DRY RUN SUMMARY`.
- Output includes the accepted folder name.
- Summary shows at least one folder / one rule with status `Planned` and `Ready`.
- Captured logger output contains unsafe-host warnings for rejected cases.
- Fetched URL list contains only the safe URL(s).
- `api_client._api_stats["control_d_api_calls"]` remains `0` after the run.

## No-live-API guard

When proving that `--dry-run` does not call the Control D API:

- Patch `sync.create_client` to raise `AssertionError` if invoked.
- Check `api_client._api_stats["control_d_api_calls"]` at the end of the run.
- The only HTTP traffic in dry-run mode should be blocklist fetches for
  allowlisted `--folder-url` values (mocked in the harness).

## Live-mode (non dry-run) harness without Control D credentials

`TOKEN` / `PROFILE` are usually unavailable, but the live sync path (folder
deletion, folder-creation polling, existing-rules scan, rule batching) can still
be driven end-to-end by faking the Control D API with `httpx.MockTransport`:

- Patch `sync.create_client` to return
  `httpx.Client(transport=httpx.MockTransport(handler))`.
- Patch `sync.plan.fetch_folder_data` (plan.py imports the helper as a module-level
  name, so patching `sync.plan.fetch_folder_data` is what the parallel-deletion
  tests do) and `sync.validate_folder_url` — the latter must still expose
  `.cache_clear()`, so wrap the stub in `functools.lru_cache`, because
  `sync_profile` clears the cache on entry.
- Patch `sync.countdown_timer` to record its argument instead of sleeping; the
  post-deletion propagation wait is 60s and would otherwise stall the run.
- Set `config.FOLDER_CREATION_DELAY = 0`, lower `api_client.MAX_RETRIES`, and
  no-op `sync.time.sleep` / `api_client.time.sleep` to keep polling fast.
- Clear `sync._cache` before each scenario.

The handler should serve `GET/POST /profiles/<id>/groups`,
`DELETE /profiles/<id>/groups/<fid>`, `GET /profiles/<id>/rules[/<fid>]` and
`POST /profiles/<id>/rules` (form-encoded `hostnames[i]` keys). Useful
assertions: which folder IDs were deleted, whether the 60s wait fired, which
folders got rules-scanned (deleted folders must be excluded), the number of
`GET /groups` calls (1 = direct-response folder ID, 2 = one poll), and the
deduplicated hostnames in the `POST /rules` form.

For refactor PRs, run the same harness against a `git worktree` of the base
branch (`git worktree add /tmp/<name> main`) with the module dir injected via
`sys.path` / `TARGET` env var and diff the JSON reports — a byte-identical diff
is strong evidence of behavior preservation. The same A/B trick works for
`uv run python main.py --dry-run` output (strip timestamps and durations before
diffing).

## Notes

- Clear `main.validate_hostname` and `main.validate_folder_url` caches
  before/after mocked DNS tests.
- Clear `_cache` and `_disk_cache` in runtime harnesses to avoid cached
  blocklist data bypassing fetch assertions.
- Avoid committing temporary harnesses, evidence files, screenshots, or test
  reports unless explicitly requested.
