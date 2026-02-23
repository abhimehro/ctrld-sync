from unittest.mock import MagicMock
import pytest
import main

def test_rule_validation_structure():
    """Verify that rule validation handles structural errors correctly."""
    mock_log = MagicMock()
    original_log = main.log
    main.log = mock_log

    try:
        # Case 1: Valid structure
        valid_data = {
            "group": {"group": "Valid"},
            "rule_groups": [
                {
                    "rules": [{"pk": "rule1"}, {"pk": "rule2"}]
                }
            ]
        }
        assert main.validate_folder_data(valid_data, "http://valid.com") is True

        # Case 2: rules is not a list
        invalid_rules_type = {
            "group": {"group": "Invalid Rules Type"},
            "rule_groups": [
                {
                    "rules": "not-a-list"
                }
            ]
        }
        assert main.validate_folder_data(invalid_rules_type, "http://invalid.com") is False
        mock_log.error.assert_called_with("Invalid data from http://invalid.com: rule_groups[0].rules must be a list.")

        # Case 3: rule item is not a dict
        invalid_rule_item = {
            "group": {"group": "Invalid Rule Item"},
            "rule_groups": [
                {
                    "rules": [{"pk": "rule1"}, "not-a-dict", {"pk": "rule3"}]
                }
            ]
        }
        assert main.validate_folder_data(invalid_rule_item, "http://invalid-item.com") is False
        # Verify that the log message contains the correct index (1)
        mock_log.error.assert_called_with("Invalid data from http://invalid-item.com: rule_groups[0].rules[1] must be an object.")

    finally:
        main.log = original_log
