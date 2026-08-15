import os
import sys
import unittest
from unittest.mock import MagicMock, patch

import httpx

# Add root to path to import main
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))



class TestPushRulesPerf(unittest.TestCase):
    def setUp(self):
        # Import main freshly or get current from sys.modules
        # Because other tests (like test_parallel_deletion.py) might reload main
        if "main" in sys.modules:
            self.main = sys.modules["main"]
        else:
            import main

            self.main = main

        self.client = MagicMock()
        self.profile_id = "test_profile"
        self.folder_name = "test_folder"
        self.folder_id = "test_folder_id"
        self.do = 1
        self.status = 1
        self.existing_rules = set()

    @patch("main.concurrent.futures.ThreadPoolExecutor")
    def test_push_rules_single_batch_optimization(self, mock_executor):
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
        mock_future.result.return_value = hostnames  # Success
        mock_executor_instance.submit.return_value = mock_future

        # We also need to mock _api_post_form since it will be called directly
        # patch("main._api_post_form") patches what is in sys.modules['main']
        # self.main is likely sys.modules['main'] due to setUp logic

        with patch("sync._api_post_form") as mock_post:
            ctx = self.main.SyncContext(
                profile_id=self.profile_id,
                client=self.client,
                existing_rules=self.existing_rules,
            )
            action = self.main.RuleAction(do=self.do, status=self.status)
            self.main.push_rules(
                ctx,
                self.folder_name,
                self.folder_id,
                action,
                hostnames,
            )

            self.assertTrue(mock_post.called, "Expected _api_post_form to be called")

        # Verify if Executor was called.
        # AFTER OPTIMIZATION: This should be False.
        self.assertFalse(
            mock_executor.called,
            "ThreadPoolExecutor should NOT be called for single batch",
        )

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

        mock_as_completed.return_value = [mock_future, mock_future]  # 2 batches

        with patch("sync._api_post_form"):
            ctx = self.main.SyncContext(
                profile_id=self.profile_id,
                client=self.client,
                existing_rules=self.existing_rules,
            )
            action = self.main.RuleAction(do=self.do, status=self.status)
            self.main.push_rules(
                ctx,
                self.folder_name,
                self.folder_id,
                action,
                hostnames,
            )

        # This should ALWAYS be True
        self.assertTrue(
            mock_executor.called, "ThreadPoolExecutor should be called for multi-batch"
        )

    def test_push_rules_skips_validation_for_existing(self):
        """
        Test that validation is NOT called for rules that are already in existing_rules.
        """
        # Patch is_valid_rule on the sync module (canonical owner)
        with patch("sync.is_valid_rule", return_value=True) as mock_is_valid:
            hostnames = ["h1", "h2"]
            # h1 is already known, h2 is new
            existing_rules = {"h1"}

            with patch("sync._api_post_form"):
                ctx = self.main.SyncContext(
                    profile_id=self.profile_id,
                    client=self.client,
                    existing_rules=existing_rules,
                )
                action = self.main.RuleAction(do=self.do, status=self.status)
                self.main.push_rules(
                    ctx,
                    self.folder_name,
                    self.folder_id,
                    action,
                    hostnames,
                )

            # h1 is in existing_rules, so we should skip validation for it.
            # h2 is NOT in existing_rules, so we should validate it.
            # So validation should be called EXACTLY once, with "h2".
            mock_is_valid.assert_called_once_with("h2")

    @patch("main.concurrent.futures.as_completed")
    def test_push_rules_uses_provided_executor(self, mock_as_completed):
        """
        Test that push_rules uses the provided executor.
        """
        # Create > 500 rules (2 batches)
        hostnames = [f"example{i}.com" for i in range(600)]

        # Mock the executor passed as argument
        mock_executor = MagicMock()
        mock_future = MagicMock()
        mock_future.result.return_value = ["some_rule"]
        mock_executor.submit.return_value = mock_future

        # Mock as_completed to return our futures
        mock_as_completed.return_value = [mock_future, mock_future]

        ctx = self.main.SyncContext(
            profile_id=self.profile_id,
            client=self.client,
            existing_rules=self.existing_rules,
            batch_executor=mock_executor,
        )
        action = self.main.RuleAction(do=self.do, status=self.status)

        self.main.push_rules(
            ctx,
            self.folder_name,
            self.folder_id,
            action,
            hostnames,
        )

        # Verify executor.submit was called twice (once for each batch)
        self.assertEqual(mock_executor.submit.call_count, 2)

    @patch("sync._api_post_form")
    def test_push_rules_partial_failure_updates_existing_rules(self, mock_api_post):
        """A failed batch leaves successful batches in existing_rules."""
        batch_size = self.main.BATCH_SIZE
        hostnames = [f"example{i}.com" for i in range(batch_size)] + ["bad.com"]

        def side_effect(client, url, data=None):
            if data and data.get("hostnames[0]") == "bad.com":
                raise httpx.RequestError("boom")
            return MagicMock(spec=httpx.Response)

        mock_api_post.side_effect = side_effect

        ctx = self.main.SyncContext(
            profile_id=self.profile_id,
            client=self.client,
            existing_rules=set(),
        )
        action = self.main.RuleAction(do=self.do, status=self.status)

        with self.assertLogs("control-d-sync", level="WARNING") as cm:
            result = self.main.push_rules(
                ctx,
                self.folder_name,
                self.folder_id,
                action,
                hostnames,
            )

        self.assertFalse(result)
        self.assertEqual(len(ctx.existing_rules), batch_size)
        self.assertNotIn("bad.com", ctx.existing_rules)
        self.assertTrue(
            any("only 1/2 batches succeeded (Partial)" in m for m in cm.output),
            f"Expected partial-failure log, got: {cm.output}",
        )

    @patch("sync._api_post_form")
    def test_push_rules_total_failure_logs_zero_batches(self, mock_api_post):
        """All failed batches return False and log the total failure."""
        hostnames = [f"example{i}.com" for i in range(600)]
        mock_api_post.side_effect = httpx.RequestError("boom")

        ctx = self.main.SyncContext(
            profile_id=self.profile_id,
            client=self.client,
            existing_rules=set(),
        )
        action = self.main.RuleAction(do=self.do, status=self.status)

        with self.assertLogs("control-d-sync", level="ERROR") as cm:
            result = self.main.push_rules(
                ctx,
                self.folder_name,
                self.folder_id,
                action,
                hostnames,
            )

        self.assertFalse(result)
        self.assertEqual(len(ctx.existing_rules), 0)
        self.assertTrue(
            any("0/2 batches succeeded" in m for m in cm.output),
            f"Expected total-failure log, got: {cm.output}",
        )

    @patch("sync.concurrent.futures.as_completed")
    def test_push_rules_provided_executor_is_not_shut_down(self, mock_as_completed):
        """An externally supplied executor must not be shut down or exited."""
        batch_size = self.main.BATCH_SIZE
        hostnames = [f"example{i}.com" for i in range(batch_size + 1)]

        mock_executor = MagicMock()
        mock_future_1 = MagicMock()
        mock_future_1.result.return_value = hostnames[:batch_size]
        mock_future_2 = MagicMock()
        mock_future_2.result.return_value = hostnames[batch_size:]
        mock_executor.submit.side_effect = [mock_future_1, mock_future_2]
        mock_as_completed.return_value = [mock_future_1, mock_future_2]

        ctx = self.main.SyncContext(
            profile_id=self.profile_id,
            client=self.client,
            existing_rules=set(),
            batch_executor=mock_executor,
        )
        action = self.main.RuleAction(do=self.do, status=self.status)

        with patch("sync._api_post_form"):
            result = self.main.push_rules(
                ctx,
                self.folder_name,
                self.folder_id,
                action,
                hostnames,
            )

        self.assertTrue(result)
        self.assertEqual(mock_executor.submit.call_count, 2)
        mock_executor.shutdown.assert_not_called()
        mock_executor.__exit__.assert_not_called()

    @patch("sync._api_post_form")
    def test_push_rules_short_final_batch(self, mock_api_post):
        """A final batch smaller than BATCH_SIZE emits only one hostnames[0] key."""
        batch_size = self.main.BATCH_SIZE
        hostnames = [f"example{i}.com" for i in range(batch_size)] + ["final.com"]
        payloads: list[dict] = []

        def side_effect(client, url, data=None):
            if data is not None:
                payloads.append(data.copy())
            return MagicMock(spec=httpx.Response)

        mock_api_post.side_effect = side_effect

        ctx = self.main.SyncContext(
            profile_id=self.profile_id,
            client=self.client,
            existing_rules=set(),
        )
        action = self.main.RuleAction(do=self.do, status=self.status)

        result = self.main.push_rules(
            ctx,
            self.folder_name,
            self.folder_id,
            action,
            hostnames,
        )

        self.assertTrue(result)
        self.assertEqual(len(payloads), 2)

        hostname_key_counts = [
            len([k for k in p if k.startswith("hostnames[")]) for p in payloads
        ]
        self.assertIn(batch_size, hostname_key_counts)
        self.assertIn(1, hostname_key_counts)

        short_payloads = [
            p
            for p in payloads
            if len([k for k in p if k.startswith("hostnames[")]) == 1
        ]
        self.assertEqual(len(short_payloads), 1)
        short_payload = short_payloads[0]
        self.assertEqual(short_payload["hostnames[0]"], "final.com")
        self.assertNotIn("hostnames[1]", short_payload)


if __name__ == "__main__":
    unittest.main()
