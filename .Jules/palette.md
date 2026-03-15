## 2025-01-26 - [Silent Waits in CI]
**Learning:** Long silent waits in CLI tools (especially in CI/non-interactive mode) cause user anxiety about hung processes.
**Action:** Always provide periodic heartbeat logs (e.g. every 10s) for long operations in non-interactive environments.

## 2025-02-14 - [ASCII Fallback for Tables]
**Learning:** Using Unicode box drawing characters enhances the CLI experience, but a robust ASCII fallback is crucial for CI environments and piped outputs.
**Action:** Always implement a fallback mechanism (like checking `sys.stderr.isatty()`) when using rich text or Unicode symbols.

## 2025-02-28 - [Interactive Restart]
**Learning:** Reconstructing command arguments manually for process restarts is brittle and breaks forward compatibility.
**Action:** When restarting a CLI tool with modified flags (e.g., removing `--dry-run`), filter `sys.argv` instead of rebuilding the argument list from parsed args.

## 2025-03-05 - [CLI Progress Line Residue]
**Learning:** When using carriage return (`\r`) to animate CLI progress bars or countdowns, shrinking strings (e.g., transitioning from "10s" to "9s") leave visible ghost characters (residue) at the end of the line if not explicitly cleared.
**Action:** Always prefix carriage-return updates with the ANSI clear-line sequence (`\033[K`) to ensure the entire line is cleanly re-rendered.

## 2025-03-05 - [CLI Empty States]
**Learning:** Presenting a simple "Nothing to do" message when an operation is empty leaves the user without guidance.
**Action:** When presenting empty states in the CLI (e.g., no items to process), always provide actionable hints or call-to-actions, such as suggesting relevant CLI flags or configuration edits.

## 2025-03-12 - [Visual Hierarchy in CLI]
**Learning:** Using bright colors (like CYAN) for both primary actions and secondary hints creates visual noise and makes it harder for users to focus on what matters.
**Action:** Use DIM ANSI escape codes (\033[2m) for secondary or optional CLI text (like hints and follow-up instructions) to establish a clear visual hierarchy and reduce noise.

## 2025-03-12 - [Interactive Prompt Forgiveness]
**Learning:** When prompting users to press Enter to continue or Ctrl+C to cancel, users will often instinctively type "n", "no", or "quit" and press Enter. Ignoring this input and proceeding anyway leads to accidental and potentially destructive actions. Furthermore, prompts without a trailing space cause user input to visually collide with the prompt text.
**Action:** Always add a trailing space to input prompts, and gracefully intercept common cancellation strings (e.g., "n", "no", "quit") even if the explicit instruction only mentions Ctrl+C.
