## 2024-03-25 - [SSRF Protection Gap]
**Vulnerability:** The `validate_folder_url` function checked for private IPs only if the input was an IP literal, allowing domains resolving to private IPs to bypass the check.
**Learning:** `ipaddress.ip_address()` raises `ValueError` for domains, which was caught and ignored. Validating a URL requires resolving the domain to an IP to check network-level access restrictions.
**Prevention:** Always resolve hostnames to IPs when validating against network boundaries (like private vs public networks), and handle DNS resolution failures securely (fail closed).
