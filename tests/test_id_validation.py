from unittest.mock import MagicMock
import main

def test_validate_resource_id_valid():
    assert main.validate_resource_id("12345", "Test ID") is True
    assert main.validate_resource_id("abc_def-123", "Test ID") is True
    assert main.validate_resource_id("test_id", "Test ID") is True

def test_validate_resource_id_invalid_format():
    assert main.validate_resource_id("invalid/id", "Test ID", log_errors=False) is False
    assert main.validate_resource_id("invalid id", "Test ID", log_errors=False) is False
    assert main.validate_resource_id("invalid.id", "Test ID", log_errors=False) is False # dot not allowed in PK
    assert main.validate_resource_id("<script>", "Test ID", log_errors=False) is False

def test_validate_resource_id_invalid_length():
    long_id = "a" * 65
    assert main.validate_resource_id(long_id, "Test ID", log_errors=False) is False

def test_validate_resource_id_empty():
    assert main.validate_resource_id("", "Test ID", log_errors=False) is False
    assert main.validate_resource_id(None, "Test ID", log_errors=False) is False

def test_is_valid_folder_name_whitelist():
    # Valid
    assert main.is_valid_folder_name("My Folder") is True
    assert main.is_valid_folder_name("Folder (Work)") is True
    assert main.is_valid_folder_name("Folder_123") is True
    assert main.is_valid_folder_name("Folder-Home") is True
    assert main.is_valid_folder_name("Folder [Special]") is True
    assert main.is_valid_folder_name("domain.com") is True

    # Invalid
    assert main.is_valid_folder_name("Folder/Slash") is False # Slash not in whitelist
    assert main.is_valid_folder_name("Folder@At") is False
    assert main.is_valid_folder_name("Folder&Amp") is False
    assert main.is_valid_folder_name("Folder;Semi") is False
    assert main.is_valid_folder_name("Folder<Tags>") is False
    assert main.is_valid_folder_name("Folder'Quote") is False
    assert main.is_valid_folder_name("Folder`Backtick") is False
    assert main.is_valid_folder_name("Folder$Dollar") is False

def test_is_valid_folder_name_length():
    long_name = "a" * 65
    assert main.is_valid_folder_name(long_name) is False
