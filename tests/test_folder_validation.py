from unittest.mock import MagicMock

import pytest

import main


def test_folder_name_security():
    """
    Verify that validate_folder_data enforces security checks on folder names.
    """
    # Mock logger to verify errors
    mock_log = MagicMock()
    original_log = main.log
    main.log = mock_log

    try:
        # Case 1: Valid Folder Name
        valid_data = {"group": {"group": "Safe Folder Name (Work)"}}
        assert main.validate_folder_data(valid_data, "http://valid.com") is True

        # Case 2: XSS Payload
        xss_data = {"group": {"group": "<script>alert(1)</script>"}}
        assert main.validate_folder_data(xss_data, "http://evil.com") is False

        # Case 3: Invalid Type
        invalid_type_data = {"group": {"group": 123}}
        assert (
            main.validate_folder_data(invalid_type_data, "http://badtype.com") is False
        )

        # Case 4: Dangerous characters
        dangerous_data = {"group": {"group": 'Folder"Name'}}
        assert (
            main.validate_folder_data(dangerous_data, "http://dangerous.com") is False
        )

        # Case 5: Empty/Strip folder name
        empty_data = {"group": {"group": "   "}}
        assert main.validate_folder_data(empty_data, "http://empty.com") is False

        # Case 6: Path Separators
        slash_data = {"group": {"group": "Folder/Name"}}
        assert main.validate_folder_data(slash_data, "http://slash.com") is False

        backslash_data = {"group": {"group": "Folder\\Name"}}
        assert main.validate_folder_data(backslash_data, "http://backslash.com") is False

        # Case 7: Bidi Control Characters (RTLO)
        # \u202e is Right-To-Left Override
        rtlo_data = {"group": {"group": "SafeName\u202eexe.pdf"}}
        assert main.validate_folder_data(rtlo_data, "http://rtlo.com") is False

        # Case 8: Other Bidi Char
        lre_data = {"group": {"group": "Name\u202a"}}
        assert main.validate_folder_data(lre_data, "http://lre.com") is False

    finally:
        main.log = original_log
