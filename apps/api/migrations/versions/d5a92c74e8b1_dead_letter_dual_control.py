"""dead-letter dual control: request and approval must be two different people

Replaying a dead-lettered event risks a duplicate side effect; discarding it
loses the event for good. Neither is one person's call (M21), so the request
and its approval are recorded separately and the approver cannot be the
requester.

The partial unique index allows any number of decided reviews per message but
only one open request, so two approvers cannot apply two different actions to
the same message.

Revision ID: d5a92c74e8b1
Revises: c3f81d5e60a2
Create Date: 2026-09-18 17:45:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd5a92c74e8b1'
down_revision: str | None = 'c3f81d5e60a2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTION = sa.Enum(
    'REPLAY', 'DISCARD',
    name='deadletteraction', native_enum=False, length=40,
)
_REVIEW_STATUS = sa.Enum(
    'PENDING', 'APPROVED', 'REJECTED',
    name='deadletterreviewstatus', native_enum=False, length=40,
)


def upgrade() -> None:
    op.create_table(
        'outbox_dead_letter_review',
        sa.Column('id', sa.String(length=64), nullable=False),
        sa.Column('message_id', sa.String(length=64), nullable=False),
        sa.Column('organization_id', sa.String(length=64), nullable=True),
        sa.Column('action', _ACTION, nullable=False),
        sa.Column('status', _REVIEW_STATUS, nullable=False),
        sa.Column('requested_by_person_id', sa.String(length=64), nullable=False),
        sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('request_reason', sa.Text(), nullable=False),
        sa.Column('decided_by_person_id', sa.String(length=64), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decision_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['message_id'], ['outbox_message.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'uq_dead_letter_open_review',
        'outbox_dead_letter_review',
        ['message_id'],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )


def downgrade() -> None:
    op.drop_index('uq_dead_letter_open_review', table_name='outbox_dead_letter_review')
    op.drop_table('outbox_dead_letter_review')
