import os
import stat
import sys
from unittest.mock import MagicMock

import pytest

import fix_env
import main


def test_push_rules_filters_xss_payloads():
    """
    Verify that push_rules filters out malicious strings (XSS payloads).
    """
    mock_client = MagicMock()
    mock_post_form = MagicMock()

    # Patch the API call
    original_post_form = main._api_post_form
    main._api_post_form = mock_post_form

    # Patch the logger to verify warnings
    mock_log = MagicMock()
    original_log = main.log
    main.log = mock_log

    try:
        malicious_rules = [
            "<script>alert(1)</script>",
            "valid.com",
            "javascript:void(0)",
            "fail' OR '1'='1",
            "img src=x onerror=alert(1)",
            "safe-domain.com",
            "1.1.1.1",
            "*.wildcard.com",
        ]

        main.push_rules(
            profile_id="p1",
            folder_name="f1",
            folder_id="fid1",
            do=1,
            status=1,
            hostnames=malicious_rules,
            existing_rules=set(),
            client=mock_client,
        )

        # Check what was sent
        assert mock_post_form.called
        calls = mock_post_form.call_args_list

        sent_rules = []
        for call in calls:
            args, kwargs = call
            data = kwargs["data"]
            for k, v in data.items():
                if k.startswith("hostnames["):
                    sent_rules.append(v)

        # EXPECTED BEHAVIOR: Malicious rules are NOT sent
        assert "<script>alert(1)</script>" not in sent_rules
        assert "javascript:void(0)" not in sent_rules  # Contains parenthesis/colon?
        # Wait, 'javascript:void(0)' has '('. My validator blocks '('.
        assert "fail' OR '1'='1" not in sent_rules  # Contains '
        assert (
            "img src=x onerror=alert(1)" not in sent_rules
        )  # Contains ( ) or =? No = is allowed?
        # "img src=x onerror=alert(1)" contains spaces?
        # My validator: isprintable() is True.
        # dangerous_chars: set("<>\"'`();{}[]")
        # <script> has < >
        # javascript:void(0) has ( )
        # fail' has '
        # img src=x ... has ( )

        # Valid rules MUST be sent
        assert "valid.com" in sent_rules
        assert "safe-domain.com" in sent_rules
        assert "1.1.1.1" in sent_rules
        assert "*.wildcard.com" in sent_rules

        # Check logs for warnings
        # We expect 4 skipped rules
        assert mock_log.warning.call_count >= 1
        found_unsafe_log = False
        for call in mock_log.warning.call_args_list:
            if "Skipping unsafe rule" in str(call):
                found_unsafe_log = True
        assert found_unsafe_log

    finally:
        main._api_post_form = original_post_form
        main.log = original_log


@pytest.mark.skipif(
    os.name == "nt", reason="Unix permissions not applicable on Windows"
)
def test_env_permission_check_warns_on_insecure_permissions(monkeypatch, tmp_path):
    """Test that insecure .env permissions trigger a warning."""
    # Import main to get access to check_env_permissions and Colors
    import main

    # Create a temporary .env file
    env_file = tmp_path / ".env"
    env_file.write_text("TOKEN=test")
    os.chmod(env_file, 0o644)

    # Mock sys.stderr to capture warnings
    mock_stderr = MagicMock()
    monkeypatch.setattr(sys, "stderr", mock_stderr)

    # Run the permission check logic
    main.check_env_permissions(str(env_file))

    # Verify warning was written
    mock_stderr.write.assert_called()
    call_args = mock_stderr.write.call_args[0][0]
    assert "Security Warning" in call_args
    assert "readable by others" in call_args
    assert "644" in call_args


@pytest.mark.skipif(
    os.name == "nt", reason="Unix permissions not applicable on Windows"
)
def test_env_permission_check_no_warn_on_secure_permissions(monkeypatch, tmp_path):
    """Test that secure .env permissions do not trigger a warning."""
    # Import main to get access to check_env_permissions
    import main

    # Create a temporary .env file
    env_file = tmp_path / ".env"
    env_file.write_text("TOKEN=test")
    os.chmod(env_file, 0o600)

    # Mock sys.stderr to capture warnings
    mock_stderr = MagicMock()
    monkeypatch.setattr(sys, "stderr", mock_stderr)

    # Run the permission check logic
    main.check_env_permissions(str(env_file))

    # Verify no warning was written
    mock_stderr.write.assert_not_called()


def test_env_permission_check_handles_stat_error(monkeypatch):
    """Test that permission check handles stat() errors gracefully."""
    # Import main to get access to check_env_permissions
    import main

    # Mock sys.stderr to capture warnings
    mock_stderr = MagicMock()
    monkeypatch.setattr(sys, "stderr", mock_stderr)

    # Mock os.stat to raise an exception
    def mock_stat(path):
        raise PermissionError("Cannot access file")

    monkeypatch.setattr(os, "stat", mock_stat)
    # Mock os.path.exists to return True so the check proceeds
    monkeypatch.setattr(os.path, "exists", lambda x: True)

    # Run the permission check - should handle the error gracefully
    main.check_env_permissions(".env")

    # Verify error warning was written
    mock_stderr.write.assert_called()
    call_args = mock_stderr.write.call_args[0][0]
    assert "Security Warning" in call_args
    assert "Could not check .env permissions" in call_args
    assert "PermissionError" in call_args


@pytest.mark.skipif(
    os.name == "nt", reason="Unix permissions not applicable on Windows"
)
def test_fix_env_sets_secure_permissions(tmp_path, monkeypatch):
    """Test that fix_env.py sets secure permissions on .env file."""
    # Change to temp directory
    monkeypatch.chdir(tmp_path)

    # Create a .env file with insecure content
    env_file = tmp_path / ".env"
    env_file.write_text("TOKEN='test_token'\\nPROFILE='test_profile'\\n")

    # Set insecure permissions initially
    os.chmod(env_file, 0o644)

    # Run fix_env
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
    env_file.write_text("TOKEN='test_token'\\nPROFILE='test_profile'\\n")

    # Mock os.name to simulate Windows
    monkeypatch.setattr(os, "name", "nt")

    # Mock os.chmod to verify it's not called
    mock_chmod = MagicMock()
    monkeypatch.setattr(os, "chmod", mock_chmod)

    # Run fix_env
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
        result = format(stat.S_IMODE(mode), "03o")
        # Should always be 3 digits
        assert len(result) == 3, f"Expected 3 digits for {oct(mode)}, got {result}"
        # Should be numeric
        assert result.isdigit(), f"Expected numeric for {oct(mode)}, got {result}"
