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

## 2025-01-24 - [SSRF via DNS Resolution]
**Vulnerability:** The `validate_folder_url` function blocked private IP literals but failed to resolve domain names to check their underlying IPs. An attacker could use a domain (e.g., `local.test`) that resolves to a private IP (e.g., `127.0.0.1`) to bypass the SSRF protection and access internal services.
**Learning:** Blocking IP literals is insufficient for SSRF protection. DNS resolution must be performed to verify that a domain does not resolve to a restricted IP address. Additionally, comprehensive checks are needed for all dangerous IP ranges (private, loopback, link-local, reserved, multicast).
**Prevention:**
1. Resolve domain names using `socket.getaddrinfo` before making requests.
2. Verify all resolved IP addresses against private/loopback/link-local/reserved/multicast ranges.
3. Handle DNS resolution failures securely (fail-closed), catching both `socket.gaierror` and `OSError`.
4. Strip IPv6 zone identifiers before IP validation.
**Known Limitations:**
- DNS rebinding attacks (TOCTOU): An attacker's DNS server could return a safe IP during validation and a private IP during the actual request. This is a fundamental limitation of DNS-based SSRF protection.
