import main


def test_is_valid_folder_name_length_limit():
    """
    Test that folder names exceeding the maximum length are rejected.
    Current behavior: Accepts any length.
    Expected behavior: Should reject length > 64.
    """
    # Create a name with 65 characters
    long_name = "a" * 65

    # This should return False after the fix, but currently returns True
    # We assert False to confirm the "failure" (vulnerability presence) or "success" (fix verification)
    assert main.is_valid_folder_name(long_name) is False


def test_is_valid_folder_name_acceptable_length():
    """Test that folder names within limit are accepted."""
    name = "a" * 64
    assert main.is_valid_folder_name(name) is True


def test_is_valid_rule_length_limit():
    """
    Test that rules exceeding the maximum length are rejected.
    Current behavior: Accepts any length (matching regex).
    Expected behavior: Should reject length > 255.
    """
    # Create a rule with 256 characters (valid chars)
    long_rule = "a" * 256 + ".com"

    # This should return False after the fix
    assert main.is_valid_rule(long_rule) is False


def test_is_valid_rule_acceptable_length():
    """Test that rules within limit are accepted."""
    rule = "a" * 250 + ".com"
    assert main.is_valid_rule(rule) is True


def test_is_valid_profile_id_length_limit_constant():
    """
    Test that profile ID validation respects the length limit.
    Note: This function already had a length check, we are just formalizing it with a constant.
    """
    # 65 chars
    long_id = "a" * 65
    assert main.validate_profile_id(long_id, log_errors=False) is False

    # 64 chars
    valid_id = "a" * 64
    assert main.validate_profile_id(valid_id, log_errors=False) is True


def test_validate_folder_url_length_limit():
    """
    Test that folder URLs exceeding the maximum length are rejected.
    """
    # Create a URL with length > MAX_URL_LENGTH (2048)
    long_url = "https://" + "a" * 2045

    # Should be rejected
    assert main.validate_folder_url(long_url) is False


def test_validate_folder_url_acceptable_length():
    """Test that folder URLs within limit are accepted."""
    # Create a URL within the limit
    url = "https://example.com/folder.json"

    # We clear the cache to ensure the method runs fully, but we don't care about the HTTP request
    main.validate_folder_url.cache_clear()

    # If the domain doesn't resolve in the test env, it might still return False due to validate_hostname
    # But it won't fail the length check
    # We'll just verify it doesn't fail fast via length check if possible, or mock validate_hostname
    from unittest.mock import patch
    with patch('main.validate_hostname', return_value=True):
        assert main.validate_folder_url(url) is True
