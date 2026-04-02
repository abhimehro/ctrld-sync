# PR Triage Findings

## Exact / High-Confidence Duplicates

- `abhimehro/ctrld-sync#395` duplicates test-workflow scope now represented by `#402` (newer, passing).
- `abhimehro/ctrld-sync#399` and `#405` duplicate the newer parallel-pytest workflow variant `#406`.
- `abhimehro/email-security-pipeline#372` semantically overlaps nested-archive fix in `#381`; marked duplicate of the newer security-focused PR.

## Superseded PRs (No Net Diff vs Base)

- `abhimehro/ctrld-sync#397` has `changedFiles=0`; treated as superseded/already absorbed.
- `abhimehro/email-security-pipeline#370` has `changedFiles=0`; treated as superseded/already absorbed.
- `abhimehro/email-security-pipeline#371` has `changedFiles=0`; treated as superseded/already absorbed.
- `abhimehro/email-security-pipeline#373` has `changedFiles=0`; treated as superseded/already absorbed.
- `abhimehro/personal-config#379` has `changedFiles=0`; treated as superseded/already absorbed.
- `abhimehro/personal-config#380` has `changedFiles=0`; treated as superseded/already absorbed.
- `abhimehro/personal-config#382` has `changedFiles=0`; treated as superseded/already absorbed.
- `abhimehro/personal-config#383` has `changedFiles=0`; treated as superseded/already absorbed.
- `abhimehro/personal-config#387` has `changedFiles=0`; treated as superseded/already absorbed.
- `abhimehro/personal-config#390` has `changedFiles=0`; treated as superseded/already absorbed.

## Conflicting PRs

- `abhimehro/ctrld-sync#394` currently reports merge conflicts and requires manual rebase.
- `abhimehro/email-security-pipeline#381` currently reports merge conflicts and requires manual rebase.

## Stale PR Check

- No PR met stale criteria (`>30 days`, no activity, and failing CI).

## Permission Boundary Encountered

- This integration can read PR metadata and enable auto-merge in `abhimehro/ctrld-sync`, but cannot close PRs, add review comments, or request changes (`Resource not accessible by integration`).
- Cross-repo write permissions are inconsistent: auto-merge enabled in `ctrld-sync`, denied in `email-security-pipeline` and `personal-config`.
