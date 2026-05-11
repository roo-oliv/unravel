"""GitHub → Postgres sync for PR metadata and comments.

Phase 0: pull-only. A future Phase 1 will add webhook-driven push updates,
but the read path here is the canonical hydration point regardless of which
trigger fires (background polling, manual refresh, post-create resync).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from unravel.api import github_client
from unravel.api.db_models import PrComment, Walkthrough

logger = logging.getLogger(__name__)


class WalkthroughHasNoPrError(LookupError):
    """The walkthrough is not associated with a GitHub PR."""


async def refresh_pr(
    session: AsyncSession, walkthrough_id: UUID
) -> Walkthrough:
    """Fetch the PR + its comments from GitHub and upsert them into Postgres.

    Returns the refreshed Walkthrough. Raises ``WalkthroughHasNoPrError`` if the
    walkthrough has no recorded repo/PR number.
    """
    walkthrough = await _load(session, walkthrough_id)
    if not (walkthrough.repo_full_name and walkthrough.pr_number):
        raise WalkthroughHasNoPrError(str(walkthrough_id))

    repo = walkthrough.repo_full_name
    number = walkthrough.pr_number

    pr = await github_client.fetch_pr(repo, number)
    walkthrough.pr_state = pr.state
    walkthrough.pr_is_draft = pr.is_draft
    walkthrough.pr_merged_at = pr.merged_at
    walkthrough.pr_closed_at = pr.closed_at
    walkthrough.pr_html_url = pr.html_url or walkthrough.pr_html_url
    walkthrough.pr_title = pr.title or walkthrough.pr_title
    walkthrough.pr_body = pr.body
    walkthrough.pr_head_sha = pr.head_sha or walkthrough.pr_head_sha
    walkthrough.pr_synced_at = datetime.now(UTC)

    # Pull comments in three buckets — issue (top-level), reviews, review
    # comments (line-anchored). We unify them into one table; ``github_kind``
    # plus ``anchor_path``/``anchor_line`` are enough to render them.
    issue_comments = await github_client.list_issue_comments(repo, number)
    reviews = await github_client.list_reviews(repo, number)
    review_comments = await github_client.list_review_comments(repo, number)

    await _upsert_comments(
        session,
        walkthrough_id=walkthrough_id,
        fetched=[*issue_comments, *reviews, *review_comments],
    )

    await session.commit()
    return await _load(session, walkthrough_id)


async def post_issue_comment(
    session: AsyncSession,
    walkthrough_id: UUID,
    body: str,
    *,
    local_author_login: str,
) -> PrComment:
    """Append a top-level issue comment, persisted both locally and to GitHub.

    The flow is intentionally synchronous in Phase 0 (no background queue): we
    insert a ``local`` row, then call the GitHub API, then flip ``sync_state``.
    Failure leaves the row at ``failed`` so the UI can render a retry pill.
    """
    walkthrough = await _load(session, walkthrough_id)
    if not (walkthrough.repo_full_name and walkthrough.pr_number):
        raise WalkthroughHasNoPrError(str(walkthrough_id))

    row = PrComment(
        walkthrough_id=walkthrough_id,
        github_kind="issue",
        author_login=local_author_login,
        body=body,
        sync_state="syncing",
        local_author_login=local_author_login,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    try:
        comment = await github_client.create_issue_comment(
            walkthrough.repo_full_name, walkthrough.pr_number, body
        )
    except Exception as exc:  # noqa: BLE001 — surface every failure to the UI
        logger.exception("create_issue_comment failed")
        row.sync_state = "failed"
        row.sync_error = str(exc)[:1000]
        await session.commit()
        await session.refresh(row)
        return row

    row.github_id = comment.github_id
    row.author_login = comment.author_login or row.author_login
    row.author_avatar_url = comment.author_avatar_url
    row.html_url = comment.html_url
    row.github_created_at = comment.github_created_at
    row.github_updated_at = comment.github_updated_at
    row.sync_state = "synced"
    row.sync_error = None
    await session.commit()
    await session.refresh(row)
    return row


async def list_comments(
    session: AsyncSession, walkthrough_id: UUID
) -> list[PrComment]:
    stmt = (
        select(PrComment)
        .where(PrComment.walkthrough_id == walkthrough_id)
        .order_by(
            PrComment.github_created_at.asc().nulls_last(),
            PrComment.created_at.asc(),
        )
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def walkthrough_pr_to_dto(walkthrough: Walkthrough) -> dict[str, Any]:
    return {
        "repo": walkthrough.repo_full_name,
        "number": walkthrough.pr_number,
        "state": walkthrough.pr_state,
        "is_draft": walkthrough.pr_is_draft,
        "title": walkthrough.pr_title,
        "body": walkthrough.pr_body,
        "html_url": walkthrough.pr_html_url,
        "head_sha": walkthrough.pr_head_sha,
        "merged_at": (
            walkthrough.pr_merged_at.isoformat()
            if walkthrough.pr_merged_at
            else None
        ),
        "closed_at": (
            walkthrough.pr_closed_at.isoformat()
            if walkthrough.pr_closed_at
            else None
        ),
        "synced_at": (
            walkthrough.pr_synced_at.isoformat()
            if walkthrough.pr_synced_at
            else None
        ),
    }


def comment_to_dto(comment: PrComment) -> dict[str, Any]:
    return {
        "id": str(comment.id),
        "github_id": comment.github_id,
        "kind": comment.github_kind,
        "author_login": comment.author_login,
        "author_avatar_url": comment.author_avatar_url,
        "body": comment.body,
        "html_url": comment.html_url,
        "anchor": (
            {
                "path": comment.anchor_path,
                "line": comment.anchor_line,
                "side": comment.anchor_side,
            }
            if comment.anchor_path
            else None
        ),
        "review_state": comment.review_state,
        "in_reply_to_github_id": comment.in_reply_to_github_id,
        "sync_state": comment.sync_state,
        "sync_error": comment.sync_error,
        "created_at": (
            comment.github_created_at.isoformat()
            if comment.github_created_at
            else comment.created_at.isoformat()
            if comment.created_at
            else None
        ),
        "updated_at": (
            comment.github_updated_at.isoformat()
            if comment.github_updated_at
            else None
        ),
    }


async def _load(session: AsyncSession, walkthrough_id: UUID) -> Walkthrough:
    walkthrough = await session.get(Walkthrough, walkthrough_id)
    if walkthrough is None:
        raise LookupError(f"Walkthrough not found: {walkthrough_id}")
    return walkthrough


async def _upsert_comments(
    session: AsyncSession,
    *,
    walkthrough_id: UUID,
    fetched: list[github_client.Comment],
) -> None:
    """Merge a fresh GitHub fetch into ``pr_comments`` for this walkthrough.

    Match strategy: ``(github_id, github_kind)`` is the unique key. Rows in
    ``local`` or ``syncing`` state without a ``github_id`` are left alone (a
    parallel POST is in flight).
    """
    if not fetched:
        return

    stmt = select(PrComment).where(
        PrComment.walkthrough_id == walkthrough_id,
        PrComment.github_id.is_not(None),
    )
    result = await session.execute(stmt)
    existing_by_key: dict[tuple[int, str], PrComment] = {
        (row.github_id, row.github_kind): row
        for row in result.scalars().all()
        if row.github_id is not None
    }

    for c in fetched:
        key = (c.github_id, c.kind)
        row = existing_by_key.get(key)
        if row is None:
            row = PrComment(
                walkthrough_id=walkthrough_id,
                github_id=c.github_id,
                github_kind=c.kind,
                sync_state="synced",
            )
            session.add(row)

        row.author_login = c.author_login
        row.author_avatar_url = c.author_avatar_url
        row.body = c.body
        row.html_url = c.html_url
        row.anchor_path = c.anchor_path
        row.anchor_line = c.anchor_line
        row.anchor_side = c.anchor_side
        row.review_state = c.review_state
        row.in_reply_to_github_id = c.in_reply_to_github_id
        row.github_created_at = c.github_created_at
        row.github_updated_at = c.github_updated_at
        row.sync_state = "synced"
        row.sync_error = None
