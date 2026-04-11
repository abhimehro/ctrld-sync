## 2025-04-07 - Add explicit loopback IP check to prevent SSRF bypass
**Vulnerability:** The `_is_safe_ip` function relied primarily on `is_private` and `is_global` properties of Python's `ipaddress` module to prevent SSRF loopback connections. While these often cover `127.0.0.1` and `::1`, edge cases and alternative loopback addresses may bypass these checks depending on OS/network configurations.
**Learning:** Defense-in-depth is essential when validating IPs. Relying solely on `is_private` or `is_global` without explicitly checking `is_loopback` creates potential edge cases where loopback traffic might not be caught, increasing SSRF risk.
**Prevention:** Explicitly check for `is_loopback` along with `is_unspecified` and `is_private` to ensure comprehensive outbound SSRF filtering.

## 2025-04-11 - Add explicit link-local IP check to prevent SSRF bypass
**Vulnerability:** The `_is_safe_ip` function relied on `is_private` and `is_global` properties of Python's `ipaddress` module to prevent SSRF connections. While these often cover many internal ranges, edge cases like link-local addresses (e.g. `169.254.169.254`) may bypass these checks depending on OS/network configurations.
**Learning:** Defense-in-depth is essential when validating IPs. Relying solely on `is_private` or `is_global` without explicitly checking `is_link_local` creates potential edge cases where link-local traffic might not be caught, increasing SSRF risk (e.g. to cloud metadata services).
**Prevention:** Explicitly check for `is_link_local` along with `is_unspecified`, `is_loopback` and `is_private` to ensure comprehensive outbound SSRF filtering.
