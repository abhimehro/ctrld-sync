# Palette's Journal

## 2024-10-18 - CLI UX Adaptation
**Learning:** When a "frontend" agent encounters a CLI-only repo, the "interface" becomes the terminal output. Accessibility principles (contrast, readability, clear feedback) still apply but translate to ANSI colors, clear spacing, and descriptive log messages instead of ARIA labels.
**Action:** Adapting web-centric UX patterns (like "toast notifications") to CLI equivalents (colored log lines or summary tables).

## 2025-02-18 - Visual Feedback in CLI Tables
**Learning:** CLI summary tables are the "dashboard" of a command-line tool. Missing visual cues (like color-coding status) in these tables reduces scannability, just like a dashboard widget without status indicators.
**Action:** Always check if status indicators in CLI output are visually distinct (colored) to improve "glanceability" of the results.

## 2025-05-23 - Interactive Wait States
**Learning:** Long static sleeps (like 60s) in CLIs cause "is it hung?" anxiety for users. Static logs aren't enough for long pauses.
**Action:** Always use a countdown or progress indicator for waits > 5s to provide reassurance of activity.
## 2024-03-22 - CLI Interactive Fallbacks
**Learning:** CLI tools often fail hard when config is missing, but interactive contexts allow for graceful recovery. Users appreciate being asked for missing info instead of just receiving an error.
**Action:** When `sys.stdin.isatty()` is true, prompt for missing configuration instead of exiting with an error code.

## 2025-06-15 - Managing Visual Noise
**Learning:** Adding progress bars to verbose/chatty CLI processes (streams of logs) creates visual clutter and flickering. It's better to keep progress bars for "silent" wait states (like cache warming) and leave verbose processes as streams.
**Action:** Only implement progress bars for phases that are otherwise silent or have low log volume; avoid them for high-frequency logging loops.
