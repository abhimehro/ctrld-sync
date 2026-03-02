===== ELIR =====
PURPOSE: Added modern Python 3.10+ type annotations (`dict[str, Any]`, `str | None`) to all functions in `main.py` and enabled `ruff`'s `ANN` check suite to enforce these annotations going forward.
SECURITY: No new logic was added. This only updates documentation and type introspection.
FAILS IF: An argument passes a non-compliant type that trips up static analysis, but shouldn't fail runtime since Python is dynamically typed at execution.
VERIFY: CI tests should pass, as well as `uv run ruff check main.py --select ANN`
MAINTAIN: Going forward, any functions added to `main.py` will require type hints or CI checks using `ruff` will fail.
