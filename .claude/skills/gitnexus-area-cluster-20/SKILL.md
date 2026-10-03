---
name: gitnexus-area-cluster-20
description: "Skill for the Cluster_20 area of ctrld-sync. 4 symbols across 1 files."
---

# Cluster_20

4 symbols | 1 files | Cohesion: 75%

## When to Use

- Understanding how _build_dry_run_command_str, _print_dry_run_failure,
  _print_dry_run_next_steps work
- Modifying cluster_20-related functionality

## Key Files

| File      | Symbols                                                                                               |
| --------- | ----------------------------------------------------------------------------------------------------- |
| `main.py` | _build_dry_run_command_str, _print_dry_run_failure, _print_dry_run_next_steps, _print_dry_run_success |

## Key Symbols

| Symbol                       | Type     | File      | Line |
| ---------------------------- | -------- | --------- | ---- |
| `_build_dry_run_command_str` | Function | `main.py` | 487  |
| `_print_dry_run_failure`     | Function | `main.py` | 516  |
| `_print_dry_run_next_steps`  | Function | `main.py` | 526  |
| `_print_dry_run_success`     | Function | `main.py` | 506  |

## Execution Flows

| Flow                                              | Type            | Steps |
| ------------------------------------------------- | --------------- | ----- |
| `_print_dry_run_next_steps → _clear_current_line` | cross_community | 4     |

## How to Explore

1. `context({name: "_build_dry_run_command_str"})` — see callers and callees
2. `query({search_query: "cluster_20"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings
   (source→sink data flows), when indexed with `--pdg`
