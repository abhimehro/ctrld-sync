## 2024-05-23 - Reuse HTTP Client in ThreadPoolExecutor
**Learning:** When using `httpx.Client` with `concurrent.futures.ThreadPoolExecutor`, ensure the client context manager encloses the executor context manager (or at least the `submit` calls). The client must remain open while threads are running. Passing a closed client to threads will cause errors.
**Action:** Always structure the context managers as `with client: with executor: ...`.
