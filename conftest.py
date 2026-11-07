import pytest

import main


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
