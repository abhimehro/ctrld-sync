## 2025-03-21 - Escape Hatches in Interactive Error States
**Learning:** During interactive CLI loops, providing an escape hatch (like `Ctrl+C to cancel`) only for empty inputs traps users who repeatedly enter invalid data and become frustrated. Errors should also present the cancellation instructions.
**Action:** Consistently append cancellation guidance (`EMPTY_INPUT_HINT`) to error messages for invalid inputs in input-validation loops, and proactively flush `sys.stdout`/`sys.stderr` before all `input()`/`getpass()` prompts to ensure visibility.
