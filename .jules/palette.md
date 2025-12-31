## 2024-02-14 - Interactive CLI Configuration
**Learning:** CLI tools often fail hard on missing config, but interactive fallbacks turn a configuration error into a guided setup.
**Action:** When required config is missing in a CLI, check `isatty()` and prompt the user instead of exiting.
