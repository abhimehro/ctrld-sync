
import unittest
import sys
import os

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main

class TestCSVInjection(unittest.TestCase):
    def test_csv_injection_prevention(self):
        """
        Verify that sanitize_for_log correctly keeps quotes around strings
        that start with characters known to trigger formula execution in spreadsheets
        (CSV Injection).
        """
        # Test cases for CSV injection characters
        dangerous_inputs = [
            "=cmd|' /C calc'!A0",
            "+cmd|' /C calc'!A0",
            "-cmd|' /C calc'!A0",
            "@cmd|' /C calc'!A0",
        ]

        for inp in dangerous_inputs:
            sanitized = main.sanitize_for_log(inp)
            # Should keep quotes (repr adds them)
            # repr("=...") -> "'=...'"
            # So sanitized should start with ' or "
            self.assertTrue(sanitized.startswith("'") or sanitized.startswith('"'),
                            f"Input '{inp}' should be quoted to prevent CSV injection. Got: {sanitized}")

            # Should contain the input
            self.assertIn(inp, sanitized)

    def test_normal_string_behavior(self):
        """
        Verify that normal strings (not starting with =, +, -, @) still have
        their outer quotes stripped, preserving existing behavior.
        """
        safe_inputs = [
            "NormalString",
            "Folder Name",
            "12345",
            "<script>alert(1)</script>", # XSS attempt (handled by repr escaping but checked here for quote stripping)
        ]

        for inp in safe_inputs:
            sanitized = main.sanitize_for_log(inp)
            # Should NOT start with quote (unless repr escaped something inside and used different quotes, but for simple strings it shouldn't)
            # Actually, repr("NormalString") is 'NormalString'. Stripped -> NormalString.
            # repr("Folder Name") is 'Folder Name'. Stripped -> Folder Name.
            self.assertFalse(sanitized.startswith("'") and sanitized.endswith("'"),
                             f"Input '{inp}' should have outer quotes stripped. Got: {sanitized}")

            # For strict check:
            self.assertEqual(sanitized, repr(inp)[1:-1])

    def test_empty_input(self):
        """Verify empty input handling."""
        self.assertEqual(main.sanitize_for_log(""), "")
        self.assertEqual(main.sanitize_for_log(None), "None")

if __name__ == '__main__':
    unittest.main()
