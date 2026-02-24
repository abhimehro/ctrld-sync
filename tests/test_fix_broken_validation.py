import unittest
from unittest.mock import MagicMock
import sys
import os

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main

class TestFixBrokenValidation(unittest.TestCase):
    def setUp(self):
        self.original_log = main.log
        main.log = MagicMock()

    def tearDown(self):
        main.log = self.original_log

    def test_invalid_rule_type_in_rule_groups(self):
        """
        Verify that validate_folder_data correctly identifies and rejects
        non-dict rules inside rule_groups.
        This tests the fix for the broken syntax block.
        """
        # Data with invalid rule (string instead of dict) inside rule_groups
        invalid_data = {
            "group": {"group": "Test Group"},
            "rule_groups": [
                {
                    "rules": [
                        {"PK": "valid.com"},
                        "invalid_string_rule" # Should trigger the error
                    ]
                }
            ]
        }

        result = main.validate_folder_data(invalid_data, "http://test.com")

        self.assertFalse(result, "Should return False for invalid rule type")

        # Verify the error log message
        # We expect: "Invalid data from http://test.com: rule_groups[0].rules[1] must be an object."
        main.log.error.assert_called()
        found = False
        for call in main.log.error.call_args_list:
            if "rule_groups[0].rules[1] must be an object" in call[0][0]:
                found = True
                break
        self.assertTrue(found, "Did not find expected error message for invalid rule type")

    def test_invalid_rules_list_type(self):
         """
         Verify that if 'rules' is not a list, it is caught.
         This tests the fix for the malformed logging block above the loop.
         """
         invalid_data = {
            "group": {"group": "Test Group"},
            "rule_groups": [
                {
                    "rules": "not_a_list" # Should trigger error
                }
            ]
         }

         result = main.validate_folder_data(invalid_data, "http://test.com")
         self.assertFalse(result)

         main.log.error.assert_called()
         found = False
         for call in main.log.error.call_args_list:
             if "rule_groups[0].rules must be a list" in call[0][0]:
                 found = True
                 break
         self.assertTrue(found, "Did not find expected error message for invalid rules list type")

if __name__ == '__main__':
    unittest.main()
