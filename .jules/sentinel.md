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

## 2026-02-09 - Insecure Symlink Follow in Permission Fix

**Vulnerability:** The `check_env_permissions` function used `os.chmod` on `.env` without checking if it was a symlink. An attacker could symlink `.env` to a system file (e.g., `/etc/passwd`), causing the script to change its permissions to 600, leading to Denial of Service or security issues. Additionally, `fix_env.py` overwrote `.env` insecurely, allowing arbitrary file overwrite via symlink.

**Learning:** `os.chmod` and `open()` follow symlinks by default in Python (and most POSIX environments).

**Prevention:** Always use `os.path.islink()` to check for symlinks before modifying file metadata or content if the path is user-controlled or in a writable directory. Use `os.open` with `O_CREAT | O_WRONLY | O_TRUNC` and `os.chmod(fd)` on the file descriptor to avoid race conditions (TOCTOU) and ensure operations apply to the file itself, not a symlink target.

## 2026-10-24 - TOCTOU Race Condition in File Permission Checks

**Vulnerability:** The `check_env_permissions` function checked for symlinks (`os.path.islink`) and then modified permissions (`os.chmod`) using the file path. This created a Time-of-Check Time-of-Use (TOCTOU) race condition where an attacker could swap the file with a symlink between the check and the modification.

**Learning:** Path-based checks (`os.path.islink`, `os.stat`) followed by path-based operations (`os.chmod`) are inherently racy. File descriptors are the only way to pin the resource.

**Prevention:** Use `os.open` with `O_NOFOLLOW` to open the file securely (failing if it's a symlink). Then use file-descriptor-based operations: `os.fstat(fd)` to check modes and `os.fchmod(fd, mode)` to modify permissions. This ensures operations apply to the exact inode opened.
