# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The authoritative version is defined in [`pyproject.toml`](./pyproject.toml).

---

## [Unreleased]

_No unreleased changes yet._

---

## [0.1.0] — 2026-02-28

Initial working release of `ctrld-sync`, a Python 3.13+ CLI utility that
synchronises Control D DNS filtering folders with remote JSON block-lists via
the Control D REST API.

### Added

**Core functionality**
- Single-file CLI (`main.py`, ~3,200 lines) with `--dry-run`, multi-profile,
  and `--verbose` flags
- YAML config loading via `config.yaml` / `pyyaml`; falls back to environment
  variables (`TOKEN`, `PROFILE`)
- Persistent disk cache with `ETag` / `Last-Modified` validation to skip
  unchanged block-lists on repeat runs
- Memory-efficient streaming for large block-lists (100k+ entries)
- Smart API batching with dynamic batch size tuned to rule complexity
- Exponential backoff with jitter for transient API errors (configurable
  `MAX_RETRIES`)
- Human-readable CLI summary tables with duration formatting (e.g. `2m 5.5s`)

**Security hardening**
- `sanitize_for_log()` — redacts `TOKEN`, Basic-Auth credentials, and
  sensitive query parameters; escapes control characters in log output
- SSRF guard — blocks sync targets that resolve to `localhost` / RFC-1918
  private ranges
- CSV-injection prevention in any output that could be opened as a spreadsheet

**Testing**
- 29 + dedicated test modules under `tests/` covering security, performance,
  cache, config, SSRF, CSV injection, benchmarks, and UX formatting
- `test_main.py` — 30 + integration-style test functions
- `pytest-benchmark` integration for performance regression detection
  (`tests/test_benchmarks.py`)
- `pytest-xdist` enabled for parallel test execution (`-n auto`)
- `pytest-cov` with `fail_under = 55` minimum coverage threshold

**Developer experience**
- `CONTRIBUTING.md` with full setup guide, secrets handling, and PR
  conventions
- `SECURITY.md` with vulnerability reporting policy and supported-version
  table (v0.1.x)
- Pre-commit hooks configuration (`.pre-commit-config.yaml`)
- `uv` as the project package manager; `pyproject.toml` as the single source
  of truth for dependencies and tooling

**CI / automation**
- `test.yml` — pytest on every PR and push to `main` (Python 3.13, xdist)
- `bandit.yml` — SAST scanning for known Python security patterns
- `codacy.yml` — code-quality analysis
- `performance.yml` — benchmark suite with `github-action-benchmark`; alerts
  at > 150 % regression vs. cached baseline
- `sync.yml` — scheduled daily live sync workflow
- Daily QA and Backlog Burner agentic workflows

### Fixed

- Python version mismatch in `copilot-setup-steps.yml` workflow (pinned to
  3.13)
- `SECURITY.md` placeholder version table replaced with accurate `0.1.x` data
- README clone-URL placeholder `your-username` → `abhimehro`
- README reference to non-existent `ci.yml` workflow corrected to `test.yml`

---

[Unreleased]: https://github.com/abhimehro/ctrld-sync/compare/main...HEAD
[0.1.0]: https://github.com/abhimehro/ctrld-sync/tree/main
