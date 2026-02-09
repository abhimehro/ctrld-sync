"""Tests for push_rules performance optimization."""
import unittest
from unittest.mock import MagicMock, patch


class TestPushRulesPerf(unittest.TestCase):
    """Test performance optimizations in push_rules."""

    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_client.post.return_value.status_code = 200
        self.mock_client.post.return_value.raise_for_status = MagicMock()

    @patch('concurrent.futures.as_completed')
    @patch('concurrent.futures.ThreadPoolExecutor')
    def test_single_batch_avoids_thread_pool(
        self, mock_executor, mock_as_completed
    ):
        """Test that single batch pushes avoid creating a ThreadPoolExecutor."""
        import main

        # Setup: < 500 rules (BATCH_SIZE is 500)
        rules = [f"rule{i}.com" for i in range(100)]
        existing_rules = set()

        # Mock the executor context manager
        mock_executor_instance = mock_executor.return_value
        mock_executor_instance.__enter__.return_value = mock_executor_instance

        # Mock submit to return a future
        mock_future = MagicMock()
        mock_future.result.return_value = ["rule0.com"]  # Dummy result
        mock_executor_instance.submit.return_value = mock_future

        # Mock as_completed to return the future once (so loop runs once)
        mock_as_completed.return_value = [mock_future]

        # Execute
        main.push_rules(
            profile_id="test_profile",
            folder_name="test_folder",
            folder_id="test_id",
            do=0,
            status=1,
            hostnames=rules,
            existing_rules=existing_rules,
            client=self.mock_client
        )

        # Assert: ThreadPoolExecutor should NOT be called
        mock_executor.assert_not_called()

        # Verify: client.post should be called once
        self.assertEqual(self.mock_client.post.call_count, 1)

    @patch('concurrent.futures.as_completed')
    @patch('concurrent.futures.ThreadPoolExecutor')
    def test_multi_batch_uses_thread_pool(
        self, mock_executor, mock_as_completed
    ):
        """Test that multiple batch pushes DO create a ThreadPoolExecutor."""
        import main

        # Setup: > 500 rules
        rules = [f"rule{i}.com" for i in range(1000)]
        existing_rules = set()

        # Mock the executor context manager
        mock_executor_instance = mock_executor.return_value
        mock_executor_instance.__enter__.return_value = mock_executor_instance

        # Create distinct mock futures for each batch
        mock_future1 = MagicMock()
        mock_future1.result.return_value = ["some_rules_batch1"]
        mock_future2 = MagicMock()
        mock_future2.result.return_value = ["some_rules_batch2"]

        # Mock submit to return distinct futures
        mock_executor_instance.submit.side_effect = [mock_future1, mock_future2]

        # Mock as_completed to return 2 distinct futures (2 batches)
        mock_as_completed.return_value = [mock_future1, mock_future2]

        # Execute
        main.push_rules(
            profile_id="test_profile",
            folder_name="test_folder",
            folder_id="test_id",
            do=0,
            status=1,
            hostnames=rules,
            existing_rules=existing_rules,
            client=self.mock_client
        )

        # Assert: ThreadPoolExecutor SHOULD be called
        mock_executor.assert_called()
        # Verify submit was called 2 times (for 2 batches)
        self.assertEqual(mock_executor_instance.submit.call_count, 2)
