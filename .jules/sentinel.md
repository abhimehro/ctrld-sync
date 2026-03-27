## 2024-05-24 - DoS Risk from Unrestricted URL Lengths
**Vulnerability:** The application was not enforcing a maximum length limit on parsed folder URLs before validation via `httpx.URL()` and downstream logic. This could allow an attacker to trigger a Denial of Service (DoS) attack by passing excessively long, maliciously crafted URLs designed to exhaust parsing resources.
**Learning:** Even internal tooling is susceptible to resource exhaustion if user input length is not constrained before running relatively complex regexes or parsers.
**Prevention:** Apply a strict max length check (e.g., `MAX_URL_LENGTH = 2048`) on URL strings as the very first operation inside the URL validation function.
