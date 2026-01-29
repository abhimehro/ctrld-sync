## 2025-01-29 - Terminal Injection in CLI Tables
**Vulnerability:** User-controlled input (Profile ID) was printed directly to stdout in a summary table, allowing ANSI escape codes to be injected.
**Learning:** Even invalid inputs that are flagged as errors might still be printed to the logs or console for reporting purposes.
**Prevention:** Always sanitize user input before printing to terminal, using a function like `repr()` or stripping control characters, even for "summary" or "error" tables.
