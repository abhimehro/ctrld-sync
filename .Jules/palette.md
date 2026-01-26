## 2024-05-22 - Helpful CLI Prompts
**Learning:** Even in CLI tools, users often get stuck on authentication steps (Tokens/IDs). Providing direct URLs or location hints in the prompt text significantly reduces friction compared to forcing users to consult external docs.
**Action:** When prompting for credentials in CLI tools, always include a "Where to find this" hint or direct URL.

## 2024-05-23 - CLI Progress Bars
**Learning:** Using clear-line ANSI codes (`\033[K`) is significantly more robust than space-padding for overwriting CLI lines, especially when line lengths vary between updates. Visual progress bars (e.g., `[██░░]`) provide better psychological feedback for waiting periods than simple countdowns.
**Action:** Use `\033[K` for dynamic CLI updates and favor visual bars for waits > 5 seconds.

## 2024-05-24 - Fail Fast & Friendly
**Learning:** In CLI tools involving APIs, cascade failures (hundreds of "Failed to X") caused by basic auth issues (401/403) are overwhelming and confusing. A dedicated "Pre-flight Check" that validates credentials *before* attempting the main workload allows for specific, actionable error messages (e.g. "Check your token at [URL]") instead of generic HTTP errors.
**Action:** Implement a `check_api_access()` step at the start of any CLI workflow to validate permissions and provide human-readable guidance on failure.

## 2024-05-25 - Smart Input Extraction
**Learning:** Users often copy full URLs instead of specific IDs because it's easier and they lack context on what exactly defines the "ID". Accepting the full URL and extracting the ID programmatically prevents validation errors and reduces user friction.
**Action:** When asking for an ID that is part of a URL, accept the full URL and extract the ID automatically using regex.
