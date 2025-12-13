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
