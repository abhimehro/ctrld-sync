import unittest
import sys
from unittest.mock import MagicMock

# Mock dependencies that are missing in the environment
sys.modules["httpx"] = MagicMock()
sys.modules["dotenv"] = MagicMock()
sys.modules["yaml"] = MagicMock()
sys.modules["cache"] = MagicMock()
sys.modules["api_client"] = MagicMock()

# Now we can import main
import main

class TestCleanEnvKV(unittest.TestCase):
    def test_clean_env_kv_none(self):
        self.assertIsNone(main._clean_env_kv(None, "TOKEN"))

    def test_clean_env_kv_empty(self):
        self.assertEqual(main._clean_env_kv("", "TOKEN"), "")

    def test_clean_env_kv_whitespace_only(self):
        self.assertEqual(main._clean_env_kv("   ", "TOKEN"), "")

    def test_clean_env_kv_raw_value(self):
        self.assertEqual(main._clean_env_kv("my-token-123", "TOKEN"), "my-token-123")

    def test_clean_env_kv_key_value_simple(self):
        self.assertEqual(main._clean_env_kv("TOKEN=my-token-123", "TOKEN"), "my-token-123")

    def test_clean_env_kv_key_value_with_spaces(self):
        self.assertEqual(main._clean_env_kv("TOKEN = my-token-123", "TOKEN"), "my-token-123")
        self.assertEqual(main._clean_env_kv("  TOKEN  =  my-token-123  ", "TOKEN"), "my-token-123")

    def test_clean_env_kv_mismatched_key(self):
        # Should return the value as-is (stripped) if key doesn't match
        self.assertEqual(main._clean_env_kv("OTHER=value", "TOKEN"), "OTHER=value")

    def test_clean_env_kv_no_value_after_equals(self):
        # If no value follows the equals sign, regex (.+) fails to match
        self.assertEqual(main._clean_env_kv("TOKEN=", "TOKEN"), "TOKEN=")
        self.assertEqual(main._clean_env_kv("TOKEN= ", "TOKEN"), "TOKEN=")

    def test_clean_env_kv_profile_id(self):
        self.assertEqual(main._clean_env_kv("PROFILE=p12345", "PROFILE"), "p12345")
        self.assertEqual(main._clean_env_kv("p12345", "PROFILE"), "p12345")

if __name__ == "__main__":
    unittest.main()
