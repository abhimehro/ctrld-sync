# Performance Monitoring Guide

## Overview
This guide covers performance measurement strategies for ctrld-sync, including how to efficiently measure impact, common bottlenecks, and testing approaches.

## Key Performance Metrics

### User-Facing Metrics
- **Cold start sync time**: First run without cache (baseline: ~10-30s for 23 folders)
- **Warm cache sync time**: Subsequent runs with valid cache (target: <5s)
- **API calls per sync**: Total API requests made (fewer is better, measure before/after)
- **Rules processed per second**: Throughput for large rule sets

### System Metrics
- **Cache hit rate**: (hits + validations) / total requests (target: >80% on warm runs)
- **Memory peak usage**: Maximum RSS during sync (baseline: <100MB for typical workloads)
- **API rate limit headroom**: Distance from 429 errors

## Critical Constraints

### API Rate Limits (Non-Negotiable)
The Control D API has strict rate limits. Existing safeguards:
- Serial processing (max_workers=1) to prevent 429 errors
- 60-second wait after deletions to prevent "zombie state"
- Conservative DELETE_WORKERS=3 for parallel deletes
- Batch size of 500 items per request (empirically chosen)

**Never increase parallelism without first implementing rate limit header parsing.**

### Batch Size Rationale
The 500-item batch size is not dynamic. It was chosen through production testing to stay under API limits. Rather than smart batching, focus on better retry logic (exponential backoff with jitter).

## Measurement Strategies

### Quick Synthetic Benchmarks
```bash
# Measure cache effectiveness (after implementation)
python main.py --dry-run  # Should show cache stats

# Measure rule validation performance
pytest tests/test_security.py -v  # Look for slow tests

# Profile memory usage
python -m memory_profiler main.py --dry-run
```

### Realistic User Journey Tests
```bash
# Cold start (clear cache first)
rm -rf ~/.cache/ctrld-sync/blocklists.json
time python main.py --dry-run

# Warm cache (run twice)
time python main.py --dry-run
time python main.py --dry-run  # Second run should be faster
```

### CI Performance Tracking
- Monitor GitHub Actions workflow duration trends
- Track test suite execution time with `pytest --durations=10`
- Use CI artifacts to store timing data across runs

## Common Bottlenecks

### 1. Cold Start Downloads
**Symptom**: Slow first run
**Causes**: 
- Downloading all blocklists from scratch
- No persistent cache or stale cache
**Solutions**:
- ✅ Persistent disk cache with ETag/Last-Modified (implemented)
- ✅ HTTP conditional requests (304 Not Modified) (implemented)
- Future: Parallel DNS validation (deferred due to complexity)

### 2. API Request Overhead
**Symptom**: High latency even with small rule sets
**Causes**:
- Too many small API calls
- No request batching
**Solutions**:
- Batch rule updates (500 items per request)
- Track API call counts to identify inefficiencies
- Connection pooling (httpx already configured)

### 3. Test Suite Duration
**Symptom**: Slow CI runs
**Causes**:
- Sequential test execution
- No dependency caching
**Solutions**:
- ✅ pytest-xdist for parallel execution (implemented)
- ✅ CI pip dependency caching (implemented)

## Performance Engineering Workflow

### 1. Identify Target
Review performance plan discussion and choose specific bottleneck.

### 2. Establish Baseline
Before making changes:
```bash
# Run tests and record timing
pytest --durations=10 > baseline-tests.txt

# Run actual sync and record metrics
python main.py --dry-run > baseline-sync.txt 2>&1
```

### 3. Implement Change
Make focused, minimal changes. Avoid premature optimization.

### 4. Measure Impact
After changes:
```bash
# Compare test timing
pytest --durations=10 > optimized-tests.txt
diff baseline-tests.txt optimized-tests.txt

# Compare sync performance
python main.py --dry-run > optimized-sync.txt 2>&1
diff baseline-sync.txt optimized-sync.txt
```

### 5. Validate Correctness
Ensure tests still pass:
```bash
pytest -n auto  # Parallel test execution
```

## Success Criteria

### For This Optimization (API Call Tracking)
- ✅ API call counter added to global stats
- ✅ Summary output includes "API calls made"
- ✅ No regression in existing tests
- ✅ Non-intrusive implementation (minimal code changes)

### General Performance PR Requirements
- Clear before/after measurements
- No test regressions
- Documentation of trade-offs
- Reproducible test instructions

## Graceful Degradation

Performance optimizations must fail safely:
- Corrupted cache should trigger clean cold start, not crash
- Failed API calls should retry with exponential backoff
- Performance tracking failures should not block sync

## Future Optimization Targets

Based on maintainer priorities:
1. **Performance regression tests**: Automated benchmarks in CI
2. **Improved retry logic**: Exponential backoff with jitter
3. **Memory efficiency**: Streaming for 100k+ rule sets (low priority)
4. **Rate limit header parsing**: Required before any parallelization increase
