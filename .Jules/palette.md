## 2024-05-22 - [CLI Table Micro-UX]
**Learning:** Even in CLI tools, consistent formatting and human-readable units (like duration) significantly reduce cognitive load. Encapsulating UI logic (tables) into dedicated functions prevents code duplication and makes 'visual polish' easier to maintain.
**Action:** When refactoring CLI scripts, look for inline print blocks that can be extracted into reusable components, especially for complex outputs like tables.
