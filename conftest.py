# Disable pytest cache provider due to container permission issues
import pytest

import main

pytest_plugins: list[str] = []


def pytest_configure(config):
    config.option.cache = "no"


@pytest.fixture(autouse=True)
def _default_test_blocklist_allowlist():
    inline_executor = getattr(main, "_INLINE_BATCH_EXECUTOR", None)
    if inline_executor is not None:
        inline_executor.shutdown(wait=False, cancel_futures=True)
        main._INLINE_BATCH_EXECUTOR = None
    main.set_allowed_blocklist_domains(
        [
            "raw.githubusercontent.com",
            "github.com",
            "example.com",
        ]
    )
    yield
    inline_executor = getattr(main, "_INLINE_BATCH_EXECUTOR", None)
    if inline_executor is not None:
        inline_executor.shutdown(wait=False, cancel_futures=True)
        main._INLINE_BATCH_EXECUTOR = None
    main.set_allowed_blocklist_domains(None)
