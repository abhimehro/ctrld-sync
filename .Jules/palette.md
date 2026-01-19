## 2024-05-22 - Helpful CLI Prompts
**Learning:** Even in CLI tools, users often get stuck on authentication steps (Tokens/IDs). Providing direct URLs or location hints in the prompt text significantly reduces friction compared to forcing users to consult external docs.
**Action:** When prompting for credentials in CLI tools, always include a "Where to find this" hint or direct URL.

## 2024-05-23 - CLI Progress Bars
**Learning:** Using clear-line ANSI codes (`\033[K`) is significantly more robust than space-padding for overwriting CLI lines, especially when line lengths vary between updates. Visual progress bars (e.g., `[██░░]`) provide better psychological feedback for waiting periods than simple countdowns.
**Action:** Use `\033[K` for dynamic CLI updates and favor visual bars for waits > 5 seconds.
