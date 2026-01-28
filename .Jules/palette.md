# Palette's Journal - Critical UX/Accessibility Learnings

## 2024-05-22 - Initial Setup
**Learning:** This journal was created to track UX learnings.
**Action:** Will document impactful UX discoveries here.

## 2024-05-22 - CLI UX: Graceful Exits
**Learning:** Users often use Ctrl+C to exit interactive prompts. Showing a Python traceback is hostile UX.
**Action:** Always wrap interactive CLI entry points in `try...except KeyboardInterrupt` to show a clean "Cancelled" message.
