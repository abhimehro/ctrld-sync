# Palette's Journal

## 2025-12-24 - Interactive CLI Configuration
**Learning:** CLI tools often fail hard when configuration is missing, but interactive sessions provide an opportunity to recover by asking the user for input. This turns a "crash" into a "setup wizard".
**Action:** When required env vars are missing, check `sys.stdin.isatty()` and prompt the user before exiting.
