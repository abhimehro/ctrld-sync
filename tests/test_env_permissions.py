"""Tests for .env file permissions checking — mock-only branches not covered by real-file tests."""

import os
import stat
from unittest.mock import MagicMock, patch

# Set TOKEN before importing main to avoid issues with load_dotenv()
os.environ.setdefault("TOKEN", "test-token-123")
os.environ.setdefault("NO_COLOR", "1")


def test_env_permissions_auto_fix_failure():
    """Test warning when auto-fix fails."""
    from main import check_env_permissions

    with (
        patch("os.name", "posix"),
        patch("os.path.exists", return_value=True),
        patch("os.path.islink", return_value=False),
    ):
        mock_open = MagicMock(return_value=123)
        mock_stat_result = MagicMock()
        mock_stat_result.st_mode = stat.S_IFREG | 0o666
        mock_fstat = MagicMock(return_value=mock_stat_result)

        # Mock fchmod to fail
        mock_fchmod = MagicMock(side_effect=OSError("Permission denied"))

        with (
            patch("os.open", mock_open),
            patch("os.close", MagicMock()),
            patch("os.fstat", mock_fstat),
            patch("os.fchmod", mock_fchmod, create=True),
        ):
            mock_stderr = MagicMock()
            with patch("sys.stderr", mock_stderr):
                check_env_permissions()

                # Verify warning was written
                mock_stderr.write.assert_called()
                output = "".join(
                    call.args[0] for call in mock_stderr.write.call_args_list
                )
                assert "Security Warning" in output
                assert "Auto-fix failed" in output
                assert "chmod 600 .env" in output


def test_env_permissions_windows_warning():
    """Test that Windows shows a warning (no auto-fix)."""
    from main import check_env_permissions

    with patch("os.name", "nt"), patch("os.path.exists", return_value=True):
        mock_stderr = MagicMock()
        with patch("sys.stderr", mock_stderr):
            check_env_permissions()

            # Verify warning was written (not a fix message)
            mock_stderr.write.assert_called_once()
            output = mock_stderr.write.call_args[0][0]
            assert "Security Warning" in output
            assert "Please ensure .env is only readable by you" in output


def test_env_permissions_file_not_exists():
    """Test that missing .env file is silently ignored."""
    from main import check_env_permissions

    with patch("os.path.exists", return_value=False):
        mock_stderr = MagicMock()
        with patch("sys.stderr", mock_stderr):
            check_env_permissions()
            mock_stderr.write.assert_not_called()


def test_env_permissions_respects_custom_path():
    """Test that custom .env path is respected."""
    from main import check_env_permissions

    with (
        patch("os.name", "posix"),
        patch("os.path.exists", return_value=True),
        patch("os.path.islink", return_value=False),
    ):
        mock_open = MagicMock(return_value=123)
        mock_stat_result = MagicMock()
        mock_stat_result.st_mode = stat.S_IFREG | 0o644
        mock_fstat = MagicMock(return_value=mock_stat_result)
        mock_fchmod = MagicMock()

        with (
            patch("os.open", mock_open),
            patch("os.close", MagicMock()),
            patch("os.fstat", mock_fstat),
            patch("os.fchmod", mock_fchmod, create=True),
        ):
            mock_stderr = MagicMock()
            with patch("sys.stderr", mock_stderr):
                check_env_permissions("/custom/.env")

                # Verify os.open called with custom path
                args, _ = mock_open.call_args
                assert args[0] == "/custom/.env"
