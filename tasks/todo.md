# ABHI-1481: SSRF domain allowlisting

**Route:** T1+S+H
**Threat model:** User-controlled blocklist URLs (config/CLI) drive outbound HTTPS fetches. Existing IP/hostname checks reduce risk; deny-by-default domain allowlisting shrinks the residual attack surface. Control D API base is hardcoded but should be host-pinned for defense in depth.

**Trust boundaries:**
- Untrusted: `folders[].url`, `--folder-url`, `allowed_blocklist_domains` config
- Trusted (code-controlled): `API_BASE` → `api.controld.com` only
- Not allowlisted for blocklists: `controld.com` (API only per issue)

## Checklist

- [x] Add `yokoffing.github.io` to `DEFAULT_ALLOWED_BLOCKLIST_DOMAINS`
- [x] Pin Control D API requests to `api.controld.com` in `api_client.py`
- [x] Keep `controld.com` out of blocklist allowlist (API-only)
- [x] Update `config.yaml.example` + README allowlist docs
- [x] Add/extend SSRF tests (allowlisted + rejected + API host pin)
- [x] Run pytest SSRF/security suite + ruff
- [x] ELIR handoff + commit/push/PR (#1025)
- [x] Update Linear ABHI-1481 (+ related ABHI-1366)
