"""Create Client cluster."""

from __future__ import annotations

import httpx

import config
import sync

from api_client import _CONNECT_ERROR_HINT, _TIMEOUT_HINT
from display import Colors
from validation import sanitize_for_log, set_token_for_redaction


def create_client(token: str) -> httpx.Client:
    set_token_for_redaction(token)
    return httpx.Client(
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": config.USER_AGENT,
        },
        # SECURITY: Explicit timeouts prevent resource exhaustion/DoS via Slowloris
        timeout=httpx.Timeout(10.0, connect=5.0),
        follow_redirects=False,
    )


def check_api_access(client: httpx.Client, profile_id: str) -> bool:
    """
    Verifies API access and Profile existence before starting heavy work.
    Returns True if access is good, False otherwise (with helpful logs).
    """
    url = f"{config.API_BASE}/{profile_id}/groups"
    try:
        # We use a raw request here to avoid the automatic retries of _retry_request
        # for auth errors, which are permanent.
        resp = client.get(url)
        resp.raise_for_status()
        return True
    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        if code == 401:
            sync.log.critical(
                f"{Colors.FAIL}❌ Authentication Failed: The API Token is invalid.{Colors.ENDC}"
            )
            sync.log.critical(
                f"{Colors.FAIL}   Please check your token at: https://controld.com/account/manage-account{Colors.ENDC}"
            )
        elif code == 403:
            sync.log.critical(
                f"{Colors.FAIL}🚫 Access Denied: Token lacks permission for Profile {profile_id}.{Colors.ENDC}"
            )
        elif code == 404:
            sync.log.critical(
                f"{Colors.FAIL}🔍 Profile Not Found: The ID '{sanitize_for_log(profile_id)}' does not exist.{Colors.ENDC}"
            )
            sync.log.critical(
                f"{Colors.FAIL}   Please verify the Profile ID from your Control D Dashboard URL.{Colors.ENDC}"
            )
        else:
            sync.log.error(f"API Access Check Failed ({code}): {sanitize_for_log(e)}")
        return False
    except httpx.RequestError as e:
        hint = ""
        if isinstance(e, httpx.TimeoutException):
            hint = f" | hint: {_TIMEOUT_HINT}"
        elif isinstance(e, httpx.ConnectError):
            hint = f" | hint: {_CONNECT_ERROR_HINT}"
        sync.log.error(
            f"Network Error during access check: {sanitize_for_log(e)}{hint}"
        )
        return False
