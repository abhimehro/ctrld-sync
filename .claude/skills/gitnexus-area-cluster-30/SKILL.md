---
name: gitnexus-area-cluster-30
description: "Skill for the Cluster_30 area of ctrld-sync. 30 symbols across 1 files."
---

# Cluster_30

30 symbols | 1 files | Cohesion: 100%

## When to Use

- Understanding how reload_main_with_env, test_check_env_permissions_secure,
  test_get_all_existing_rules_updates_correctly work
- Modifying cluster_30-related functionality

## Key Files

| File           | Symbols                                                                                                                                                          |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `test_main.py` | reload_main_with_env, test_check_env_permissions_secure, test_get_all_existing_rules_updates_correctly, test_get_password, test_get_password_graceful_exit (+25) |

## Entry Points

Start here when exploring this area:

- **`reload_main_with_env`** (Function) — `test_main.py:20`
- **`test_check_env_permissions_secure`** (Function) — `test_main.py:732`
- **`test_get_all_existing_rules_updates_correctly`** (Function) —
  `test_main.py:94`
- **`test_get_password`** (Function) — `test_main.py:558`
- **`test_get_password_graceful_exit`** (Function) — `test_main.py:660`

## Key Symbols

| Symbol                                          | Type     | File           | Line |
| ----------------------------------------------- | -------- | -------------- | ---- |
| `reload_main_with_env`                          | Function | `test_main.py` | 20   |
| `test_check_env_permissions_secure`             | Function | `test_main.py` | 732  |
| `test_get_all_existing_rules_updates_correctly` | Function | `test_main.py` | 94   |
| `test_get_password`                             | Function | `test_main.py` | 558  |
| `test_get_password_graceful_exit`               | Function | `test_main.py` | 660  |
| `test_get_password_interrupt`                   | Function | `test_main.py` | 622  |
| `test_get_progress_bar_width`                   | Function | `test_main.py` | 679  |
| `test_get_validated_input_graceful_exit`        | Function | `test_main.py` | 641  |
| `test_get_validated_input_interrupt`            | Function | `test_main.py` | 605  |
| `test_get_validated_input_retry`                | Function | `test_main.py` | 529  |
| `test_interactive_input_extracts_id`            | Function | `test_main.py` | 469  |
| `test_interactive_prompts_show_hints`           | Function | `test_main.py` | 264  |
| `test_is_valid_profile_id_format`               | Function | `test_main.py` | 841  |
| `test_progress_functions_use_dynamic_width`     | Function | `test_main.py` | 710  |
| `test_push_rules_logs_conditionally_use_colors` | Function | `test_main.py` | 187  |
| `test_push_rules_updates_data_with_batch_keys`  | Function | `test_main.py` | 128  |
| `test_push_rules_updates_existing_rules`        | Function | `test_main.py` | 162  |
| `test_push_rules_writes_colored_stderr`         | Function | `test_main.py` | 233  |
| `test_render_progress_bar`                      | Function | `test_main.py` | 581  |
| `test_use_colors_respects_isatty_false`         | Function | `test_main.py` | 88   |

## How to Explore

1. `context({name: "reload_main_with_env"})` — see callers and callees
2. `query({search_query: "cluster_30"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings
   (source→sink data flows), when indexed with `--pdg`
