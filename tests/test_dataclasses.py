import dataclasses
import sys
import os
from unittest.mock import MagicMock, patch

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@pytest.fixture(name="main_module")
def _main_module():
    """Return the already-imported main module (or import it fresh)."""
    if "main" in sys.modules:
        return sys.modules["main"]
    import main  # noqa: PLC0415

    return main


def test_rule_action_is_immutable(main_module):
    """RuleAction is frozen=True – mutating any field must raise FrozenInstanceError."""
    action = main_module.RuleAction(do=1, status=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        action.do = 99  # type: ignore[misc]


def test_sync_context_batch_executor_defaults_to_none(main_module):
    """SyncContext.batch_executor should default to None when not provided."""
    ctx = main_module.SyncContext(
        profile_id="p1",
        client=MagicMock(),
        existing_rules=set(),
    )
    assert ctx.batch_executor is None


@patch("main.concurrent.futures.as_completed")
@patch("main.concurrent.futures.ThreadPoolExecutor")
def test_push_rules_creates_executor_when_none(
    mock_tpe_cls, mock_as_completed, main_module
):
    """push_rules must create a ThreadPoolExecutor internally when ctx.batch_executor is None."""
    # Derive sizes from the module constant so this test stays correct if BATCH_SIZE is tuned.
    batch_size = main_module.BATCH_SIZE
    hostnames = [f"example{i}.com" for i in range(batch_size + 1)]  # 2 batches

    mock_executor_instance = MagicMock()
    mock_tpe_cls.return_value.__enter__ = MagicMock(
        return_value=mock_executor_instance
    )
    mock_tpe_cls.return_value.__exit__ = MagicMock(return_value=False)

    # Use two distinct futures representing the two batches
    mock_future_1 = MagicMock()
    mock_future_1.result.return_value = hostnames[:batch_size]
    mock_future_2 = MagicMock()
    mock_future_2.result.return_value = hostnames[batch_size:]

    mock_executor_instance.submit.side_effect = [mock_future_1, mock_future_2]
    mock_as_completed.return_value = [mock_future_1, mock_future_2]

    with patch("main._api_post_form"):
        ctx = main_module.SyncContext(
            profile_id="p1",
            client=MagicMock(),
            existing_rules=set(),
            batch_executor=None,
        )
        action = main_module.RuleAction(do=1, status=1)
        result = main_module.push_rules(
            ctx,
            "folder_name",
            "folder_id",
            action,
            hostnames,
        )

    assert result is True
    assert mock_tpe_cls.called, "ThreadPoolExecutor should be created when batch_executor is None"
