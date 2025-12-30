# Palette's Journal

## 2024-10-18 - CLI UX Adaptation
**Learning:** When a "frontend" agent encounters a CLI-only repo, the "interface" becomes the terminal output. Accessibility principles (contrast, readability, clear feedback) still apply but translate to ANSI colors, clear spacing, and descriptive log messages instead of ARIA labels.
**Action:** Adapting web-centric UX patterns (like "toast notifications") to CLI equivalents (colored log lines or summary tables).

## 2025-02-18 - Visual Feedback in CLI Tables
**Learning:** CLI summary tables are the "dashboard" of a command-line tool. Missing visual cues (like color-coding status) in these tables reduces scannability, just like a dashboard widget without status indicators.
**Action:** Always check if status indicators in CLI output are visually distinct (colored) to improve "glanceability" of the results.

## 2025-02-24 - Visual Countdowns for Long Waits
**Learning:** Static logs for long wait times (>5s) look like the process has hung. A simple countdown timer on the same line provides reassurance and feedback.
**Action:** Replace `time.sleep(n)` with `_wait_with_feedback(n)` for any wait longer than 5 seconds in interactive CLIs.
