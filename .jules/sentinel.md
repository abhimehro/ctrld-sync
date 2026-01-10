# Sentinel's Journal

## 2025-01-20 - SSRF Vulnerability in URL Validation
**Vulnerability:** The `validate_folder_url` function checked for explicit localhost strings and IP literals but failed to resolve domain names. This allowed attackers to bypass SSRF protection by using a domain name that resolves to a private IP (e.g., `local.example.com` -> `127.0.0.1`).
**Learning:** Checking hostnames against a blocklist is insufficient because DNS resolution decouples the name from the IP. `ipaddress` library only validates literals.
**Prevention:** Always resolve the hostname to an IP address and check the resolved IP against private ranges (`is_private`, `is_loopback`) before making a request. Be aware of TOCTOU (Time-of-Check Time-of-Use) issues like DNS rebinding, though basic resolution is a good first line of defense.
