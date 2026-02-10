import os
import stat
import pytest
from unittest.mock import MagicMock, patch
import main

def test_check_env_permissions_skips_symlink(tmp_path):
    """
    Verify that check_env_permissions skips symlinks and logs a warning.
    This prevents modifying permissions of the symlink target.
    """
    # Create a target file
    target_file = tmp_path / "target_file"
    target_file.write_text("target content")

    # Set permissions to 644 (world-readable)
    target_file.chmod(0o644)
    initial_mode = target_file.stat().st_mode

    # Create a symlink to the target
    symlink = tmp_path / ".env_symlink"
    try:
        os.symlink(target_file, symlink)
    except OSError:
        pytest.skip("Symlinks not supported on this platform")

    # Mock stderr to verify warning
    with patch("sys.stderr") as mock_stderr:
        # Run check_env_permissions on the symlink
        main.check_env_permissions(str(symlink))

        # Verify warning was logged
        assert mock_stderr.write.called
        warning_msg = mock_stderr.write.call_args[0][0]
        assert "Security Warning" in warning_msg
        assert "is a symlink" in warning_msg

    # Verify target permissions are UNCHANGED
    final_mode = target_file.stat().st_mode
    assert final_mode == initial_mode
    assert (final_mode & 0o777) == 0o644  # Still 644, not 600

def test_check_env_permissions_fixes_file(tmp_path):
    """
    Verify that check_env_permissions fixes permissions for a regular file.
    """
    if os.name == 'nt':
        pytest.skip("Permission fix not supported on Windows")

    # Create a regular file
    env_file = tmp_path / ".env_file"
    env_file.write_text("content")

    # Set permissions to 644 (world-readable)
    env_file.chmod(0o644)

    # Run check_env_permissions
    with patch("sys.stderr") as mock_stderr:
        main.check_env_permissions(str(env_file))

        # Verify success message (or at least no warning about symlink)
        # Note: Depending on implementation, it might log "Fixed .env permissions"
        # We can check permissions directly.

    # Verify permissions are fixed to 600
    final_mode = env_file.stat().st_mode
    assert (final_mode & 0o777) == 0o600
