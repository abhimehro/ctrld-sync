
import logging
from main import sanitize_for_log

TOKEN = "secret_token"
import main
main.TOKEN = TOKEN

def test_sanitize():
    entry_name = "Folder with " + TOKEN
    sanitized = sanitize_for_log(entry_name)
    print(f"Original: {entry_name}")
    print(f"Sanitized: {sanitized}")
    assert "[REDACTED]" in sanitized
    assert TOKEN not in sanitized

if __name__ == "__main__":
    test_sanitize()
