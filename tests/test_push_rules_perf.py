
import unittest
from unittest.mock import MagicMock, patch, ANY
import sys
import os

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main

class TestPushRulesPerf(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.profile_id = "test_profile"
        self.folder_name = "test_folder"
        self.folder_id = "test_folder_id"
        self.do = 1
        self.status = 1
        self.existing_rules = set()

    @patch("main.concurrent.futures.as_completed")
    @patch("main.concurrent.futures.ThreadPoolExecutor")
    def test_push_rules_single_batch_optimization(self, mock_executor, mock_as_completed):
        """
        Test that push_rules avoids ThreadPoolExecutor for single batch (< 500 rules).
        """
        # Create < 500 rules (1 batch)
        hostnames = [f"example{i}.com" for i in range(100)]

        # Mock executor context manager
        mock_executor_instance = mock_executor.return_value
        mock_executor_instance.__enter__.return_value = mock_executor_instance
        mock_executor_instance.__exit__.return_value = None

        # Mock future
        mock_future = MagicMock()
        mock_future.result.return_value = hostnames # Success
        mock_executor_instance.submit.return_value = mock_future

        # Mock as_completed to yield the future immediately
        mock_as_completed.return_value = [mock_future]

        # Since we are bypassing TPE, we might need to mock API call?
        # The code will call process_batch(1, batch).
        # process_batch calls _api_post_form.
        # client is mocked, so _api_post_form works (retries mocked).
        # But we need to ensure process_batch works correctly in isolation.

        # For this test, we mock _api_post_form?
        # No, _api_post_form calls client.post.

        main.push_rules(
            self.profile_id,
            self.folder_name,
            self.folder_id,
            self.do,
            self.status,
            hostnames,
            self.existing_rules,
            self.client
        )

        # Verify if Executor was called.
        # AFTER OPTIMIZATION: This should be False.
        self.assertFalse(mock_executor.called, "ThreadPoolExecutor should NOT be called for single batch")

    @patch("main.concurrent.futures.as_completed")
    @patch("main.concurrent.futures.ThreadPoolExecutor")
    def test_push_rules_multi_batch(self, mock_executor, mock_as_completed):
        """
        Test that push_rules uses ThreadPoolExecutor for multiple batches (> 500 rules).
        """
        # Create > 500 rules (2 batches)
        hostnames = [f"example{i}.com" for i in range(600)]

        mock_executor_instance = mock_executor.return_value
        mock_executor_instance.__enter__.return_value = mock_executor_instance

        # Mock submit to return a Future
        mock_future = MagicMock()
        mock_future.result.return_value = ["some_rule"]
        mock_executor_instance.submit.return_value = mock_future

        mock_as_completed.return_value = [mock_future, mock_future] # 2 batches

        main.push_rules(
            self.profile_id,
            self.folder_name,
            self.folder_id,
            self.do,
            self.status,
            hostnames,
            self.existing_rules,
            self.client
        )

        # This should ALWAYS be True
        self.assertTrue(mock_executor.called, "ThreadPoolExecutor should be called for multi-batch")

    @patch.object(main, "RULE_PATTERN")
    def test_push_rules_skips_validation_for_existing(self, mock_rule_pattern):
        """
        Test that RULE_PATTERN.match is NOT called for rules that are already in existing_rules.
        """
        # Configure the mock match method
        mock_match = mock_rule_pattern.match
        mock_match.return_value = True

        hostnames = ["h1", "h2"]
        # h1 is already known, h2 is new
        existing_rules = {"h1"}

        main.push_rules(
            self.profile_id,
            self.folder_name,
            self.folder_id,
            self.do,
            self.status,
            hostnames,
            existing_rules,
            self.client
        )

        # h1 is in existing_rules, so we should skip validation for it.
        # h2 is NOT in existing_rules, so we should validate it.
        # So match should be called EXACTLY once, with "h2".
        mock_match.assert_called_once_with("h2")

if __name__ == '__main__':
    unittest.main()
