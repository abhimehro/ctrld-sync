---
name: gitnexus-area-display
description: "Skill for the Display area of ctrld-sync. 59 symbols across 17 files."
---

# Display

59 symbols | 17 files | Cohesion: 76%

## When to Use

- Working with code in `display/`
- Understanding how get_cache_dir, load_disk_cache, save_disk_cache work
- Modifying display-related functionality

## Key Files

| File                  | Symbols                                                                                                                 |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `display/tables.py`   | _print_hint_if_no_folders, _get_display_profile, _render_ascii_table, _render_unicode_table, make_col_separator (+6)    |
| `display/plan.py`     | _format_dimmed_hint, _format_empty_warning, _format_folder_line, _format_plan_header, _get_action_text (+2)             |
| `sync/batches.py`     | _log_batch_result, _managed_batch_executor, _process_batches_with_executor, _push_rule_batches, _push_single_batch (+1) |
| `main.py`             | _handle_clear_cache, _prompt_for_missing_config, validate_profile_input, _write_plan_json, main                         |
| `display/output.py`   | _print_hint, _clear_current_line, _print_completion, _print_bold_header                                                 |
| `display/stats.py`    | display_api_statistics, display_cache_statistics, display_rate_limit_status, display_statistics                         |
| `cache.py`            | get_cache_dir, load_disk_cache, save_disk_cache                                                                         |
| `validation.py`       | extract_profile_id, is_valid_profile_id_format, validate_profile_id                                                     |
| `display/progress.py` | _get_progress_bar_width, countdown_timer, render_progress_bar                                                           |
| `display/text.py`     | pluralize, _display_len, _pad_string                                                                                    |

## Entry Points

Start here when exploring this area:

- **`get_cache_dir`** (Function) — `cache.py:85`
- **`load_disk_cache`** (Function) — `cache.py:109`
- **`save_disk_cache`** (Function) — `cache.py:194`
- **`get_password`** (Function) — `display/prompts.py:75`
- **`validate_profile_input`** (Function) — `main.py:455`

## Key Symbols

| Symbol                                                            | Type     | File                            | Line |
| ----------------------------------------------------------------- | -------- | ------------------------------- | ---- |
| `get_cache_dir`                                                   | Function | `cache.py`                      | 85   |
| `load_disk_cache`                                                 | Function | `cache.py`                      | 109  |
| `save_disk_cache`                                                 | Function | `cache.py`                      | 194  |
| `get_password`                                                    | Function | `display/prompts.py`            | 75   |
| `validate_profile_input`                                          | Function | `main.py`                       | 455  |
| `main`                                                            | Function | `main.py`                       | 632  |
| `validator`                                                       | Function | `test_main.py`                  | 564  |
| `test_main_reloads_token_from_env`                                | Function | `tests/test_bootstrapping.py`   | 9    |
| `test_write_plan_json_is_atomic_and_owner_only`                   | Function | `tests/test_plan_json_write.py` | 11   |
| `test_write_plan_json_removes_temp_file_when_serialization_fails` | Function | `tests/test_plan_json_write.py` | 22   |
| `extract_profile_id`                                              | Function | `validation.py`                 | 300  |
| `is_valid_profile_id_format`                                      | Function | `validation.py`                 | 316  |
| `validate_profile_id`                                             | Function | `validation.py`                 | 331  |
| `countdown_timer`                                                 | Function | `display/progress.py`           | 27   |
| `render_progress_bar`                                             | Function | `display/progress.py`           | 65   |
| `pluralize`                                                       | Function | `display/text.py`               | 8    |
| `warm_up_cache`                                                   | Function | `gh_client.py`                  | 312  |
| `make_col_separator`                                              | Function | `display/tables.py`             | 193  |
| `print_line`                                                      | Function | `display/tables.py`             | 34   |
| `print_row`                                                       | Function | `display/tables.py`             | 39   |

## Execution Flows

| Flow                                                      | Type            | Steps |
| --------------------------------------------------------- | --------------- | ----- |
| `Print_summary_table → _display_len`                      | intra_community | 5     |
| `_prompt_for_missing_config → Is_valid_profile_id_format` | cross_community | 5     |
| `Push_rules → _clear_current_line`                        | cross_community | 5     |
| `Push_rules → Pluralize`                                  | cross_community | 5     |
| `Push_rules → _api_post_form`                             | cross_community | 5     |
| `_prompt_for_missing_config → _log_validation_error`      | cross_community | 5     |
| `_push_rule_batches → _escape_for_log`                    | cross_community | 5     |
| `_push_rule_batches → _redact_secrets`                    | cross_community | 5     |
| `Print_summary_table → Make_col_separator`                | intra_community | 4     |
| `_prompt_for_missing_config → Extract_profile_id`         | cross_community | 4     |

## How to Explore

1. `context({name: "get_cache_dir"})` — see callers and callees
2. `query({search_query: "display"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings
   (source→sink data flows), when indexed with `--pdg`
