"""Async task completion callbacks and structured error logging."""

from __future__ import annotations

import concurrent.futures
import logging
from typing import Any


class AlertSystem:
    """Handles async enqueue callbacks and structured error logging.

    Attaches to ``concurrent.futures.Future`` objects via
    ``add_done_callback`` so that errors surfacing inside worker threads are
    captured and logged in a single, consistent place.

    **Architectural role:** Rather than scattering ``try/except`` blocks
    around every ``executor.submit()`` call, callers register a single
    ``AlertSystem`` callback on each future.  This centralises error
    observability and makes it easy to extend (e.g. add metrics, alerts, or
    structured logging) without touching every call site.

    Usage::

        system = AlertSystem()
        fut = executor.submit(some_task)
        fut.add_done_callback(system._on_enqueue_done)
    """

    def __init__(self, logger: logging.Logger | None = None) -> None:
        # Allow callers (and tests) to inject a custom logger; fall back to the
        # module-level logger so production behaviour stays unchanged.
        # Use the same named logger as the rest of this module to keep logs
        # consistent and to honour the "module-level logger" contract.
        self.logger = logger or logging.getLogger("control-d-sync")

    def _on_enqueue_done(
        self,
        future: concurrent.futures.Future[
            Any
        ],  # Accept futures of any return type; we only inspect exceptions
    ) -> None:
        """Callback invoked when an enqueue future completes.

        Three code paths ("branches") are handled here:

        * **Branch A** – ``future.exception()`` returns ``None``: normal
          completion; nothing extra is logged.
        * **Branch B** – ``future.exception()`` returns a non-``None``
          exception object: we log this as an error and pass the exception
          instance as ``exc_info`` so that the full traceback is preserved and
          log handlers (and tests) can inspect the real error.
        * **Branch C** – ``future.exception()`` itself raises (e.g. the future
          was cancelled before we could inspect it): we catch *that* secondary
          exception and log it, again passing the actual exception instance as
          ``exc_info`` so that the full traceback is preserved and callers can
          programmatically inspect the real error.
        """
        try:
            exc = future.exception()
            if exc is not None:
                # We are *not* in an ``except`` block here, so there is no
                # active exception for logging to pull from ``sys.exc_info()``.
                # Construct the (type, value, traceback) tuple explicitly so the
                # original worker-thread traceback is preserved.
                self.logger.error(
                    "Enqueued task raised an exception",
                    exc_info=(type(exc), exc, exc.__traceback__),
                )
        except Exception:
            # Here we *are* in an ``except`` context, so logging can safely use
            # the current exception from ``sys.exc_info()``. Using
            # ``exc_info=True`` is the idiomatic way to log this traceback.
            self.logger.error(
                "Unexpected error while inspecting enqueue future",
                exc_info=True,
            )


__all__ = ["AlertSystem"]
