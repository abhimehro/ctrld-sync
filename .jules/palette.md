## 2025-05-23 - Interactive Wait States
**Learning:** Long static sleeps (like 60s) in CLIs cause "is it hung?" anxiety for users. Static logs aren't enough for long pauses.
**Action:** Always use a countdown or progress indicator for waits > 5s to provide reassurance of activity.

## 2024-03-22 - CLI Interactive Fallbacks
**Learning:** CLI tools often fail hard when config is missing, but interactive contexts allow for graceful recovery. Users appreciate being asked for missing info instead of just receiving an error.
**Action:** When `sys.stdin.isatty()` is true, prompt for missing configuration instead of exiting with an error code.

## 2024-03-24 - Active Waiting Feedback
**Learning:** Even short recurring waits (like polling retries) can feel unresponsive if they only show a static log message. A "spinner" or countdown makes the CLI feel alive and working.
**Action:** Replace static `sleep()` loops with visual countdowns in interactive modes, while preserving logs for non-interactive/audit modes.
