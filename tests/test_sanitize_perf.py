
import time
import sys
import os

# Ensure we can import main from parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main
from unittest import mock

# Ensure we can import main from parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main

def test_sanitize_fast_path_skips_regex_sub_calls():
    """
    Verify that sanitize_for_log uses a fast path for non-URL/non-query strings
    and does not invoke the expensive regex .sub() calls.

    This replaces the previous time-based benchmark with a deterministic
    behavioral test that will fail if a regression causes unnecessary regex
    work on simple log messages.
    """
    # Use a message without '://', '?', '&', '/', or '#' so that any logic
    # checking for URL/query markers should treat it as a simple string.
    text_simple = "Just a normal log message with some folder name"

    # Create mock pattern objects with a .sub() method we can assert on.
    mock_basic_pattern = mock.Mock()
    mock_basic_pattern.sub = mock.Mock(side_effect=lambda s: s)

    mock_sensitive_pattern = mock.Mock()
    mock_sensitive_pattern.sub = mock.Mock(side_effect=lambda s: s)

    # Patch the patterns on the main module. We use create=True to avoid
    # failures if these attributes are missing in some versions; in that case,
    # the test still asserts that the fast path does not touch them.
    with mock.patch.object(main, "_BASIC_AUTH_PATTERN", mock_basic_pattern, create=True), \
         mock.patch.object(main, "_SENSITIVE_PARAM_PATTERN", mock_sensitive_pattern, create=True):

        result = main.sanitize_for_log(text_simple)

        # Behavior: simple strings should not be modified by sanitization.
        assert result == text_simple

        # Performance behavior: the regex .sub() methods should not be invoked
        # for inputs that don't contain URL or query markers.
        mock_basic_pattern.sub.assert_not_called()
        mock_sensitive_pattern.sub.assert_not_called()
