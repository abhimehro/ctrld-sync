## 2026-02-09 - RTLO/Bidi Spoofing in Folder Names

**Vulnerability:** Input validation for folder names allowed Unicode Bidi control characters (e.g., `\u202e`), enabling Homograph/Spoofing attacks (RTLO - Right-To-Left Override).

**Example Attack:** A folder name like `"safe\u202eexe.pdf"` would render as `"safepdf.exe"` in some terminals and UIs, potentially misleading users about file types or content.

**Learning:** Standard "printable" checks (`isprintable()`) do not block Bidi control characters, which can manipulate text direction and visual presentation.

**Prevention:** Explicitly block all known Bidi control characters (U+202A-U+202E, U+2066-U+2069, U+200E-U+200F) in user-visible strings. Also block path separators (/, \) to prevent confusion.

**Implementation:** Pre-compiled character sets at module level for performance, tested comprehensively for all 11 blocked Bidi characters.

## 2026-10-24 - Unbounded Retries on Client Errors (DoS Risk)

**Vulnerability:** The retry logic blindly retried all `httpx.HTTPError` exceptions, including 400 (Bad Request) and 401/403 (Auth failures). This causes API spamming, potential account lockouts, and delays in error reporting.

**Learning:** `httpx.HTTPStatusError` (raised by `raise_for_status()`) inherits from `httpx.HTTPError`. Generic `except httpx.HTTPError:` blocks will catch it and retry client errors unless explicitly handled.

**Prevention:** Inside retry loops, catch `httpx.HTTPStatusError` first. Check `response.status_code`. If `400 <= code < 500` (and not `429`), re-raise immediately.
