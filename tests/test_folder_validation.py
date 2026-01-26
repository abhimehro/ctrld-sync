import pytest
from unittest.mock import MagicMock
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
        assert main.validate_folder_data(invalid_type_data, "http://badtype.com") is False

        # Case 4: Dangerous characters
        dangerous_data = {"group": {"group": "Folder\"Name"}}
        assert main.validate_folder_data(dangerous_data, "http://dangerous.com") is False

    finally:
        main.log = original_log
