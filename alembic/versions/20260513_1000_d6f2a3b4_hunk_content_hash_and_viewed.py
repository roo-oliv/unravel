"""hunks.content_hash + hunk_viewed table

Revision ID: d6f2a3b4
Revises: c5e1a2d3
Create Date: 2026-05-13 10:00:00.000000+00:00

Adds a stable content-derived identity to every hunk and a per-user
``hunk_viewed`` table keyed on that identity. Viewed marks survive walkthrough
regeneration: hunks whose textual content is unchanged keep the same hash, so
the existing rows still match.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd6f2a3b4'
down_revision: str | Sequence[str] | None = 'c5e1a2d3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'hunks',
        sa.Column(
            'content_hash',
            sa.String(length=64),
            nullable=False,
            server_default='',
        ),
    )
    op.create_index(
        'ix_hunks_content_hash', 'hunks', ['content_hash']
    )
    op.create_table(
        'hunk_viewed',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            'user_id',
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column(
            'viewed_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            'user_id', 'content_hash', name='uq_hunk_viewed_user_content'
        ),
    )
    op.create_index('ix_hunk_viewed_user', 'hunk_viewed', ['user_id'])
    op.create_index(
        'ix_hunk_viewed_content_hash', 'hunk_viewed', ['content_hash']
    )


def downgrade() -> None:
    op.drop_index('ix_hunk_viewed_content_hash', table_name='hunk_viewed')
    op.drop_index('ix_hunk_viewed_user', table_name='hunk_viewed')
    op.drop_table('hunk_viewed')
    op.drop_index('ix_hunks_content_hash', table_name='hunks')
    op.drop_column('hunks', 'content_hash')
