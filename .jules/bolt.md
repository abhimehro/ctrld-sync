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

## 2024-05-24 - Deduplicate before API calls
**Learning:** Sending duplicate items in API requests wastes bandwidth and processing time. If the input list might contain duplicates (common in aggregated blocklists), deduplicate it locally before sending.
**Action:** Use `set` logic to filter duplicates from input lists before batching for API calls.

## 2024-05-24 - Parallelize independent batches
**Learning:** When sending large amounts of data in batches to an API, processing batches sequentially blocks on network latency. Using a thread pool to send multiple batches concurrently can significantly speed up the process, provided the API rate limits are respected.
**Action:** Refactor sequential batch processing loops to use `ThreadPoolExecutor` with a conservative number of workers (e.g., 3-5) for write operations.

## 2024-05-24 - Pass Local State to Avoid Redundant Reads
**Learning:** When a process involves modifying remote state (e.g. deleting folders) and then querying it (e.g. getting rules from remaining folders), maintaining a local replica of the state avoids redundant API calls. If you know what you deleted, you don't need to ask the server "what's left?".
**Action:** Identify sequences of "Read -> Modify -> Read" and optimize to "Read -> Modify (update local) -> Use local".

## 2024-05-24 - Parallelize DNS Validation
**Learning:** DNS lookups (`socket.getaddrinfo`) are blocking I/O operations. Performing them sequentially in a list comprehension (e.g., to filter URLs) can be a major bottleneck. Parallelizing them alongside the fetch operation can significantly reduce startup time.
**Action:** Move validation logic that involves network I/O into the parallel worker thread instead of pre-filtering sequentially.

## 2026-01-27 - Redundant Validation for Cached Data
**Learning:** Re-validating resource properties (like DNS/IP) when using *cached content* is pure overhead. If the content is served from memory (proven safe at fetch time), checking the *current* state of the source is disconnected from the data being used.
**Action:** When using a multi-stage pipeline (Warmup -> Process), ensure validation state persists alongside the data cache. Avoid clearing validation caches between stages if the data cache is not also cleared.

## 2026-01-28 - [Thread Pool Overhead on Small Batches]
**Learning:** Creating a `ThreadPoolExecutor` has measurable overhead (thread creation, context switching). For small tasks (e.g., a single batch of API requests), the overhead of the thread pool can exceed the benefit of parallelization, especially when the task itself is just a single synchronous I/O call.
**Action:** Always check if the workload justifies the overhead of a thread pool. For single-item or very small workloads, bypass the pool and execute synchronously.
