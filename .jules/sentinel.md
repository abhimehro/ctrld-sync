## 2026-02-09 - RTLO/Bidi Spoofing in Folder Names

**Vulnerability:** Input validation for folder names allowed Unicode Bidi control characters (e.g., `\u202e`), enabling Homograph/Spoofing attacks (RTLO - Right-To-Left Override).

**Example Attack:** A folder name like `"safe\u202eexe.pdf"` would render as `"safepdf.exe"` in some terminals and UIs, potentially misleading users about file types or content.

**Learning:** Standard "printable" checks (`isprintable()`) do not block Bidi control characters, which can manipulate text direction and visual presentation.

**Prevention:** Explicitly block all known Bidi control characters (U+202A-U+202E, U+2066-U+2069, U+200E-U+200F) in user-visible strings. Also block path separators (/, \) to prevent confusion.

**Implementation:** Pre-compiled character sets at module level for performance, tested comprehensively for all 11 blocked Bidi characters.
