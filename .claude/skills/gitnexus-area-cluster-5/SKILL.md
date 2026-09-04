---
name: gitnexus-area-cluster-5
description: "Skill for the Cluster_5 area of ctrld-sync. 4 symbols across 1 files."
---

# Cluster_5

4 symbols | 1 files | Cohesion: 86%

## When to Use

- Understanding how _is_invalid_name, _is_invalid_url, _validate_folder_entry
  work
- Modifying cluster_5-related functionality

## Key Files

| File        | Symbols                                                                      |
| ----------- | ---------------------------------------------------------------------------- |
| `config.py` | _is_invalid_name, _is_invalid_url, _validate_folder_entry, _validate_folders |

## Key Symbols

| Symbol                   | Type     | File        | Line |
| ------------------------ | -------- | ----------- | ---- |
| `_is_invalid_name`       | Function | `config.py` | 105  |
| `_is_invalid_url`        | Function | `config.py` | 101  |
| `_validate_folder_entry` | Function | `config.py` | 124  |
| `_validate_folders`      | Function | `config.py` | 117  |

## Execution Flows

| Flow                                      | Type            | Steps |
| ----------------------------------------- | --------------- | ----- |
| `_resolve_folder_urls → _is_invalid_name` | cross_community | 6     |
| `_resolve_folder_urls → _is_invalid_url`  | cross_community | 6     |

## How to Explore

1. `context({name: "_is_invalid_name"})` — see callers and callees
2. `query({search_query: "cluster_5"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings
   (source→sink data flows), when indexed with `--pdg`
