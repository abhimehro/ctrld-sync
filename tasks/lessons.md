# Lessons Learned

## 2026-02-26
- Add preflight bot PR dedupe check: close no-diff bot PRs before deeper review to reduce queue churn.
- Require bot to batch related workflow/test tweaks into one PR per repository to avoid triage collisions.
- Treat unresolved review-thread count as a fast risk signal; high-thread PRs are rarely merge-ready.
- Validate integration token scopes per repository before autonomous sessions (comment/review/close permissions were inconsistent).
