---
name: gitnexus-area-cluster-2
description: "Skill for the Cluster_2 area of ctrld-sync. 6 symbols across 1 files."
---

# Cluster_2

6 symbols | 1 files | Cohesion: 91%

## When to Use

- Understanding how _extract_int_header, _has_any_rate_limit_headers,
  _has_rate_limit_headers work
- Modifying cluster_2-related functionality

## Key Files

| File            | Symbols                                                                                                                            |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `api_client.py` | _extract_int_header, _has_any_rate_limit_headers, _has_rate_limit_headers, _log_rate_limit_warning, _parse_rate_limit_headers (+1) |

## Key Symbols

| Symbol                        | Type     | File            | Line |
| ----------------------------- | -------- | --------------- | ---- |
| `_extract_int_header`         | Function | `api_client.py` | 125  |
| `_has_any_rate_limit_headers` | Function | `api_client.py` | 161  |
| `_has_rate_limit_headers`     | Function | `api_client.py` | 152  |
| `_log_rate_limit_warning`     | Function | `api_client.py` | 137  |
| `_parse_rate_limit_headers`   | Function | `api_client.py` | 187  |
| `_update_rate_limit_info`     | Function | `api_client.py` | 168  |

## Execution Flows

| Flow                                           | Type            | Steps |
| ---------------------------------------------- | --------------- | ----- |
| `_api_delete → _extract_int_header`            | cross_community | 4     |
| `_api_delete → _has_any_rate_limit_headers`    | cross_community | 4     |
| `_api_delete → _has_rate_limit_headers`        | cross_community | 4     |
| `_api_delete → _update_rate_limit_info`        | cross_community | 4     |
| `_api_post → _extract_int_header`              | cross_community | 4     |
| `_api_post → _has_any_rate_limit_headers`      | cross_community | 4     |
| `_api_post → _has_rate_limit_headers`          | cross_community | 4     |
| `_api_post → _update_rate_limit_info`          | cross_community | 4     |
| `_api_post_form → _extract_int_header`         | cross_community | 4     |
| `_api_post_form → _has_any_rate_limit_headers` | cross_community | 4     |

## How to Explore

1. `context({name: "_extract_int_header"})` — see callers and callees
2. `query({search_query: "cluster_2"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings
   (source→sink data flows), when indexed with `--pdg`
