"""Batch edits + history endpoints — replaces the autosave PATCH from earlier.

Edit model: the UI accumulates pending edits in localStorage; one POST commits
a batch. Each commit creates one history row per field, grouped by batch_id.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from unravel.api.db import get_db
from unravel.api.deps import CurrentUser, auth_user
from unravel.api.services.walkthrough_store import (
    EditRequest,
    EditValidationError,
    apply_edits_batch,
    field_edit_to_dto,
    load_edit_history,
    walkthrough_to_dto,
)
from unravel.api.services.walkthrough_store import load_full_walkthrough

router = APIRouter()


class EditBody(BaseModel):
    target_kind: str = Field(pattern=r"^(walkthrough|thread|step)$")
    target_id: UUID
    field: str = Field(max_length=64)
    value: str = Field(max_length=20_000)


class BatchEditsBody(BaseModel):
    edits: list[EditBody] = Field(min_length=0, max_length=200)


@router.post("/walkthroughs/{walkthrough_uuid}/edits")
async def submit_edits(
    walkthrough_uuid: UUID,
    body: BatchEditsBody,
    user: CurrentUser = Depends(auth_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    walkthrough = await load_full_walkthrough(db, id=walkthrough_uuid)
    if walkthrough is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Walkthrough not found: {walkthrough_uuid}",
        )
    edit_requests = [
        EditRequest(
            target_kind=e.target_kind,
            target_id=e.target_id,
            field=e.field,
            value=e.value,
        )
        for e in body.edits
    ]
    try:
        history = await apply_edits_batch(db, walkthrough, edit_requests, editor=user.id)
    except EditValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    # Reload to ensure relationships are fresh (apply mutates in place but a
    # fresh selectinload guarantees the DTO reflects committed state).
    refreshed = await load_full_walkthrough(db, id=walkthrough_uuid)
    assert refreshed is not None
    return {
        "walkthrough": walkthrough_to_dto(refreshed),
        "applied": [field_edit_to_dto(h) for h in history],
    }


@router.get("/walkthroughs/{walkthrough_uuid}/edit-history")
async def get_edit_history(
    walkthrough_uuid: UUID,
    user: CurrentUser = Depends(auth_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    history = await load_edit_history(db, walkthrough_uuid)
    return {"history": [field_edit_to_dto(h) for h in history]}
