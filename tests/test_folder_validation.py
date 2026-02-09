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

        # Case 6: Path Separators (prevent confusion)
        for separator in ("/", "\\"):
            separator_data = {"group": {"group": f"Folder{separator}Name"}}
            assert (
                main.validate_folder_data(separator_data, f"http://sep-{ord(separator)}.com")
                is False
            ), f"Path separator '{separator}' should be blocked"

        # Case 7: Unicode Bidi Control Characters (RTLO spoofing prevention)
        # Test ALL blocked bidi characters for comprehensive coverage
        bidi_test_cases = [
            ("\u202a", "LRE - LEFT-TO-RIGHT EMBEDDING"),
            ("\u202b", "RLE - RIGHT-TO-LEFT EMBEDDING"),
            ("\u202c", "PDF - POP DIRECTIONAL FORMATTING"),
            ("\u202d", "LRO - LEFT-TO-RIGHT OVERRIDE"),
            ("\u202e", "RLO - RIGHT-TO-LEFT OVERRIDE (primary attack)"),
            ("\u2066", "LRI - LEFT-TO-RIGHT ISOLATE"),
            ("\u2067", "RLI - RIGHT-TO-LEFT ISOLATE"),
            ("\u2068", "FSI - FIRST STRONG ISOLATE"),
            ("\u2069", "PDI - POP DIRECTIONAL ISOLATE"),
            ("\u200e", "LRM - LEFT-TO-RIGHT MARK"),
            ("\u200f", "RLM - RIGHT-TO-LEFT MARK"),
        ]

        for char, description in bidi_test_cases:
            # Test with char in different positions
            for test_name in [f"Safe{char}Name", f"{char}StartName", f"EndName{char}"]:
                bidi_data = {"group": {"group": test_name}}
                assert (
                    main.validate_folder_data(bidi_data, f"http://bidi-{ord(char)}.com")
                    is False
                ), f"Bidi character {description} (U+{ord(char):04X}) should be blocked in '{test_name}'"

    finally:
        main.log = original_log
