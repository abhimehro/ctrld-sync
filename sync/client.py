"""Authenticated httpx client factory for the Control D API."""

from __future__ import annotations

import httpx

import config
from validation import set_token_for_redaction


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
