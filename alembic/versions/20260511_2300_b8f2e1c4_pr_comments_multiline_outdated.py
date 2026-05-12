"""pr_comments multi-line anchor + outdated flag

Revision ID: b8f2e1c4
Revises: a1c4f7e8
Create Date: 2026-05-11 23:00:00.000000+00:00

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b8f2e1c4'
down_revision: str | Sequence[str] | None = 'a1c4f7e8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'pr_comments',
        sa.Column('anchor_start_line', sa.Integer(), nullable=True),
    )
    op.add_column(
        'pr_comments',
        sa.Column('anchor_start_side', sa.String(length=8), nullable=True),
    )
    op.add_column(
        'pr_comments',
        sa.Column(
            'is_outdated',
            sa.Boolean(),
            nullable=False,
            server_default=sa.text('false'),
        ),
    )


def downgrade() -> None:
    op.drop_column('pr_comments', 'is_outdated')
    op.drop_column('pr_comments', 'anchor_start_side')
    op.drop_column('pr_comments', 'anchor_start_line')
