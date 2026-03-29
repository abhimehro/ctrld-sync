## 2024-05-24 - [Avoid Redundant Dictionary Lookups for Deletion]
**Learning:** Checking for key existence before deleting it (`if key in dict: del dict[key]`) requires two dictionary lookups.
**Action:** Use `dict.pop(key, None)` instead to remove a key with a single operation, avoiding KeyError and the redundant lookup overhead.
