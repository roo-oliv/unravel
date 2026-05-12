"""walkthroughs.pr_node_id (GraphQL global id for the PR)

Revision ID: c5e1a2d3
Revises: b8f2e1c4
Create Date: 2026-05-12 12:00:00.000000+00:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c5e1a2d3'
down_revision: str | Sequence[str] | None = 'b8f2e1c4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'walkthroughs',
        sa.Column('pr_node_id', sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('walkthroughs', 'pr_node_id')
