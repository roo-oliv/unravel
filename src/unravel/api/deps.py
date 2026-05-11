"""FastAPI dependencies.

Order of precedence in ``auth_user``:
  1. Session cookie (real GitHub user). Cookie is signed; row is the truth.
  2. ``DEV_AUTH=1`` + ``X-Dev-User`` header (Phase 0 dev fallback).
  3. 401.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from unravel.api.auth import sessions as sess
from unravel.api.auth.crypto import TokenCryptoError, decrypt
from unravel.api.db import get_db
from unravel.api.db_models import User

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CurrentUser:
    """The caller of an API request.

    ``id`` is a UUID string for OAuth-authenticated users, or a synthetic
    ``dev-<login>`` for the local-only DEV_AUTH path. ``github_access_token``
    is decrypted on auth (may be ``None`` for dev users — services fall back
    to the ``GITHUB_TOKEN`` env var in that case).
    """

    id: str
    github_login: str
    name: str | None = None
    email: str | None = None
    avatar_url: str | None = None
    github_access_token: str | None = None
    is_dev_user: bool = False


async def auth_user(
    request: Request,
    x_dev_user: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    cookie = request.cookies.get(sess.COOKIE_NAME)
    if cookie:
        user = await _resolve_session(db, cookie)
        if user is not None:
            return user

    if os.environ.get("DEV_AUTH") == "1":
        login = x_dev_user or os.environ.get("DEV_USER_LOGIN", "alice")
        return CurrentUser(
            id=f"dev-{login}",
            github_login=login,
            github_access_token=None,
            is_dev_user=True,
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Sign in at /auth/github.",
    )


async def _resolve_session(
    db: AsyncSession, cookie: str
) -> CurrentUser | None:
    sid = sess.unsign(cookie)
    if sid is None:
        return None
    row = await sess.load_session(db, sid)
    if row is None:
        return None
    await sess.maybe_roll(db, row)

    user = await db.get(User, row.user_id)
    if user is None:
        # Dangling session — kill it so the next request goes straight to login.
        await sess.delete_session(db, sid)
        return None

    user.last_seen_at = datetime.now(UTC)
    await db.commit()

    try:
        access_token = decrypt(user.encrypted_access_token)
    except TokenCryptoError as exc:
        logger.warning("Token decrypt failed for user %s: %s", user.id, exc)
        access_token = None

    return CurrentUser(
        id=str(user.id),
        github_login=user.github_login,
        name=user.name,
        email=user.email,
        avatar_url=user.avatar_url,
        github_access_token=access_token,
        is_dev_user=False,
    )
