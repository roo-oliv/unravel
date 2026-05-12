"""PR status + GitHub comments endpoints.

Phase 0 contract:
- ``GET /walkthroughs/{uuid}/pr`` returns the cached PR snapshot. If we've
  never synced, kicks off a sync inline so the first hit returns real data.
- ``POST /walkthroughs/{uuid}/pr/refresh`` forces a fresh fetch.
- ``GET /walkthroughs/{uuid}/comments`` lists every cached comment.
- ``POST /walkthroughs/{uuid}/comments`` posts a top-level issue comment;
  body is persisted locally first, then synced to GitHub.

Errors:
- 404 when the walkthrough doesn't exist or has no associated PR
- 500 surfaces ``GitHubError`` / ``GitHubConfigError`` with a readable message
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from unravel.api.db import get_db
from unravel.api.deps import CurrentUser, auth_user
from unravel.api.github_client import GitHubConfigError, GitHubError
from unravel.api.services.github_sync import (
    CommentNotFoundError,
    DraftReviewComment,
    InvalidReplyTargetError,
    MissingCommitShaError,
    WalkthroughHasNoPrError,
    comment_to_dto,
    fetch_pr_file_lines,
    list_comments,
    post_issue_comment,
    post_review_comment,
    post_review_comment_reply,
    refresh_pr,
    submit_review,
    walkthrough_pr_to_dto,
)
from unravel.api.services.walkthrough_store import load_full_walkthrough

logger = logging.getLogger(__name__)

router = APIRouter()

# Treat a sync younger than this as fresh; GETs reuse the cached snapshot.
PR_AUTO_SYNC_MAX_AGE = timedelta(seconds=60)


class CommentBody(BaseModel):
    body: str = Field(min_length=1, max_length=65_000)


class ReviewCommentBody(BaseModel):
    body: str = Field(min_length=1, max_length=65_000)
    path: str = Field(min_length=1, max_length=2048)
    line: int = Field(ge=1)
    side: str = Field(default="RIGHT", pattern="^(LEFT|RIGHT)$")
    start_line: int | None = Field(default=None, ge=1)
    start_side: str | None = Field(default=None, pattern="^(LEFT|RIGHT)$")


class ReviewDraftComment(BaseModel):
    body: str = Field(min_length=1, max_length=65_000)
    path: str = Field(min_length=1, max_length=2048)
    line: int = Field(ge=1)
    side: str = Field(default="RIGHT", pattern="^(LEFT|RIGHT)$")
    start_line: int | None = Field(default=None, ge=1)
    start_side: str | None = Field(default=None, pattern="^(LEFT|RIGHT)$")


class ReviewSubmission(BaseModel):
    event: str = Field(pattern="^(APPROVE|COMMENT|REQUEST_CHANGES)$")
    body: str | None = Field(default=None, max_length=65_000)
    comments: list[ReviewDraftComment] = Field(default_factory=list)


@router.get("/walkthroughs/{walkthrough_uuid}/pr")
async def get_pr(
    walkthrough_uuid: UUID,
    user: CurrentUser = Depends(auth_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    walkthrough = await load_full_walkthrough(db, id=walkthrough_uuid)
    if walkthrough is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Walkthrough not found: {walkthrough_uuid}",
        )
    if not (walkthrough.repo_full_name and walkthrough.pr_number):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Walkthrough is not associated with a GitHub PR.",
        )

    stale = (
        walkthrough.pr_synced_at is None
        or datetime.now(UTC) - walkthrough.pr_synced_at > PR_AUTO_SYNC_MAX_AGE
    )
    if stale:
        try:
            walkthrough = await refresh_pr(
                db, walkthrough_uuid, token=user.github_access_token
            )
        except (GitHubError, GitHubConfigError) as exc:
            # Fall back to whatever snapshot we have. The DTO carries
            # ``synced_at`` so the UI can show the last successful refresh.
            logger.warning("PR auto-refresh failed: %s", exc)

    return walkthrough_pr_to_dto(walkthrough)


@router.post("/walkthroughs/{walkthrough_uuid}/pr/refresh")
async def force_refresh_pr(
    walkthrough_uuid: UUID,
    user: CurrentUser = Depends(auth_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        walkthrough = await refresh_pr(
            db, walkthrough_uuid, token=user.github_access_token
        )
    except WalkthroughHasNoPrError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Walkthrough is not associated with a GitHub PR.",
        ) from exc
    except GitHubConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except GitHubError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    comments = await list_comments(db, walkthrough_uuid)
    return {
        "pr": walkthrough_pr_to_dto(walkthrough),
        "comments": [comment_to_dto(c) for c in comments],
    }


@router.get("/walkthroughs/{walkthrough_uuid}/comments")
async def get_comments(
    walkthrough_uuid: UUID,
    user: CurrentUser = Depends(auth_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    walkthrough = await load_full_walkthrough(db, id=walkthrough_uuid)
    if walkthrough is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Walkthrough not found: {walkthrough_uuid}",
        )
    if not (walkthrough.repo_full_name and walkthrough.pr_number):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Walkthrough is not associated with a GitHub PR.",
        )
    comments = await list_comments(db, walkthrough_uuid)
    return {"comments": [comment_to_dto(c) for c in comments]}


@router.post(
    "/walkthroughs/{walkthrough_uuid}/comments",
    status_code=status.HTTP_201_CREATED,
)
async def create_comment(
    walkthrough_uuid: UUID,
    body: CommentBody,
    user: CurrentUser = Depends(auth_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        row = await post_issue_comment(
            db,
            walkthrough_uuid,
            body.body,
            local_author_login=user.github_login,
            token=user.github_access_token,
        )
    except WalkthroughHasNoPrError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Walkthrough is not associated with a GitHub PR.",
        ) from exc
    except GitHubConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return comment_to_dto(row)


@router.post(
    "/walkthroughs/{walkthrough_uuid}/review-comments",
    status_code=status.HTTP_201_CREATED,
)
async def create_review_comment_endpoint(
    walkthrough_uuid: UUID,
    body: ReviewCommentBody,
    user: CurrentUser = Depends(auth_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Post a single line-anchored review comment (no review wrapper)."""
    try:
        row = await post_review_comment(
            db,
            walkthrough_uuid,
            body=body.body,
            path=body.path,
            line=body.line,
            side=body.side,
            start_line=body.start_line,
            start_side=body.start_side,
            local_author_login=user.github_login,
            token=user.github_access_token,
        )
    except WalkthroughHasNoPrError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Walkthrough is not associated with a GitHub PR.",
        ) from exc
    except MissingCommitShaError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="PR has no recorded head SHA — refresh the PR first.",
        ) from exc
    except GitHubConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return comment_to_dto(row)


@router.post(
    "/walkthroughs/{walkthrough_uuid}/reviews",
    status_code=status.HTTP_201_CREATED,
)
async def submit_review_endpoint(
    walkthrough_uuid: UUID,
    payload: ReviewSubmission,
    user: CurrentUser = Depends(auth_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Submit a PR review (Approve / Comment / Request changes) with inline comments."""
    if payload.event == "APPROVE" and not (payload.body or payload.comments):
        # GitHub accepts a no-op approval but we still require *something* so
        # users don't accidentally approve with an empty composer.
        pass
    if payload.event != "APPROVE" and not (payload.body or payload.comments):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A review must include a summary or at least one inline comment.",
        )
    drafts = [
        DraftReviewComment(
            path=c.path,
            line=c.line,
            side=c.side,
            body=c.body,
            start_line=c.start_line,
            start_side=c.start_side,
        )
        for c in payload.comments
    ]
    try:
        review_row, comment_rows = await submit_review(
            db,
            walkthrough_uuid,
            event=payload.event,
            body=payload.body,
            comments=drafts,
            local_author_login=user.github_login,
            token=user.github_access_token,
        )
    except WalkthroughHasNoPrError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Walkthrough is not associated with a GitHub PR.",
        ) from exc
    except MissingCommitShaError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="PR has no recorded head SHA — refresh the PR first.",
        ) from exc
    except GitHubConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except GitHubError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return {
        "review": comment_to_dto(review_row) if review_row else None,
        "comments": [comment_to_dto(c) for c in comment_rows],
    }


@router.get("/walkthroughs/{walkthrough_uuid}/file")
async def get_pr_file_slice(
    walkthrough_uuid: UUID,
    path: str = Query(..., min_length=1, max_length=2048),
    start: int = Query(..., ge=1),
    end: int = Query(..., ge=1),
    user: CurrentUser = Depends(auth_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fetch a 1-indexed slice of file content at the PR's head SHA.

    Backs the diff viewer's expand-context action and auto-expand for
    out-of-hunk anchored comments. Returns ``{path, ref, total, lines: [{line, content}]}``.
    """
    try:
        return await fetch_pr_file_lines(
            db,
            walkthrough_uuid,
            path,
            start,
            end,
            token=user.github_access_token,
        )
    except WalkthroughHasNoPrError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Walkthrough is not associated with a GitHub PR.",
        ) from exc
    except GitHubConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except GitHubError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


@router.post(
    "/walkthroughs/{walkthrough_uuid}/comments/{parent_id}/reply",
    status_code=status.HTTP_201_CREATED,
)
async def reply_to_comment(
    walkthrough_uuid: UUID,
    parent_id: UUID,
    body: CommentBody,
    user: CurrentUser = Depends(auth_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        row = await post_review_comment_reply(
            db,
            walkthrough_uuid,
            parent_id,
            body.body,
            local_author_login=user.github_login,
            token=user.github_access_token,
        )
    except WalkthroughHasNoPrError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Walkthrough is not associated with a GitHub PR.",
        ) from exc
    except CommentNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parent comment not found: {parent_id}",
        ) from exc
    except InvalidReplyTargetError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except GitHubConfigError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    return comment_to_dto(row)
