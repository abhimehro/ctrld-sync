## 2024-05-22 - CLI Dry-Run Visibility
**Learning:** Users running destructive CLI tools (sync/delete) rely heavily on dry-run output to trust the tool. Providing high-level stats is insufficient; showing exactly *what* will be affected (e.g., specific folder names and actions) reduces anxiety and prevents errors.
**Action:** When implementing `--dry-run`, always list the specific entities that would be created, modified, or deleted, not just counts.
