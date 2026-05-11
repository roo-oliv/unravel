"""SQLAlchemy models for Phase 0 persistence.

Subset of the full schema in the plan. Phase 0 omits users/teams/repos/PRs —
walkthroughs are identified by ``slug`` (matches fixture filename). Phase 1
will add team_id + pr_id FKs and migrate slug → derived field.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from unravel.api.db import Base


class Walkthrough(Base):
    __tablename__ = "walkthroughs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    overview: Mapped[str] = mapped_column(Text, default="", nullable=False)
    suggested_order: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, nullable=False
    )
    hunk_captions: Mapped[dict[str, str]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    raw_diff: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # GitHub source (populated when the walkthrough analyses a PR).
    repo_full_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pr_head_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pr_html_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    pr_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    pr_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    pr_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pr_is_draft: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    pr_merged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pr_closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pr_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    threads: Mapped[list[Thread]] = relationship(
        back_populates="walkthrough",
        cascade="all, delete-orphan",
        order_by="Thread.position",
    )
    hunks: Mapped[list[Hunk]] = relationship(
        back_populates="walkthrough",
        cascade="all, delete-orphan",
    )


class Thread(Base):
    __tablename__ = "threads"
    __table_args__ = (
        UniqueConstraint("walkthrough_id", "ref", name="uq_threads_walkthrough_ref"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    walkthrough_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("walkthroughs.id", ondelete="CASCADE"),
        nullable=False,
    )
    ref: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, default="", nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    root_cause: Mapped[str] = mapped_column(Text, default="", nullable=False)
    dependencies: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )

    walkthrough: Mapped[Walkthrough] = relationship(back_populates="threads")
    steps: Mapped[list[ThreadStep]] = relationship(
        back_populates="thread",
        cascade="all, delete-orphan",
        order_by="ThreadStep.step_order",
    )


class ThreadStep(Base):
    __tablename__ = "thread_steps"
    __table_args__ = (
        UniqueConstraint(
            "thread_id", "step_order", name="uq_thread_steps_thread_order"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    narration: Mapped[str] = mapped_column(Text, default="", nullable=False)
    narration_edited_at: Mapped[datetime | None] = mapped_column(nullable=True)
    narration_edited_by: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    thread: Mapped[Thread] = relationship(back_populates="steps")
    hunk_links: Mapped[list[ThreadStepHunk]] = relationship(
        back_populates="step",
        cascade="all, delete-orphan",
        order_by="ThreadStepHunk.position",
    )


class Hunk(Base):
    __tablename__ = "hunks"
    __table_args__ = (
        UniqueConstraint("walkthrough_id", "ref", name="uq_hunks_walkthrough_ref"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    walkthrough_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("walkthroughs.id", ondelete="CASCADE"),
        nullable=False,
    )
    ref: Mapped[str] = mapped_column(String(64), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, default="", nullable=False)
    old_start: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    old_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_start: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    context_before: Mapped[str] = mapped_column(Text, default="", nullable=False)
    context_after: Mapped[str] = mapped_column(Text, default="", nullable=False)
    language: Mapped[str | None] = mapped_column(String(64), nullable=True)
    caption: Mapped[str] = mapped_column(Text, default="", nullable=False)
    additions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deletions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    walkthrough: Mapped[Walkthrough] = relationship(back_populates="hunks")


class ThreadStepHunk(Base):
    """Join table preserving hunk order within a step."""

    __tablename__ = "thread_step_hunks"

    thread_step_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("thread_steps.id", ondelete="CASCADE"),
        primary_key=True,
    )
    hunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hunks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    step: Mapped[ThreadStep] = relationship(back_populates="hunk_links")
    hunk: Mapped[Hunk] = relationship()


class FieldEdit(Base):
    """One row per (field, batch) — append-only edit history."""

    __tablename__ = "field_edits"
    __table_args__ = (
        Index(
            "ix_field_edits_target",
            "target_kind",
            "target_id",
            "field",
            "created_at",
        ),
        Index("ix_field_edits_walkthrough", "walkthrough_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    walkthrough_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("walkthroughs.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[str] = mapped_column(Text, default="", nullable=False)
    new_value: Mapped[str] = mapped_column(Text, default="", nullable=False)
    editor: Mapped[str] = mapped_column(String(255), nullable=False)
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), nullable=False
    )


class PrComment(Base):
    """A PR comment mirrored from (or destined for) GitHub.

    ``github_kind`` distinguishes:
      - ``issue`` — top-level PR thread (``/issues/{n}/comments``)
      - ``review`` — a review summary (``/pulls/{n}/reviews``)
      - ``review_comment`` — line-anchored review comment (``/pulls/{n}/comments``)

    ``sync_state`` runs ``local → syncing → synced`` (or ``failed``). Rows
    inserted from a GitHub fetch start as ``synced`` already; rows posted by
    a local user start as ``local`` and flip when the GitHub API call lands.
    """

    __tablename__ = "pr_comments"
    __table_args__ = (
        UniqueConstraint(
            "github_id", "github_kind", name="uq_pr_comments_github"
        ),
        Index(
            "ix_pr_comments_walkthrough_created",
            "walkthrough_id",
            "created_at",
        ),
        Index(
            "ix_pr_comments_anchor",
            "walkthrough_id",
            "anchor_path",
            "anchor_line",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    walkthrough_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("walkthroughs.id", ondelete="CASCADE"),
        nullable=False,
    )
    github_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    github_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    author_login: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    html_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    anchor_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    anchor_line: Mapped[int | None] = mapped_column(Integer, nullable=True)
    anchor_side: Mapped[str | None] = mapped_column(String(8), nullable=True)
    review_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    in_reply_to_github_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    sync_state: Mapped[str] = mapped_column(
        String(16), default="synced", server_default="synced", nullable=False
    )
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_author_login: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    github_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    github_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class User(Base):
    """A GitHub user signed into Unravel.

    ``encrypted_access_token`` stores the GitHub OAuth token enciphered with
    Fernet (see ``auth.crypto``); decryption is intentionally explicit at the
    call sites that need to hit the GitHub API on the user's behalf.
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("github_id", name="uq_users_github_id"),
        Index("ix_users_github_login", "github_login"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    github_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    github_login: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_access_token: Mapped[str] = mapped_column(Text, nullable=False)
    token_scopes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Session(Base):
    """A server-side session row backing the HttpOnly cookie.

    The cookie value is the signed (itsdangerous) sid; this row is the source
    of truth for expiry, last-seen, and the FK to ``users``. Deleting the row
    invalidates the session immediately.
    """

    __tablename__ = "sessions"
    __table_args__ = (
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_expires_at", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


__all__ = [
    "Walkthrough",
    "Thread",
    "ThreadStep",
    "Hunk",
    "ThreadStepHunk",
    "FieldEdit",
    "PrComment",
    "User",
    "Session",
]
