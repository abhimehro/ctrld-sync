🎯 **What:** The `_retry_request` function in `api_client.py` was too long and complex. The logic inside the try/except block was extracted into smaller helper functions (`_get_error_hint`, `_log_debug_response_content`, `_handle_rate_limit`, `_check_client_error`).
💡 **Why:** This improves the readability, modularity, and maintainability of `api_client.py`. It also resolves the "Bumpy Road Ahead" / "Brain Method" code smell by reducing cyclomatic complexity.
✅ **Verification:** I ran `uv tool run ruff format .`, `uv tool run ruff check .`, `uv run pytest`, and `uv tool run pre-commit run --all-files`. All checks passed.
✨ **Result:** A simplified `_retry_request` function, making it easier to parse and debug without altering its underlying logic.
