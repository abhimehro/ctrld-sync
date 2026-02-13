"""Tests for the format_duration function."""

import main


def test_format_duration_sub_minute():
    """Test format_duration with durations less than 60 seconds."""
    # Exact values
    assert main.format_duration(0) == "0s"
    assert main.format_duration(5) == "5s"
    assert main.format_duration(42) == "42s"
    assert main.format_duration(59) == "59s"

    # Rounding behavior for sub-minute values
    assert main.format_duration(5.4) == "5s"  # Rounds down
    assert main.format_duration(5.5) == "6s"  # Rounds up (banker's rounding to even)
    assert main.format_duration(59.4) == "59s"  # Rounds down
    assert main.format_duration(59.5) == "1m 00s"  # Rounds to 60 -> shows as 1m 00s
    assert main.format_duration(59.95) == "1m 00s"  # Edge case: rounds to 60 -> 1m 00s


def test_format_duration_exact_minutes():
    """Test format_duration with exact minute values."""
    assert main.format_duration(60) == "1m 00s"
    assert main.format_duration(120) == "2m 00s"
    assert main.format_duration(300) == "5m 00s"
    assert main.format_duration(3600) == "60m 00s"


def test_format_duration_mixed():
    """Test format_duration with minutes and seconds."""
    assert main.format_duration(65) == "1m 05s"
    assert main.format_duration(125) == "2m 05s"
    assert main.format_duration(185) == "3m 05s"
    assert main.format_duration(305.5) == "5m 06s"  # Rounds to 306 seconds = 5m 06s


def test_format_duration_rounding_boundaries():
    """Test format_duration rounding behavior at boundaries.
    
    These boundary tests protect against the issue mentioned in the PR review
    where 59.95s would show as "60.0s" instead of "1m 00s" due to truncation.
    By rounding first, we get consistent behavior: values that round to 60+
    seconds are displayed in minutes format for clarity.
    """
    # Just under a minute: should round down and stay in seconds
    assert main.format_duration(59.4) == "59s"
    
    # Halfway to next second at boundary: rounds to 60 -> shown as minutes
    assert main.format_duration(59.5) == "1m 00s"
    
    # Very close to a minute: rounds to 60 -> shown as 1m 00s (clearer than "60s")
    assert main.format_duration(59.95) == "1m 00s"
    
    # Just over a minute: should be in minutes format
    assert main.format_duration(60.1) == "1m 00s"
    assert main.format_duration(60.5) == "1m 00s"  # Banker's rounding: rounds to 60 (even)
    assert main.format_duration(61.5) == "1m 02s"  # Banker's rounding: rounds to 62 (even)
    
    # Edge cases around 2 minutes
    assert main.format_duration(119.4) == "1m 59s"  # Rounds down
    assert main.format_duration(119.5) == "2m 00s"  # Rounds up
    assert main.format_duration(125.9) == "2m 06s"  # Example from PR review


def test_format_duration_large_values():
    """Test format_duration with large durations."""
    assert main.format_duration(3661) == "61m 01s"
    assert main.format_duration(7200) == "120m 00s"
    assert main.format_duration(7325.7) == "122m 06s"  # 7326 seconds = 122m 06s
