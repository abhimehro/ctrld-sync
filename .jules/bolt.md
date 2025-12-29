## 2024-05-24 - Python Thread Safety with httpx
**Learning:** `httpx.Client` is thread-safe and can be reused across threads. Reusing the client in a threaded application (even with `max_workers=1`) significantly reduces connection overhead (TCP/SSL) compared to creating a new client per task.
**Action:** When working with threaded workers that make API calls, instantiate the HTTP client once in the main thread and pass it to workers, ensuring it is properly closed after all workers finish.
