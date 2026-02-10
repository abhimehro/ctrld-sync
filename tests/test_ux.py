
import sys
from unittest.mock import MagicMock
import main
import pytest

def test_countdown_timer_visuals(monkeypatch):
    """Verify that countdown_timer writes a progress bar to stderr."""
    # Force colors on
    monkeypatch.setattr(main, "USE_COLORS", True)

    # Mock stderr
    mock_stderr = MagicMock()
    monkeypatch.setattr(sys, "stderr", mock_stderr)

    # Mock time.sleep to run instantly
    monkeypatch.setattr(main.time, "sleep", MagicMock())

    main.countdown_timer(3, "Test")

    # Check calls
    writes = [args[0] for args, _ in mock_stderr.write.call_args_list]
    combined_output = "".join(writes)

    # Check for progress bar chars
    assert "░" in combined_output
    assert "█" in combined_output
    assert "Test" in combined_output
    assert "Done!" in combined_output

    # Check for ANSI clear line code
    assert "\033[K" in combined_output

def test_countdown_timer_no_colors(monkeypatch):
    """Verify that countdown_timer sleeps without writing to stderr if NO_COLOR."""
    monkeypatch.setattr(main, "USE_COLORS", False)
    mock_stderr = MagicMock()
    monkeypatch.setattr(sys, "stderr", mock_stderr)
    mock_sleep = MagicMock()
    monkeypatch.setattr(main.time, "sleep", mock_sleep)

    main.countdown_timer(3, "Test")

    # Should not write to stderr
    mock_stderr.write.assert_not_called()
    # Should call sleep exactly once with full seconds
    mock_sleep.assert_called_once_with(3)

@pytest.mark.parametrize("seconds, expected", [
    (5.2, "5.2s"),
    (0.0, "0.0s"),
    (59.9, "59.9s"),
    (60.0, "1m 00s"),
    (65.5, "1m 05s"),
    (125.0, "2m 05s"),
    (3600.0, "60m 00s"),
])
def test_format_duration(seconds, expected):
    """Verify format_duration output for various inputs."""
    assert main.format_duration(seconds) == expected
