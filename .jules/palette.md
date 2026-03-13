## 2025-03-03 - CLI Visual Hierarchy with DIM
**Learning:** Using bright colors like CYAN for secondary or optional CLI text (like hints) creates visual noise that distracts from primary actions. Using the DIM ANSI escape code (`\033[2m`) instead establishes a much clearer visual hierarchy.
**Action:** When designing CLI outputs, reserve bright colors for primary status/data and use DIM for helper text, hints, or optional suggestions.
