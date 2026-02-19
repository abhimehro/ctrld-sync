---
description: Guide for API performance optimization and rate limit management
audience: developers working on API integration, performance optimization, and reliability
---

# API Performance Optimization

This guide covers API performance patterns, rate limit management, and optimization strategies specific to ctrld-sync's Control D API integration.

## Rate Limit Management

### Current Implementation

The codebase implements **proactive rate limit monitoring** through HTTP response header parsing:

````python
# Rate limit info is automatically parsed from all API responses
response = _api_get(client, url)
# Headers parsed: X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset
````

**Key headers:**
- `X-RateLimit-Limit`: Total requests allowed per window (e.g., 100/hour)
- `X-RateLimit-Remaining`: Requests left in current window
- `X-RateLimit-Reset`: Unix timestamp when quota resets

### Rate Limit Visibility

Check summary output after sync for rate limit status:

````
API Rate Limit Status:
  • Requests limit:          100
  • Requests remaining:       45 (45.0%)  [color-coded: green/yellow/red]
  • Limit resets at:       14:30:00
````

**Color coding:**
- 🟢 Green: > 50% remaining (healthy)
- 🟡 Yellow: 20-50% remaining (caution)
- 🔴 Red: < 20% remaining (critical)

### 429 (Too Many Requests) Handling

**Retry-After header is honored:**

````python
# When 429 is returned with Retry-After: 30
# The retry logic waits exactly 30 seconds before retrying
# Falls back to exponential backoff if Retry-After is missing
````

**Why this matters:** Respecting `Retry-After` prevents:
- Thundering herd syndrome (multiple clients retrying simultaneously)
- Account bans from aggressive retry patterns
- Wasted CPU/network resources on failed requests

### Thread Pool Sizing Constraints

**CRITICAL:** Worker pool sizes are **NOT** performance tuning parameters. They are **API constraint parameters**.

````python
DELETE_WORKERS = 3  # Conservative for DELETE operations
# Folder processing: max_workers=1 (sequential to prevent 429s)
````

**Never increase worker counts without:**
1. Verifying API rate limits support it
2. Testing with actual API credentials
3. Monitoring 429 response rates

**Common mistake:**
````python
# ❌ DON'T: Increase workers hoping for speed gains
DELETE_WORKERS = 10  # Will trigger 429 errors!

# ✅ DO: Measure actual API latency and adjust batching instead
batch_size = 500  # Reduce per-request overhead
````

## Performance Measurement

### Quick Synthetic Tests

Test individual API operations in isolation:

````python
# Measure single API call latency
import time
start = time.time()
response = _api_get(client, f"{API_BASE}/{profile_id}")
print(f"GET latency: {time.time() - start:.3f}s")
````

### Realistic User Scenarios

Run end-to-end sync with cache instrumentation:

````bash
# Cold start (no cache)
rm -rf ~/.cache/ctrld-sync
time python main.py --profile YOUR_PROFILE

# Warm cache (should be faster)
time python main.py --profile YOUR_PROFILE
````

**Measurement targets:**
- Cold start sync time (first run, downloads all blocklists)
- Warm cache sync time (304 Not Modified for unchanged data)
- API calls per sync operation (check summary output)

### Cache Effectiveness

Monitor cache hit rates in summary output:

````
Cache Statistics:
  • Hits (in-memory):         15
  • Misses (downloaded):       8
  • Validations (304):        23  ← Server confirmed cache is fresh
  • Cache effectiveness:   82.6%  ← Avoided 82.6% of full downloads
````

**High effectiveness (> 80%):** Good! Most blocklists unchanged between runs.
**Low effectiveness (< 30%):** Investigate:
- Are blocklists updating too frequently?
- Is disk cache being cleared?
- Are ETag/Last-Modified headers missing?

## Optimization Strategies

### 1. Batch Size Tuning

Current batch size: **500 rules per request**

**How to adjust:**
````python
# main.py, push_rules()
batch_size = 500  # Empirically chosen to stay under API limits

# To test different sizes:
# 1. Start small (100) and measure
# 2. Increase gradually (200, 400, 500)
# 3. Stop before you see 413 (Payload Too Large) or 429 (Rate Limit)
````

**Trade-off:** Larger batches = fewer API calls but higher risk of limits.

### 2. Connection Pooling

**Already optimized:** Single `httpx.Client` instance reused across operations.

````python
# ✅ Current implementation (correct)
with _api_client() as client:
    for folder in folders:
        _api_get(client, url)  # Reuses connection

# ❌ Anti-pattern (DO NOT DO)
for folder in folders:
    with _api_client() as client:  # New connection each time!
        _api_get(client, url)
````

### 3. Retry Strategy Optimization

**Exponential backoff with jitter** (PR #295) prevents synchronized retry storms.

**When to customize:**
- Transient network issues: Increase `MAX_RETRIES` (default: 3)
- Slow API responses: Increase `RETRY_DELAY` (default: 2s)
- Never decrease for production use

### 4. Proactive Throttling (Advanced)

**Future optimization:** Slow down requests when approaching limits.

````python
# Pseudocode for future implementation
with _rate_limit_lock:
    if _rate_limit_info["remaining"] < 10:
        time.sleep(1)  # Throttle when critically low
````

**Why not implemented yet:** Current workloads don't hit limits. Add only when needed.

## Common Pitfalls

### 1. Ignoring 429 Responses

**Symptom:** Sync fails with "Too Many Requests"  
**Fix:** Check rate limit status in summary, space out syncs

### 2. Over-Parallelizing

**Symptom:** 429 errors despite low overall request volume  
**Fix:** Reduce worker counts, never exceed API-documented limits

### 3. Stale Cache Corruption

**Symptom:** Sync uses outdated rules despite blocklist changes  
**Fix:** Cache invalidation is automatic via ETag/Last-Modified. If issues persist, clear cache: `rm -rf ~/.cache/ctrld-sync`

### 4. Ignoring Summary Statistics

**Symptom:** Unclear why sync is slow  
**Fix:** Always check summary output for:
- Cache effectiveness (should be > 70% for repeated runs)
- Rate limit remaining (should not drop to < 10%)
- Total duration vs. number of folders (identify slow operations)

## Testing Rate Limit Handling

Simulate rate limit scenarios:

````python
# Mock 429 response in tests
mock_response.status_code = 429
mock_response.headers = {
    "Retry-After": "5",
    "X-RateLimit-Remaining": "0"
}

# Verify retry logic respects Retry-After
# See tests/test_rate_limit.py for examples
````

## Further Reading

- **PERFORMANCE.md**: General performance patterns and cache optimization
- **main.py:932**: `_retry_request()` implementation with rate limit handling
- **main.py:653**: `_parse_rate_limit_headers()` parsing logic
- **tests/test_rate_limit.py**: Comprehensive rate limit test suite
