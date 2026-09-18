"""inbox record: make outbox consumption idempotent

The outbox delivers at least once. Without an inbox, a handler that succeeds
and then loses its process is replayed and does its work twice. The claim is
written in the same transaction as the handler's effects, so the replay either
sees it and stops, or rolls back with the work and retries.

Revision ID: c3f81d5e60a2
Revises: b7e2a4c91f08
Create Date: 2026-09-18 17:20:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c3f81d5e60a2'
down_revision: str | None = 'b7e2a4c91f08'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'inbox_record',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('consumer', sa.String(length=120), nullable=False),
        sa.Column('message_id', sa.String(length=64), nullable=False),
        sa.Column('organization_id', sa.String(length=64), nullable=True),
        sa.Column('event_type', sa.String(length=120), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('consumer', 'message_id', name='uq_inbox_consumer_message'),
    )


def downgrade() -> None:
    op.drop_table('inbox_record')
