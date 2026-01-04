## 2024-03-24 - [Reusing HTTP Clients]
**Learning:** Instantiating `httpx.Client` (or `requests.Session`) inside a loop for API calls defeats the purpose of connection pooling and Keep-Alive. Reusing a single client instance across serial or parallel tasks significantly reduces TCP/SSL overhead.
**Action:** Always check loop bodies for client/session instantiation. Lift the instantiation to the outer scope and pass the client down.
