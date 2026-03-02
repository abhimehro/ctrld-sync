import os
import pytest
import fix_env


def test_fix_env_skips_symlink(tmp_path):
    """
    Verify that fix_env replaces a symlink with a regular file
    using atomic temp file replacement to prevent TOCTOU.
    """
    # Create a target file
    target_file = tmp_path / "target_file"

    # Use realistic values so fix_env heuristic doesn't swap them
    token = "api.1234567890abcdef"
    profile = "12345abc"
    target_file.write_text(f"TOKEN={token}\nPROFILE={profile}")

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        symlink = tmp_path / ".env"
        try:
            os.symlink(target_file.name, symlink.name)
        except OSError:
            pytest.skip("Symlinks not supported")

        fix_env.fix_env()

        # The symlink should be gone, replaced by a real file
        assert not os.path.islink(".env")
        assert os.path.isfile(".env")

        # The target file should remain untouched
        assert target_file.read_text() == f"TOKEN={token}\nPROFILE={profile}"

        # The new .env file should contain the formatted output
        content = symlink.read_text()
        assert f'TOKEN="{token}"' in content
        assert f'PROFILE="{profile}"' in content

    finally:
        os.chdir(cwd)


def test_fix_env_creates_secure_file(tmp_path):
    """
    Verify that fix_env creates .env with 600 permissions.
    """
    if os.name == "nt":
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
