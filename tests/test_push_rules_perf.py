
import unittest
from unittest.mock import patch, MagicMock
import concurrent.futures

# Assumes pytest is running from root, so 'main' is importable directly
import main

class TestPushRulesPerformance(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.profile_id = "test-profile"
        self.folder_name = "test-folder"
        self.folder_id = "test-folder-id"
        self.do = 0
        self.status = 1
        self.existing_rules = set()

    @patch('concurrent.futures.ThreadPoolExecutor')
    def test_single_batch_thread_pool_usage(self, mock_executor):
        """
        Verify optimization: ThreadPoolExecutor is NOT used for single batch.
        """
        # Setup: < 500 rules (one batch)
        hostnames = [f"example{i}.com" for i in range(100)]

        # Mock executor context manager (should not be called, but just in case)
        mock_executor_instance = MagicMock()
        mock_executor.return_value.__enter__.return_value = mock_executor_instance

        # Call push_rules
        main.push_rules(
            self.profile_id,
            self.folder_name,
            self.folder_id,
            self.do,
            self.status,
            hostnames,
            self.existing_rules,
            self.mock_client
        )

        # Verification: Check if ThreadPoolExecutor was used
        # OPTIMIZATION: Should NOT be called
        mock_executor.assert_not_called()

    @patch('concurrent.futures.ThreadPoolExecutor')
    def test_multiple_batches_thread_pool_usage(self, mock_executor):
        """
        Verify multiple batches still use ThreadPoolExecutor.
        """
        # Setup: > 500 rules (multiple batches)
        hostnames = [f"example{i}.com" for i in range(1000)]

        # Mock executor context manager
        mock_executor_instance = MagicMock()
        mock_executor.return_value.__enter__.return_value = mock_executor_instance

        # Mock submit to return a Future
        future = concurrent.futures.Future()
        future.set_result(["processed"])
        mock_executor_instance.submit.return_value = future

        # Call push_rules
        main.push_rules(
            self.profile_id,
            self.folder_name,
            self.folder_id,
            self.do,
            self.status,
            hostnames,
            self.existing_rules,
            self.mock_client
        )

        # Verification: executor should be called
        mock_executor.assert_called()
