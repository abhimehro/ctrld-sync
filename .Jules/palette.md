## 2025-01-26 - [Silent Waits in CI]
**Learning:** Long silent waits in CLI tools (especially in CI/non-interactive mode) cause user anxiety about hung processes.
**Action:** Always provide periodic heartbeat logs (e.g. every 10s) for long operations in non-interactive environments.

## 2025-02-14 - [ASCII Fallback for Tables]
**Learning:** Using Unicode box drawing characters enhances the CLI experience, but a robust ASCII fallback is crucial for CI environments and piped outputs.
**Action:** Always implement a fallback mechanism (like checking `sys.stderr.isatty()`) when using rich text or Unicode symbols.

## 2025-02-28 - [Interactive Restart]
**Learning:** Reconstructing command arguments manually for process restarts is brittle and breaks forward compatibility.
**Action:** When restarting a CLI tool with modified flags (e.g., removing `--dry-run`), filter `sys.argv` instead of rebuilding the argument list from parsed args.
