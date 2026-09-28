"""Rule batching, deduplication and parallel pushing to folders."""

from __future__ import annotations

import concurrent.futures
import contextlib
import logging
from dataclasses import dataclass

import httpx

import config
import sync
from display import (
    _clear_current_line,
    _print_completion,
    pluralize,
    render_progress_bar,
)
from models import RuleAction, SyncContext
from sync.rules import _filter_rules_for_folder
from validation import sanitize_for_log


@dataclass(frozen=True, slots=True)
class _BatchTarget:
    """Per-folder invariants for a batched rule push."""

    profile_id: str
    sanitized_name: str
    str_do: str
    str_status: str
    str_group: str
    progress_label: str

    @classmethod
    def from_parts(
        cls,
        profile_id: str,
        folder_name: str,
        folder_id: str,
        action: RuleAction,
    ) -> _BatchTarget:
        sanitized_name = sanitize_for_log(folder_name)
        return cls(
            profile_id=profile_id,
            sanitized_name=sanitized_name,
            str_do=str(action.do),
            str_status=str(action.status),
            str_group=str(folder_id),
            progress_label=f"Folder {sanitized_name}",
        )


def _managed_batch_executor(
    ctx: SyncContext,
) -> contextlib.AbstractContextManager[concurrent.futures.Executor]:
    """Return a context manager for the batch executor.

    Reuses an externally provided executor when available; otherwise creates a
    fresh ThreadPoolExecutor with max_workers=4 that is shut down on exit.
    """
    if ctx.batch_executor is not None:
        return contextlib.nullcontext(ctx.batch_executor)
    return concurrent.futures.ThreadPoolExecutor(max_workers=4)


def _run_single_batch(
    ctx: SyncContext,
    target: _BatchTarget,
    batch: list[str],
) -> int:
    """Push a single batch synchronously and update state."""
    result = _push_single_batch(ctx.client, target, 1, batch)
    successful_batches = 1 if result else 0
    if result:
        ctx.existing_rules.update(result)
    render_progress_bar(successful_batches, 1, target.progress_label)
    return successful_batches


def _push_single_batch(
    client: httpx.Client,
    target: _BatchTarget,
    batch_idx: int,
    batch_data: list[str],
) -> list[str] | None:
    """Process a single batch of rules by sending an API request."""
    data = {
        "do": target.str_do,
        "status": target.str_status,
        "group": target.str_group,
    }
    # Optimization: Use pre-calculated keys and zip for faster dict update
    # strict=False is intentional: batch_data may be shorter than BATCH_KEYS for final batch
    data.update(zip(config.BATCH_KEYS, batch_data, strict=False))

    try:
        sync._api_post_form(
            client, f"{config.API_BASE}/{target.profile_id}/rules", data=data
        )
        if not sync.USE_COLORS:
            sync.log.info(
                "Folder %s – batch %d: added %d %s",
                target.sanitized_name,
                batch_idx,
                len(batch_data),
                pluralize(len(batch_data), "rule"),
            )
        return batch_data
    except httpx.HTTPError as e:
        _clear_current_line()
        hint = ""
        if isinstance(e, httpx.HTTPStatusError):
            # Use a more specific name to avoid confusion with the rule "status" payload
            status_code = e.response.status_code
            hint = f" ({config._STATUS_HINTS.get(status_code, f'HTTP {status_code}')})"
        sync.log.error(
            f"Failed to push batch {batch_idx} for folder {target.sanitized_name}{hint}: {sanitize_for_log(e)}"
        )
        response = getattr(e, "response", None)
        if response is not None and sync.log.isEnabledFor(logging.DEBUG):
            sync.log.debug(f"Response content: {sanitize_for_log(response.text)}")
        return None


def _process_batches_with_executor(
    executor: concurrent.futures.Executor,
    ctx: SyncContext,
    target: _BatchTarget,
    batches: list[list[str]],
) -> int:
    """Process batches using the provided executor and return successful batch count."""
    successful_batches = 0
    futures = {
        executor.submit(_push_single_batch, ctx.client, target, i, batch): i
        for i, batch in enumerate(batches, 1)
    }

    for future in concurrent.futures.as_completed(futures):
        result = future.result()
        if result:
            successful_batches += 1
            ctx.existing_rules.update(result)

        render_progress_bar(successful_batches, len(batches), target.progress_label)

    return successful_batches


def _log_batch_result(
    target: _BatchTarget,
    successful_batches: int,
    total_batches: int,
    total_rules: int,
) -> bool:
    """Helper to evaluate and log the result of a batch rule push."""
    if successful_batches == total_batches:
        _print_completion(
            f"Folder {target.sanitized_name}: Finished ({total_rules:,} {pluralize(total_rules, 'rule')})"
        )
        return True

    _clear_current_line()
    batch_word = pluralize(total_batches, "batch", "batches")
    if successful_batches > 0:
        sync.log.warning(
            "Folder %s – only %d/%d %s succeeded (Partial)",
            target.sanitized_name,
            successful_batches,
            total_batches,
            batch_word,
        )
    else:
        sync.log.error(
            "Folder %s – 0/%d %s succeeded",
            target.sanitized_name,
            total_batches,
            batch_word,
        )
    return False


def _push_rule_batches(
    ctx: SyncContext,
    target: _BatchTarget,
    filtered_hostnames: list[str],
) -> bool:
    """
    Splits rules into batches and pushes them to the API in parallel.
    """
    batches = [
        filtered_hostnames[start : start + config.BATCH_SIZE]
        for start in range(0, len(filtered_hostnames), config.BATCH_SIZE)
    ]
    total_batches = len(batches)

    if total_batches == 1:
        successful_batches = _run_single_batch(ctx, target, batches[0])
    else:
        with _managed_batch_executor(ctx) as executor:
            successful_batches = _process_batches_with_executor(
                executor, ctx, target, batches
            )

    return _log_batch_result(
        target,
        successful_batches,
        total_batches,
        len(filtered_hostnames),
    )


def push_rules(
    ctx: SyncContext,
    folder_name: str,
    folder_id: str,
    action: RuleAction,
    hostnames: list[str],
) -> bool:
    """
    Pushes rules to a folder in batches, filtering duplicates and invalid rules.

    Deduplicates input, validates rules against _ALLOWED_RULE_CHARS, and sends batches
    in parallel for optimal performance. Updates ctx.existing_rules set with newly
    added rules. Returns True if all batches succeed.
    """
    if not hostnames:
        sync.log.info("Folder %s - no rules to push", sanitize_for_log(folder_name))
        return True

    filtered_hostnames = _filter_rules_for_folder(
        ctx.existing_rules, hostnames, folder_name
    )

    if not filtered_hostnames:
        sync.log.info(
            f"Folder {sanitize_for_log(folder_name)} - no new rules to push after filtering duplicates"
        )
        return True

    target = _BatchTarget.from_parts(ctx.profile_id, folder_name, folder_id, action)
    return _push_rule_batches(ctx, target, filtered_hostnames)
