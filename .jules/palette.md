## 2025-01-26 - [Silent Waits in CI]

**Learning:** Long silent waits in CLI tools (especially in CI/non-interactive
mode) cause user anxiety about hung processes. **Action:** Always provide
periodic heartbeat logs (e.g. every 10s) for long operations in non-interactive
environments.

## 2025-02-14 - [ASCII Fallback for Tables]

**Learning:** Using Unicode box drawing characters enhances the CLI experience,
but a robust ASCII fallback is crucial for CI environments and piped outputs.
**Action:** Always implement a fallback mechanism (like checking
`sys.stderr.isatty()`) when using rich text or Unicode symbols.

## 2025-02-28 - [Interactive Restart]

**Learning:** Reconstructing command arguments manually for process restarts is
brittle and breaks forward compatibility. **Action:** When restarting a CLI tool
with modified flags (e.g., removing `--dry-run`), filter `sys.argv` instead of
rebuilding the argument list from parsed args.

## 2025-03-05 - [CLI Progress Line Residue]

**Learning:** When using carriage return (`\r`) to animate CLI progress bars or
countdowns, shrinking strings (e.g., transitioning from "10s" to "9s") leave
visible ghost characters (residue) at the end of the line if not explicitly
cleared. **Action:** Always prefix carriage-return updates with the ANSI
clear-line sequence (`\033[K`) to ensure the entire line is cleanly re-rendered.

## 2025-03-05 - [CLI Empty States]

**Learning:** Presenting a simple "Nothing to do" message when an operation is
empty leaves the user without guidance. **Action:** When presenting empty states
in the CLI (e.g., no items to process), always provide actionable hints or
call-to-actions, such as suggesting relevant CLI flags or configuration edits.

## 2025-03-12 - [Visual Hierarchy in CLI]

**Learning:** Using bright colors (like CYAN) for both primary actions and
secondary hints creates visual noise and makes it harder for users to focus on
what matters. **Action:** Use DIM ANSI escape codes (\033[2m) for secondary or
optional CLI text (like hints and follow-up instructions) to establish a clear
visual hierarchy and reduce noise.

## 2025-03-12 - [Interactive Prompt Forgiveness]

**Learning:** When prompting users to press Enter to continue or Ctrl+C to
cancel, users will often instinctively type "n", "no", or "quit" and press
Enter. Ignoring this input and proceeding anyway leads to accidental and
potentially destructive actions. Furthermore, prompts without a trailing space
cause user input to visually collide with the prompt text. **Action:** Always
add a trailing space to input prompts, and gracefully intercept common
cancellation strings (e.g., "n", "no", "quit") even if the explicit instruction
only mentions Ctrl+C.

## 2025-03-24 - [Input Prompt Collision]

**Learning:** When prompting users for input via generic wrappers (e.g.,
`input()` or `getpass()`), if the prompt string lacks a trailing space, the
user's typed input will visually collide with the prompt text, creating a poor
aesthetic and confusing UX. **Action:** Always append a trailing space
automatically to prompt strings in generic input handler functions if one is not
provided by the caller.

## 2025-03-24 - [Generic Input Cancellation Safety]

**Learning:** While intercepting strings like "n" or "no" for cancellation in
interactive boolean prompts (e.g., "Ready to launch?") is good UX, applying this
same interception logic universally to _generic_ input functions (like
`get_validated_input` or `get_password`) introduces severe functional and
security regressions. A user whose valid answer is "no" or whose password
happens to match a cancellation string will be unexpectedly booted from the
application. **Action:** Confine string-based cancellation interception to
specific, appropriate contexts (like interactive confirmations). For generic
input and password fields, rely solely on standard interrupt signals (Ctrl+C /
Ctrl+D).

## 2024-04-15 - Uncolored Constant Embeddings

**Learning:** Hardcoding static ANSI color constants into string properties
(e.g. `EMPTY_INPUT_HINT = f" {Colors.DIM}💡 Hint...{Colors.ENDC}"`) breaks the
fallback display formatting when NO_COLOR is set, because evaluating
`Colors.DIM` occurs _before_ `USE_COLORS` resolves appropriately during import,
or simply creates issues in non-interactive environments where emojis and hints
get completely stripped out if a lazy developer adds them conditionally.
Instead, the actual hints should be clean strings (with emojis intact), and they
should be passed to a helper function like `_print_hint` that explicitly wraps
the output in colors _only_ if `USE_COLORS` is true. **Action:** When adding
static string constants to the module level or passing them around, never embed
`Colors.XXX` directly. Instead, maintain pure strings and apply styling logic at
the exact point of printing via conditional checks (`if USE_COLORS`). This
ensures emojis and semantic information are preserved as uncolored text for
fallback modes while keeping the CLI pretty when allowed.

## 2024-04-15 - Semantic Emojis in No-Color Fallbacks

**Learning:** When stripping ANSI colors for fallback modes (e.g., `NO_COLOR=1`
or non-TTY environments), it's a common mistake to accidentally strip semantic
emojis along with the color formatting. Emojis provide vital scannability and
context that users rely on when color cues are absent. **Action:** Always ensure
that `if USE_COLORS` else blocks preserve emojis in the uncolored strings. Never
treat emojis as part of the "color decoration" to be discarded.

## 2025-05-18 - [CLI Empty State UI]

**Learning:** When displaying data tables or CLI interfaces that fall back to
placeholders for empty or unsaved state (e.g., `dry-run-placeholder` internally
used when no profile is given), leaking the literal placeholder string creates
an unpolished and confusing UX. **Action:** Always intercept placeholder
constants at the UI boundary and render them as clean, human-readable strings
like `(Unspecified)` or `(None)`.

## 2025-06-13 - [CLI Empty State UI]

**Learning:** When displaying data tables or CLI interfaces that calculate
widths for alignment (e.g., using `len()` for padding calculations), emojis and
full-width characters cause misalignment because they occupy 2 columns in the
terminal but count as 1 character in Python's `len()`. **Action:** Always use a
custom display width calculation (like `unicodedata.east_asian_width` or
`_display_len`) when calculating padding around strings that may contain emojis
or full-width characters to ensure perfect alignment.

## 2025-03-04 - CLI Table Alignment with Emojis

**Learning:** Python's standard `len()` and f-string padding mechanisms fail to
correctly align CLI tables when dealing with emojis and full-width characters.
These characters typically take 2 terminal columns but count as 1 character in
standard string length calculations, causing visual misalignment. **Action:**
Use a custom display width calculation leveraging `unicodedata.east_asian_width`
to manually calculate and apply padding lengths for strings containing emojis or
CJK characters.

## 2025-10-24 - [CLI Table Alignment with ANSI Codes]

**Learning:** Python calculates width by character count. ANSI color escape
sequences take 0 columns, breaking border alignment. **Action:** Fix this by
stripping ANSI escape sequences (e.g., via regex
`\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])`) and using a custom display width
calculation to accurately measure visual padding.

## 2025-03-03 - CLI Plan Details Alignment Fix

**Learning:** Python's standard `len()` and format alignment (`:<`) calculate
widths by raw character count, causing visual misalignment in CLI tables when
strings contain emojis or full-width characters (which take 2 visual columns but
count as 1). **Action:** When printing structured CLI output like dry-run plan
details, use a custom display width calculation (like `_display_len` via
`unicodedata`) and custom padding logic (like `_pad_string`) instead of relying
on standard f-string formatting.

## 2024-06-29 - CLI Table Alignment with Emojis

**Learning:** Standard Python `len()` calculates string length based on
character count, which treats emojis (like ✅, ⛔, 🧪) as 1 character. However,
terminal emulators render these specific symbols as 2 columns wide. If strings
with emojis are padded using `len()`, the table borders will misalign. Using
`unicodedata.east_asian_width` helps, but many emojis return `N` (Neutral) or
`A` (Ambiguous) for east asian width while still being rendered as 2 columns by
the terminal. **Action:** When building custom CLI tables that pad text
containing emojis, calculate the display width manually by extending the width
check to include `So` (Symbol, Other) or `Sk` (Symbol, Modifier) unicode
categories with a codepoint > 0x2000.

## 2025-10-25 - [Terminal Residue in Non-Interactive Mode]

**Learning:** When handling `KeyboardInterrupt` or `EOFError` during long
operations, explicitly clearing the terminal line using ANSI sequences
(`\r\033[K`) without checking if the environment is a TTY
(`sys.stderr.isatty()`) leaks visible ANSI garbage into non-interactive
execution logs (like CI or piped output). **Action:** Always guard terminal
clearance codes and carriage returns with a `sys.stderr.isatty()` check, even if
global color settings (`USE_COLORS`) are theoretically supposed to cover it, as
`USE_COLORS` might be overridden or misused in edge cases.

## 2025-10-25 - [Cyclomatic Complexity from Nested Formatting Checks]

**Learning:** When separating formatting logic (like TTY vs colors) within
complex, hot paths (like rule pushing), introducing deeply nested `if/else`
conditionals rapidly increments cyclomatic complexity and triggers CodeScene
`Complex Method` failures. **Action:** Always favor early guard clauses (e.g.,
`if not sys.stderr.isatty(): return`) and flatten text assignment blocks before
output to reduce branching depth and keep logic clean.

## 2025-10-25 - [Terminal Residue When Colors Disabled]

**Learning:** When handling `KeyboardInterrupt` or `EOFError` during long
operations, tying the terminal line clearance using ANSI sequences (`\r\033[K`)
strictly to a color configuration flag (`USE_COLORS`) instead of just TTY
detection (`sys.stderr.isatty()`) means that disabling colors leaves visible
ghost characters (`^C`) in the interactive shell. **Action:** Always base
terminal clearance codes on TTY detection (`sys.stderr.isatty()`), regardless of
whether global color output is enabled or disabled.

## 2025-10-25 - [Terminal Residue Clean-Up on Cancellation]

**Learning:** In interactive CLI flows where input is cancelled (e.g. `input()`
raising `KeyboardInterrupt`), printing a cancellation message directly leaves
awkward extraneous blank lines if the cancellation message contains a leading
newline or if the `^C` symbol isn't correctly wiped first. Additionally, the
cancellation message shouldn't introduce extra vertical space that disrupts the
terminal flow. **Action:** When handling `KeyboardInterrupt` or `EOFError`,
clear the line using `\r\033[K` (guarded by `sys.stderr.isatty()`), and print a
concise cancellation message without leading newlines to maintain a clean
terminal state. [K`(guarded by`sys.stderr.isatty()`), and print a concise
cancellation message without leading newlines to maintain a clean terminal
state.

## 2026-07-05 - [Terminal Residue Clean-Up on Cancellation]

**Learning:** In interactive CLI flows where input is cancelled (e.g. `input()`
raising `KeyboardInterrupt`), printing a cancellation message directly leaves
awkward extraneous blank lines if the prompt string contains a leading newline,
which breaks terminal clearing logic (`\r\033[K`) by displacing the cursor.
**Action:** When printing vertical spacing before interactive prompts, print it
structurally using an explicit `print()` rather than embedding a leading newline
(`\n`) directly in the prompt string.

## 2023-11-09 - [Safe Substring Removal in ANSI Strings]

**Learning:** Using index slicing (`string[:idx] + string[idx+1:]`) to remove
substrings (like newlines) from strings that contain ANSI escape codes is
fragile and can lead to unintended removals if the string structure changes or
is miscalculated, potentially breaking the prompt output or corrupting the
escape codes. **Action:** When removing specific characters from strings that
may contain ANSI escape sequences, use `.replace(char, "", 1)` to safely and
precisely target the first occurrence of the character without relying on
hardcoded indices.

## 2026-08-01 - [Visual Hierarchy in Terminal Output]

**Learning:** When displaying multiple blocks of statistical data in the
terminal (like API calls, cache hits, rate limits), using bold text alone for
section headers isn't enough to make the data quickly scannable, especially when
the surrounding text is dense. **Action:** Always add semantic emojis (like 📊,
⚡, 🚦) to the start of statistical or categorical section headers. Emojis act
as strong visual anchors, allowing users to instantly locate the information
they need in a dense CLI output.

## 2026-07-19 - [Terminal Color Hardcoding]

**Learning:** When displaying data tables or CLI interfaces, hardcoding ANSI
escape codes (e.g. `Colors.BOLD`) without checking if `USE_COLORS` is active
creates an unpolished and confusing UX in environments where colors are disabled
or unsupported (like CI pipelines or when NO_COLOR is set). **Action:** Always
check `USE_COLORS` before embedding ANSI escape codes in CLI output, and provide
a clean fallback string (e.g., maintaining semantic emojis but dropping the
`Colors` attributes) to ensure graceful degradation. Prefer a small helper (e.g.
`_print_bold_header`) so the call site does not gain cyclomatic complexity.

## YYYY-MM-DD - [CLI Table Alignment with Unicode/Emojis]

**Learning:** Using standard string length formatting (e.g. `:<` or `^`) inside
f-strings fails when text contains emojis or full-width characters (like ✅ or
📋) because standard calculations evaluate their width as 1 character while
terminals render them as 2 columns. **Action:** When printing tables or
structured outputs, use custom padding functions (like `_pad_string`) for all
table content that could contain emojis or unicode characters to ensure exact
column alignment.

## 2025-10-25 - [CLI Batch Operation Feedback]

**Learning:** When executing batch operations in a CLI tool, grouping partial
successes (e.g., where `0 < success_count < total`) under a generic 'Errors'
status provides inaccurate feedback and can cause unnecessary user alarm.
**Action:** Implement a dedicated '⚠️ Partial' status (using `Colors.WARNING` or
similar) to provide nuanced feedback for partial successes in batch operations.

## 2026-10-24 - [CLI Command Suggestions]

**Learning:** When generating and suggesting CLI commands to users for
subsequent execution (e.g., 'next steps' after a dry run), omitting custom
context-specific flags (such as `--config` or `--no-delete`) that the user
initially provided creates a dangerous UX. If the user blindly copy-pastes the
suggested command, they might unintentionally run with default settings or
execute destructive operations. **Action:** Always reconstruct suggested
follow-up commands by preserving all relevant user-provided arguments and
context flags to ensure safety and predictability.

## 2026-07-31 - Visual hierarchy in CLI prompts
**Learning:** Found an opportunity to improve visual hierarchy in CLI prompts by utilizing `Colors.DIM` for secondary/optional text (hints). This makes it easier for users to scan the primary action required, reducing visual noise.
**Action:** Use `Colors.DIM` to style secondary instructions in prompts such as `_get_interactive_restart_confirmation` in `main.py`.

## 2026-08-01 - [Visual Hierarchy for Auto-Appended Hints]
**Learning:** When auto-appending informative hints (like "(typing will be hidden)") to CLI prompts, appending them as plain text can cause them to blend in with the primary instruction, reducing visual hierarchy.
**Action:** Use `Colors.DIM` (conditionally checking `USE_COLORS`) to style auto-appended secondary instructions, making them visually distinct from the main prompt while remaining accessible.

## 2026-08-01 - [Visual Polish for Progress Bars]
**Learning:** The unfilled portion of progress bars ("·" characters) can visually compete with the filled portion when rendered in the same color, reducing the scannability of the progress state.
**Action:** Apply `Colors.DIM` to the unfilled portion of CLI progress bars and countdown timers to create better contrast and a more polished, intuitive visual hierarchy.

## 2026-08-02 - [Visual Hierarchy for CLI Prompts]
**Learning:** When a CLI input field supports complex or multiple values (e.g., comma-separated), proactively including a formatting hint directly in the prompt is helpful, but if appended as plain text, it competes with the primary instruction.
**Action:** Use `Colors.DIM` to style secondary instructions or format hints in CLI prompts, reducing visual noise and establishing a clear hierarchy while remaining accessible.
