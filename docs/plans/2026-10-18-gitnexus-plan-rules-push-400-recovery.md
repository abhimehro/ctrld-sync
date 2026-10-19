# GitNexus Engineering Plan

> Task: Recover from intermittent Control D rules-API 400s on batched rule
> pushes (retry + per-rule isolation). Evidence verified at commit
> 51a0a9dcac1eb528ea2310b965bc517e60fbef77; GitNexus index refreshed this
> session (--index-only --pdg, runner 1.6.13-rc.38). Evidence provenance schema
> 2; global dirty digest
> d3e8238eb128140e8b233567ee2501f9151fc66c1f42f1f642c17a6750d507be; cited-path
> manifest 12 sorted entries; exact generated plan path excluded.

## Objective (§1)

Nightly sync intermittently fails a profile when the Control D rules API rejects
a whole-batch push with 400 (profile 780323dal5ac — Xiaomi/Huawei Tracker
folders; a different profile Oct 14; adjacent nights green). Make a 400-rejected
batch recover: one same-payload retry (transient rejections), then bisection
down to single-rule POSTs (deterministic bad-rule case), dropping only rejected
hostnames with sanitized warnings. Fix ships via PR; Trunk fmt lands on main
first (user-directed order, separate commit).

## Current Behaviour (§2–3)

- [verified] `push_rules` (sync/batches.py:214-243) filters/dedups, then
  `_push_rule_batches` (184-211) chunks hostnames into `config.BATCH_SIZE`=500
  batches; `_push_single_batch` (82-124) form-POSTs each batch at once
  (`hostnames[i]` keys, config.py:70-71) via `sync._api_post_form` →
  `POST {config.API_BASE}/{profile_id}/rules`.
- [verified] `api_client._retry_request` (370-427) retries transport/timeout/5xx
  (full jitter, MAX_RETRIES=10) and 429 (Retry-After), but `_check_client_error`
  (344-366) raises 4xx≠429 immediately — a 400 is never retried, so one rejected
  hostname fails all 500 rules of its batch.
- [verified] `_push_single_batch` catches `httpx.HTTPError`, logs a status hint,
  returns `None` → batch failed → `_log_batch_result` returns False → folder
  marked failed at sync/profile.py:190,200 → profile fails.
  Per-folder/per-profile isolation already exists (matches alert: 5/6 profiles
  green).

## Findings (§4–5)

- [graph]
  `impact _push_single_batch --direction upstream --depth 2 --include-tests` →
  risk LOW, exact; d=1 = `_run_single_batch` only; d=2 chain ends inside
  sync/batches.py.
- [graph] `impact push_rules --direction upstream` → UNKNOWN ("No callers
  resolved" + riskNote) → resolved by text search: production callers
  sync/profile.py:190,200; re-export sync/**init**.py:59.
- [verified] Existing retry infra (`_retry_request`) deliberately excludes
  4xx≠429 (documented security stance, api_client.py:386-388) — the fix belongs
  in the batch layer, not `_retry_request`.
- [graph] PDG slice @ sync/batches.py:99 (`impact --mode pdg`,
  upstream+downstream): the POST is a terminal side-effecting statement;
  intra-procedural dependents are entry/return blocks only (affectedStatements:
  lines 82, 88) — wrapping it in recovery breaks no data flow. Callers seed
  `ctx.existing_rules` from the return value, so recovery must return only rules
  actually accepted (else dropped rules would be skipped by all future runs).

## Proposed Changes (§6)

All production changes in `sync/batches.py`; public signatures unchanged:

- `_push_single_batch` (82-124): keep building `data`; route the POST through
  new `_post_chunk_with_400_recovery`. Non-400 `httpx.HTTPError` → existing
  hint-log path, return `None`. Empty accepted set → `None` (callers'
  truthy/falsy contract preserved for `_run_single_batch`,
  `_process_batches_with_executor`).
- New
  `_post_chunk_with_400_recovery(client, target, chunk_idx, chunk) -> list[str]`:
  POST the chunk; on 400 → one same-payload retry after a short sleep, then if
  len(chunk) > 1 bisect into halves and recurse; a single-rule chunk that still
  400s → drop with `sync.log.warning` (sanitized rule names, bounded sample).
  Returns the accepted hostnames.
- New module constant `_400_RETRY_DELAY_S` (short fixed delay; no new config
  surface). Reuse `sanitize_for_log` / `_clear_current_line` patterns.
- Constraints: no changes to api_client.py retry semantics; no changes to
  `_run_single_batch`, `_process_batches_with_executor`, `push_rules`,
  `_log_batch_result` contracts.

## Implementation Sequence (§7)

1. **Trunk (main, direct push — user-directed):** run `trunk fmt --all`; review
   every Trunk change; run the full suite; commit `.trunk/trunk.yaml` (user's
   linter update, already dirty) + fmt output, excluding `docs/plans/`; push
   main.
2. Branch `fix/rules-push-400-recovery` off updated main (impact pre-check
   satisfied: LOW, §4).
3. Implement §6 in sync/batches.py.
4. Add `tests/test_batch_400_recovery.py` (§8); run focused tests → full suite →
   `ruff check .` → mypy module set. Risk note: keep `_push_single_batch`'s
   return contract exact (`None` vs non-empty list) — both callers count and
   seed `existing_rules` from it.
5. `node .gitnexus/run.cjs detect-changes --scope all --repo .` (AGENTS.md
   pre-commit gate); resolve flagged regressions.
6. Commit fix + this plan; push; open PR; watch CI (`gh pr checks --watch`) and
   bot reviews; iterate to green.

## Test Strategy (§8)

New `tests/test_batch_400_recovery.py`, following tests/test_status_hints.py
conventions (`patch("sync._api_post_form", side_effect=...)`,
`_make_http_status_error`, `patch("sync.log")`,
`patch("sync.USE_COLORS", False)`):

- transient-400: side_effect [HTTPStatusError(400), None] → `push_rules` True;
  two POSTs; `existing_rules` contains all rules.
- bad-rule isolation: chunk set of 4 where any POST containing "bad.domain" 400s
  → `existing_rules` = other 3; warning names "bad.domain"; `push_rules` True.
- all-rejected: every POST 400s (retry + bisection exhausts) → `push_rules`
  False; drops logged; `existing_rules` unchanged.
- non-400 regression: 401 → existing hint-log + `None` behavior unchanged
  (mirrors tests/test_status_hints.py:155-171).
- Optional end-to-end per .agents/skills/testing-ctrld-sync/SKILL.md:
  `httpx.MockTransport` handler 400-ing any `/rules` POST whose form contains a
  poisoned hostname; folder completes with the rest.

Verification: `uv run pytest tests/ test_main.py -v`; `uv run ruff check .`;
`uv run mypy main.py models.py validation.py config.py display/ gh_client.py sync/ api_client.py cache.py fix_env.py`
(CI: .github/workflows/test.yml runs pytest with coverage on PRs).

## Implementation Context (§11)

```yaml
implementation_context:
  task_summary: >
    Add 400-recovery to Control D rule pushes: when a 500-hostname batch POST is
    rejected with 400 (intermittent per nightly-run evidence), retry once same-payload,
    then bisect down to single-rule POSTs; drop rejected hostnames with sanitized
    warnings; return only accepted rules so ctx.existing_rules stays truthful (dropped
    rules retry on the next nightly). Production change confined to sync/batches.py.
    Sequence: Trunk fmt direct-push to main first, then fix branch -> PR -> CI green.
  evidence_provenance:
    schema_version: 2
    head_commit: 51a0a9dcac1eb528ea2310b965bc517e60fbef77
    generated_plan_path: docs/plans/2026-10-18-gitnexus-plan-rules-push-400-recovery.md
    global_dirty_digest:
      algorithm: sha256
      canonicalization: gitnexus-evidence-provenance-v2 NUL-framed UTF-8 records
      value: d3e8238eb128140e8b233567ee2501f9151fc66c1f42f1f642c17a6750d507be
    cited_path_manifest:
      - path: .agents/skills/testing-ctrld-sync/SKILL.md
        object_kind: {
          head: regular,
          index: regular,
          worktree: regular,
          untracked: absent,
        }
        state: clean
        rename_from: null
        rename_to: null
        head_digest: sha256:6f3f0c85d8792aaa709aac43237fcd67b56b4548bd9fa9c9eac14906eedd3cff
        index_digest: sha256:6f3f0c85d8792aaa709aac43237fcd67b56b4548bd9fa9c9eac14906eedd3cff
        worktree_digest: sha256:6f3f0c85d8792aaa709aac43237fcd67b56b4548bd9fa9c9eac14906eedd3cff
        untracked_digest: absent
      - path: .github/workflows/test.yml
        object_kind: {
          head: regular,
          index: regular,
          worktree: regular,
          untracked: absent,
        }
        state: clean
        rename_from: null
        rename_to: null
        head_digest: sha256:b48a5523c79a8f3bf427744bc58d42f8043b784d175d2b8374004c1b9b1c9804
        index_digest: sha256:b48a5523c79a8f3bf427744bc58d42f8043b784d175d2b8374004c1b9b1c9804
        worktree_digest: sha256:b48a5523c79a8f3bf427744bc58d42f8043b784d175d2b8374004c1b9b1c9804
        untracked_digest: absent
      - path: .trunk/trunk.yaml
        object_kind: {
          head: regular,
          index: regular,
          worktree: regular,
          untracked: absent,
        }
        state: unstaged
        rename_from: null
        rename_to: null
        head_digest: sha256:b1bb9beab391ba23e35cd447b2b7f5faf86b833da618d58062c5e85a6a124a02
        index_digest: sha256:b1bb9beab391ba23e35cd447b2b7f5faf86b833da618d58062c5e85a6a124a02
        worktree_digest: sha256:d0a15e4247fb8af04d538a3ed6a924ac32e8c7c65bf5dcfdccace23d62f1bc13
        untracked_digest: absent
      - path: api_client.py
        object_kind: {
          head: regular,
          index: regular,
          worktree: regular,
          untracked: absent,
        }
        state: clean
        rename_from: null
        rename_to: null
        head_digest: sha256:84ec7af20ce891638524b974eba95cb0806d19ff3b9290084a1eceff5b18311f
        index_digest: sha256:84ec7af20ce891638524b974eba95cb0806d19ff3b9290084a1eceff5b18311f
        worktree_digest: sha256:84ec7af20ce891638524b974eba95cb0806d19ff3b9290084a1eceff5b18311f
        untracked_digest: absent
      - path: config.py
        object_kind: {
          head: regular,
          index: regular,
          worktree: regular,
          untracked: absent,
        }
        state: clean
        rename_from: null
        rename_to: null
        head_digest: sha256:7bdbaaf9850a65af0a2d759c2ef19b625362e9abc268d098526d95f7bf64994a
        index_digest: sha256:7bdbaaf9850a65af0a2d759c2ef19b625362e9abc268d098526d95f7bf64994a
        worktree_digest: sha256:7bdbaaf9850a65af0a2d759c2ef19b625362e9abc268d098526d95f7bf64994a
        untracked_digest: absent
      - path: pyproject.toml
        object_kind: {
          head: regular,
          index: regular,
          worktree: regular,
          untracked: absent,
        }
        state: clean
        rename_from: null
        rename_to: null
        head_digest: sha256:e655ca77a326d595084c07921948d13fbdb7bc03db517900201bbeda8c006257
        index_digest: sha256:e655ca77a326d595084c07921948d13fbdb7bc03db517900201bbeda8c006257
        worktree_digest: sha256:e655ca77a326d595084c07921948d13fbdb7bc03db517900201bbeda8c006257
        untracked_digest: absent
      - path: sync/__init__.py
        object_kind: {
          head: regular,
          index: regular,
          worktree: regular,
          untracked: absent,
        }
        state: clean
        rename_from: null
        rename_to: null
        head_digest: sha256:5ec564137b49a4b0151253ed82d632c3fc87e8eff7d02fc66925ee70d16de132
        index_digest: sha256:5ec564137b49a4b0151253ed82d632c3fc87e8eff7d02fc66925ee70d16de132
        worktree_digest: sha256:5ec564137b49a4b0151253ed82d632c3fc87e8eff7d02fc66925ee70d16de132
        untracked_digest: absent
      - path: sync/batches.py
        object_kind: {
          head: regular,
          index: regular,
          worktree: regular,
          untracked: absent,
        }
        state: clean
        rename_from: null
        rename_to: null
        head_digest: sha256:7200d6f1f40a197ca7f4645d08ee435ae50072cefe287535ef54dceb8297251f
        index_digest: sha256:7200d6f1f40a197ca7f4645d08ee435ae50072cefe287535ef54dceb8297251f
        worktree_digest: sha256:7200d6f1f40a197ca7f4645d08ee435ae50072cefe287535ef54dceb8297251f
        untracked_digest: absent
      - path: sync/profile.py
        object_kind: {
          head: regular,
          index: regular,
          worktree: regular,
          untracked: absent,
        }
        state: clean
        rename_from: null
        rename_to: null
        head_digest: sha256:dc9ec4a19c45aefb4ebafb0630feb7cfedb4b99df4222f34de7d00a4d15fc182
        index_digest: sha256:dc9ec4a19c45aefb4ebafb0630feb7cfedb4b99df4222f34de7d00a4d15fc182
        worktree_digest: sha256:dc9ec4a19c45aefb4ebafb0630feb7cfedb4b99df4222f34de7d00a4d15fc182
        untracked_digest: absent
      - path: sync/rules.py
        object_kind: {
          head: regular,
          index: regular,
          worktree: regular,
          untracked: absent,
        }
        state: clean
        rename_from: null
        rename_to: null
        head_digest: sha256:decbbe1c1c65b97f168d65365925634d716dcc1233cdc5861e18c64de4d0428c
        index_digest: sha256:decbbe1c1c65b97f168d65365925634d716dcc1233cdc5861e18c64de4d0428c
        worktree_digest: sha256:decbbe1c1c65b97f168d65365925634d716dcc1233cdc5861e18c64de4d0428c
        untracked_digest: absent
      - path: tests/test_security_hardening.py
        object_kind: {
          head: regular,
          index: regular,
          worktree: regular,
          untracked: absent,
        }
        state: clean
        rename_from: null
        rename_to: null
        head_digest: sha256:7c110b22f3c3053d5477ea87d2ce88a765c9712cd713bcff1b705030283aa8e2
        index_digest: sha256:7c110b22f3c3053d5477ea87d2ce88a765c9712cd713bcff1b705030283aa8e2
        worktree_digest: sha256:7c110b22f3c3053d5477ea87d2ce88a765c9712cd713bcff1b705030283aa8e2
        untracked_digest: absent
      - path: tests/test_status_hints.py
        object_kind: {
          head: regular,
          index: regular,
          worktree: regular,
          untracked: absent,
        }
        state: clean
        rename_from: null
        rename_to: null
        head_digest: sha256:17d097a5848552111888ba236efc478a8f32912faf5d3cfc2e2dff130e60d0ba
        index_digest: sha256:17d097a5848552111888ba236efc478a8f32912faf5d3cfc2e2dff130e60d0ba
        worktree_digest: sha256:17d097a5848552111888ba236efc478a8f32912faf5d3cfc2e2dff130e60d0ba
        untracked_digest: absent
  files_to_modify:
    - file: sync/batches.py
      symbols: [
        _push_single_batch,
        _post_chunk_with_400_recovery (new),
        _400_RETRY_DELAY_S (new),
      ]
      intended_change: >
        Route the batch POST through a 400-recovery helper: same-payload retry, then
        bisection to single-rule POSTs; drop rejected hostnames with sanitized warnings;
        return only accepted rules; non-400 errors keep today's hint-log + None behavior.
    - file: tests/test_batch_400_recovery.py
      symbols: [new test module]
      intended_change: Mock-based scenarios per plan §8 (transient, bad-rule isolation, all-rejected, non-400 regression; optional MockTransport e2e).
    - file: docs/plans/2026-10-18-gitnexus-plan-rules-push-400-recovery.md
      symbols: []
      intended_change: This plan ships with the fix PR (not in the Trunk commit).
  tests:
    - file: tests/test_batch_400_recovery.py
      scenarios:
        - "transient 400 (side_effect [err400, None]) -> push_rules True, 2 POSTs, existing_rules complete"
        - "bad-rule isolation (400 iff chunk contains bad.domain) -> other rules accepted, warning names bad.domain"
        - "all-rejected (every POST 400) -> push_rules False, drops logged, existing_rules unchanged"
        - "non-400 (401) -> unchanged hint-log + None path (regression vs tests/test_status_hints.py:155)"
        - "optional httpx.MockTransport e2e per testing-ctrld-sync skill"
  verification_commands:
    - "uv run pytest tests/ test_main.py -v"
    - "uv run pytest tests/test_batch_400_recovery.py -v"
    - "uv run ruff check ."
    - "uv run mypy main.py models.py validation.py config.py display/ gh_client.py sync/ api_client.py cache.py fix_env.py"
    - "node .gitnexus/run.cjs detect-changes --scope all --repo ."
  pdg_constraints:
    - description: "Batch POST (sync/batches.py:98-101) is terminal/side-effecting; intra-procedural dependents are entry/return blocks only"
      affected_statements: [
        "sync/batches.py:82",
        "sync/batches.py:88",
        "sync/batches.py:99",
      ]
      implementation_consequence: "Wrap the POST in recovery without touching surrounding data flow; keep the return value = accepted-rules list (callers seed ctx.existing_rules from it)"
  assumptions:
    - "400s are intermittent/transient API rejections (alert: adjacent nights green, 5/6 profiles green) — re-verify cheaply by reading the next nightly's logs after merge"
    - "Rules API validates the whole form payload, so one bad hostname 400s all 500 — verify by inspecting the 400 recovery warnings once they occur live"
    - "Callers rely only on truthiness of _push_single_batch's return (verified: _run_single_batch 68-79, _process_batches_with_executor 127-149)"
  open_questions:
    - "Exact server-side 400 cause is unverifiable from this repo (no response bodies retained); monitor post-merge nightlies"
    - "Should 422 (duplicate/unsupported value hint) get the same bisection treatment? Deferred — not requested"
  avoid:
    - "Do not change api_client.py retry semantics (documented security stance: no blanket 4xx retry)"
    - "Do not add dropped rules to ctx.existing_rules (they must retry next run)"
    - "Do not alter signatures/contracts of _run_single_batch, _process_batches_with_executor, push_rules, _log_batch_result"
    - "Do not include docs/plans/ in the Trunk commit; do not PR the Trunk changes (user-directed direct push to main)"
    - "No live Control D API calls in tests; mock sync._api_post_form or use httpx.MockTransport"
    - "Do not repeat full repository discovery; this pack is the entry point"
```

## Assumptions and Open Questions (§12)

- [assumed] 400s are transient/intermittent API rejections (alert evidence:
  adjacent nights green, 5/6 profiles green same night); no server-side payload
  evidence exists locally — the design is deliberately cause-agnostic (retry +
  isolate).
- [assumed] The rules API validates the whole form payload, so one rejected
  hostname can 400 all 500 of its batch (consistent with folder-wide failures
  and the `hostnames[i]` form design).
- Worst case for a fully-rejected batch ≈ 2×len(chunk) recovery POSTs
  (bisection) — accepted: folders process serially and 429/Retry-After is still
  honored per POST. Deferred follow-ups: per-batch recovery-POST cap; extending
  bisection to 422.
- Dropped rules are NOT added to `existing_rules`, so the next nightly run
  retries them (self-healing; folders may stay partially populated instead of
  empty).
- Folder-level accounting stays batch-granular (a batch with drops still counts
  "successful") — accepted trade-off; drops are loudly logged per batch.
- Open: exact server-side 400 cause; watch the first post-merge nightly.

## Definition of Done (§13)

- A 400-rejected batch recovers when recovery can succeed (transient retry, or
  bad-rule isolation); rejected rules are logged (sanitized) and excluded from
  `existing_rules`; folder/profile isolation unchanged.
- Non-400 error paths behave exactly as before;
  `uv run pytest tests/ test_main.py -v` green; `ruff check .` and the mypy
  module set clean; PR CI green.
- Trunk fmt (reviewed + test-verified) landed directly on main before the fix PR
  was opened.
