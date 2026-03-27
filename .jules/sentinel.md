## 2024-05-24 - DoS Risk from Unrestricted URL Lengths

**Vulnerability:** The application was not enforcing a maximum length limit on parsed folder URLs before validation via `httpx.URL()` and downstream logic. This could allow an attacker to trigger a Denial of Service (DoS) attack by passing excessively long, maliciously crafted URLs designed to exhaust parsing resources.
**Learning:** Even internal tooling is susceptible to resource exhaustion if user input length is not constrained before running relatively complex regexes or parsers.
**Prevention:** Apply a strict max length check (e.g., `MAX_URL_LENGTH = 2048`) on URL strings as the very first operation inside the URL validation function.

## 2024-05-24 - DoS Risk in String Parsing due to Unrestricted Lengths

**Vulnerability:** Several utility functions parsing or validating user-provided strings (`extract_profile_id`, `is_valid_profile_id_format`, `validate_folder_id`, `validate_hostname`) were running complex operations (like regular expressions or DNS lookups) without enforcing an upper length limit on the input first. This could allow for resource exhaustion Denial of Service (DoS) attacks.
**Learning:** Strict input length limits (like `MAX_URL_LENGTH`) must be proactively and consistently enforced across all validation boundaries before any computationally expensive processing (such as regex evaluation or network calls) occurs.
**Prevention:** Add explicit max length bounds to all user-input strings before validation and parsing operations, establishing consistent global constants (`MAX_FOLDER_ID_LENGTH`, `MAX_HOSTNAME_LENGTH`).
