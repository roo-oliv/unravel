"""Server-side session store with a signed-cookie front door.

The browser carries the **signed** session id (so tampering is detected before
hitting the DB); the session row in Postgres is the source of truth for expiry,
user, and last activity. Sessions are rolling: an active request that's older
than half the TTL pushes ``expires_at`` forward by a full TTL.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from unravel.api.db_models import Session as SessionRow

COOKIE_NAME = "unravel_session"
SESSION_TTL = timedelta(days=30)
ROLLING_THRESHOLD = SESSION_TTL / 2

_SERIALIZER_SALT = "unravel.session.v1"


@dataclass(frozen=True)
class CookieAttrs:
    secure: bool
    samesite: str
    domain: str | None


def _serializer() -> URLSafeSerializer:
    secret = os.environ.get("SESSION_SECRET", "").strip()
    if not secret:
        raise RuntimeError("SESSION_SECRET is not set")
    return URLSafeSerializer(secret, salt=_SERIALIZER_SALT)


def cookie_attrs() -> CookieAttrs:
    """Default cookie attributes — relaxed for localhost dev.

    Dev mode keeps Secure=False so http://localhost works. Prod must override
    via env to require HTTPS; we don't auto-detect because the proxy boundary
    is install-specific.
    """
    secure_env = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
    samesite = os.environ.get("SESSION_COOKIE_SAMESITE", "lax").lower()
    domain = os.environ.get("SESSION_COOKIE_DOMAIN") or None
    return CookieAttrs(secure=secure_env, samesite=samesite, domain=domain)


def sign(sid: str) -> str:
    return _serializer().dumps(sid)


def unsign(token: str) -> str | None:
    try:
        value = _serializer().loads(token)
    except BadSignature:
        return None
    return value if isinstance(value, str) else None


async def create_session(
    db: AsyncSession,
    *,
    user_id: UUID,
    user_agent: str | None,
    ip: str | None,
) -> SessionRow:
    sid = secrets.token_urlsafe(32)
    row = SessionRow(
        id=sid,
        user_id=user_id,
        expires_at=datetime.now(UTC) + SESSION_TTL,
        user_agent=(user_agent or None),
        ip=(ip or None),
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def load_session(
    db: AsyncSession, sid: str
) -> SessionRow | None:
    row = await db.get(SessionRow, sid)
    if row is None:
        return None
    if row.expires_at <= datetime.now(UTC):
        await db.delete(row)
        await db.commit()
        return None
    return row


async def maybe_roll(db: AsyncSession, row: SessionRow) -> SessionRow:
    """Extend the session if it's past half-TTL.

    Cheap write — only fires once per ~15d per active user. Skips the commit
    when the session is still fresh.
    """
    now = datetime.now(UTC)
    if row.expires_at - now > ROLLING_THRESHOLD:
        return row
    row.expires_at = now + SESSION_TTL
    await db.commit()
    return row


async def delete_session(db: AsyncSession, sid: str) -> None:
    await db.execute(delete(SessionRow).where(SessionRow.id == sid))
    await db.commit()


async def delete_expired_sessions(db: AsyncSession) -> int:
    """Purge expired rows. Cron-callable in the future; not auto-scheduled yet."""
    result = await db.execute(
        delete(SessionRow).where(SessionRow.expires_at <= datetime.now(UTC))
    )
    await db.commit()
    return result.rowcount or 0


__all__ = [
    "COOKIE_NAME",
    "SESSION_TTL",
    "CookieAttrs",
    "cookie_attrs",
    "create_session",
    "delete_expired_sessions",
    "delete_session",
    "load_session",
    "maybe_roll",
    "sign",
    "unsign",
    "select",  # re-export for convenience in dep code
]
