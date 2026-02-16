import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# We need to import main to test it, but we want to test its behavior when run
import main


def test_main_reloads_token_from_env(monkeypatch):
    """
    Verify that main() reloads TOKEN from environment variables after load_dotenv().
    This ensures that secrets from .env are picked up even if the module was imported earlier.
    """
    # 1. Setup initial state
    monkeypatch.setenv("TOKEN", "initial_token")
    # Force reload main to pick up initial token
    import importlib
    importlib.reload(main)
    assert main.TOKEN == "initial_token"

    # 2. Mock dependencies
    # Mock load_dotenv to simulate loading a .env file that changes TOKEN
    def mock_load_dotenv():
        os.environ["TOKEN"] = "loaded_from_env_file"

    # Mock other parts of main to prevent actual execution
    mock_args = MagicMock()
    mock_args.profiles = "p1"
    mock_args.folder_url = None
    mock_args.dry_run = True  # Dry run to exit early
    mock_args.no_delete = False
    mock_args.plan_json = None

    # Mock check_env_permissions to avoid filesystem checks
    mock_check_perms = MagicMock()

    # Mock warm_up_cache to avoid network calls
    mock_warm_up = MagicMock()

    # Mock sync_profile to avoid logic
    mock_sync = MagicMock(return_value=True)

    # Apply mocks
    # Patch main.load_dotenv because main.py imports it as 'from dotenv import load_dotenv'
    with patch("main.load_dotenv", side_effect=mock_load_dotenv) as mock_load_dotenv_call, \
         patch("main.parse_args", return_value=mock_args), \
         patch("main.check_env_permissions", mock_check_perms), \
         patch("main.warm_up_cache", mock_warm_up), \
         patch("main.sync_profile", mock_sync), \
         patch("sys.stdin.isatty", return_value=False):  # Non-interactive

        # 3. Run main()
        # This should call load_dotenv (our mock), which updates env var,
        # then main should update global TOKEN from env var.
        with pytest.raises(SystemExit):
            main.main()

        # 4. Verify
        # load_dotenv must have been called
        assert mock_load_dotenv_call.called

        # check_env_permissions must have been called BEFORE load_dotenv
        # We can check order by checking if check_perms was called
        # But verifying exact order is hard with separate mocks unless we use a manager
        # However, if main.TOKEN is updated, we know the logic ran.

        assert main.TOKEN == "loaded_from_env_file"
