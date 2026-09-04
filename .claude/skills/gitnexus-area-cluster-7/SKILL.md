---
name: gitnexus-area-cluster-7
description: "Skill for the Cluster_7 area of ctrld-sync. 8 symbols across 2 files."
---

# Cluster_7

8 symbols | 2 files | Cohesion: 88%

## When to Use

- Understanding how get_default_config, load_config,
  set_allowed_blocklist_domains work
- Modifying cluster_7-related functionality

## Key Files

| File            | Symbols                                                                                                                              |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `config.py`     | _load_allowed_blocklist_domains, _read_config_yaml, _resolve_folder_urls, _validate_allowed_blocklist_domains, _validate_config (+2) |
| `validation.py` | set_allowed_blocklist_domains                                                                                                        |

## Entry Points

Start here when exploring this area:

- **`get_default_config`** (Function) — `config.py:88`
- **`load_config`** (Function) — `config.py:229`
- **`set_allowed_blocklist_domains`** (Function) — `validation.py:289`

## Key Symbols

| Symbol                                | Type     | File            | Line |
| ------------------------------------- | -------- | --------------- | ---- |
| `get_default_config`                  | Function | `config.py`     | 88   |
| `load_config`                         | Function | `config.py`     | 229  |
| `set_allowed_blocklist_domains`       | Function | `validation.py` | 289  |
| `_load_allowed_blocklist_domains`     | Function | `config.py`     | 265  |
| `_read_config_yaml`                   | Function | `config.py`     | 173  |
| `_resolve_folder_urls`                | Function | `config.py`     | 299  |
| `_validate_allowed_blocklist_domains` | Function | `config.py`     | 284  |
| `_validate_config`                    | Function | `config.py`     | 155  |

## Execution Flows

| Flow                                                         | Type            | Steps |
| ------------------------------------------------------------ | --------------- | ----- |
| `_resolve_folder_urls → _is_invalid_name`                    | cross_community | 6     |
| `_resolve_folder_urls → _is_invalid_url`                     | cross_community | 6     |
| `_resolve_folder_urls → _is_valid_positive_int`              | cross_community | 5     |
| `_resolve_folder_urls → _validate_allowed_blocklist_domains` | intra_community | 4     |
| `_resolve_folder_urls → _read_config_yaml`                   | intra_community | 3     |
| `_resolve_folder_urls → Set_allowed_blocklist_domains`       | intra_community | 3     |
| `_resolve_folder_urls → Get_default_config`                  | intra_community | 3     |

## How to Explore

1. `context({name: "get_default_config"})` — see callers and callees
2. `query({search_query: "cluster_7"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings
   (source→sink data flows), when indexed with `--pdg`
