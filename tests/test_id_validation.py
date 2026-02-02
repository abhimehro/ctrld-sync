import pytest
from unittest.mock import MagicMock
import main

def test_validate_resource_id_valid():
    """Test valid resource IDs."""
    valid_ids = [
        "123",
        "abc",
        "ABC",
        "Folder_1",
        "Profile-2",
        "valid_id_123-ABC",
        "a" * 64,  # Max length
    ]
    for rid in valid_ids:
        assert main.validate_resource_id(rid) is True, f"Should accept {rid}"

def test_validate_resource_id_invalid_format():
    """Test invalid formats (unsafe chars)."""
    invalid_ids = [
        "id with space",
        "id/slash",
        "id\\backslash",
        "id.dot",
        "id:colon",
        "id<script>",
        "../../etc/passwd",
        "; drop table",
        "&",
        "$",
    ]
    # Mock log to silence errors during test
    original_log = main.log
    main.log = MagicMock()
    try:
        for rid in invalid_ids:
            assert main.validate_resource_id(rid) is False, f"Should reject {rid}"
    finally:
        main.log = original_log

def test_validate_resource_id_invalid_length():
    """Test invalid length."""
    original_log = main.log
    main.log = MagicMock()
    try:
        long_id = "a" * 65
        assert main.validate_resource_id(long_id) is False
    finally:
        main.log = original_log

def test_validate_resource_id_empty():
    """Test empty ID."""
    assert main.validate_resource_id("") is False
    assert main.validate_resource_id(None) is False

def test_is_valid_folder_name_whitelist():
    """Test the stricter whitelist for folder names."""
    valid_names = [
        "Work",
        "Home Network",
        "Folder (Private)",
        "Use [Brackets]",
        "Use {Braces}",
        "Hyphen-ated",
        "Under_score",
        "Dot.Name",
        "123456",
    ]
    for name in valid_names:
        assert main.is_valid_folder_name(name) is True, f"Should accept {name}"

    invalid_names = [
        "Folder with <",
        "Folder with >",
        "Folder with '",
        "Folder with \"",
        "Folder with `",
        "Folder with ;", # New restriction
        "Folder with &", # New restriction
        "Folder with |", # New restriction
        "Folder with $", # New restriction
        "Folder with \\", # New restriction
    ]
    for name in invalid_names:
        assert main.is_valid_folder_name(name) is False, f"Should reject {name}"

def test_is_valid_folder_name_length():
    """Test folder name length limit."""
    long_name = "a" * 65
    assert main.is_valid_folder_name(long_name) is False
