"""Tests for the JsonFormatter structured logging mode (JSON_LOG env var)."""

import json
import logging
import unittest

import main


class TestJsonFormatter(unittest.TestCase):
    """Verify that JsonFormatter emits valid JSON with required fields."""

    def _make_record(self, message: str, level: int = logging.INFO) -> logging.LogRecord:
        return logging.LogRecord(
            name="test-logger",
            level=level,
            pathname="",
            lineno=0,
            msg=message,
            args=(),
            exc_info=None,
        )

    def test_output_is_valid_json(self):
        """JsonFormatter must produce a string that parses as JSON."""
        formatter = main.JsonFormatter()
        record = self._make_record("hello world")
        output = formatter.format(record)
        parsed = json.loads(output)
        self.assertIsInstance(parsed, dict)

    def test_required_fields_present(self):
        """Parsed JSON must contain time, level, logger, and message keys."""
        formatter = main.JsonFormatter()
        record = self._make_record("test message")
        parsed = json.loads(formatter.format(record))
        for field in ("time", "level", "logger", "message"):
            self.assertIn(field, parsed, f"Missing required field: {field}")

    def test_message_content(self):
        """The message field must match the original log message."""
        formatter = main.JsonFormatter()
        record = self._make_record("syncing folder xyz")
        parsed = json.loads(formatter.format(record))
        self.assertEqual(parsed["message"], "syncing folder xyz")

    def test_level_name(self):
        """The level field must reflect the record's level name."""
        formatter = main.JsonFormatter()
        for level, name in (
            (logging.DEBUG, "DEBUG"),
            (logging.INFO, "INFO"),
            (logging.WARNING, "WARNING"),
            (logging.ERROR, "ERROR"),
        ):
            record = self._make_record("msg", level=level)
            parsed = json.loads(formatter.format(record))
            self.assertEqual(parsed["level"], name)

    def test_logger_name(self):
        """The logger field must match the record's logger name."""
        formatter = main.JsonFormatter()
        record = self._make_record("msg")
        parsed = json.loads(formatter.format(record))
        self.assertEqual(parsed["logger"], "test-logger")

    def test_time_format(self):
        """The time field must follow ISO-8601 format ending in Z."""

        formatter = main.JsonFormatter()
        record = self._make_record("msg")
        parsed = json.loads(formatter.format(record))
        # e.g. "2026-03-03T13:00:00Z"
        self.assertRegex(parsed["time"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_no_ansi_codes_in_output(self):
        """JSON output must not contain ANSI escape sequences."""
        formatter = main.JsonFormatter()
        record = self._make_record("colored message")
        output = formatter.format(record)
        self.assertNotIn("\033[", output)

    def test_json_formatter_class_exists(self):
        """main.JsonFormatter must be importable and a logging.Formatter subclass."""
        self.assertTrue(issubclass(main.JsonFormatter, logging.Formatter))


if __name__ == "__main__":
    unittest.main()
