# Bolt's Journal

## 2024-03-24 - [Reusing HTTP Clients]
**Learning:** Instantiating `httpx.Client` (or `requests.Session`) inside a loop for API calls defeats the purpose of connection pooling and Keep-Alive. Reusing a single client instance across serial or parallel tasks significantly reduces TCP/SSL overhead.
**Action:** Always check loop bodies for client/session instantiation. Lift the instantiation to the outer scope and pass the client down.

## 2024-05-23 - Initial Setup
**Learning:** Initialized Bolt's journal.
**Action:** Always check this journal for past learnings before starting.

## 2024-05-23 - Parallel IO for independent resources
**Learning:** Python's `concurrent.futures.ThreadPoolExecutor` is a low-effort, high-reward optimization for independent IO operations (like fetching multiple URLs). Even with standard synchronous libraries like `httpx` (unless using its async version), threading can significantly reduce total execution time from sum(latency) to max(latency).
**Action:** Always look for loops performing IO that don't depend on each other's results and parallelize them. Be mindful of thread safety if shared resources (like a cache) are modified.

## 2024-05-24 - Thread Safety in Parallel IO
**Learning:** When parallelizing IO operations that update a shared collection (like a set of existing rules), always use a `threading.Lock` for the write operations. While Python's GIL makes some operations atomic, explicit locking ensures correctness and prevents race conditions during complex update logic (e.g. checks then writes).
**Action:** Use `threading.Lock` when refactoring sequential loops into `ThreadPoolExecutor` if they modify shared state.

## 2024-05-24 - Avoid Copying Large Sets for Membership Checks
**Learning:** Copying a large set (e.g. 100k items) to create a snapshot for read-only membership checks is expensive O(N) and unnecessary. Python's set membership testing is thread-safe.
**Action:** When filtering data against a shared large set, iterate and check membership directly instead of snapshotting, unless strict transactional consistency across the entire iteration is required.

## 2025-02-24 - Parallelize Batch Deletions
**Learning:** Sequential deletion of resources (folders) via REST API is a major bottleneck when syncing state, as latency accumulates linearly. Since deletions are independent operations, they can be parallelized safely.
**Action:** Use `ThreadPoolExecutor` to parallelize deletion loops, but limit max_workers (e.g., 5) to avoid rate limits.
