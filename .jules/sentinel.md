## 2025-04-07 - Add explicit loopback IP check to prevent SSRF bypass
**Vulnerability:** The `_is_safe_ip` function relied primarily on `is_private` and `is_global` properties of Python's `ipaddress` module to prevent SSRF loopback connections. While these often cover `127.0.0.1` and `::1`, edge cases and alternative loopback addresses may bypass these checks depending on OS/network configurations.
**Learning:** Defense-in-depth is essential when validating IPs. Relying solely on `is_private` or `is_global` without explicitly checking `is_loopback` creates potential edge cases where loopback traffic might not be caught, increasing SSRF risk.
**Prevention:** Explicitly check for `is_loopback` along with `is_unspecified` and `is_private` to ensure comprehensive outbound SSRF filtering.

## 2025-04-07 - Add explicit link-local IP check to prevent SSRF bypass
**Vulnerability:** The `_is_safe_ip` function lacked an explicit check for link-local addresses (like `169.254.169.254`, commonly used for cloud metadata services), implicitly relying on `is_global` or `is_private`.
**Learning:** OS-specific network stacks might unexpectedly route link-local addresses or fail to properly classify them as non-global or private. This could allow attackers to bypass SSRF protections and access sensitive internal metadata endpoints.
**Prevention:** Defense-in-depth requires explicitly blocking `ip.is_link_local` alongside `is_loopback`, `is_unspecified`, and `is_private` to ensure complete outbound SSRF filtering.
