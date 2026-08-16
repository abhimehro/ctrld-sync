"""Control D folder/rule synchronization package."""

from __future__ import annotations

import concurrent.futures  # noqa: F401
import logging

import api_client
import display
import gh_client
import validation

import sync.client
import sync.folders
import sync.rules
import sync.batches
import sync.plan
import sync.profile

log = logging.getLogger("sync")
USE_COLORS = display.USE_COLORS

_api_get = api_client._api_get
_api_post = api_client._api_post
_api_post_form = api_client._api_post_form
_api_delete = api_client._api_delete
_CONNECT_ERROR_HINT = api_client._CONNECT_ERROR_HINT
_TIMEOUT_HINT = api_client._TIMEOUT_HINT

countdown_timer = display.countdown_timer
_clear_current_line = display._clear_current_line
_print_completion = display._print_completion
pluralize = display.pluralize
render_progress_bar = display.render_progress_bar
print_plan_details = display.print_plan_details
Colors = display.Colors

_ALLOWED_RULE_CHARS = validation._ALLOWED_RULE_CHARS
MAX_RULE_LENGTH = validation.MAX_RULE_LENGTH
is_valid_rule = validation.is_valid_rule
sanitize_for_log = validation.sanitize_for_log
set_token_for_redaction = validation.set_token_for_redaction
validate_folder_id = validation.validate_folder_id
validate_folder_url = validation.validate_folder_url
validate_hostname = validation.validate_hostname

_cache = gh_client._cache
_cache_lock = gh_client._cache_lock
fetch_folder_data = gh_client.fetch_folder_data

create_client = sync.client.create_client
check_api_access = sync.client.check_api_access
create_folder = sync.folders.create_folder
delete_folder = sync.folders.delete_folder
list_existing_folders = sync.folders.list_existing_folders
verify_access_and_get_folders = sync.folders.verify_access_and_get_folders
_extract_from_groups_list = sync.folders._extract_from_groups_list
_poll_for_folder_id = sync.folders._poll_for_folder_id
get_all_existing_rules = sync.rules.get_all_existing_rules
push_rules = sync.batches.push_rules
_build_plan_entry = sync.plan._build_plan_entry
_fetch_all_folder_data = sync.plan._fetch_all_folder_data
_FolderPreparationContext = sync.profile._FolderPreparationContext
_prepare_folders_and_rules = sync.profile._prepare_folders_and_rules
_process_single_folder = sync.profile._process_single_folder
sync_profile = sync.profile.sync_profile

__all__ = [
    "create_client",
    "sync_profile",
    "push_rules",
    "get_all_existing_rules",
    "check_api_access",
    "list_existing_folders",
    "verify_access_and_get_folders",
    "delete_folder",
    "create_folder",
]
