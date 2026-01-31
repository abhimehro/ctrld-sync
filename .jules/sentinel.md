## 2025-02-18 - [Preventing SSRF via DNS Rebinding with Post-Connect Verification]
**Vulnerability:** Validation of URLs checks the resolved IP, but `httpx` re-resolves the domain during connection, allowing a TOCTOU (Time-of-Check Time-of-Use) attack where the IP changes to a private one (DNS Rebinding).
**Learning:** Standard URL validation is insufficient against sophisticated attackers controlling DNS. Checking the IP *after* the connection is established (using `stream.get_extra_info("server_addr")`) is a robust defense because it verifies the actual endpoint used.
**Prevention:** Always verify the peer/server address after connection establishment when making requests to untrusted or user-controlled URLs, especially when preventing access to internal resources.
