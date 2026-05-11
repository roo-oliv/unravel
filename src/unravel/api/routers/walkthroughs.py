"""Walkthrough endpoints — Phase 0 reads fixtures, persists in Postgres on first hit."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from unravel.api.db import get_db
from unravel.api.deps import CurrentUser, auth_user
from unravel.api.fixtures import list_fixtures, load_fixture
from unravel.api.services.walkthrough_store import (
    get_or_create_walkthrough_from_fixture,
    walkthrough_to_dto,
)

router = APIRouter()


@router.get("/walkthroughs/fixture")
def list_fixture_walkthroughs(
    user: CurrentUser = Depends(auth_user),
) -> dict:
    """List available fixture slugs."""
    entries = list_fixtures()
    return {
        "fixtures": [
            {"slug": e.slug, "path": str(e.path.name)} for e in entries
        ]
    }


@router.get("/walkthroughs/fixture/{slug}")
async def get_fixture_walkthrough(
    slug: str,
    user: CurrentUser = Depends(auth_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Load a walkthrough by fixture slug.

    First hit imports the disk JSON into Postgres; subsequent hits serve the
    DB-backed version with any narration edits applied. Re-import is not
    automatic — delete the row to refresh from disk.
    """
    try:
        fixture = load_fixture(slug)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fixture not found: {slug}",
        ) from exc

    walkthrough = await get_or_create_walkthrough_from_fixture(db, slug, fixture)
    return walkthrough_to_dto(walkthrough)
