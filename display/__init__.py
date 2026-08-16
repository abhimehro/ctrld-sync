"""Terminal UI, prompts, tables, and progress helpers (display package)."""

from __future__ import annotations

import logging
import sys
import types

from .alerts import AlertSystem
from .colors import Box, Colors, USE_COLORS
from .log import ColoredFormatter, JsonFormatter
from .log import configure_logging  # noqa: F401
from .output import (
    _clear_current_line,
    _print_bold_header,
    _print_completion,
    _print_hint,
)
from .plan import print_plan_details
from .plan import (  # noqa: F401
    _format_dimmed_hint,
    _format_empty_warning,
    _format_folder_line,
    _format_plan_header,
    _get_action_text,
    _resolve_folder_action,
)
from .prompts import (
    EMPTY_INPUT_HINT,
    INVALID_INPUT_HINT,
    get_password,
    get_validated_input,
)
from .progress import countdown_timer, render_progress_bar
from .progress import _get_progress_bar_width  # noqa: F401
from .stats import display_statistics
from .stats import (  # noqa: F401
    display_api_statistics,
    display_cache_statistics,
    display_rate_limit_status,
)
from .tables import (
    _SummaryStats,
    _get_display_profile,
    _print_dashboard_url,
    _print_success_text,
    _render_ascii_table,
    _render_unicode_table,
    make_col_separator,
    print_line,
    print_row,
    print_success_message,
    print_summary_table,
)
from .tables import _print_hint_if_no_folders  # noqa: F401
from .text import _ANSI_ESCAPE_PATTERN, _display_len, _pad_string, pluralize

log = logging.getLogger(__name__)

__all__ = [
    "USE_COLORS",
    "Colors",
    "Box",
    "ColoredFormatter",
    "JsonFormatter",
    "AlertSystem",
    "pluralize",
    "countdown_timer",
    "render_progress_bar",
    "get_password",
    "get_validated_input",
    "print_plan_details",
    "print_summary_table",
    "print_success_message",
    "display_statistics",
    "_clear_current_line",
    "_print_hint",
    "_print_bold_header",
    "_print_completion",
    "_display_len",
    "_pad_string",
    "print_line",
    "print_row",
    "_SummaryStats",
    "_get_display_profile",
    "_render_ascii_table",
    "_render_unicode_table",
    "_print_success_text",
    "_print_dashboard_url",
    "_ANSI_ESCAPE_PATTERN",
    "EMPTY_INPUT_HINT",
    "INVALID_INPUT_HINT",
    "make_col_separator",
]


class _DisplayModule(types.ModuleType):
    """Custom module class to propagate USE_COLORS/log writes to display.* submodules."""

    def __setattr__(self, name: str, value: object) -> None:
        if name in ("USE_COLORS", "log"):
            for mod_name in list(sys.modules):
                if mod_name.startswith("display."):
                    try:
                        setattr(sys.modules[mod_name], name, value)
                    except AttributeError:
                        pass
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _DisplayModule
