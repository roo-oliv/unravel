"""GitHub OAuth + session endpoints.

Flow:
  ``GET  /auth/github``     → redirect to github.com/login/oauth/authorize
  ``GET  /auth/callback``   → exchange code, upsert user, create session,
                              set HttpOnly cookie, redirect to WEB_BASE_URL
  ``GET  /auth/me``         → current user (or 401)
  ``POST /auth/logout``     → drop session row + clear cookie
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx
from authlib.integrations.base_client.errors import OAuthError
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from unravel.api.auth import sessions as sess
from unravel.api.auth.crypto import TokenCryptoError, encrypt
from unravel.api.auth.github_oauth import (
    OAuthNotConfiguredError,
    github_client,
)
from unravel.api.db import get_db
from unravel.api.db_models import User
from unravel.api.deps import CurrentUser, auth_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth")

DEFAULT_API_BASE = "http://localhost:8000"
DEFAULT_WEB_BASE = "http://localhost:3000"


def _api_base() -> str:
    return os.environ.get("API_BASE_URL", DEFAULT_API_BASE).rstrip("/")


def _web_base() -> str:
    return os.environ.get("WEB_BASE_URL", DEFAULT_WEB_BASE).rstrip("/")


@router.get("/github")
async def github_login(request: Request, next: str = "/"):
    """Start the OAuth dance.

    Stores ``next`` (a relative path on the FE) in the session so the
    callback can bounce the user back to where they started. Absolute
    URLs are rejected to avoid open redirects.
    """
    try:
        client = github_client()
    except OAuthNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    safe_next = next if next.startswith("/") and not next.startswith("//") else "/"
    request.session["post_login_next"] = safe_next

    redirect_uri = f"{_api_base()}/auth/callback"
    return await client.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def github_callback(
    request: Request, db: AsyncSession = Depends(get_db)
):
    try:
        client = github_client()
    except OAuthNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    try:
        token = await client.authorize_access_token(request)
    except OAuthError as exc:
        # The user denied access, or GitHub returned an error response. Send
        # them back to the login page with the failure surfaced.
        logger.warning("OAuth callback rejected: %s", exc)
        return _redirect_with_error(exc.description or str(exc))

    access_token = token.get("access_token")
    if not access_token:
        return _redirect_with_error("No access_token in OAuth response")

    profile = await _fetch_profile(access_token)
    if profile is None:
        return _redirect_with_error("Failed to load GitHub profile")

    try:
        user = await _upsert_user(
            db,
            profile=profile,
            access_token=access_token,
            scopes=token.get("scope"),
        )
    except TokenCryptoError as exc:
        return _redirect_with_error(str(exc))

    session_row = await sess.create_session(
        db,
        user_id=user.id,
        user_agent=request.headers.get("user-agent"),
        ip=request.client.host if request.client else None,
    )

    next_path = request.session.pop("post_login_next", "/")
    response = RedirectResponse(
        url=f"{_web_base()}{next_path}", status_code=status.HTTP_302_FOUND
    )
    _set_session_cookie(response, sess.sign(session_row.id))
    return response


@router.get("/me")
async def me(user: CurrentUser = Depends(auth_user)) -> dict:
    return {
        "id": user.id,
        "github_login": user.github_login,
        "name": user.name,
        "email": user.email,
        "avatar_url": user.avatar_url,
        "is_dev_user": user.is_dev_user,
    }


@router.post("/logout")
async def logout(
    request: Request, db: AsyncSession = Depends(get_db)
) -> dict:
    cookie = request.cookies.get(sess.COOKIE_NAME)
    if cookie:
        sid = sess.unsign(cookie)
        if sid:
            await sess.delete_session(db, sid)

    from fastapi.responses import JSONResponse

    response = JSONResponse({"ok": True})
    response.delete_cookie(
        sess.COOKIE_NAME,
        path="/",
        domain=sess.cookie_attrs().domain,
    )
    return response


async def _fetch_profile(access_token: str) -> dict | None:
    """Pull identity + primary email from GitHub.

    Two calls are needed because ``/user`` doesn't include private emails;
    ``/user/emails`` returns the verified set. We pick the primary verified one
    (or fall back to whatever ``/user`` returned).
    """
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {access_token}",
        "User-Agent": "unravel-saas/0.0.0-phase1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    async with httpx.AsyncClient(timeout=10.0) as http:
        user_resp = await http.get("https://api.github.com/user", headers=headers)
        if user_resp.status_code != 200:
            logger.warning("GET /user → %s: %s", user_resp.status_code, user_resp.text[:200])
            return None
        profile = user_resp.json()

        if not profile.get("email"):
            emails_resp = await http.get(
                "https://api.github.com/user/emails", headers=headers
            )
            if emails_resp.status_code == 200:
                emails = emails_resp.json()
                primary = next(
                    (e for e in emails if e.get("primary") and e.get("verified")),
                    None,
                )
                if primary:
                    profile["email"] = primary["email"]

    return profile


async def _upsert_user(
    db: AsyncSession,
    *,
    profile: dict,
    access_token: str,
    scopes: str | None,
) -> User:
    encrypted = encrypt(access_token)

    stmt = select(User).where(User.github_id == int(profile["id"]))
    result = await db.execute(stmt)
    user = result.scalars().first()
    now = datetime.now(UTC)

    if user is None:
        user = User(
            github_id=int(profile["id"]),
            github_login=profile.get("login") or "",
            name=profile.get("name"),
            email=profile.get("email"),
            avatar_url=profile.get("avatar_url"),
            encrypted_access_token=encrypted,
            token_scopes=scopes,
            last_seen_at=now,
        )
        db.add(user)
    else:
        user.github_login = profile.get("login") or user.github_login
        user.name = profile.get("name") or user.name
        user.email = profile.get("email") or user.email
        user.avatar_url = profile.get("avatar_url") or user.avatar_url
        user.encrypted_access_token = encrypted
        user.token_scopes = scopes
        user.last_seen_at = now

    await db.commit()
    await db.refresh(user)
    return user


def _set_session_cookie(response, signed_sid: str) -> None:
    attrs = sess.cookie_attrs()
    response.set_cookie(
        sess.COOKIE_NAME,
        value=signed_sid,
        max_age=int(sess.SESSION_TTL.total_seconds()),
        httponly=True,
        secure=attrs.secure,
        samesite=attrs.samesite,
        domain=attrs.domain,
        path="/",
    )


def _redirect_with_error(message: str) -> RedirectResponse:
    qs = urlencode({"error": message[:500]})
    return RedirectResponse(
        url=f"{_web_base()}/auth/login?{qs}",
        status_code=status.HTTP_302_FOUND,
    )
