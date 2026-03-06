"""Tests for AlertSystem._on_enqueue_done async callback.

These tests verify that the two code branches in ``_on_enqueue_done`` behave
correctly:

* **Branch A** – happy path: ``future.exception()`` returns ``None``; no log
  call is made.
* **Branch B** – ``future.exception()`` itself raises an unexpected exception;
  the error must be logged with the *actual* exception instance passed as
  ``exc_info`` (not the boolean sentinel ``True``), so callers can inspect
  the real error programmatically.
"""

import unittest
from unittest.mock import MagicMock

from main import AlertSystem


class TestAlertSystemAsync(unittest.TestCase):
    """Test suite for AlertSystem async enqueue-done callback."""

    def _make_system(self) -> AlertSystem:
        """Return a fresh AlertSystem with no external side-effects."""
        return AlertSystem()

    # ------------------------------------------------------------------
    # Branch A: future completes cleanly – no logging expected
    # ------------------------------------------------------------------

    def test_branch_a_no_exception_does_not_log(self):
        """When future.exception() returns None, logger must not be called."""
        system = self._make_system()
        system.logger = MagicMock()

        fut = MagicMock()
        fut.exception.return_value = None  # clean completion

        system._on_enqueue_done(fut)

        system.logger.error.assert_not_called()

    # ------------------------------------------------------------------
    # Branch A (variant): future holds a task-level exception
    # ------------------------------------------------------------------

    def test_branch_a_task_exception_logs_error(self):
        """When future.exception() returns an exception, it must be logged."""
        system = self._make_system()
        system.logger = MagicMock()

        task_exc = ValueError("task failed")
        fut = MagicMock()
        fut.exception.return_value = task_exc

        system._on_enqueue_done(fut)

        system.logger.error.assert_called_once()
        _, kwargs = system.logger.error.call_args
        self.assertIs(kwargs.get("exc_info"), task_exc)

    # ------------------------------------------------------------------
    # Branch B: future.exception() itself raises – the core regression test
    # ------------------------------------------------------------------

    def test_branch_b_unexpected_exception_logs_error(self):
        """Unexpected raise from future.exception() must be logged with exc_info=<exception>.

        This is the regression test for the bug where ``exc_info=True`` was
        passed instead of the real exception instance, causing
        ``assertIs(exc_info, RuntimeError(...))`` to fail.
        """
        system = self._make_system()
        system.logger = MagicMock()

        fut = MagicMock()
        # Setting side_effect on a MagicMock causes the mock to *raise* when
        # called.  The raised object IS this same RuntimeError instance.
        fut.exception.side_effect = RuntimeError("internal error")

        # Must not propagate the exception out of _on_enqueue_done
        system._on_enqueue_done(fut)

        system.logger.error.assert_called_once()
        error_args, error_kwargs = system.logger.error.call_args
        self.assertIsInstance(error_args[0], str)
        self.assertTrue(
            error_args[0].startswith(
                "Unexpected error while inspecting enqueue future"
            )
        )

        # The exc_info kwarg must be the exact exception instance – not True
        exc_info_param = error_kwargs.get("exc_info")
        self.assertIs(exc_info_param, fut.exception.side_effect)

    # ------------------------------------------------------------------
    # Verify default logger is set on construction (no injection)
    # ------------------------------------------------------------------

    def test_default_logger_is_set(self):
        """AlertSystem created without args must have a non-None logger."""
        system = self._make_system()
        self.assertIsNotNone(system.logger)

    def test_custom_logger_is_used(self):
        """AlertSystem must use the injected logger, not the default one."""
        custom_logger = MagicMock()
        system = AlertSystem(logger=custom_logger)
        self.assertIs(system.logger, custom_logger)


if __name__ == "__main__":
    unittest.main()
