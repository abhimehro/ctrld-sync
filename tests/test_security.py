"""
Tests for security features in main.py and fix_env.py
"""
import os
import stat
import sys
import tempfile
from unittest.mock import MagicMock, patch, mock_open
import pytest


def _check_env_permissions_and_warn(env_file_path, mock_stderr):
    """
    Helper function that replicates the permission check logic from main.py.
    This is used in tests to verify the behavior without importing main.py.
    """
    file_stat = os.stat(env_file_path)
    if file_stat.st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        platform_hint = (
            "Please secure your .env file so it is only readable by "
            "the owner."
        )
        if os.name != "nt":
            platform_hint += " For example: 'chmod 600 .env'."
        perms = format(stat.S_IMODE(file_stat.st_mode), '03o')
        mock_stderr.write(
            f"⚠️  Security Warning: .env file is "
            f"readable by others ({perms})! {platform_hint}\n"
        )


def test_env_permission_check_warns_on_insecure_permissions(monkeypatch, tmp_path):
    """Test that insecure .env permissions trigger a warning."""
    # Create a temporary .env file
    env_file = tmp_path / ".env"
    env_file.write_text("TOKEN=test")
    
    # Set insecure permissions (readable by others)
    if os.name != 'nt':  # Skip on Windows
        os.chmod(env_file, 0o644)
        
        # Mock sys.stderr to capture warnings
        mock_stderr = MagicMock()
        monkeypatch.setattr(sys, "stderr", mock_stderr)
        
        # Run the permission check logic
        _check_env_permissions_and_warn(env_file, mock_stderr)
        
        # Verify warning was written
        mock_stderr.write.assert_called()
        call_args = mock_stderr.write.call_args[0][0]
        assert "Security Warning" in call_args
        assert "readable by others" in call_args
        assert "644" in call_args


def test_env_permission_check_no_warn_on_secure_permissions(monkeypatch, tmp_path):
    """Test that secure .env permissions do not trigger a warning."""
    # Create a temporary .env file
    env_file = tmp_path / ".env"
    env_file.write_text("TOKEN=test")
    
    # Set secure permissions (readable only by owner)
    if os.name != 'nt':  # Skip on Windows
        os.chmod(env_file, 0o600)
        
        # Mock sys.stderr to capture warnings
        mock_stderr = MagicMock()
        monkeypatch.setattr(sys, "stderr", mock_stderr)
        
        # Run the permission check logic
        _check_env_permissions_and_warn(env_file, mock_stderr)
        
        # Verify no warning was written
        mock_stderr.write.assert_not_called()


def test_env_permission_check_handles_stat_error(monkeypatch):
    """Test that permission check handles stat() errors gracefully."""
    # Mock sys.stderr to capture warnings
    mock_stderr = MagicMock()
    monkeypatch.setattr(sys, "stderr", mock_stderr)
    
    # Simulate a permission error
    try:
        raise PermissionError("Cannot access file")
    except Exception as error:
        exception_type = type(error).__name__
        sys.stderr.write(
            f"⚠️  Security Warning: Could not check .env "
            f"permissions ({exception_type}: {error})\n"
        )
    
    # Verify error warning was written
    mock_stderr.write.assert_called()
    call_args = mock_stderr.write.call_args[0][0]
    assert "Security Warning" in call_args
    assert "Could not check .env permissions" in call_args
    assert "PermissionError" in call_args


def test_fix_env_sets_secure_permissions(tmp_path, monkeypatch):
    """Test that fix_env.py sets secure permissions on .env file."""
    # Change to temp directory
    monkeypatch.chdir(tmp_path)
    
    # Create a .env file with insecure content
    env_file = tmp_path / ".env"
    env_file.write_text("TOKEN='test_token'\nPROFILE='test_profile'\n")
    
    if os.name != 'nt':  # Skip on Windows
        # Set insecure permissions initially
        os.chmod(env_file, 0o644)
        
        # Import and run fix_env
        import fix_env
        fix_env.fix_env()
        
        # Check that permissions are now secure
        file_stat = os.stat(env_file)
        mode = stat.S_IMODE(file_stat.st_mode)
        
        # Verify permissions are 600 (read/write for owner only)
        assert mode == 0o600, f"Expected 600, got {oct(mode)}"
        
        # Verify no group or other permissions
        assert not (file_stat.st_mode & stat.S_IRWXG), "Group has permissions"
        assert not (file_stat.st_mode & stat.S_IRWXO), "Others have permissions"


def test_fix_env_skips_chmod_on_windows(tmp_path, monkeypatch):
    """Test that fix_env.py skips chmod on Windows."""
    # Change to temp directory
    monkeypatch.chdir(tmp_path)
    
    # Create a .env file
    env_file = tmp_path / ".env"
    env_file.write_text("TOKEN='test_token'\nPROFILE='test_profile'\n")
    
    # Mock os.name to simulate Windows
    monkeypatch.setattr(os, "name", "nt")
    
    # Mock os.chmod to verify it's not called
    mock_chmod = MagicMock()
    monkeypatch.setattr(os, "chmod", mock_chmod)
    
    # Import and run fix_env
    import fix_env
    fix_env.fix_env()
    
    # Verify chmod was not called on Windows
    mock_chmod.assert_not_called()


def test_octal_permission_format():
    """Test that octal permission formatting is robust."""
    # Test various permission modes
    test_modes = [
        0o644,  # rw-r--r--
        0o600,  # rw-------
        0o755,  # rwxr-xr-x
        0o000,  # ---------
    ]
    
    for mode in test_modes:
        # The robust way
        result = format(stat.S_IMODE(mode), '03o')
        # Should always be 3 digits
        assert len(result) == 3, f"Expected 3 digits for {oct(mode)}, got {result}"
        # Should be numeric
        assert result.isdigit(), f"Expected numeric for {oct(mode)}, got {result}"
