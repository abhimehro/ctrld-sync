# Palette's Journal

## 2024-10-18 - CLI UX Adaptation
**Learning:** When a "frontend" agent encounters a CLI-only repo, the "interface" becomes the terminal output. Accessibility principles (contrast, readability, clear feedback) still apply but translate to ANSI colors, clear spacing, and descriptive log messages instead of ARIA labels.
**Action:** Adapting web-centric UX patterns (like "toast notifications") to CLI equivalents (colored log lines or summary tables).

## 2025-02-18 - Visual Feedback in CLI Tables
**Learning:** CLI summary tables are the "dashboard" of a command-line tool. Missing visual cues (like color-coding status) in these tables reduces scannability, just like a dashboard widget without status indicators.
**Action:** Always check if status indicators in CLI output are visually distinct (colored) to improve "glanceability" of the results.

## 2025-05-21 - Graceful CLI Interruption
**Learning:** Users often interrupt long-running CLI processes (syncs). Standard stack traces are scary and unhelpful. Providing a "partial summary" upon interruption respects the user's time and provides closure.
**Action:** Wrap main loops in `try/except KeyboardInterrupt` to show what was accomplished before the user cancelled.
