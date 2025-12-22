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

## 2024-12-22 - [Sensitive Data Exposure in Logs (Headers)]
**Vulnerability:** The application's  function was insufficient, only escaping characters but not redacting secrets. If an exception occurred that included headers (e.g. ), the  could be exposed in logs.
**Learning:** Generic sanitization (like ) is not enough for secrets. Explicit redaction of known secrets is required.
**Prevention:**
1. Maintain a list of sensitive values (tokens, keys).
2. Ensure logging utilities check against this list and mask values before outputting.

## 2024-12-22 - [Sensitive Data Exposure in Logs (Headers)]
**Vulnerability:** The application's `sanitize_for_log` function was insufficient, only escaping characters but not redacting secrets. If an exception occurred that included headers (e.g. `Authorization`), the `TOKEN` could be exposed in logs.
**Learning:** Generic sanitization (like `repr()`) is not enough for secrets. Explicit redaction of known secrets is required.
**Prevention:**
1. Maintain a list of sensitive values (tokens, keys).
2. Ensure logging utilities check against this list and mask values before outputting.
