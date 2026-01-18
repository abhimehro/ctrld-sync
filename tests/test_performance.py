import unittest
from unittest.mock import MagicMock, patch
import time
import threading
from main import push_rules, BATCH_SIZE
import httpx

class TestPushRulesPerformance(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.profile_id = "test-profile"
        self.folder_name = "test-folder"
        self.folder_id = "test-folder-id"
        self.do = 1
        self.status = 1
        self.existing_rules = set()

    @patch('main._api_post_form')
    def test_push_rules_parallel_with_lock(self, mock_post):
        # Create enough hostnames for 5 batches
        num_batches = 5
        hostnames = [f"host-{i}.com" for i in range(BATCH_SIZE * num_batches)]

        # Mock success
        mock_post.return_value = MagicMock(status_code=200)

        lock = threading.Lock()

        start_time = time.time()
        success = push_rules(
            self.profile_id,
            self.folder_name,
            self.folder_id,
            self.do,
            self.status,
            hostnames,
            self.existing_rules,
            self.client,
            existing_rules_lock=lock
        )
        duration = time.time() - start_time

        self.assertTrue(success)
        self.assertEqual(mock_post.call_count, num_batches)
        self.assertEqual(len(self.existing_rules), len(hostnames))

        print(f"\n[Parallel with Lock] Duration: {duration:.4f}s")

    @patch('main._api_post_form')
    def test_push_rules_concurrency(self, mock_post):
        # Create enough hostnames for 10 batches
        num_batches = 10
        hostnames = [f"host-{i}.com" for i in range(BATCH_SIZE * num_batches)]

        # Mock delay to simulate network latency
        def delayed_post(*args, **kwargs):
            time.sleep(0.1)
            return MagicMock(status_code=200)

        mock_post.side_effect = delayed_post

        start_time = time.time()
        success = push_rules(
            self.profile_id,
            self.folder_name,
            self.folder_id,
            self.do,
            self.status,
            hostnames,
            self.existing_rules,
            self.client
        )
        duration = time.time() - start_time

        self.assertTrue(success)
        self.assertEqual(mock_post.call_count, num_batches)

        print(f"\n[Performance Test] Duration for {num_batches} batches with 0.1s latency: {duration:.4f}s")

    @patch('main._api_post_form')
    def test_push_rules_partial_failure(self, mock_post):
        # Create enough hostnames for 5 batches
        num_batches = 5
        hostnames = [f"host-{i}.com" for i in range(BATCH_SIZE * num_batches)]

        # Mock failure for some batches
        call_count = 0
        def partial_failure(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Fail batches 2 and 4
            if call_count in [2, 4]:
                raise httpx.HTTPError("Simulated API failure")
            return MagicMock(status_code=200)

        mock_post.side_effect = partial_failure

        success = push_rules(
            self.profile_id,
            self.folder_name,
            self.folder_id,
            self.do,
            self.status,
            hostnames,
            self.existing_rules,
            self.client
        )

        # Should return False when some batches fail
        self.assertFalse(success)
        self.assertEqual(mock_post.call_count, num_batches)
        # Only 3 batches should have succeeded and updated existing_rules
        self.assertEqual(len(self.existing_rules), BATCH_SIZE * 3)

        print(f"\n[Partial Failure Test] {mock_post.call_count} batches attempted, 3 succeeded")

if __name__ == '__main__':
    unittest.main()
