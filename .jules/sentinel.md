## 2025-05-27 - Command Injection Risk via os.execv in interactive restart
**Vulnerability:** The script's interactive restart feature used `os.execv(sys.executable, new_argv)` to reload itself. Because `new_argv` was derived directly from `sys.argv`, an attacker who can tamper with the script's arguments (e.g. via an environment variable or wrapper script) could inject malicious python execution flags or sub-commands into the spawned process.
**Learning:** Even in CLI tools where the user fully controls `sys.argv`, using `os.execv` to restart a python process is flagged as an injection risk by Bandit (B606) because it inherently replaces the process using unchecked arguments.
**Prevention:** Rather than using `os.execv` to restart the script, implement the restart logic internally by modifying `sys.argv` in-place and using a `while` loop around the `main()` function. This safely avoids spawning a new process while achieving the exact same UX outcome.
## 2025-06-15 - Un-sanitized Exception Messages in Log Statements
**Vulnerability:** A log statement caught a generic `Exception` during HTTP header parsing and directly embedded `e` into the log string. Since HTTP headers can be attacker-controlled, a malicious server could return crafted headers designed to cause an exception and inject malicious payloads or control characters into the logs.
**Learning:** Even internal exception strings can leak sensitive context or allow log injection if the exception resulted from processing untrusted input.
**Prevention:** Always explicitly wrap dynamic values and caught exceptions `e` in a sanitization function like `sanitize_for_log(e)` before embedding them into any log statements, including `log.debug`.

## $(date +%Y-%m-%d) - [Sanitize Exception Messages]
**Vulnerability:** HTTP client error exception strings contained un-sanitized values (URLs with auth, or tokens in query parameters) when re-raised.
**Learning:** Re-raising an exception like `raise e` without reconstructing it with a sanitized string propagates sensitive data up the call stack, which could leak into tracebacks or uncaught exception handlers.
**Prevention:** Always reconstruct explicitly logged/re-raised `HTTPStatusError` objects using the `sanitize_for_log` equivalent, e.g., `raise httpx.HTTPStatusError(sanitize_fn(str(e)), ...) from e`.
## 2025-06-17 - Exception Chaining Data Leakage
**Vulnerability:** When re-raising sanitized exceptions (like `httpx.HTTPStatusError`), using `from e` attaches the original unsanitized exception to the `__cause__` attribute. This inadvertently leaks sensitive data (such as tokens in URLs or unsanitized original messages) into tracebacks and logging frameworks.
**Learning:** Re-constructing an exception with a sanitized message is insufficient if the original exception is preserved in the exception chain.
**Prevention:** Always explicitly suppress exception chaining by appending `from None` when re-raising a sanitized exception. Ensure you run auto-fixing linters afterward to clean up unused exception variables.
## 2025-06-20 - Exception chaining in generic raises
**Vulnerability:** When a bare `raise` or `raise e` is used at the end of retry loops or catch blocks for `HTTPStatusError`, the exception chain isn't sanitized correctly, which leaks sensitive data in the traceback.
**Learning:** Even explicit re-raises of caught exceptions must ensure that the exception is reconstructed using `sanitize_for_log(str(e))` and explicitly use `from None` to avoid original exception chaining leakage.
**Prevention:** Always check `raise` statements in `except` blocks dealing with `HTTPStatusError`. Use explicit reconstruction and `from None` to break the chain.
## 2025-06-20 - Exception chaining in generic raises (Update)
**Vulnerability:** When a bare `raise` or `raise e` is used at the end of retry loops or catch blocks for `HTTPStatusError`, the exception chain isn't sanitized correctly, which leaks sensitive data in the traceback.
**Learning:** Even explicit re-raises of caught exceptions must ensure that the exception is reconstructed using `sanitize_for_log(str(e))` and explicitly use `from None` to avoid original exception chaining leakage. However, when doing so in a generic fallback block that handles multiple exception types, make sure to ONLY apply `from None` to the sensitive exception types (like `HTTPStatusError`). Applying `raise e from None` to non-sensitive exceptions like `TimeoutException` or `ConnectError` strips the original traceback, making debugging harder.
**Prevention:** Always check `raise` statements in `except` blocks dealing with `HTTPStatusError`. Use explicit reconstruction and `from None` to break the chain, but preserve standard bare `raise` for all other exceptions to maintain debugging context.
