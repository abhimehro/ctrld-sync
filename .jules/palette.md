# Palette's Journal

## 2024-10-24 - Progress Bar in Parallel Tasks
**Learning:** When using `concurrent.futures`, standard logging can interfere with progress bars. The `render_progress_bar` implementation relies on `\r` to overwrite the line, but if another thread logs to stderr/stdout, it can break the visual.
**Action:** Always wrap logging calls inside the parallel loop with a line-clearing sequence (`\r\033[K`) if a progress bar is active.

## 2024-10-24 - Duplicate Function Definitions
**Learning:** Duplicate function definitions in Python (later overwrites earlier) can be confusing for static analysis or human reviewers, even if the runtime behavior is well-defined.
**Action:** Always scan for and remove duplicate definitions when refactoring to avoid confusion.
