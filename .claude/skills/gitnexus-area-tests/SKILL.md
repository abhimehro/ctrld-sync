---
name: gitnexus-area-tests
description: "Skill for the Tests area of ctrld-sync. 227 symbols across 35 files."
---

# Tests

227 symbols | 35 files | Cohesion: 88%

## When to Use

- Working with code in `tests/`
- Understanding how retry_with_jitter, failing_request, fetch work
- Modifying tests-related functionality

## Key Files

| File                                        | Symbols                                                                                                                                                                                                                           |
| ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `tests/test_gh_client.py`                   | fetch, test_conditional_headers_from_disk_cache, test_disk_ttl_hit_returns_without_http_and_counts_fetch, test_in_memory_hit_returns_cached_object, test_returns_none_for_invalid_url (+20)                                       |
| `tests/test_api_client.py`                  | _make_http_error, test_connect_error_hint_in_retry_warning, test_400_warning_logged, test_401_warning_logged, test_403_warning_logged (+15)                                                                                       |
| `tests/test_sync_folder_preparation.py`     | _poll_context, test_poll_fetch_exception_then_success_logs_zero_based_attempt, test_poll_finds_folder_after_misses, test_poll_finds_folder_on_first_attempt, test_poll_invalid_pk_returns_without_wait_or_final_error (+14)       |
| `tests/test_status_hints.py`                | _make_http_status_error, test_401_hint_in_message, test_403_hint_in_message, test_404_hint_in_message, test_429_hint_in_message (+10)                                                                                             |
| `api_client.py`                             | _check_client_error, _get_error_hint, _handle_rate_limit, _is_server_error, _log_debug_response_content (+9)                                                                                                                      |
| `tests/test_json_logging.py`                | _make_record, test_level_name, test_logger_name, test_message_content, test_no_ansi_codes_in_output (+6)                                                                                                                          |
| `gh_client.py`                              | _build_conditional_headers, _count_blocklist_fetch, _get_memory_cached, _gh_get, _handle_304_with_data (+5)                                                                                                                       |
| `main.py`                                   | _set_display_submodule_attr, _set_sync_submodule_attr, **setattr**, check_env_permissions, _apply_runtime_settings (+4)                                                                                                           |
| `tests/test_config.py`                      | _write_config, test_load_config_explicit_path, test_load_config_explicit_path_takes_precedence_over_cwd, test_load_config_invalid_schema_exits, test_load_config_reads_config_yaml (+4)                                           |
| `tests/test_validation_characterization.py` | _restore_token, test_sanitize_redaction_before_repr_escaping, test_sanitize_redacts_token_in_nested_containers, test_set_token_for_redaction_after_import, test_validate_folder_data_dict_subclass_rule_is_rejected_silently (+2) |

## Entry Points

Start here when exploring this area:

- **`retry_with_jitter`** (Function) — `api_client.py:241`
- **`failing_request`** (Function) — `tests/test_exception_logging.py:209`
- **`fetch`** (Function) — `tests/test_gh_client.py:393`
- **`validate_folder_url`** (Function) — `validation.py:240`
- **`create_client`** (Function) — `sync/client.py:13`

## Key Symbols

| Symbol                                             | Type     | File                                        | Line |
| -------------------------------------------------- | -------- | ------------------------------------------- | ---- |
| `retry_with_jitter`                                | Function | `api_client.py`                             | 241  |
| `failing_request`                                  | Function | `tests/test_exception_logging.py`           | 209  |
| `fetch`                                            | Function | `tests/test_gh_client.py`                   | 393  |
| `validate_folder_url`                              | Function | `validation.py`                             | 240  |
| `create_client`                                    | Function | `sync/client.py`                            | 13   |
| `test_sanitize_golden_corpus`                      | Function | `tests/test_sanitize_golden_corpus.py`      | 36   |
| `test_sanitize_redaction_before_repr_escaping`     | Function | `tests/test_validation_characterization.py` | 143  |
| `test_sanitize_redacts_token_in_nested_containers` | Function | `tests/test_validation_characterization.py` | 150  |
| `test_set_token_for_redaction_after_import`        | Function | `tests/test_validation_characterization.py` | 136  |
| `set_token_for_redaction`                          | Function | `validation.py`                             | 81   |
| `clean_val`                                        | Function | `fix_env.py`                                | 9    |
| `escape_val`                                       | Function | `fix_env.py`                                | 18   |
| `fix_env`                                          | Function | `fix_env.py`                                | 99   |
| `test_clean_val`                                   | Function | `tests/test_fix_env.py`                     | 122  |
| `test_escape_val`                                  | Function | `tests/test_fix_env.py`                     | 137  |
| `test_fix_env_creates_secure_file`                 | Function | `tests/test_fix_env.py`                     | 41   |
| `test_fix_env_handles_existing_temp_file`          | Function | `tests/test_fix_env.py`                     | 79   |
| `test_fix_env_skips_symlink`                       | Function | `tests/test_fix_env.py`                     | 7    |
| `test_fix_env_sets_secure_permissions`             | Function | `tests/test_security.py`                    | 173  |
| `test_fix_env_skips_chmod_on_windows`              | Function | `tests/test_security.py`                    | 200  |

## Execution Flows

| Flow                                                      | Type            | Steps |
| --------------------------------------------------------- | --------------- | ----- |
| `_fetch_if_valid → _escape_for_log`                       | cross_community | 8     |
| `_fetch_if_valid → _redact_secrets`                       | cross_community | 8     |
| `_fetch_if_valid → _is_safe_ip`                           | cross_community | 7     |
| `_fetch_if_valid → _is_likely_domain`                     | cross_community | 6     |
| `_validate_and_fetch_url → _escape_for_log`               | cross_community | 6     |
| `_validate_and_fetch_url → _redact_secrets`               | cross_community | 6     |
| `_resolve_folder_urls → _is_valid_positive_int`           | cross_community | 5     |
| `_prompt_for_missing_config → Is_valid_profile_id_format` | cross_community | 5     |
| `_fetch_if_valid → _is_allowed_blocklist_domain`          | cross_community | 5     |
| `_validate_and_fetch_url → _is_safe_ip`                   | cross_community | 5     |

## How to Explore

1. `context({name: "retry_with_jitter"})` — see callers and callees
2. `query({search_query: "tests"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings
   (source→sink data flows), when indexed with `--pdg`
