---
name: Bug report
about: Report a problem with the ctrld-sync CLI
title: ""
labels: ""
assignees: ""
---

**Describe the bug** A clear and concise description of what went wrong.

**Command** The exact command you ran (redact `TOKEN` / `PROFILE`):

```bash
uv run python main.py --dry-run
```

**To Reproduce**

1. Python / uv versions (`python3 --version`, `uv --version`)
2. Steps from a clean clone (`uv sync --all-extras`, then the command above)
3. Observed output or traceback

**Expected behavior** What you expected to happen instead.

**Environment**

- OS: [e.g. macOS 15 / Ubuntu 24.04]
- Python: [e.g. 3.13.x]
- uv: [e.g. 0.8.x]
- ctrld-sync version or commit: [e.g. 0.1.1 / `git rev-parse --short HEAD`]

**Additional context** Logs, `plan.json` excerpts, or related issues. Do not
paste API tokens or profile IDs.
