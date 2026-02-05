## 2024-05-21 - CLI Cursor Hygiene
**Learning:** Hiding the terminal cursor (`\033[?25l`) during progress bar updates eliminates flickering and looks more professional.
**Action:** Always use `atexit` to register a cleanup function that restores the cursor (`\033[?25h`) to prevent leaving the user's terminal in a broken state if the script crashes.
