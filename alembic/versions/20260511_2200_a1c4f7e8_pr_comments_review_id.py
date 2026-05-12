"""pr_comments.pull_request_review_id

Revision ID: a1c4f7e8
Revises: ddb9aa53
Create Date: 2026-05-11 22:00:00.000000+00:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a1c4f7e8'
down_revision: str | Sequence[str] | None = 'ddb9aa53'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'pr_comments',
        sa.Column('pull_request_review_id', sa.BigInteger(), nullable=True),
    )
    op.create_index(
        'ix_pr_comments_review',
        'pr_comments',
        ['walkthrough_id', 'pull_request_review_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_pr_comments_review', table_name='pr_comments')
    op.drop_column('pr_comments', 'pull_request_review_id')
