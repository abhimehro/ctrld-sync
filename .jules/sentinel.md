## 2025-02-12 - Broken Security Logic via Syntax Errors
**Vulnerability:** Input validation logic in `main.py` was completely disabled due to severe syntax errors (e.g., `rgi"rules"1`) and garbled code. This made the application unrunnable but also highlighted how "dead code" can hide security gaps.
**Learning:** Security controls (like input validation) must be syntactically valid and reachable to be effective. Automated tools (linters) or running the code would have caught this immediately.
**Prevention:** Always run the application or tests after modifying code. Use linters/formatters in CI/CD to catch syntax errors before they merge.
