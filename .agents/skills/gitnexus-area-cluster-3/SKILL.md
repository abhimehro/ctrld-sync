---
name: gitnexus-area-cluster-3
description: "Skill for the Cluster_3 area of ctrld-sync. 3 symbols across 1 files."
---

# Cluster_3

3 symbols | 1 files | Cohesion: 100%

## When to Use

- Understanding how main, simulate_retries_with_jitter,
  simulate_retries_without_jitter work
- Modifying cluster_3-related functionality

## Key Files

| File                        | Symbols                                                             |
| --------------------------- | ------------------------------------------------------------------- |
| `benchmark_retry_jitter.py` | main, simulate_retries_with_jitter, simulate_retries_without_jitter |

## Entry Points

Start here when exploring this area:

- **`main`** (Function) — `benchmark_retry_jitter.py:33`
- **`simulate_retries_with_jitter`** (Function) — `benchmark_retry_jitter.py:22`
- **`simulate_retries_without_jitter`** (Function) —
  `benchmark_retry_jitter.py:13`

## Key Symbols

| Symbol                            | Type     | File                        | Line |
| --------------------------------- | -------- | --------------------------- | ---- |
| `main`                            | Function | `benchmark_retry_jitter.py` | 33   |
| `simulate_retries_with_jitter`    | Function | `benchmark_retry_jitter.py` | 22   |
| `simulate_retries_without_jitter` | Function | `benchmark_retry_jitter.py` | 13   |

## How to Explore

1. `context({name: "main"})` — see callers and callees
2. `query({search_query: "cluster_3"})` — find related execution flows
3. Read key files listed above for implementation details
4. `explain({target: "<file or symbol>"})` — persisted taint findings
   (source→sink data flows), when indexed with `--pdg`
