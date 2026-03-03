# Submitting a Pull Request

## Summary

Closes #

## Branch Naming

Use a short, descriptive name:

- [ ] `fix/<short-description>` for bug fixes
- [ ] `feat/<short-description>` for new features
- [ ] `docs/<short-description>` for documentation changes
- [ ] `chore/<short-description>` for maintenance tasks

## Before Opening a PR

Run the following in order:

1. **Full test suite:** `uv run pytest tests/ -v`
2. **Linter:** `ruff check .`
3. **Pre-commit hooks:** `uv run pre-commit run --all-files`

## PR Description

### What Changed and Why

Include:

- A summary of what changed and why
- How to test or verify the change
- Any relevant issue numbers (e.g., `Closes #123`)

## Security Implications

- [ ] No secrets or credentials are introduced or exposed by this change

**Security notes:**

## Checklist

- [ ] Branch follows naming convention (`fix/<short-description>`, `feat/<short-description>`, `docs/<short-description>`, `chore/<short-description>`, etc.)
- [ ] Commit messages are clear and descriptive
- [ ] New or modified code includes relevant tests
- [ ] Pre-commit hooks pass (`uv run pre-commit run --all-files`)
- [ ] Documentation updated if behaviour changed (README, docstrings, etc.)
- [ ] No secrets, credentials, tokens, profiles, or `.env` files are included in this PR

---

## Secrets

`TOKEN` (Control D API token) and `PROFILE` (profile ID) are required only for live runs against the API.

- **Never commit these values to source control.**
- Store them in a `.env` file at the project root (already listed in `.gitignore`):

```env
TOKEN=your_control_d_api_token
PROFILE=your_profile_id
```

- For GitHub Actions, add them as repository secrets under **Settings, Secrets and variables, Actions**.
