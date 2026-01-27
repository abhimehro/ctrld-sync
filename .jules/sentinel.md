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

## 2024-12-16 - [DoS via Unbounded Response Size]

**Vulnerability:** The `_gh_get` function downloaded external JSON resources without any size limit. A malicious URL or compromised server could serve a massive file (e.g., 10GB), causing the application to consume all available memory (RAM) and crash (Denial of Service).
**Learning:** When fetching data from external sources, never assume the response size is safe. `httpx.get()` (and `requests.get`) reads the entire body into memory by default.
**Prevention:**

1. Use streaming responses (`client.stream("GET", ...)`) when fetching external resources.
2. Inspect `Content-Length` headers if available.
3. Enforce a hard limit on the number of bytes read during the stream loop.

## 2024-12-22 - [Sensitive Data Exposure in Logs (Headers)]

**Vulnerability:** The application's `sanitize_for_log` function was insufficient, only escaping characters but not redacting secrets. If an exception occurred that included headers (e.g. `Authorization`), the `TOKEN` could be exposed in logs.
**Learning:** Generic sanitization (like `repr()`) is not enough for secrets. Explicit redaction of known secrets is required.
**Prevention:**

1. Maintain a list of sensitive values (tokens, keys).
2. Ensure logging utilities check against this list and mask values before outputting.

## 2025-01-21 - [SSRF Protection and Input Limits]

**Vulnerability:** The `folder_url` validation checked for HTTPS but allowed internal IP addresses (e.g., `127.0.0.1`, `10.0.0.0/8`). This could theoretically allow Server-Side Request Forgery (SSRF) if the script is run in an environment with access to sensitive internal services. Additionally, `profile_id` had no length limit.
**Learning:** HTTPS validation alone is insufficient to prevent SSRF against internal services that might support HTTPS or use self-signed certs (if verification was disabled or bypassed). Explicitly blocking private IP ranges provides necessary defense-in-depth.
**Prevention:**

1. Parse URLs and check hostnames against `localhost` and private IP ranges using `ipaddress` module.
2. Enforce strict length limits on user inputs (e.g., profile IDs) to prevent resource exhaustion or buffer abuse.

## 2026-01-17 - [SSRF Protection Enhancement]

**Vulnerability:** The `validate_folder_url` function only checked for IP literals, allowing domains resolving to private IPs (e.g., DNS rebinding or internal domains) to bypass SSRF protection.
**Learning:** Checking `ipaddress.ip_address(hostname)` is insufficient for validation if `hostname` is a domain. DNS resolution is required to validate the actual destination.
**Prevention:**

1. Resolve domains using `socket.getaddrinfo` to obtain the underlying IP addresses.
2. Check all returned IPs against private and loopback ranges.
3. Fail closed (block the URL) if resolution fails or returns any private IP.

## 2026-03-22 - [SSRF Protection Gaps in Python ipaddress]

**Vulnerability:** The standard `ip.is_private` check in Python's `ipaddress` module misses critical ranges like Carrier-Grade NAT (100.64.0.0/10), Link-Local (169.254.0.0/16 in some versions/contexts), and Reserved IPs.
**Learning:** `ip.is_global` (available since Python 3.4) is the correct property for validating public Internet addresses. However, it considers Multicast addresses as "global" (technically true), so explicit `ip.is_multicast` checks are still needed if blocking them is desired.
**Prevention:**

1. Always use `if not ip.is_global or ip.is_multicast:` for strict SSRF filtering, rather than manual blacklists of private ranges.

## 2026-05-14 - [Indirect XSS via Third-Party Data]

**Vulnerability:** The script fetches blocklists (JSON) from external URLs and pushes them to the Control D API. It assumed the content (rules/hostnames) was safe. A compromised or malicious blocklist could contain XSS payloads (e.g., `<script>`) as "rules", which would be stored in the user's profile and potentially executed in the dashboard.
**Learning:** "Trusted" third-party data sources should still be treated as untrusted input when they cross security boundaries (like being stored in a database or displayed in a UI).
**Prevention:**

1. Implement strict validation on all data items from external lists (`is_valid_rule`).
2. Filter out items containing dangerous characters (`<`, `>`, `"` etc.) or control codes.

## 2026-05-15 - [Inconsistent Redaction in Debug Logs]

**Vulnerability:** While `sanitize_for_log` existed, it was not applied to `log.debug(e.response.text)` calls in exception handlers. This meant enabling debug logs could expose raw secrets returned by the API in error messages, bypassing the redaction mechanism.
**Learning:** Security controls (like redaction helpers) must be applied consistently at all exit points, especially in verbose/debug paths which are often overlooked during security reviews.
**Prevention:**

1. Audit all logging calls, especially `DEBUG` level ones, for potential secret exposure.
2. Wrapper functions or custom loggers can help enforce sanitization automatically, reducing reliance on manual application of helper functions.

## 2026-05-18 - [Log Injection via Unsanitized Input]

**Vulnerability:** User-controlled inputs (folder names from JSON, error messages) were logged using f-strings without sanitization. This allowed Terminal Escape Sequence Injection, potentially corrupting terminal output or spoofing log entries.
**Learning:** `repr()` is a powerful, built-in mechanism for sanitizing strings for logs because it escapes control characters (like `\x1b`) by default.
**Prevention:**

1. Identify all log call sites that include user input.
2. Wrap untrusted inputs in a sanitization function (e.g., `sanitize_for_log`) that uses `repr()` or similar escaping mechanisms.
