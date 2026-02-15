## 2025-01-26 - [Silent Waits in CI]
**Learning:** Long silent waits in CLI tools (especially in CI/non-interactive mode) cause user anxiety about hung processes.
**Action:** Always provide periodic heartbeat logs (e.g. every 10s) for long operations in non-interactive environments.
