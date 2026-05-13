"""Per-user "viewed" marks on hunks.

Keyed on ``hunks.content_hash``, not on hunks.id, so marks survive walkthrough
regeneration: a hunk whose textual content is unchanged keeps the same hash
across re-runs and the existing row still matches.

Returned hashes are filtered to those present in the requested walkthrough so
a stale client can't accidentally light up rows from an unrelated walkthrough.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from unravel.api.db import get_db
from unravel.api.db_models import Hunk, HunkViewed, Walkthrough
from unravel.api.deps import CurrentUser, auth_user

router = APIRouter()


class SetViewedBody(BaseModel):
    content_hash: str
    viewed: bool


def _require_db_user(user: CurrentUser) -> UUID:
    """Return the user's DB UUID, or 401 for synthetic dev users.

    Viewed marks are persisted via FK to ``users.id``; dev users have no row
    in that table, so we reject the write rather than silently no-op.
    """
    if user.is_dev_user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Viewed tracking requires a real GitHub login. Sign in at "
                "/auth/github or disable DEV_AUTH."
            ),
        )
    try:
        return UUID(user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed user id.",
        ) from exc


async def _walkthrough_hashes(db: AsyncSession, slug: str) -> set[str]:
    stmt = (
        select(Hunk.content_hash)
        .join(Walkthrough, Hunk.walkthrough_id == Walkthrough.id)
        .where(Walkthrough.slug == slug)
    )
    result = await db.execute(stmt)
    return {row[0] for row in result.all() if row[0]}


@router.get("/walkthroughs/{slug}/viewed-hunks")
async def list_viewed_hunks(
    slug: str,
    user: CurrentUser = Depends(auth_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the set of content_hashes the caller has marked viewed in this
    walkthrough."""
    if user.is_dev_user:
        # Dev users never persist; return empty so the FE can render cleanly.
        return {"viewed_content_hashes": []}
    user_id = _require_db_user(user)
    wt_hashes = await _walkthrough_hashes(db, slug)
    if not wt_hashes:
        return {"viewed_content_hashes": []}

    stmt = select(HunkViewed.content_hash).where(
        HunkViewed.user_id == user_id,
        HunkViewed.content_hash.in_(wt_hashes),
    )
    result = await db.execute(stmt)
    hashes = sorted({row[0] for row in result.all()})
    return {"viewed_content_hashes": hashes}


@router.post("/walkthroughs/{slug}/viewed-hunks")
async def set_hunk_viewed(
    slug: str,
    body: SetViewedBody,
    user: CurrentUser = Depends(auth_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mark/unmark a single hunk as viewed for the current user.

    The hunk must belong to ``slug`` (we check ``content_hash`` membership) so
    a stale or malicious client can't toggle marks for arbitrary hashes.
    """
    user_id = _require_db_user(user)
    if not body.content_hash:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="content_hash is required.",
        )
    wt_hashes = await _walkthrough_hashes(db, slug)
    if body.content_hash not in wt_hashes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="content_hash does not belong to this walkthrough.",
        )

    if body.viewed:
        stmt = (
            insert(HunkViewed)
            .values(user_id=user_id, content_hash=body.content_hash)
            .on_conflict_do_nothing(
                index_elements=["user_id", "content_hash"]
            )
        )
        await db.execute(stmt)
    else:
        await db.execute(
            delete(HunkViewed).where(
                HunkViewed.user_id == user_id,
                HunkViewed.content_hash == body.content_hash,
            )
        )
    await db.commit()

    return await list_viewed_hunks(slug=slug, user=user, db=db)
