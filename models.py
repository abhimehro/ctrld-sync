"""Shared data models for ctrld-sync."""

from __future__ import annotations

import concurrent.futures
import httpx
from dataclasses import dataclass
from typing import NotRequired, TypedDict

@dataclass(frozen=True)
class RuleAction:
    """Represents a rule action (do and status)."""

    do: int
    status: int

@dataclass
class SyncContext:
    """Context for syncing rules and folders."""

    profile_id: str
    client: httpx.Client
    existing_rules: set[str]
    batch_executor: concurrent.futures.Executor | None = None

class FolderAction(TypedDict, total=False):
    """The 'action' sub-object on a folder group or rule group.

    ``do`` controls the rule action type (0 = Block, 1 = Allow).
    ``status`` controls whether the rule is active (1 = enabled, 0 = disabled).
    """

    do: int
    status: int

class FolderGroup(TypedDict):
    """The 'group' object inside a folder JSON response."""

    group: str  # folder display name (required in valid data)
    PK: NotRequired[str]  # folder primary key
    action: NotRequired[FolderAction]

class RuleEntry(TypedDict, total=False):
    """A single rule entry inside a folder's rule list."""

    PK: str  # hostname / primary key
    host: str
    action: FolderAction

class RuleGroup(TypedDict, total=False):
    """A rule group (multi-action format) inside a folder JSON response."""

    rules: list[RuleEntry]
    action: FolderAction

class FolderData(TypedDict):
    """Root shape of the JSON object returned by the blocklist endpoint."""

    group: FolderGroup  # required in valid data
    rules: NotRequired[list[RuleEntry]]  # present in legacy single-action format
    rule_groups: NotRequired[list[RuleGroup]]  # present in multi-action format

class PlanRuleGroup(TypedDict):
    """Per-rule-group summary entry inside a dry-run plan folder."""

    rules: int
    action: int | None
    status: int | None

class PlanFolderEntry(TypedDict):
    """Per-folder summary entry inside a dry-run plan."""

    name: str
    rules: int
    action: NotRequired[int | None]  # single-action format
    status: NotRequired[int | None]  # single-action format
    rule_groups: NotRequired[list[PlanRuleGroup]]  # multi-action format

class PlanEntry(TypedDict):
    """Top-level dry-run plan entry for one profile."""

    profile: str
    folders: list[PlanFolderEntry]

class SyncResult(TypedDict):
    """Per-profile result recorded after a sync run."""

    profile: str
    folders: int
    rules: int
    status_label: str
    success: bool
    duration: float


__all__ = ['RuleAction', 'SyncContext', 'FolderAction', 'FolderGroup', 'RuleEntry', 'RuleGroup', 'FolderData', 'PlanRuleGroup', 'PlanFolderEntry', 'PlanEntry', 'SyncResult']
