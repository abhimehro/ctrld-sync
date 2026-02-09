"""Tests for .env file permissions checking and auto-fix functionality."""

import os
import stat
from unittest.mock import MagicMock, patch


# Set TOKEN before importing main to avoid issues with load_dotenv()
os.environ.setdefault("TOKEN", "test-token-123")
os.environ.setdefault("NO_COLOR", "1")


def test_env_permissions_auto_fix_success():
    """Test successful auto-fix of insecure .env permissions."""
    # Import here to avoid side effects during test collection
    from main import check_env_permissions
    
    # Set up POSIX environment
    with patch("os.name", "posix"), \
         patch("os.path.exists", return_value=True):
        
        # Mock file with insecure permissions (644 = world-readable)
        mock_stat_result = MagicMock()
        mock_stat_result.st_mode = stat.S_IFREG | 0o644
        
        with patch("os.stat", return_value=mock_stat_result):
            # Mock chmod to succeed
            chmod_calls = []

            def mock_chmod(path, mode):
                chmod_calls.append((path, mode))

            with patch("os.chmod", side_effect=mock_chmod):
                # Mock stderr
                mock_stderr = MagicMock()
                with patch("sys.stderr", mock_stderr):
                    check_env_permissions()

                    # Verify chmod was called with 600
                    assert len(chmod_calls) == 1
                    assert chmod_calls[0] == (".env", 0o600)

                    # Verify success message was written
                    mock_stderr.write.assert_called()
                    output = "".join(call.args[0] for call in mock_stderr.write.call_args_list)
                    assert "Fixed .env permissions" in output
                    assert "644" in output
                    assert "600" in output


def test_env_permissions_auto_fix_failure():
    """Test warning when auto-fix fails."""
    # Import here to avoid side effects during test collection
    from main import check_env_permissions
    
    with patch("os.name", "posix"), \
         patch("os.path.exists", return_value=True):
        
        # Mock file with insecure permissions
        mock_stat_result = MagicMock()
        mock_stat_result.st_mode = stat.S_IFREG | 0o666
        
        with patch("os.stat", return_value=mock_stat_result):
            # Mock chmod to fail
            with patch("os.chmod", side_effect=OSError("Permission denied")):
                # Mock stderr
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
    # Import here to avoid side effects during test collection
    from main import check_env_permissions
    
    with patch("os.name", "nt"), \
         patch("os.path.exists", return_value=True):
        
        # Mock stderr
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
    # Import here to avoid side effects during test collection
    from main import check_env_permissions
    
    with patch("os.name", "posix"), \
         patch("os.path.exists", return_value=True):
        
        # Mock file with secure permissions (600)
        mock_stat_result = MagicMock()
        mock_stat_result.st_mode = stat.S_IFREG | 0o600
        
        with patch("os.stat", return_value=mock_stat_result):
            # Mock stderr
            mock_stderr = MagicMock()
            with patch("sys.stderr", mock_stderr):
                check_env_permissions()

                # Verify no output
                mock_stderr.write.assert_not_called()


def test_env_permissions_file_not_exists():
    """Test that missing .env file is silently ignored."""
    # Import here to avoid side effects during test collection
    from main import check_env_permissions
    
    with patch("os.path.exists", return_value=False):
        # Mock stderr
        mock_stderr = MagicMock()
        with patch("sys.stderr", mock_stderr):
            check_env_permissions()

            # Verify no output
            mock_stderr.write.assert_not_called()


def test_env_permissions_stat_error():
    """Test handling of os.stat errors."""
    # Import here to avoid side effects during test collection
    from main import check_env_permissions
    
    with patch("os.name", "posix"), \
         patch("os.path.exists", return_value=True), \
         patch("os.stat", side_effect=OSError("Access denied")):
        
        # Mock stderr
        mock_stderr = MagicMock()
        with patch("sys.stderr", mock_stderr):
            check_env_permissions()

            # Verify error message
            mock_stderr.write.assert_called()
            output = "".join(call.args[0] for call in mock_stderr.write.call_args_list)
            assert "Could not check .env permissions" in output
            assert "OSError" in output


def test_env_permissions_respects_custom_path():
    """Test that custom .env path is respected."""
    # Import here to avoid side effects during test collection
    from main import check_env_permissions
    
    with patch("os.name", "posix"), \
         patch("os.path.exists", return_value=True):
        
        # Mock file with insecure permissions
        mock_stat_result = MagicMock()
        mock_stat_result.st_mode = stat.S_IFREG | 0o644
        
        stat_calls = []

        def mock_stat(path, **kwargs):
            stat_calls.append(path)
            return mock_stat_result

        with patch("os.stat", side_effect=mock_stat):
            chmod_calls = []

            def mock_chmod(path, mode):
                chmod_calls.append((path, mode))

            with patch("os.chmod", side_effect=mock_chmod):
                # Mock stderr
                mock_stderr = MagicMock()
                with patch("sys.stderr", mock_stderr):
                    check_env_permissions("/custom/.env")

                    # Verify custom path was used
                    assert "/custom/.env" in stat_calls
                    assert len(chmod_calls) == 1
                    assert chmod_calls[0][0] == "/custom/.env"

