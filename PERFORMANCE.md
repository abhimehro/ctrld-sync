# Performance Engineering Guide

This guide documents performance measurement, optimization strategies, and known
characteristics for ctrld-sync.

> **Note:** This file lives in the repository root for visibility. Copilot-specific
> detail also appears in
> `.github/copilot/instructions/performance-monitoring.md` and
> `api-performance.md`; keep those aligned when you change behaviour here.

---

## Current Performance Characteristics

### Architecture

- **Thread-based parallelization** with `ThreadPoolExecutor`:
  - Folder URL fetching (concurrent via sync plan helpers)
  - Folder deletion (`DELETE_WORKERS` = 3 in `config.py`)
  - Rule batch pushing (4 workers in `sync/batches.py`)
  - Existing rule fetching (5 workers in `sync/rules.py`)
  - Per-profile folder processing is serial (`max_workers=1` in `sync/profile.py`)
- **Connection pooling** via reused `httpx.Client`
- **Smart optimizations**:
  - Skips validation for rules already in the existing set
  - Bypasses extra batch parallelism for small single-batch pushes
  - Pre-compiled regex patterns at module level
  - Ordered deduplication using `dict.fromkeys()`

### Known Constraints

**CRITICAL:** Worker counts are constrained by Control D API rate limits, not
CPU throughput. Increasing parallelism without rate-limit headroom risks 429
errors. Profile API call patterns before tuning concurrency.

### Typical Performance

- **Small workloads** (10–20 folders, <10k rules): on the order of tens of seconds
- **Large workloads** (50+ folders, 50k+ rules): on the order of minutes
- **Bottleneck:** Network I/O to the Control D API (not CPU)

---

## Measurement

### End-to-end timing

Add wall-clock checkpoints around major sync stages (fetch folders, delete,
push rules) before micro-optimizing. Without baselines, every change is a guess.

### API call tracking

Tests in `tests/test_api_tracking.py` assert API usage patterns; when changing
sync paths, keep call counts stable or justify increases.

---

## Performance Tests (in repo)

| Asset | Purpose |
| ----- | ------- |
| `tests/test_benchmarks.py` | pytest-benchmark (`.github/workflows/performance.yml`) |
| `tests/test_performance_regression.py` | Hot-path mean-time guards |
| `tests/test_push_rules_perf.py` | ThreadPoolExecutor single vs multi-batch |
| `cache/benchmark-data.json` | Baseline JSON for GitHub benchmark action |

Run locally:

```bash
uv run pytest tests/test_push_rules_perf.py -v
uv run pytest tests/test_performance_regression.py --benchmark-only
uv run pytest tests/test_benchmarks.py --benchmark-only
```

CI runs the benchmark workflow on changes to the tests above and
`cache/benchmark-data.json`.

---

## Optimization Priorities

1. **Network I/O and API call count** (highest impact)
2. **Concurrency** (within rate limits; see `DELETE_WORKERS` and batch workers)
3. **Validation logic** (optimize only if profiling shows it on the hot path)
4. **Micro-optimizations** (lowest priority)

Profiling:

```bash
uv run python -m cProfile -o profile.stats main.py
uv run python -c "import pstats; p = pstats.Stats('profile.stats'); p.sort_stats('cumulative').print_stats(20)"
```

---

## Success Metrics

- End-to-end sync time for representative profiles (baseline, then regressions)
- API calls per sync (fewer is better unless behaviour requires more)
- Benchmark CI trend (`performance.yml` + `cache/benchmark-data.json`)

Before claiming an improvement: reproduce on the same dry-run or test fixtures,
compare benchmark output, and watch for new 429s in live runs.
