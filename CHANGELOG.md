# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Python 3.13+ type annotations on all public functions in `main.py`
- `pytest-benchmark` integration for performance regression detection (`tests/test_benchmarks.py`)
- YAML configuration file support via `config.yaml` / `config.yml` (loaded with `PyYAML`)
- `CHANGELOG.md` to track version history

### Changed
- Validation functions now use explicit `return True` to prevent implicit `None` returns

## [0.1.0] - 2026-02-01

### Added
- Initial release: single-file CLI (`main.py`) for syncing Control D DNS folders with remote JSON block-lists
- Disk cache for folder data to reduce redundant API calls
- SSRF protection for remote URL fetching
- CSV injection prevention in log output via `sanitize_for_log()`
- Multi-profile support via comma-separated `PROFILE` environment variable
- `--dry-run` mode for planning syncs without making API calls
- `SECURITY.md` vulnerability reporting policy
- Comprehensive pytest-based test suite (`tests/`)
- GitHub Actions workflows for daily sync, security scanning (Bandit, Codacy), and CI tests
- `CONTRIBUTING.md` development guide
- `PERFORMANCE.md` benchmarking notes

[Unreleased]: https://github.com/abhimehro/ctrld-sync/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/abhimehro/ctrld-sync/releases/tag/v0.1.0
