# Performance Engineering Guide

This guide documents performance measurement, optimization strategies, and known characteristics for ctrld-sync. Use this to understand how to measure, improve, and maintain performance.

---

## Current Performance Characteristics

### Architecture
- **Thread-based parallelization** with `ThreadPoolExecutor`:
  - Folder URL fetching (concurrent)
  - Folder deletion (3 workers)
  - Rule batch pushing (3 workers)
  - Existing rule fetching (5 workers)
- **Connection pooling** via `httpx.Client` reuse
- **Smart optimizations**:
  - Skips validation for rules already in existing set
  - Bypasses ThreadPoolExecutor for single batches (<500 rules)
  - Pre-compiled regex patterns at module level
  - Ordered deduplication using `dict.fromkeys()`

### Known Constraints
**CRITICAL:** Thread pool sizing (3-5 workers) is constrained by Control D API rate limits, NOT throughput optimization. Increasing worker counts risks 429 (Too Many Requests) errors. Always profile API call patterns before tuning concurrency.

### Typical Performance
- **Small workloads** (10-20 folders, <10k rules): ~30-60 seconds
- **Large workloads** (50+ folders, 50k+ rules): ~2-5 minutes
- **Bottleneck:** Network I/O to Control D API (not CPU)

---

## End-to-End Timing Instrumentation

**Priority #1:** Measure wall-clock time before optimizing anything.

### Quick Timing Decorator

Add to `main.py` for function-level timing:

```python
import time
from functools import wraps

def timed(func):
    """Decorator to measure and log execution time."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        logging.info(f"⏱️  {func.__name__} completed in {elapsed:.2f}s")
        return result
    return wrapper
```

Usage:
```python
@timed
def fetch_folder_data(url: str) -> Dict[str, Any]:
    # existing implementation
```

### Manual Timing for Workflow Stages

For main sync workflow, add checkpoints:

```python
def sync_profile(profile_id: str, client: httpx.Client):
    t0 = time.perf_counter()
    
    # Stage 1: Fetch folders
    t1 = time.perf_counter()
    folders = fetch_all_folders(profile_id, client)
    t2 = time.perf_counter()
    logging.info(f"⏱️  Fetched {len(folders)} folders in {t2-t1:.2f}s")
    
    # Stage 2: Delete folders
    delete_folders(folders, client)
    t3 = time.perf_counter()
    logging.info(f"⏱️  Deleted folders in {t3-t2:.2f}s")
    
    # Stage 3: Push rules
    push_all_rules(folders, client)
    t4 = time.perf_counter()
    logging.info(f"⏱️  Pushed rules in {t4-t3:.2f}s")
    
    logging.info(f"⏱️  TOTAL sync time: {t4-t0:.2f}s")
```

**Why this matters:** Without baseline numbers, every optimization is a guess. Start here.

---

## API Call Tracking

Track API calls as a first-class metric. Reducing calls is the fastest path to cutting sync time.

### Instrumentation Pattern

Add a call counter to your API wrapper:

```python
class APICallTracker:
    def __init__(self):
        self.calls = {"GET": 0, "POST": 0, "DELETE": 0}
        self.lock = threading.Lock()
    
    def record(self, method: str):
        with self.lock:
            self.calls[method] = self.calls.get(method, 0) + 1
    
    def summary(self):
        total = sum(self.calls.values())
        return f"API calls: {total} total ({', '.join(f'{k}:{v}' for k, v in self.calls.items())})"

# Global tracker
api_tracker = APICallTracker()

def _api_get(client, url, **kwargs):
    api_tracker.record("GET")
    # existing implementation

# At end of sync:
log.info(api_tracker.summary())
```

**Target metric:** Calls per 1,000 rules processed. Lower is better.

---

## Performance Testing

### Existing Tests
- `tests/test_push_rules_perf.py`: Validates ThreadPoolExecutor optimization for single vs. multi-batch

### Adding Performance Benchmarks

Create `tests/test_benchmarks.py`:

```python
import time
import pytest
from main import push_rules

@pytest.mark.benchmark
def test_push_rules_benchmark_10k():
    """Benchmark pushing 10,000 rules."""
    hostnames = [f"example{i}.com" for i in range(10_000)]

    # Minimal example setup. In your real tests, reuse the fixtures/setup you use elsewhere,
    # e.g. from tests like `test_push_rules_perf.py`.
    profile_id = "benchmark-profile-id"
    folder_name = "benchmark-folder"
    folder_id = "benchmark-folder-id"

    class DummyClient:
        """
        Placeholder HTTP client for benchmarking example.
        Replace with your real client or test fixture that matches push_rules expectations.
        """
        pass

    mock_client = DummyClient()

    start = time.perf_counter()
    push_rules(profile_id, folder_name, folder_id, 1, 1, hostnames, set(), mock_client)
    elapsed = time.perf_counter() - start
    # Fail if significantly slower than baseline (update threshold after establishing baseline)
    assert elapsed < 30.0, f"10k rules took {elapsed:.2f}s (expected <30s)"
```

Run benchmarks: `pytest tests/test_benchmarks.py -v -m benchmark`

### CI Performance Regression

Keep it simple. Add to `.github/workflows/sync.yml`:

```yaml
- name: Performance smoke test
  run: |
    python - << 'PYCODE'
    import time

    start = time.perf_counter()

    # TODO: Replace this with a real sync_profile(...) call for your project
    # For example, you might trigger a sync with a synthetic 10k-rule profile.
    # The sleep below is just a placeholder to keep this example runnable.
    time.sleep(1)

    elapsed = time.perf_counter() - start
    if elapsed > 60:
        raise Exception(f'Sync too slow: {elapsed:.2f}s')
    print(f'✓ Performance OK: {elapsed:.2f}s')
    PYCODE
```

**Goal:** Catch major regressions (>50% slower), not minor noise.

---

## Optimization Strategies

### What to Profile First

1. **Network I/O** (highest impact): API latency, connection pooling, batch sizes
2. **Concurrency** (medium impact): Worker pool tuning (within rate limits!)
3. **Validation logic** (low impact unless proven bottleneck): Regex, DNS lookups
4. **Data structures** (lowest impact): Already optimized with `dict.fromkeys()` and sets

**Don't optimize validation/batching micro-optimizations without profiling data showing they're the bottleneck.**

### Profiling Commands

CPU profiling:
```bash
python -m cProfile -o profile.stats main.py
python -c "import pstats; p = pstats.Stats('profile.stats'); p.sort_stats('cumulative').print_stats(20)"
```

Memory profiling (for 50k+ rule scenarios):
```bash
python -m memory_profiler main.py
```

### Common Anti-Patterns

❌ **Don't:** Increase thread pool workers without checking API rate limits
✅ **Do:** Profile API call patterns and latency first

❌ **Don't:** Optimize CPU-bound code when network I/O dominates
✅ **Do:** Measure where time is actually spent (use `@timed` decorator)

❌ **Don't:** Add caching without measuring cache hit rates
✅ **Do:** Log cache effectiveness to validate the optimization

---

## Success Metrics

### Primary Metrics
- **End-to-end sync time** (wall clock): Establish baseline, then target meaningful reductions (e.g., 20%+) for typical workloads
- **API calls per sync**: Track and minimize
- **Memory footprint**: Maintain or reduce (especially for 50k+ rules)

### Secondary Metrics
- **Rules processed per second**: Throughput indicator
- **Thread pool efficiency**: CPU utilization during parallel stages
- **Cache hit rates**: Validation and DNS caching effectiveness

### Performance Baseline Checklist

Before claiming an improvement, establish:
- [ ] Baseline timing for 10k, 20k, 50k rule sets
- [ ] API call count for each scenario
- [ ] Memory usage at peak (use `memory_profiler`)
- [ ] Reproducible test environment (same network conditions, API endpoints)

---

## Quick Reference

### Measure Performance
```bash
# Time a sync
time python main.py

# Profile CPU
python -m cProfile -s cumulative main.py | head -30

# Profile memory
python -m memory_profiler main.py
```

### Run Performance Tests
```bash
# Existing optimization tests
pytest tests/test_push_rules_perf.py -v

# Benchmarks (once created)
pytest tests/test_benchmarks.py -v -m benchmark
```

### Check for Regressions
Compare timing logs before/after changes. Look for:
- Increased total sync time (>10% = investigate)
- Increased API call count (any increase = investigate)
- Increased memory usage (for large rule sets)

---

## Next Steps

1. **Add timing instrumentation** to `sync_profile()` and key functions
2. **Establish baseline metrics** for 10k/20k/50k rule sets
3. **Add API call tracking** to all `_api_*` wrappers
4. **Create benchmark tests** for reproducible performance validation
5. **Document findings** in this guide as you learn more

Remember: **Measure twice, optimize once.** Always validate assumptions with data.
