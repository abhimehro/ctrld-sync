import unittest
from main import sanitize_for_log

class TestSecurityLog(unittest.TestCase):
    def test_redact_query_params(self):
        # Test cases for URL query parameter redaction
        test_cases = [
            (
                "https://example.com?token=secret123",
                "https://example.com?token=[REDACTED]"
            ),
            (
                "https://example.com?key=my_key&foo=bar",
                "https://example.com?key=[REDACTED]&foo=bar"
            ),
            (
                "Error fetching https://api.com?auth=xyz failed",
                "Error fetching https://api.com?auth=[REDACTED] failed"
            ),
            (
                "https://site.com?access_token=token&api_key=key",
                "https://site.com?access_token=[REDACTED]&api_key=[REDACTED]"
            ),
            (
                "https://safe.com?public=data",
                "https://safe.com?public=data"
            ),
            (
                "'https://quoted.com?password=pass'",
                "https://quoted.com?password=[REDACTED]"
            )
        ]

        for input_str, expected in test_cases:
            # sanitize_for_log uses repr() which adds quotes and escapes.
            # We need to handle that in our expectation or strip it.
            # The current implementation of sanitize_for_log returns a repr() string (quoted).
            # If our expected string is the *content* inside the quotes, we should match that.

            result = sanitize_for_log(input_str)

            # Remove surrounding quotes for easier comparison if present
            if len(result) >= 2 and result[0] == result[-1] and result[0] in ("'", '"'):
                result_content = result[1:-1]
            else:
                result_content = result

            # Also repr() escapes things.
            # Our expected strings don't have special chars that repr escapes (except maybe quotes).
            # But the proposed implementation applies redaction BEFORE repr.
            # So sanitizing "url?token=s" -> "url?token=[REDACTED]" -> repr() -> "'url?token=[REDACTED]'"

            self.assertEqual(result_content, expected, f"Failed for input: {input_str}")

if __name__ == "__main__":
    unittest.main()
