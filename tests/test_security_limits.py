import pytest
from unittest.mock import MagicMock, patch
import main

def test_is_valid_folder_name_limits():
    # Test length limit: 64 characters (pass)
    assert main.is_valid_folder_name("a" * 64) is True

    # Test length limit: 65 characters (fail)
    assert main.is_valid_folder_name("a" * 65) is False

def test_is_valid_rule_limits():
    # Test length limit: 255 characters (pass)
    # Using 'a' which matches the regex ^[a-zA-Z0-9.\-_:*/@]+$
    assert main.is_valid_rule("a" * 255) is True

    # Test length limit: 256 characters (fail)
    assert main.is_valid_rule("a" * 256) is False

def test_validate_folder_id_limits():
    # Test length limit: 64 characters (pass)
    # Using 'a' which matches ^[a-zA-Z0-9_.-]+$
    assert main.validate_folder_id("a" * 64) is True

    # Test length limit: 65 characters (fail)
    # We pass log_errors=False to avoid cluttering output
    assert main.validate_folder_id("a" * 65, log_errors=False) is False
