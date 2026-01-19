
import sys
import pytest
from unittest.mock import MagicMock, call, patch
import main

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
    # Should call sleep with full seconds
    mock_sleep.assert_called_with(3)
