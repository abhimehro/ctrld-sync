# ELIR Handoff — ABHI-1481 SSRF domain allowlisting

## Purpose

Close residual SSRF attack surface for user-controlled blocklist URLs by
completing the deny-by-default domain allowlist (`yokoffing.github.io`) and
pinning Control D API traffic to `api.controld.com` only.

## Security

- **Threat:** CWE-918 SSRF via config/`--folder-url` outbound fetches, and
  accidental/injected non-API destinations for Control D HTTP wrappers.
- **Controls:** Blocklist allowlist (HTTPS + domain match + existing IP/DNS
  checks); API host pin in `_assert_api_url` before every `_api_*` call;
  `controld.com` intentionally excluded from blocklist allowlist.
- **Trust boundary:** Config/CLI URLs are untrusted; `API_BASE` remains
  code-controlled and is now also enforced at the client wrapper.

## Failure Modes

| Failure                                     | Consequence                                      | Mitigation                                                          |
| ------------------------------------------- | ------------------------------------------------ | ------------------------------------------------------------------- |
| New legitimate blocklist host needed        | Fetch rejected                                   | Add via `allowed_blocklist_domains` or expand defaults after review |
| Typo in API URL construction                | Hard `ValueError` before request                 | Fail closed; fix caller                                             |
| Subdomain confusion (`evil.com.github.com`) | Rejected by exact/`endswith(f".{domain}")` match | Covered by existing matcher                                         |

## Review Checklist

- [ ] Defaults include `yokoffing.github.io` and exclude `controld.com`
- [ ] `api_client._assert_api_url` rejects HTTP / non-`api.controld.com`
- [ ] SSRF + API tracking tests green
- [ ] Docs (`README`, `config.yaml.example`, `SECURITY.md`) match behavior

## Maintenance

- To trust a new blocklist origin: prefer config override; only change
  `DEFAULT_ALLOWED_BLOCKLIST_DOMAINS` after security review.
- Never add `controld.com` to the blocklist allowlist — keep API pinning in
  `ALLOWED_API_HOSTS`.
