## PALETTE'S JOURNAL - CRITICAL LEARNINGS ONLY

This journal is for recording critical UX/accessibility learnings.

---

## 2024-05-23 - CLI Progress Bars in Parallel Operations
**Learning:** Adding visual feedback (progress bars) to parallel operations (like `ThreadPoolExecutor`) requires careful management of `stderr`. Standard logging (`logging.warning`) can interfere with `\r` carriage returns used for progress bars.
**Action:** Always clear the line (`\r\033[K`) before logging warnings inside a progress-tracked loop, and redraw the progress bar afterwards if necessary.
