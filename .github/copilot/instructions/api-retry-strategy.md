# API Retry Strategy Guide

## Performance Context

Control D API has strict rate limits. The sync tool retries failed requests with exponential backoff to handle transient failures (network issues, temporary server errors) while respecting API constraints.

## Current Implementation

**Location:** `main.py::_retry_request()` (line ~845)

**Key characteristics:**
- Max retries: 10 attempts (configurable via `MAX_RETRIES`)
- Base delay: 1 second (configurable via `RETRY_DELAY`)
- Exponential backoff: `delay * (2^attempt)` → 1s, 2s, 4s, 8s, 16s, ...
- Smart error handling: Don't retry 4xx errors except 429 (rate limit)
- Security-aware: Sanitizes error messages in logs

## Jitter Pattern (Recommended)

**Why jitter matters:**
When multiple requests fail simultaneously (e.g., API outage), synchronized retries create "thundering herd" - all clients retry at exact same time, overwhelming the recovering server. Jitter randomizes retry timing to spread load.

**Implementation formula:**
```python
import random
wait_time = (delay * (2 ** attempt)) * (0.5 + random.random())
```

This adds ±50% randomness: a 4s backoff becomes 2-6s range.

**Maintainer rationale (from discussion #219):**
> "API rate limits are non-negotiable. Serial processing exists because I got burned by 429s and zombie states in production. Any retry improvement needs rock-solid rate limit awareness."

## Testing Approach

**Unit tests:**
- Verify jitter stays within bounds (0.5x to 1.5x base delay)
- Confirm 4xx errors (except 429) still don't retry
- Check max retries still respected

**Integration tests:**
- Simulate transient failures (mock server returning 500s)
- Measure retry timing distribution (should show variance)
- Confirm eventual success after transient errors

**Performance validation:**
No performance degradation expected - jitter adds microseconds of `random()` overhead per retry, negligible compared to network I/O.

## Common Pitfalls

1. **Don't add jitter to initial request** - only to retries. First attempt should be immediate.
2. **Don't exceed max backoff** - cap total wait time to prevent indefinite delays.
3. **Don't jitter 429 responses** - these return `Retry-After` headers; respect those instead.
4. **Don't break existing behavior** - ensure 4xx non-retryable errors still fail fast.

## Future Improvements

- **Rate limit header parsing:** Read `Retry-After` from 429 responses instead of exponential backoff
- **Circuit breaker:** Stop retrying after consecutive failures to prevent cascading failures
- **Per-endpoint tracking:** Different backoff strategies for read vs. write operations
