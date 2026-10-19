"""
Tests for 400-recovery on batched Control D rule pushes.

Covers the recovery added to _push_single_batch (retry + bisection):
- transient 400 -> same-payload retry succeeds -> batch completes
- persistent 400 with one bad rule -> bisection isolates and drops it
- every rule rejected -> batch fails, drops logged, existing_rules untouched
- non-400 errors keep the existing hint-log + batch-failure behavior
"""

import os
import sys
from unittest.mock import MagicMock, patch

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main


def _make_http_status_error(status_code: int) -> httpx.HTTPStatusError:
    """Create a minimal HTTPStatusError with the given status code."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = status_code
    mock_request = MagicMock(spec=httpx.Request)
    return httpx.HTTPStatusError(
        f"{status_code} Error",
        request=mock_request,
        response=mock_response,
    )


def _make_ctx():
    ctx = main.SyncContext(profile_id="p1", client=MagicMock(), existing_rules=set())
    action = main.RuleAction(do=1, status=1)
    return ctx, action


def test_transient_400_recovers_with_same_payload_retry():
    err = _make_http_status_error(400)
    ctx, action = _make_ctx()

    with (
        patch("sync._api_post_form", side_effect=[err, None]),
        patch("time.sleep") as mock_sleep,
        patch("sync.log"),
        patch("sync.USE_COLORS", False),
    ):
        result = main.push_rules(ctx, "folder", "fid", action, ["a.com", "b.com"])

    assert result is True
    assert ctx.existing_rules == {"a.com", "b.com"}
    assert mock_sleep.call_count == 1


def test_persistent_400_isolates_and_drops_bad_rule():
    """A 400 caused by one rule must drop only that rule, not the batch."""
    posted = []

    def rejecting_post(client, url, data):
        posted.append(data)
        values = [v for k, v in data.items() if str(k).startswith("hostnames")]
        if "bad.domain" in values:
            raise _make_http_status_error(400)

    ctx, action = _make_ctx()
    rules = ["a.com", "bad.domain", "c.com", "d.com"]

    with (
        patch("sync._api_post_form", side_effect=rejecting_post),
        patch("time.sleep"),
        patch("sync.log") as mock_log,
        patch("sync.USE_COLORS", False),
    ):
        result = main.push_rules(ctx, "folder", "fid", action, rules)

    assert result is True
    assert ctx.existing_rules == {"a.com", "c.com", "d.com"}
    assert "bad.domain" in str(mock_log.warning.call_args_list)


def test_all_rules_rejected_fails_the_batch():
    ctx, action = _make_ctx()

    with (
        patch("sync._api_post_form", side_effect=_make_http_status_error(400)),
        patch("time.sleep"),
        patch("sync.log") as mock_log,
        patch("sync.USE_COLORS", False),
    ):
        result = main.push_rules(ctx, "folder", "fid", action, ["a.com", "b.com"])

    assert result is False
    assert ctx.existing_rules == set()
    assert "dropping rule" in str(mock_log.warning.call_args_list)


def test_non_400_error_keeps_existing_failure_behavior():
    err = _make_http_status_error(401)
    ctx, action = _make_ctx()

    with (
        patch("sync._api_post_form", side_effect=err),
        patch("time.sleep") as mock_sleep,
        patch("sync.log") as mock_log,
        patch("sync.USE_COLORS", False),
    ):
        result = main.push_rules(ctx, "folder", "fid", action, ["a.com"])

    assert result is False
    assert ctx.existing_rules == set()
    assert mock_sleep.call_count == 0
    assert "TOKEN" in str(mock_log.error.call_args_list)
