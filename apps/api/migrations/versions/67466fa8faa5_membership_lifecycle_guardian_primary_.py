"""membership lifecycle, guardian primary/revoke, merge review

Revision ID: 67466fa8faa5
Revises: 3fed03b597f7
Create Date: 2026-07-20 20:10:09.444875
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '67466fa8faa5'
down_revision: str | None = '3fed03b597f7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Guardian primary-contact flag (§25). Backfill existing rows to false, then
    # drop the server default so the column matches the model (Python-side default).
    op.add_column(
        'guardian_organization_access',
        sa.Column('is_primary_contact', sa.Boolean(), nullable=False,
                  server_default=sa.text('false')),
    )
    op.alter_column('guardian_organization_access', 'is_primary_contact', server_default=None)
    op.create_index(
        'uq_guardian_primary_contact', 'guardian_organization_access',
        ['organization_id', 'child_person_id'], unique=True,
        postgresql_where=sa.text('is_primary_contact'),
    )

    # School-local member data (§8/§9/§10) — nullable, unique code within the org.
    op.add_column(
        'organization_membership', sa.Column('local_member_code', sa.String(length=60),
                                             nullable=True))
    op.add_column('organization_membership', sa.Column('admin_note', sa.Text(), nullable=True))
    op.create_index(
        'uq_org_local_member_code', 'organization_membership',
        ['organization_id', 'local_member_code'], unique=True,
        postgresql_where=sa.text('local_member_code IS NOT NULL'),
    )

    # Duplicate-review case fields (§13–15). person_merge_record is append-only and
    # empty pre-migration, so organization_id may be added NOT NULL directly.
    op.add_column('person_merge_record', sa.Column('organization_id', sa.String(length=64),
                                                   nullable=False))
    op.add_column(
        'person_merge_record',
        sa.Column('status',
                  sa.Enum('FLAGGED', 'MERGED', 'DISMISSED', name='personmergestatus',
                          native_enum=False, length=40),
                  nullable=False, server_default=sa.text("'FLAGGED'")),
    )
    op.alter_column('person_merge_record', 'status', server_default=None)
    op.add_column('person_merge_record', sa.Column('flagged_by_person_id', sa.String(length=64),
                                                   nullable=True))
    op.create_foreign_key(
        'fk_person_merge_record_organization', 'person_merge_record', 'organization',
        ['organization_id'], ['id'], ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint('fk_person_merge_record_organization', 'person_merge_record',
                       type_='foreignkey')
    op.drop_column('person_merge_record', 'flagged_by_person_id')
    op.drop_column('person_merge_record', 'status')
    op.drop_column('person_merge_record', 'organization_id')
    op.drop_index('uq_org_local_member_code', table_name='organization_membership',
                  postgresql_where=sa.text('local_member_code IS NOT NULL'))
    op.drop_column('organization_membership', 'admin_note')
    op.drop_column('organization_membership', 'local_member_code')
    op.drop_index('uq_guardian_primary_contact', table_name='guardian_organization_access',
                  postgresql_where=sa.text('is_primary_contact'))
    op.drop_column('guardian_organization_access', 'is_primary_contact')
