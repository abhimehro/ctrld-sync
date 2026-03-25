import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".github" / "scripts"))

from repository_automation_common import latest_tag_for_action, ref_exists, target_ref
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
    # Setup fake workflow file
    mock_workflows_dir = MagicMock()
    mock_file = MagicMock()
    mock_file.read_text.return_value = "uses: actions/checkout@v4"
    mock_file.relative_to.return_value = ".github/workflows/test.yml"
    mock_workflows_dir.glob.return_value = [mock_file]
    mock_root.__truediv__.return_value = mock_workflows_dir

    # The workflow_file_plans function uses an internal cache: latest_cache: dict[str, str] = {}
    # Because of this cache, we cannot just change mock_ref_exists on a second call
    # without running into potential issues if it caches the result or if the generator is exhausted.
    # We should run it fresh each time.

    # Sorted iterator issue? The glob uses sorted(), so if it's not a real path it might fail inside sorted
    # Let's mock the actual path representation
    mock_file.__lt__ = lambda self, other: True

    # Let's just create a list of mock files directly
    # Wait, the code is: sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))

    # Resetting the mock iterables correctly so multiple calls work
    mock_file1 = MagicMock()
    mock_file1.read_text.return_value = "uses: actions/checkout@v4"
    mock_file1.relative_to.return_value = ".github/workflows/test.yml"
    mock_file1.__lt__ = lambda self, other: True

    mock_file2 = MagicMock()
    mock_file2.read_text.return_value = "uses: actions/setup-node@v3"
    mock_file2.relative_to.return_value = ".github/workflows/test2.yml"
    mock_file2.__lt__ = lambda self, other: True

    # To fix issues with the pathlib mock, define a mock path class.
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
