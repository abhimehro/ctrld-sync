
import sys
from unittest.mock import MagicMock
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

def test_countdown_timer_no_colors_short(monkeypatch):
    """Verify that short countdowns sleep silently without writing to stderr if NO_COLOR."""
    monkeypatch.setattr(main, "USE_COLORS", False)
    mock_stderr = MagicMock()
    monkeypatch.setattr(sys, "stderr", mock_stderr)
    mock_sleep = MagicMock()
    monkeypatch.setattr(main.time, "sleep", mock_sleep)

    # Mock log to ensure it's not called
    mock_log = MagicMock()
    monkeypatch.setattr(main, "log", mock_log)

    main.countdown_timer(10, "Test")

    # Should not log
    mock_log.info.assert_not_called()
    # Should call sleep exactly once with full seconds
    mock_sleep.assert_called_once_with(10)
    # Should not write anything to stderr for short, no-color countdowns
    mock_stderr.write.assert_not_called()
    mock_stderr.flush.assert_not_called()


def test_countdown_timer_no_colors_long(monkeypatch):
    """Verify that long countdowns log periodic updates if NO_COLOR."""
    monkeypatch.setattr(main, "USE_COLORS", False)
    mock_sleep = MagicMock()
    monkeypatch.setattr(main.time, "sleep", mock_sleep)

    mock_log = MagicMock()
    monkeypatch.setattr(main, "log", mock_log)

    # Test with 25 seconds
    main.countdown_timer(25, "LongWait")

    # Expected sleep calls:
    # 1. min(10, 25) -> 10 (remaining 25)
    # 2. min(10, 15) -> 10 (remaining 15)
    # 3. min(10, 5) -> 5 (remaining 5)

    # Expected log calls:
    # 1. "LongWait: 15s remaining..." (after first sleep/loop iteration)
    # 2. "LongWait: 5s remaining..." (after second sleep/loop iteration)

    assert mock_sleep.call_count == 3
    mock_sleep.assert_any_call(10)
    mock_sleep.assert_any_call(5)

    assert mock_log.info.call_count == 2
    mock_log.info.assert_any_call("LongWait: 15s remaining...")
    mock_log.info.assert_any_call("LongWait: 5s remaining...")
