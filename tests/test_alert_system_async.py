"""Tests for AlertSystem._on_enqueue_done async callback.

These tests verify that the three code branches in ``_on_enqueue_done`` behave
correctly:

* **Branch A** – ``future.exception()`` returns ``None``; no log call is made.
* **Branch B** – ``future.exception()`` returns a non-``None`` exception object;
  the error is logged and ``record.exc_info`` captures the full traceback tuple
  ``(type, value, traceback)`` so handlers can format it correctly.
* **Branch C** – ``future.exception()`` itself raises an unexpected exception;
  the error is logged with ``exc_info=True`` (idiomatic inside an ``except``
  block) so ``record.exc_info`` is populated from ``sys.exc_info()`` at log time.

Tests that validate ``exc_info`` content capture real ``logging.LogRecord``
objects via an in-process handler rather than asserting on MagicMock call
arguments, so they exercise the actual stdlib logging path.
"""

import contextlib
import logging
import unittest
from collections.abc import Iterator
from unittest.mock import MagicMock

from main import AlertSystem

_LOGGER_NAME = "control-d-sync"


@contextlib.contextmanager
def _capture_records(logger_name: str = _LOGGER_NAME) -> Iterator[list[logging.LogRecord]]:
    """Attach a list-collecting handler to *logger_name* for the duration of the block.

    Propagation is temporarily disabled so that captured records do not also
    bubble up to the root logger and pollute other test output.
    """
    records: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Collector()
    logger = logging.getLogger(logger_name)
    original_propagate = logger.propagate
    logger.addHandler(handler)
    logger.propagate = False
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.propagate = original_propagate


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
        fut = MagicMock()
        fut.exception.return_value = None  # clean completion

        with _capture_records() as records:
            system._on_enqueue_done(fut)

        self.assertEqual(records, [], "No records should be emitted for a clean future")

    # ------------------------------------------------------------------
    # Branch B: future holds a task-level exception
    # ------------------------------------------------------------------

    def test_branch_b_task_exception_logs_error(self):
        """When future.exception() returns an exception, it must be logged.

        Branch B passes ``exc_info=(type, value, traceback)`` explicitly because
        we are *not* inside an ``except`` block, so ``sys.exc_info()`` would
        return ``(None, None, None)``.  The explicit tuple ensures the full
        worker-thread traceback is preserved in the LogRecord.
        """
        task_exc = ValueError("task failed")
        fut = MagicMock()
        fut.exception.return_value = task_exc

        system = self._make_system()
        with _capture_records() as records:
            system._on_enqueue_done(fut)

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.levelno, logging.ERROR)
        self.assertEqual(record.getMessage(), "Enqueued task raised an exception")
        # exc_info is a (type, value, traceback) tuple; confirm the exception
        # instance is preserved so formatters can render the correct traceback.
        self.assertIsNotNone(record.exc_info, "exc_info must be set on the LogRecord")
        self.assertIs(record.exc_info[1], task_exc)

    # ------------------------------------------------------------------
    # Branch C: future.exception() itself raises – the core regression test
    # ------------------------------------------------------------------

    def test_branch_c_unexpected_exception_logs_error(self):
        """Unexpected raise from future.exception() must be logged with exc_info populated.

        Branch C uses ``exc_info=True`` (idiomatic within an ``except`` block)
        so that the stdlib logging machinery captures the active exception via
        ``sys.exc_info()``.  We verify the resulting ``LogRecord.exc_info``
        contains the right exception type and message rather than asserting on
        the raw kwarg value, which makes this test independent of the logging
        call-site convention (``True`` vs explicit tuple).
        """
        fut = MagicMock()
        # side_effect causes the mock to *raise* the given exception when called.
        fut.exception.side_effect = RuntimeError("internal error")

        system = self._make_system()
        with _capture_records() as records:
            # Must not propagate the exception out of _on_enqueue_done
            system._on_enqueue_done(fut)

        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record.levelno, logging.ERROR)
        self.assertTrue(
            record.getMessage().startswith(
                "Unexpected error while inspecting enqueue future"
            )
        )
        # exc_info is populated by the stdlib from sys.exc_info() inside the
        # except block; confirm it carries the right exception.
        self.assertIsNotNone(record.exc_info, "exc_info must be set on the LogRecord")
        self.assertIsInstance(record.exc_info[1], RuntimeError)
        self.assertEqual(str(record.exc_info[1]), "internal error")

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
