# Bolt's Journal

## 2024-05-23 - Initial Setup
**Learning:** Initialized Bolt's journal.
**Action:** Always check this journal for past learnings before starting.
## 2024-05-23 - Parallel IO for independent resources
**Learning:** Python's `concurrent.futures.ThreadPoolExecutor` is a low-effort, high-reward optimization for independent IO operations (like fetching multiple URLs). Even with standard synchronous libraries like `httpx` (unless using its async version), threading can significantly reduce total execution time from sum(latency) to max(latency).
**Action:** Always look for loops performing IO that don't depend on each other's results and parallelize them. Be mindful of thread safety if shared resources (like a cache) are modified.
## 2024-05-24 - Thread Safety in Parallel IO
**Learning:** When parallelizing IO operations that update a shared collection (like a set of existing rules), always use a `threading.Lock` for the write operations. While Python's GIL makes some operations atomic, explicit locking ensures correctness and prevents race conditions during complex update logic (e.g. checks then writes).
**Action:** Use `threading.Lock` when refactoring sequential loops into `ThreadPoolExecutor` if they modify shared state.
