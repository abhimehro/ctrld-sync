## 2024-05-23 - [Input Validation and Syntax Fix]
**Vulnerability:** The `create_folder` function contained a syntax error (positional arg after keyword arg) preventing execution. Additionally, `folder_url` and `profile_id` lacked validation, potentially allowing SSRF (via non-HTTPS URLs) or path traversal/injection (via crafted profile IDs).
**Learning:** Even simple scripts need robust input validation, especially when inputs are used to construct URLs or file paths. A syntax error can mask security issues by preventing the code from running in the first place.
**Prevention:**
1. Always validate external inputs against a strict allowlist (e.g., regex for IDs, protocol check for URLs).
2. Use linters/static analysis to catch syntax errors before runtime.

## 2024-12-13 - [Sensitive Data Exposure in Logs]
**Vulnerability:** The application was logging full HTTP response bodies at ERROR level when requests failed. This could expose sensitive information (secrets, PII) returned by the API during failure states.
**Learning:** Defaulting to verbose logging in error handlers (e.g., `log.error(e.response.text)`) is risky because API error responses often contain context that should not be persisted in production logs.
**Prevention:**
1. Log sensitive data (like full request/response bodies) only at DEBUG level.
2. Sanitize or truncate log messages if they must be logged at higher levels.

## 2024-12-15 - [Sensitive Data Exposure in Logs]
**Vulnerability:** The application was logging full HTTP error response bodies at `ERROR` level. API error responses can often contain sensitive data like tokens, PII, or internal debug info.
**Learning:** Default logging configurations can lead to data leaks if raw response bodies are logged without sanitization or level checks.
**Prevention:**
1. Log potentially sensitive data (like raw HTTP bodies) only at `DEBUG` level.
2. At `INFO`/`ERROR` levels, log only safe summaries or status codes.

## 2025-01-20 - [DoS Protection via Response Size Limit]
**Vulnerability:** The application fetched external JSON resources without any size limits using `httpx.get()`, which loads the entire response into memory. A malicious or compromised server could serve a very large file, causing the application to crash due to memory exhaustion (OOM).
**Learning:** Trusting external resources to be "reasonable" in size is a risk. HTTP clients often buffer full responses by default. Streaming responses and enforcing a byte limit is necessary for robust file downloads.
**Prevention:**
1. Use streaming APIs (e.g., `client.stream("GET", ...)`) when downloading files.
2. Enforce a strict `MAX_RESPONSE_SIZE` and abort the download if the limit is exceeded.
3. Handle encoding/JSON parsing errors gracefully to prevent application crashes.
