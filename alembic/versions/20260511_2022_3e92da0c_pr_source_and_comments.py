"""pr source columns + pr_comments table

Revision ID: 3e92da0c
Revises: 6fd55d764c78
Create Date: 2026-05-11 20:22:00.000000+00:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '3e92da0c'
down_revision: str | Sequence[str] | None = '6fd55d764c78'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'walkthroughs',
        sa.Column('repo_full_name', sa.String(length=255), nullable=True),
    )
    op.add_column(
        'walkthroughs',
        sa.Column('pr_number', sa.Integer(), nullable=True),
    )
    op.add_column(
        'walkthroughs',
        sa.Column('pr_head_sha', sa.String(length=64), nullable=True),
    )
    op.add_column(
        'walkthroughs',
        sa.Column('pr_html_url', sa.String(length=512), nullable=True),
    )
    op.add_column(
        'walkthroughs',
        sa.Column('pr_title', sa.Text(), nullable=True),
    )
    op.add_column(
        'walkthroughs',
        sa.Column('pr_body', sa.Text(), nullable=True),
    )
    op.add_column(
        'walkthroughs',
        sa.Column('pr_state', sa.String(length=32), nullable=True),
    )
    op.add_column(
        'walkthroughs',
        sa.Column('pr_is_draft', sa.Boolean(), nullable=True),
    )
    op.add_column(
        'walkthroughs',
        sa.Column('pr_merged_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'walkthroughs',
        sa.Column('pr_closed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'walkthroughs',
        sa.Column('pr_synced_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        'ix_walkthroughs_repo_pr',
        'walkthroughs',
        ['repo_full_name', 'pr_number'],
        unique=False,
    )

    op.create_table(
        'pr_comments',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('walkthrough_id', sa.UUID(), nullable=False),
        sa.Column('github_id', sa.BigInteger(), nullable=True),
        sa.Column('github_kind', sa.String(length=32), nullable=False),
        sa.Column('author_login', sa.String(length=255), nullable=True),
        sa.Column('author_avatar_url', sa.Text(), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('html_url', sa.Text(), nullable=True),
        sa.Column('anchor_path', sa.Text(), nullable=True),
        sa.Column('anchor_line', sa.Integer(), nullable=True),
        sa.Column('anchor_side', sa.String(length=8), nullable=True),
        sa.Column('review_state', sa.String(length=32), nullable=True),
        sa.Column('in_reply_to_github_id', sa.BigInteger(), nullable=True),
        sa.Column('sync_state', sa.String(length=16), nullable=False, server_default=sa.text("'synced'")),
        sa.Column('sync_error', sa.Text(), nullable=True),
        sa.Column('local_author_login', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('github_created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('github_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['walkthrough_id'], ['walkthroughs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('github_id', 'github_kind', name='uq_pr_comments_github'),
    )
    op.create_index(
        'ix_pr_comments_walkthrough_created',
        'pr_comments',
        ['walkthrough_id', 'created_at'],
        unique=False,
    )
    op.create_index(
        'ix_pr_comments_anchor',
        'pr_comments',
        ['walkthrough_id', 'anchor_path', 'anchor_line'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_pr_comments_anchor', table_name='pr_comments')
    op.drop_index('ix_pr_comments_walkthrough_created', table_name='pr_comments')
    op.drop_table('pr_comments')
    op.drop_index('ix_walkthroughs_repo_pr', table_name='walkthroughs')
    op.drop_column('walkthroughs', 'pr_synced_at')
    op.drop_column('walkthroughs', 'pr_closed_at')
    op.drop_column('walkthroughs', 'pr_merged_at')
    op.drop_column('walkthroughs', 'pr_is_draft')
    op.drop_column('walkthroughs', 'pr_state')
    op.drop_column('walkthroughs', 'pr_body')
    op.drop_column('walkthroughs', 'pr_title')
    op.drop_column('walkthroughs', 'pr_html_url')
    op.drop_column('walkthroughs', 'pr_head_sha')
    op.drop_column('walkthroughs', 'pr_number')
    op.drop_column('walkthroughs', 'repo_full_name')
