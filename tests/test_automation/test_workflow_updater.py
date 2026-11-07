import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".github" / "scripts"))

from repository_automation_common import (
    is_commit_sha,
    latest_tag_for_action,
    ref_exists,
    target_ref,
)
from repository_automation_tasks import workflow_file_plans


@patch("repository_automation_common.gh_json")
@patch("repository_automation_common.gh_text")
def test_latest_tag_for_action_prerelease(mock_gh_text, mock_gh_json):
    # Setup: releases/latest returns empty (404), releases list returns non-prerelease
    mock_gh_text.side_effect = ["", "v1.2.3"]
    mock_gh_json.return_value = "v2.0.0"

    assert latest_tag_for_action("actions/checkout") == "v2.0.0"


@patch("repository_automation_common.gh_json")
@patch("repository_automation_common.gh_text")
def test_latest_tag_for_action_empty(mock_gh_text, mock_gh_json):
    # Setup: releases/latest returns empty (404)
    mock_gh_text.side_effect = ["", ""]
    mock_gh_json.return_value = None

    assert latest_tag_for_action("actions/checkout") == ""


def test_target_ref_skips_commit_sha_pins():
    sha = "deadbeef" + "0" * 32
    assert is_commit_sha(sha)
    assert target_ref(sha, "v5.0.0") is None


def test_target_ref_valid_and_invalid():
    # Valid upgrades
    assert target_ref("v4", "v5.0.0") == "v5"
    assert target_ref("v4.2.2", "v4.3.0") == "v4.3.0"
    # When current is 'v4' and latest is 'v4.3.0', target_ref returns 'v4' which triggers a skip later
    assert target_ref("v4", "v4.3.0") == "v4"

    # Invalid tag inputs or no upgrades
    assert target_ref("v4", "v3.0.0") is None
    assert target_ref("v4", "v4") is None
    assert target_ref("invalid", "v5.0.0") is None
    assert target_ref("v4", "invalid") is None


@patch("repository_automation_common.run_process")
def test_ref_exists(mock_run_process):
    # Setup for tag exists
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_run_process.return_value = mock_result
    assert ref_exists("actions/checkout", "v5") is True

    # Setup for tag fails, branch exists
    mock_tag_result = MagicMock()
    mock_tag_result.returncode = 1
    mock_branch_result = MagicMock()
    mock_branch_result.returncode = 0
    mock_run_process.side_effect = [mock_tag_result, mock_branch_result]
    assert ref_exists("actions/checkout", "v5") is True

    # Setup for both fail
    mock_tag_result = MagicMock()
    mock_tag_result.returncode = 1
    mock_branch_result = MagicMock()
    mock_branch_result.returncode = 1
    mock_run_process.side_effect = [mock_tag_result, mock_branch_result]
    assert ref_exists("actions/checkout", "v5") is False


@patch("repository_automation_tasks.ROOT")
@patch("repository_automation_tasks.latest_tag_for_action")
@patch("repository_automation_tasks.ref_exists")
def test_workflow_file_plans_skips_non_existent(
    mock_ref_exists, mock_latest_tag, mock_root
):
    class MockPath:
        def __init__(self, name, text):
            self.name = name
            self._text = text

        def read_text(self):
            return self._text

        def relative_to(self, root):
            return self.name

        def __lt__(self, other):
            return self.name < other.name

        def __str__(self):
            return self.name

    with patch("repository_automation_tasks.target_ref") as mock_target_ref:
        # Test 1: ref does not exist
        p1 = MockPath(".github/workflows/test.yml", "uses: actions/checkout@v4")
        mock_root.__truediv__.return_value.__truediv__.return_value.glob.return_value = [
            p1
        ]

        mock_target_ref.return_value = "v5"
        mock_ref_exists.return_value = False
        plans_missing = workflow_file_plans()
        assert len(plans_missing) == 0  # Should be skipped because ref doesn't exist

        # Test 2: ref exists
        p2 = MockPath(".github/workflows/test2.yml", "uses: actions/setup-node@v3")
        mock_root.__truediv__.return_value.__truediv__.return_value.glob.return_value = [
            p2
        ]

        mock_target_ref.return_value = "v4"
        mock_ref_exists.return_value = True
        plans_exist = workflow_file_plans()

        assert len(plans_exist) == 1
        assert plans_exist[0]["replacements"][0]["target"] == "v4"
        assert plans_exist[0]["replacements"][0]["is_major_bump"] is True
