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
            "example.com",
        ]
    )
    yield
    main.set_allowed_blocklist_domains(None)


@pytest.fixture(autouse=True)
def _reset_default_batch_executor():
    main._DEFAULT_BATCH_EXECUTOR = None
    yield
    executor = main._DEFAULT_BATCH_EXECUTOR
    main._DEFAULT_BATCH_EXECUTOR = None
    if executor is not None:
        executor.shutdown(wait=False)
