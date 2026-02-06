# Palette's Journal

## 2025-05-15 - CLI Dependency Experience
**Learning:** Users often run scripts directly (`python main.py`) without setting up the environment, leading to intimidating traceback errors (`ModuleNotFoundError`).
**Action:** Wrap external imports in `try/except` blocks to provide friendly, actionable instructions (e.g., "Please run `uv sync`") instead of raw stack traces.
