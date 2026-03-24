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
    Test that URLs exceeding the maximum length are rejected.
    Expected behavior: Should reject length > 2048.
    """
    main.validate_folder_url.cache_clear()

    # Create a URL with 2049 characters
    long_url = "https://example.com/" + "a" * 2029
    assert len(long_url) == 2049

    # This should return False after the fix
    assert main.validate_folder_url(long_url) is False


def test_validate_folder_url_acceptable_length():
    """Test that URLs within limit are accepted."""
    main.validate_folder_url.cache_clear()

    # Create a URL with exactly 2048 characters
    # Note: httpx URL parsing might be strict, so use a simple structure
    url = "https://example.com/" + "a" * 2028
    assert len(url) == 2048

    # We expect True, but if DNS resolution is involved in tests it might fail for other reasons.
    # To isolate the length check, we can use unittest.mock or just check it doesn't fail fast on length.
    # Actually, the test_ssrf.py shows we mock socket.getaddrinfo.
    # Let's mock it here.
    import socket
    from unittest.mock import patch

    with patch("socket.getaddrinfo") as mock_getaddrinfo:
        # Simulate resolving to 8.8.8.8
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))
        ]

        # main.validate_folder_url also checks validate_hostname, which calls socket.getaddrinfo
        assert main.validate_folder_url(url) is True
