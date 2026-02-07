# Sentinel's Journal

## 2025-02-07 - Secure File Creation Pattern
**Vulnerability:** Default `open()` creates files with user umask, which might allow group/world read access for sensitive files like `plan.json`.
**Learning:** Python's `open()` mode `w` respects `umask` but doesn't enforce restrictive permissions by default. `os.chmod` after creation leaves a small race condition window.
**Prevention:** Use `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)` to create the file descriptor with correct permissions atomically, then wrap with `os.fdopen()`.
