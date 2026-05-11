"""FastAPI dependencies."""

from __future__ import annotations

import os
from dataclasses import dataclass

from fastapi import Header, HTTPException, status


@dataclass(frozen=True)
class CurrentUser:
    """Phase 0 dev user. Phase 1 will load from sessions/users tables."""

    id: str
    github_login: str


def auth_user(
    x_dev_user: str | None = Header(default=None),
) -> CurrentUser:
    """Resolve the current user.

    Phase 0: when ``DEV_AUTH=1``, accept ``X-Dev-User`` header and return
    a synthetic user. The id is deterministic so DB rows are stable across
    restarts during development.
    """
    if os.environ.get("DEV_AUTH") == "1":
        login = x_dev_user or os.environ.get("DEV_USER_LOGIN", "alice")
        return CurrentUser(id=f"dev-{login}", github_login=login)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication not configured. Set DEV_AUTH=1 for Phase 0 dev.",
    )
