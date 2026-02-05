## 2025-02-18 - [RTLO/Bidi Spoofing in Folder Names]
**Vulnerability:** Input validation for folder names allowed Unicode Bidi control characters (e.g., `\u202e`), enabling Homograph/Spoofing attacks (RTLO).
**Learning:** Standard "printable" checks (`isprintable()`) do not block Bidi control characters, which can be used to mislead users about file extensions or content types.
**Prevention:** Explicitly block known Bidi control characters (U+202A-U+202E, U+2066-U+2069) in user-visible strings.
