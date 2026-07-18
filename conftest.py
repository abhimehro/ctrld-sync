# Disable pytest cache provider due to container permission issues
import pytest

import main

pytest_plugins: list[str] = []


def pytest_configure(config):
    config.option.cache = "no"


@pytest.fixture(autouse=True)
def _default_test_blocklist_allowlist():
    main.set_allowed_blocklist_domains(
        [
            "raw.githubusercontent.com",
            "github.com",
            "yokoffing.github.io",
            "example.com",
        ]
    )
    yield
    main.set_allowed_blocklist_domains(None)
