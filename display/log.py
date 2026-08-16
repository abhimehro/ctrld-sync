"""Logging formatters and root logger configuration."""

from __future__ import annotations

import json
import logging
import os
import time

from .colors import Colors


class ColoredFormatter(logging.Formatter):
    """Custom formatter to add colors to log levels."""

    LEVEL_COLORS = {
        logging.DEBUG: Colors.BLUE,
        logging.INFO: Colors.CYAN,
        logging.WARNING: Colors.WARNING,
        logging.ERROR: Colors.FAIL,
        logging.CRITICAL: Colors.FAIL + Colors.BOLD,
    }

    def __init__(self, fmt=None, datefmt=None, style="%", validate=True):
        super().__init__(fmt, datefmt, style, validate)
        self.delegate_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s", datefmt="%H:%M:%S"
        )

    def format(self, record):
        original_levelname = record.levelname
        color = self.LEVEL_COLORS.get(record.levelno, Colors.ENDC)
        padded_level = f"{original_levelname:<8}"
        record.levelname = f"{color}{padded_level}{Colors.ENDC}"
        result = self.delegate_formatter.format(record)
        record.levelname = original_levelname
        return result


class JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record for structured/observability pipelines.

    Activated by setting the ``JSON_LOG`` environment variable to a non-empty
    value (e.g. ``JSON_LOG=1``).  When active, ``USE_COLORS`` is also disabled
    so that ANSI escape codes never pollute the JSON stream.

    Each line contains at minimum:
        ``time``    – ISO-8601 timestamp (UTC, second precision)
        ``level``   – log level name (DEBUG / INFO / WARNING / ERROR / CRITICAL)
        ``logger``  – logger name
        ``message`` – formatted log message
    """

    @staticmethod
    def converter(
        t: float | None,
    ) -> time.struct_time:  # ensure timestamps are always UTC
        return time.gmtime(t)

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, str] = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            # Mirror stdlib logging.Formatter behavior:
            # cache the formatted exception in record.exc_text so that
            # other formatters/handlers don't need to reformat it.
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
            if record.exc_text:
                payload["exc"] = record.exc_text
        return json.dumps(payload)


def configure_logging() -> None:
    """Configure the root logger for the CLI.

    Emits coloured text by default and structured JSON lines when ``JSON_LOG``
    is set.  Also suppresses noisy ``httpx`` library logs.
    """
    if os.getenv("JSON_LOG"):
        formatter: logging.Formatter = JsonFormatter()
    else:
        formatter = ColoredFormatter()
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    logging.getLogger("httpx").setLevel(logging.WARNING)


__all__ = ["ColoredFormatter", "JsonFormatter", "configure_logging"]
