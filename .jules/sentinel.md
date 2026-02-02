## 2025-10-26 - Trusting API IDs
**Vulnerability:** IDOR / Path Traversal risk if API returns unsafe IDs.
**Learning:** Even "trusted" upstream APIs can be compromised or buggy. Trust nothing.
**Prevention:** Validate all resource IDs (PKs) from APIs against a strict whitelist before using them in local operations or downstream requests.
