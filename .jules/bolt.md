# Bolt's Journal

## 2024-05-23 - Initial Setup
**Learning:** Initialized Bolt's journal.
**Action:** Always check this journal for past learnings before starting.
## 2024-05-23 - Parallel IO for independent resources
**Learning:** Python's `concurrent.futures.ThreadPoolExecutor` is a low-effort, high-reward optimization for independent IO operations (like fetching multiple URLs). Even with standard synchronous libraries like `httpx` (unless using its async version), threading can significantly reduce total execution time from sum(latency) to max(latency).
**Action:** Always look for loops performing IO that don't depend on each other's results and parallelize them. Be mindful of thread safety if shared resources (like a cache) are modified.
