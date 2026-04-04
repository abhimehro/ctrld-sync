import os
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
    # We changed the empty character from '░' to '·' in the progress bar
    assert "·" in combined_output
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


def test_print_success_message_single_profile(monkeypatch):
    """Verify success message includes dashboard link for single profile."""
    # Force colors on
    monkeypatch.setattr(main, "USE_COLORS", True)
    # Monkeypatch Colors attributes because they are computed at import time
    monkeypatch.setattr(main.Colors, "CYAN", "\033[96m")
    monkeypatch.setattr(main.Colors, "UNDERLINE", "\033[4m")
    monkeypatch.setattr(main.Colors, "ENDC", "\033[0m")
    monkeypatch.setattr(main.Colors, "GREEN", "\033[92m")

    # Mock stdout
    mock_stdout = MagicMock()
    # print() writes to sys.stdout by default
    monkeypatch.setattr(sys, "stdout", mock_stdout)

    profile_ids = ["123456"]
    main.print_success_message(profile_ids)

    # Check calls
    writes = [args[0] for args, _ in mock_stdout.write.call_args_list]
    combined_output = "".join(writes)

    # Verify content
    # Note: The output is ANSI colored, so exact string matching might fail if color codes are interspersed
    # But "View your changes" should be there
    assert "View your changes" in combined_output
    assert "https://controld.com/dashboard/profiles/123456/filters" in combined_output
    # Check for color codes presence (cyan or underline)
    assert "\033[96m" in combined_output or "\033[4m" in combined_output


def test_print_success_message_multiple_profiles(monkeypatch):
    """Verify success message includes general dashboard link for multiple profiles."""
    monkeypatch.setattr(main, "USE_COLORS", True)
    # Monkeypatch Colors attributes
    monkeypatch.setattr(main.Colors, "CYAN", "\033[96m")
    monkeypatch.setattr(main.Colors, "UNDERLINE", "\033[4m")
    monkeypatch.setattr(main.Colors, "ENDC", "\033[0m")
    monkeypatch.setattr(main.Colors, "GREEN", "\033[92m")

    mock_stdout = MagicMock()
    monkeypatch.setattr(sys, "stdout", mock_stdout)

    profile_ids = ["123", "456"]
    main.print_success_message(profile_ids)

    writes = [args[0] for args, _ in mock_stdout.write.call_args_list]
    combined_output = "".join(writes)

    assert "View your changes" in combined_output
    assert "https://controld.com/dashboard/profiles" in combined_output
    assert "/123/filters" not in combined_output  # Should not link to specific profile


def test_print_success_message_no_colors(monkeypatch):
    """Verify uncolored success message is printed if colors are disabled."""
    monkeypatch.setattr(main, "USE_COLORS", False)
    mock_stdout = MagicMock()
    monkeypatch.setattr(sys, "stdout", mock_stdout)

    main.print_success_message(["123"])

    writes = [args[0] for args, _ in mock_stdout.write.call_args_list]
    combined_output = "".join(writes)

    assert "View your changes" in combined_output
    assert "https://controld.com/dashboard/profiles/123/filters" in combined_output


class TestGetProgressBarWidth:
    def test_returns_int_within_bounds(self, monkeypatch):
        """Width is always between 15 and 50 for a normal terminal."""
        monkeypatch.setattr(
            main.shutil,
            "get_terminal_size",
            lambda fallback=(80, 24): os.terminal_size((80, 24)),
        )
        result = main._get_progress_bar_width()
        assert isinstance(result, int)
        assert 15 <= result <= 50

    def test_narrow_terminal_clamps_to_minimum(self, monkeypatch):
        """Narrow terminal (e.g., 20 cols) yields the 15-char minimum."""
        monkeypatch.setattr(
            main.shutil,
            "get_terminal_size",
            lambda fallback=(80, 24): os.terminal_size((20, 24)),
        )
        assert main._get_progress_bar_width() == 15

    def test_wide_terminal_clamps_to_maximum(self, monkeypatch):
        """Very wide terminal (e.g., 200 cols) yields the 50-char maximum."""
        monkeypatch.setattr(
            main.shutil,
            "get_terminal_size",
            lambda fallback=(80, 24): os.terminal_size((200, 24)),
        )
        assert main._get_progress_bar_width() == 50


class TestRenderProgressBar:
    def test_no_output_when_use_colors_false(self, monkeypatch, capsys):
        """render_progress_bar writes nothing when USE_COLORS is False."""
        monkeypatch.setattr(main, "USE_COLORS", False)
        main.render_progress_bar(5, 10, "test")
        assert capsys.readouterr().err == ""

    def test_no_output_when_total_zero(self, monkeypatch, capsys):
        """render_progress_bar exits early when total=0 to avoid division by zero."""
        monkeypatch.setattr(main, "USE_COLORS", True)
        main.render_progress_bar(0, 0, "test")
        assert capsys.readouterr().err == ""

    def test_writes_progress_bar_to_stderr(self, monkeypatch, capsys):
        """render_progress_bar writes a formatted bar to stderr when enabled."""
        monkeypatch.setattr(main, "USE_COLORS", True)
        monkeypatch.setattr(
            main.shutil,
            "get_terminal_size",
            lambda fallback=(80, 24): os.terminal_size((80, 24)),
        )
        main.render_progress_bar(5, 10, "Loading")
        err = capsys.readouterr().err
        assert "Loading" in err
        assert "█" in err
        assert "\r\033[K" in err


class TestMakeColSeparator:
    def test_basic_separator(self):
        """Test with a simple set of column widths."""
        result = main.make_col_separator(
            left="<", mid="|", right=">", horiz="-", col_widths=[2, 3]
        )
        # column 0 width=2 -> horiz * (2+2) -> "----"
        # column 1 width=3 -> horiz * (3+2) -> "-----"
        # joined by mid "|" -> "----|-----"
        # left "<", right ">" -> "<----|----->"
        assert result == "<----|----->"

    def test_empty_columns(self):
        """Test with an empty list of column widths."""
        result = main.make_col_separator(
            left="[", mid="+", right="]", horiz="=", col_widths=[]
        )
        assert result == "[]"

    def test_single_column(self):
        """Test with a single column width."""
        result = main.make_col_separator(
            left="[", mid="+", right="]", horiz="*", col_widths=[5]
        )
        # horiz * (5+2) = "*******"
        assert result == "[*******]"

    def test_typical_layout(self):
        """Test with typical lengths used in the script."""
        result = main.make_col_separator(
            left="L", mid="M", right="R", horiz="H", col_widths=[25, 10, 12, 10, 15]
        )
        expected_parts = ["H" * 27, "H" * 12, "H" * 14, "H" * 12, "H" * 17]
        expected = "L" + "M".join(expected_parts) + "R"
        assert result == expected


def test_print_line():
    """Verify print_line produces correct unicode table borders."""
    w = [2, 3]
    result = main.print_line("[", "*", "]", w)
    assert result.startswith(main.Colors.BOLD)
    assert result.endswith(main.Colors.ENDC)
    inner = result.replace(main.Colors.BOLD, "").replace(main.Colors.ENDC, "")
    assert inner == "[────*─────]"


def test_print_row():
    """Verify print_row produces correctly padded columns with bold separators."""
    w = [2, 3, 4, 5, 6]
    cols = ["A", "B", "C", "D", "E"]
    result = main.print_row(cols, w)
    expected_inner = "│ A  │   B │    C │     D │ E      │"
    clean_result = result.replace(main.Colors.BOLD, "").replace(main.Colors.ENDC, "")
    assert clean_result == expected_inner


def test_print_summary_table_unicode_print_line(monkeypatch, capsys):
    """
    Test that print_summary_table correctly uses the print_line and print_row helpers
    when USE_COLORS is True (unicode table mode).
    """
    monkeypatch.setattr(main, "USE_COLORS", True)
    sync_results = [
        {
            "profile": "Profile_1",
            "folders": 3,
            "rules": 1500,
            "duration": 2.5,
            "status_label": "ok",
            "success": True,
        }
    ]
    main.print_summary_table(
        sync_results=sync_results, success_count=1, total=1, dry_run=False
    )
    captured = capsys.readouterr()
    assert "┌─" in captured.out
    assert "─┐" in captured.out
    assert "├─" in captured.out or "├" in captured.out
    assert "┼" in captured.out
    assert "┤" in captured.out
    assert "└─" in captured.out or "└" in captured.out
    assert "┴" in captured.out
    assert "┘" in captured.out
    assert "SYNC SUMMARY" in captured.out
    assert "Profile_1" in captured.out
    assert "1,500" in captured.out
    assert "2.5s" in captured.out


def test_print_summary_table_ascii_fallback(monkeypatch, capsys):
    """
    Test that print_summary_table correctly falls back to ASCII output
    when USE_COLORS is False.
    """
    monkeypatch.setattr(main, "USE_COLORS", False)
    sync_results = [
        {
            "profile": "Profile_2",
            "folders": 1,
            "rules": 250,
            "duration": 1.1,
            "status_label": "error",
            "success": False,
        }
    ]
    main.print_summary_table(
        sync_results=sync_results, success_count=0, total=1, dry_run=True
    )
    captured = capsys.readouterr()
    assert "┌─" not in captured.out
    assert "├" not in captured.out
    assert "│" not in captured.out
    assert "-" * 20 in captured.out
    assert "DRY RUN SUMMARY" in captured.out
    assert "Profile_2" in captured.out
    assert "error" in captured.out


class _DummyStdin:
    """Simple stdin stub with configurable TTY behavior for tests."""

    def __init__(self, is_tty: bool):
        # Store the desired TTY behavior so tests can control it explicitly.
        self._is_tty = is_tty

    def isatty(self) -> bool:
        # Match the standard sys.stdin.isatty() interface.
        return self._is_tty


class TestPromptForInteractiveRestart:
    def test_skips_when_not_tty(self, monkeypatch):
        """Should return immediately if sys.stdin is not a TTY."""
        # Patch sys.stdin itself to a stub object rather than mutating
        # the isatty attribute on the real TextIOWrapper instance.
        monkeypatch.setattr(sys, "stdin", _DummyStdin(is_tty=False))
        # Should not raise exception or call execv
        main.prompt_for_interactive_restart(["123"])

    def test_handles_keyboard_interrupt(self, monkeypatch, capsys):
        """Should handle Ctrl+C gracefully."""
        # Simulate running in an interactive TTY.
        monkeypatch.setattr(sys, "stdin", _DummyStdin(is_tty=True))

        def mock_input(_):
            raise KeyboardInterrupt()

        monkeypatch.setattr("builtins.input", mock_input)
        mock_execv = MagicMock()
        monkeypatch.setattr(os, "execv", mock_execv)

        main.prompt_for_interactive_restart(["123"])

        mock_execv.assert_not_called()
        captured = capsys.readouterr()
        assert "Cancelled" in captured.out

    def test_handles_text_cancellation(self, monkeypatch, capsys):
        """Should handle typing 'n', 'no', 'quit' gracefully."""
        # Simulate running in an interactive TTY.
        monkeypatch.setattr(sys, "stdin", _DummyStdin(is_tty=True))

        for cancel_input in ["n", "NO", "  quit  ", "Cancel"]:
            # Local scope closure
            def make_mock_input(val):
                return lambda _: val

            monkeypatch.setattr("builtins.input", make_mock_input(cancel_input))
            mock_execv = MagicMock()
            monkeypatch.setattr(os, "execv", mock_execv)

            main.prompt_for_interactive_restart(["123"])

            mock_execv.assert_not_called()
            captured = capsys.readouterr()
            assert "Cancelled" in captured.out
