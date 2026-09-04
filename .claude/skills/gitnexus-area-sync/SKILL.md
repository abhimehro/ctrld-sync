---
name: gitnexus-area-sync
description: "Skill for the Sync area of ctrld-sync. 37 symbols across 9 files."
---

# Sync

37 symbols | 9 files | Cohesion: 61%

## When to Use

- Working with code in `sync/`
- Understanding how push_rules, check_api_access, delete_folder work
- Modifying sync-related functionality

## Key Files

| File                     | Symbols                                                                                                                       |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| `sync/folders.py`        | delete_folder, _extract_folder_id_from_response, _extract_from_groups_list, _find_folder_in_groups, _poll_folder_attempt (+6) |
| `sync/profile.py`        | _process_folders, _sync_profile_live, sync_profile, _delete_folders, _partition_folders_for_deletion (+3)                     |
| `validation.py`          | _escape_for_log, _redact_secrets, sanitize_for_log, _log_validation_error, validate_folder_id (+1)                            |
| `sync/rules.py`          | get_all_existing_rules, _fetch_folder_rules, _deduplicate_hostnames, _filter_rules_for_folder, _log_filtering_results         |
| `gh_client.py`           | _content_length_if_over_limit, _read_body                                                                                     |
| `sync/batches.py`        | push_rules, from_parts                                                                                                        |
| `sync/client.py`         | check_api_access                                                                                                              |
| `sync/plan.py`           | _fetch_all_folder_data                                                                                                        |
| `tests/test_security.py` | test_is_valid_rule_strict                                                                                                     |

## Entry Points

Start here when exploring this area:

- **`push_rules`** (Function) — `sync/batches.py:213`
- **`check_api_access`** (Function) — `sync/client.py:27`
- **`delete_folder`** (Function) — `sync/folders.py:162`
- **`sync_profile`** (Function) — `sync/profile.py:239`
- **`get_all_existing_rules`** (Function) — `sync/rules.py:15`

## Key Symbols

| Symbol                          | Type     | File                     | Line |
| ------------------------------- | -------- | ------------------------ | ---- |
| `push_rules`                    | Function | `sync/batches.py`        | 213  |
| `check_api_access`              | Function | `sync/client.py`         | 27   |
| `delete_folder`                 | Function | `sync/folders.py`        | 162  |
| `sync_profile`                  | Function | `sync/profile.py`        | 239  |
| `get_all_existing_rules`        | Function | `sync/rules.py`          | 15   |
| `sanitize_for_log`              | Function | `validation.py`          | 117  |
| `create_folder`                 | Function | `sync/folders.py`        | 290  |
| `list_existing_folders`         | Function | `sync/folders.py`        | 32   |
| `verify_access_and_get_folders` | Function | `sync/folders.py`        | 91   |
| `validate_folder_id`            | Function | `validation.py`          | 361  |
| `test_is_valid_rule_strict`     | Function | `tests/test_security.py` | 274  |
| `is_valid_rule`                 | Function | `validation.py`          | 384  |
| `from_parts`                    | Method   | `sync/batches.py`        | 36   |
| `_content_length_if_over_limit` | Function | `gh_client.py`           | 57   |
| `_read_body`                    | Function | `gh_client.py`           | 78   |
| `_fetch_all_folder_data`        | Function | `sync/plan.py`           | 16   |
| `_process_folders`              | Function | `sync/profile.py`        | 211  |
| `_sync_profile_live`            | Function | `sync/profile.py`        | 127  |
| `_fetch_folder_rules`           | Function | `sync/rules.py`          | 29   |
| `_escape_for_log`               | Function | `validation.py`          | 102  |

## Execution Flows

| Flow                                          | Type            | Steps |
| --------------------------------------------- | --------------- | ----- |
| `Create_folder → _escape_for_log`             | cross_community | 8     |
| `Create_folder → _redact_secrets`             | cross_community | 8     |
| `_fetch_if_valid → _escape_for_log`           | cross_community | 8     |
| `_fetch_if_valid → _redact_secrets`           | cross_community | 8     |
| `Create_folder → _log_validation_error`       | cross_community | 7     |
| `_poll_for_folder_id → _escape_for_log`       | cross_community | 7     |
| `_poll_for_folder_id → _redact_secrets`       | cross_community | 7     |
| `_poll_for_folder_id → _log_validation_error` | cross_community | 6     |
| `_validate_and_fetch_url → _escape_for_log`   | cross_community | 6     |
| `_validate_and_fetch_url → _redact_secrets`   | cross_community | 6     |

## How to Explore

1. `context({name: "push_rules"})` — see callers and callees
2. `query({search_query: "sync"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings
   (source→sink data flows), when indexed with `--pdg`
