## 2026-01-29 - CLI UX Patterns
**Learning:** CLI tools often suffer from "duplicate feedback" where a validator logs an error AND the input loop prints a generic error.
**Action:** Silence the generic error if the validator provides specific feedback, or direct the user to the specific errors.
