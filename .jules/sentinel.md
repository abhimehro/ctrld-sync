## 2025-05-23 - URL Credential Leakage in Logs
**Vulnerability:** `sanitize_for_log` only redacted the API token but allowed URLs containing Basic Auth credentials (e.g. `https://user:pass@host`) to be logged in plain text.
**Learning:** Sanitization functions often focus on known secrets (like specific tokens) but miss pattern-based leaks like standard URI credentials.
**Prevention:** Always scrub user:password combinations from any URL before logging. Use regex or URL parsing libraries to identifying and redact the authority section.
