"""Tests for .env file permissions checking and auto-fix functionality."""

import os
import stat
from unittest.mock import MagicMock, patch, call


# Set TOKEN before importing main to avoid issues with load_dotenv()
os.environ.setdefault("TOKEN", "test-token-123")
os.environ.setdefault("NO_COLOR", "1")


def test_env_permissions_auto_fix_success():
    """Test successful auto-fix of insecure .env permissions."""
    from main import check_env_permissions
    
    with patch("os.name", "posix"), \
         patch("os.path.exists", return_value=True), \
         patch("os.path.islink", return_value=False):

        # Mock low-level file operations
        mock_open = MagicMock(return_value=123)
        mock_close = MagicMock()
        mock_fstat = MagicMock()
        mock_fchmod = MagicMock()
        
        # Mock file with insecure permissions (644)
        mock_stat_result = MagicMock()
        mock_stat_result.st_mode = stat.S_IFREG | 0o644
        mock_fstat.return_value = mock_stat_result
        
        with patch("os.open", mock_open), \
             patch("os.close", mock_close), \
             patch("os.fstat", mock_fstat), \
             patch("os.fchmod", mock_fchmod, create=True):

            # Mock stderr
            mock_stderr = MagicMock()
            with patch("sys.stderr", mock_stderr):
                check_env_permissions()

                # Verify fchmod was called with 600
                mock_fchmod.assert_called_with(123, 0o600)

                # Verify success message was written
                mock_stderr.write.assert_called()
                output = "".join(call.args[0] for call in mock_stderr.write.call_args_list)
                assert "Fixed .env permissions" in output
                assert "644" in output
                assert "600" in output


def test_env_permissions_auto_fix_failure():
    """Test warning when auto-fix fails."""
    from main import check_env_permissions
    
    with patch("os.name", "posix"), \
         patch("os.path.exists", return_value=True), \
         patch("os.path.islink", return_value=False):
        
        mock_open = MagicMock(return_value=123)
        mock_stat_result = MagicMock()
        mock_stat_result.st_mode = stat.S_IFREG | 0o666
        mock_fstat = MagicMock(return_value=mock_stat_result)
        
        # Mock fchmod to fail
        mock_fchmod = MagicMock(side_effect=OSError("Permission denied"))

        with patch("os.open", mock_open), \
             patch("os.close", MagicMock()), \
             patch("os.fstat", mock_fstat), \
             patch("os.fchmod", mock_fchmod, create=True):

            mock_stderr = MagicMock()
            with patch("sys.stderr", mock_stderr):
                check_env_permissions()

                # Verify warning was written
                mock_stderr.write.assert_called()
                output = "".join(call.args[0] for call in mock_stderr.write.call_args_list)
                assert "Security Warning" in output
                assert "Auto-fix failed" in output
                assert "chmod 600 .env" in output


def test_env_permissions_windows_warning():
    """Test that Windows shows a warning (no auto-fix)."""
    from main import check_env_permissions
    
    with patch("os.name", "nt"), \
         patch("os.path.exists", return_value=True):
        
        mock_stderr = MagicMock()
        with patch("sys.stderr", mock_stderr):
            check_env_permissions()

            # Verify warning was written (not a fix message)
            mock_stderr.write.assert_called_once()
            output = mock_stderr.write.call_args[0][0]
            assert "Security Warning" in output
            assert "Please ensure .env is only readable by you" in output


def test_env_permissions_secure_file_no_output():
    """Test that secure permissions don't trigger any output."""
    from main import check_env_permissions
    
    with patch("os.name", "posix"), \
         patch("os.path.exists", return_value=True), \
         patch("os.path.islink", return_value=False):
        
        mock_open = MagicMock(return_value=123)
        mock_stat_result = MagicMock()
        mock_stat_result.st_mode = stat.S_IFREG | 0o600
        mock_fstat = MagicMock(return_value=mock_stat_result)
        mock_fchmod = MagicMock()
        
        with patch("os.open", mock_open), \
             patch("os.close", MagicMock()), \
             patch("os.fstat", mock_fstat), \
             patch("os.fchmod", mock_fchmod, create=True):

            mock_stderr = MagicMock()
            with patch("sys.stderr", mock_stderr):
                check_env_permissions()

                # Verify no output and no fchmod
                mock_stderr.write.assert_not_called()
                mock_fchmod.assert_not_called()


def test_env_permissions_file_not_exists():
    """Test that missing .env file is silently ignored."""
    from main import check_env_permissions
    
    with patch("os.path.exists", return_value=False):
        mock_stderr = MagicMock()
        with patch("sys.stderr", mock_stderr):
            check_env_permissions()
            mock_stderr.write.assert_not_called()


def test_env_permissions_stat_error():
    """Test handling of os.open/os.fstat errors."""
    from main import check_env_permissions
    
    with patch("os.name", "posix"), \
         patch("os.path.exists", return_value=True), \
         patch("os.path.islink", return_value=False):
        
        # Mock os.open to fail
        with patch("os.open", side_effect=OSError("Access denied")):
            mock_stderr = MagicMock()
            with patch("sys.stderr", mock_stderr):
                check_env_permissions()

                # Verify error message
                mock_stderr.write.assert_called()
                output = "".join(call.args[0] for call in mock_stderr.write.call_args_list)
                assert "Could not check .env permissions" in output
                assert "OSError" in output or "Access denied" in output


def test_env_permissions_respects_custom_path():
    """Test that custom .env path is respected."""
    from main import check_env_permissions
    
    with patch("os.name", "posix"), \
         patch("os.path.exists", return_value=True), \
         patch("os.path.islink", return_value=False):
        
        mock_open = MagicMock(return_value=123)
        mock_stat_result = MagicMock()
        mock_stat_result.st_mode = stat.S_IFREG | 0o644
        mock_fstat = MagicMock(return_value=mock_stat_result)
        mock_fchmod = MagicMock()
        
        with patch("os.open", mock_open), \
             patch("os.close", MagicMock()), \
             patch("os.fstat", mock_fstat), \
             patch("os.fchmod", mock_fchmod, create=True):

            mock_stderr = MagicMock()
            with patch("sys.stderr", mock_stderr):
                check_env_permissions("/custom/.env")

                # Verify os.open called with custom path
                args, _ = mock_open.call_args
                assert args[0] == "/custom/.env"
