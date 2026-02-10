import os
import stat
import pytest
from unittest.mock import MagicMock, patch
import fix_env

def test_fix_env_skips_symlink(tmp_path):
    """
    Verify that fix_env skips symlinks and logs a warning.
    This prevents overwriting the target file.
    """
    # Create a target file
    target_file = tmp_path / "target_file"
    target_file.write_text("TOKEN=foo\nPROFILE=bar")

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        symlink = tmp_path / ".env"
        try:
            os.symlink(target_file.name, symlink.name)
        except OSError:
            pytest.skip("Symlinks not supported")

        # Mock print to verify warning
        with patch("builtins.print") as mock_print:
            fix_env.fix_env()

            # Verify warning was printed
            assert mock_print.called
            found = False
            for call_args in mock_print.call_args_list:
                msg = call_args[0][0]
                if "Security Warning" in msg and "symlink" in msg:
                    found = True
                    break
            assert found, "Warning about symlink not found"

        # Verify target file content is UNCHANGED
        assert target_file.read_text() == "TOKEN=foo\nPROFILE=bar"

    finally:
        os.chdir(cwd)

def test_fix_env_creates_secure_file(tmp_path):
    """
    Verify that fix_env creates .env with 600 permissions.
    """
    if os.name == 'nt':
        pytest.skip("Permission check not supported on Windows")

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        # Use realistic token (starts with api. or long)
        # nosec - testing token, not real secret
        token = "api.1234567890abcdef"
        profile = "12345abc"

        with open(".env", "w") as f:
            f.write(f"TOKEN={token}\nPROFILE={profile}")

        # Set permissions to 644 (world-readable), which should be fixed to 600
        # 0o777 is flagged by bandit B103
        os.chmod(".env", 0o644)

        # Run fix_env
        fix_env.fix_env()

        # Verify permissions are 600
        st = os.stat(".env")
        assert (st.st_mode & 0o777) == 0o600

        # Verify content is fixed and quoted
        content = open(".env").read()
        assert f'TOKEN="{token}"' in content
        assert f'PROFILE="{profile}"' in content

    finally:
        os.chdir(cwd)
