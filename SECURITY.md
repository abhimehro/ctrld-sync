# Security Policy

## Supported Versions

This project is currently in early development. We provide security updates for the latest release version.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

**Note:** As this is an early-stage project (v0.1.x), the API and security posture may change between releases. We recommend always using the latest version.

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please report it responsibly:

### How to Report

1. **DO NOT** open a public GitHub issue for security vulnerabilities
2. Use GitHub's private security reporting feature by navigating to this repository's **Security** tab and selecting **"Report a vulnerability"**.
3. If that option is not available, email our security contact at `security@example.com`.
4. Include the following in your report:
   - Description of the vulnerability
   - Steps to reproduce the issue
   - Potential impact
   - Suggested fix (if available)

### What to Expect

- **Initial Response:** Within 48-72 hours acknowledging receipt
- **Status Updates:** We'll keep you informed as we investigate and work on a fix
- **Resolution Timeline:** Depends on severity and complexity, typically within 7-14 days for critical issues
- **Credit:** With your permission, we'll acknowledge your contribution in the security advisory and release notes

### Security Best Practices

When using this tool:
- Store your Control D API token securely (use `.env` file, never commit it)
- Keep your Python environment and dependencies up to date
- Review the code before running, especially when syncing to production profiles
- Use dedicated API tokens with minimal necessary permissions
