---
name: gitnexus-area-cluster-15
description: "Skill for the Cluster_15 area of ctrld-sync. 6 symbols across 1 files."
---

# Cluster_15

6 symbols | 1 files | Cohesion: 43%

## When to Use

- Understanding how _build_cache_entry, _fetch_unconditional,
  _parse_and_cache_response work
- Modifying cluster_15-related functionality

## Key Files

| File           | Symbols                                                                                                         |
| -------------- | --------------------------------------------------------------------------------------------------------------- |
| `gh_client.py` | _build_cache_entry, _fetch_unconditional, _parse_and_cache_response, _parse_json_bytes, _record_cache_miss (+1) |

## Key Symbols

| Symbol                      | Type     | File           | Line |
| --------------------------- | -------- | -------------- | ---- |
| `_build_cache_entry`        | Function | `gh_client.py` | 110  |
| `_fetch_unconditional`      | Function | `gh_client.py` | 192  |
| `_parse_and_cache_response` | Function | `gh_client.py` | 126  |
| `_parse_json_bytes`         | Function | `gh_client.py` | 100  |
| `_record_cache_miss`        | Function | `gh_client.py` | 121  |
| `_validate_content_type`    | Function | `gh_client.py` | 48   |

## How to Explore

1. `context({name: "_build_cache_entry"})` — see callers and callees
2. `query({search_query: "cluster_15"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings
   (source→sink data flows), when indexed with `--pdg`
