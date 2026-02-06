import os
import stat
import sys
from unittest.mock import MagicMock
import main

def test_check_env_permissions_fixes_loose_permissions(monkeypatch):
    """Test that check_env_permissions attempts to fix loose permissions."""

    # Mock os.name to be 'posix' (non-nt)
    monkeypatch.setattr(os, "name", "posix")

    # Mock os.path.exists to return True
    monkeypatch.setattr(os.path, "exists", lambda x: True)

    # Mock os.stat to return loose permissions (e.g., 777)
    mock_stat = MagicMock()
    mock_stat.st_mode = 0o777
    monkeypatch.setattr(os, "stat", lambda x: mock_stat)

    # Mock os.chmod
    mock_chmod = MagicMock()
    monkeypatch.setattr(os, "chmod", mock_chmod)

    # Mock sys.stderr to capture output
    mock_stderr = MagicMock()
    monkeypatch.setattr(sys, "stderr", mock_stderr)

    # Run
    main.check_env_permissions(".env")

    # Assert chmod was called with 600 (stat.S_IRUSR | stat.S_IWUSR)
    mock_chmod.assert_called_once_with(".env", stat.S_IRUSR | stat.S_IWUSR)

    # Assert success message logged
    # We check if at least one call contained the success message
    found = False
    for call_args in mock_stderr.write.call_args_list:
        if "Fixed .env permissions" in call_args[0][0] and "set to 600" in call_args[0][0]:
            found = True
            break
    assert found, "Success message not found in stderr writes"

def test_check_env_permissions_warns_on_fix_failure(monkeypatch):
    """Test that it warns if chmod fails."""

    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(os.path, "exists", lambda x: True)

    mock_stat = MagicMock()
    mock_stat.st_mode = 0o777
    monkeypatch.setattr(os, "stat", lambda x: mock_stat)

    # Mock chmod to raise exception
    def raise_error(*args):
        raise PermissionError("Access denied")
    monkeypatch.setattr(os, "chmod", raise_error)

    mock_stderr = MagicMock()
    monkeypatch.setattr(sys, "stderr", mock_stderr)

    main.check_env_permissions(".env")

    # Assert warning message logged with failure hint
    found = False
    for call_args in mock_stderr.write.call_args_list:
        msg = call_args[0][0]
        if "Security Warning" in msg and "Auto-fix failed" in msg:
            found = True
            break
    assert found, "Failure warning not found in stderr writes"

def test_check_env_permissions_ignores_secure_permissions(monkeypatch):
    """Test that it does nothing if permissions are already secure."""

    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setattr(os.path, "exists", lambda x: True)

    # 0o600 is S_IRUSR | S_IWUSR
    # os.stat returns st_mode which includes file type bits, but check_env_permissions masks with S_IRWXG | S_IRWXO
    # So we just need to ensure the group/other bits are 0.
    mock_stat = MagicMock()
    mock_stat.st_mode = stat.S_IRUSR | stat.S_IWUSR # 600
    monkeypatch.setattr(os, "stat", lambda x: mock_stat)

    mock_chmod = MagicMock()
    monkeypatch.setattr(os, "chmod", mock_chmod)

    mock_stderr = MagicMock()
    monkeypatch.setattr(sys, "stderr", mock_stderr)

    main.check_env_permissions(".env")

    # Assert chmod NOT called
    mock_chmod.assert_not_called()

    # Assert nothing written to stderr
    mock_stderr.write.assert_not_called()

def test_check_env_permissions_warns_on_windows(monkeypatch):
    """Test that it only warns (no fix attempt) on Windows."""

    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(os.path, "exists", lambda x: True)

    mock_stat = MagicMock()
    mock_stat.st_mode = 0o777
    monkeypatch.setattr(os, "stat", lambda x: mock_stat)

    mock_chmod = MagicMock()
    monkeypatch.setattr(os, "chmod", mock_chmod)

    mock_stderr = MagicMock()
    monkeypatch.setattr(sys, "stderr", mock_stderr)

    main.check_env_permissions(".env")

    # Assert chmod NOT called
    mock_chmod.assert_not_called()

    # Assert warning message logged
    found = False
    for call_args in mock_stderr.write.call_args_list:
        msg = call_args[0][0]
        if "Security Warning" in msg and "chmod 600 .env" in msg:
            found = True
            break
    assert found, "Windows warning not found"
