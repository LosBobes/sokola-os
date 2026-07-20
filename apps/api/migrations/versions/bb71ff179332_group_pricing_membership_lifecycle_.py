"""group pricing, membership lifecycle, structure links

Revision ID: bb71ff179332
Revises: 67466fa8faa5
Create Date: 2026-07-20 20:50:10.058064
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'bb71ff179332'
down_revision: str | None = '67466fa8faa5'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PRD 04 M4 — nullable links into the structure domain (SET NULL so
    # archiving a program/location never destroys group history).
    op.add_column('group', sa.Column('program_id', sa.String(length=64), nullable=True))
    op.add_column('group', sa.Column('location_id', sa.String(length=64), nullable=True))
    op.create_foreign_key(
        'fk_group_program', 'group', 'structure_program',
        ['program_id'], ['id'], ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_group_location', 'group', 'structure_location',
        ['location_id'], ['id'], ondelete='SET NULL',
    )

    # PRD 04 M1 — group list price, in the organization's minor currency unit.
    op.add_column(
        'group', sa.Column('base_monthly_price_minor', sa.Integer(), nullable=True)
    )

    # PRD 04 M2 — membership lifecycle status, replacing the ended_at-only proxy.
    # Backfill existing rows to ACTIVE, then drop the server default so the
    # column matches the model (Python-side default).
    op.add_column(
        'group_membership',
        sa.Column(
            'status',
            sa.Enum('ACTIVE', 'SUSPENDED', 'ENDED', name='groupmembershipstatus',
                    native_enum=False, length=40),
            nullable=False, server_default=sa.text("'ACTIVE'"),
        ),
    )
    op.alter_column('group_membership', 'status', server_default=None)

    # PRD 04 M1 — absolute per-member discount, in minor currency units.
    op.add_column(
        'group_membership',
        sa.Column('discount_minor', sa.Integer(), nullable=False, server_default=sa.text('0')),
    )
    op.alter_column('group_membership', 'discount_minor', server_default=None)

    # Replace the plain (group_id, person_id) unique constraint with a partial
    # unique index over non-ENDED rows only, so a person can rejoin a group
    # they previously left as a fresh membership row (M2's `end` is terminal).
    op.drop_constraint('uq_group_membership', 'group_membership', type_='unique')
    op.create_index(
        'uq_group_membership_active', 'group_membership', ['group_id', 'person_id'],
        unique=True, postgresql_where=sa.text("status != 'ENDED'"),
    )


def downgrade() -> None:
    op.drop_index(
        'uq_group_membership_active', table_name='group_membership',
        postgresql_where=sa.text("status != 'ENDED'"),
    )
    op.create_unique_constraint(
        'uq_group_membership', 'group_membership', ['group_id', 'person_id']
    )
    op.drop_column('group_membership', 'discount_minor')
    op.drop_column('group_membership', 'status')
    op.drop_column('group', 'base_monthly_price_minor')
    op.drop_constraint('fk_group_location', 'group', type_='foreignkey')
    op.drop_constraint('fk_group_program', 'group', type_='foreignkey')
    op.drop_column('group', 'location_id')
    op.drop_column('group', 'program_id')
