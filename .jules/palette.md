## 2024-03-22 - CLI Interactive Fallbacks
**Learning:** CLI tools often fail hard when config is missing, but interactive contexts allow for graceful recovery. Users appreciate being asked for missing info instead of just receiving an error.
**Action:** When `sys.stdin.isatty()` is true, prompt for missing configuration instead of exiting with an error code.
