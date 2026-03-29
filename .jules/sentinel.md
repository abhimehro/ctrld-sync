## 2025-03-05 - DoS Prevention via Length Limits
**Vulnerability:** Expensive operations like URL parsing (`httpx.URL`), Regex pattern matching (`re.match`), and network lookups (`socket.getaddrinfo`) were vulnerable to Denial of Service via resource exhaustion from inputs without maximum length caps.
**Learning:** Checking lengths after executing these operations, or omitting length checks completely, allows an attacker to tie up thread pool workers and CPU cycles by submitting massively long strings.
**Prevention:** Always enforce strict maximum length limits (e.g., `MAX_URL_LENGTH = 2048`, `MAX_HOSTNAME_LENGTH = 253`) on user-provided strings *prior* to parsing, matching, or network resolution.
