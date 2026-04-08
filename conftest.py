# Disable pytest cache provider due to container permission issues
pytest_plugins: list[str] = []


def pytest_configure(config):
    config.option.cache = "no"
