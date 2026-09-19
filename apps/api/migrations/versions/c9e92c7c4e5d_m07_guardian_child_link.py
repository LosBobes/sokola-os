"""M07 guardian child link

M07 §2.3.

The first M07 table: one school's verified link between an adult and a child.

It goes in **alongside** `guardian_relationship` and `guardian_school_access`,
which stay exactly as they are. Those two have 107 readers between them across
identity, the parent router, communications and events (F-31), so the
replacement is staged — new table first, readers moved domain by domain, the
old ones dropped only once nothing looks at them. Nothing reads this table
yet; that is deliberate, and it is what makes this migration safe to deploy on
its own.

No data is copied from the old tables here either. §7.10 forbids guessing which
school an ambiguous legacy row belongs to, and `guardian_relationship` is
global — it has no school at all. Every existing row is therefore ambiguous by
construction, so a backfill would have to invent the one fact the contract says
may not be invented. That is a separate, operator-directed migration.

Two constraints are worth reading twice:

* the **triple foreign keys** carry the membership *type*, not just the tenant.
  `(school_id, membership_id, membership_type) -> school_membership
  (school_id, id, membership_type)`, against M06's
  `uq_school_membership_tenant_type`. Without the type in the key, a guardian
  link could name the same person's STAFF membership and read as perfectly
  valid. The two denormalized type columns exist only to make the key
  expressible and are pinned by CHECK to the single value each may hold.
* `uq_guardian_child_link_open` is **partial**, over
  `status IN ('PENDING_VERIFICATION', 'ACTIVE')`. §5.3 makes a fresh check a
  new row with a new id rather than a revived one, so REJECTED and REVOKED rows
  are the history and several per pair are expected. A total unique key would
  make the second check of a pair unrecordable. It is scoped by `school_id`
  because two schools reaching different conclusions about the same adult and
  child is the point, not a conflict — the defect F-31 names in the existing
  global `UNIQUE (guardian_person_id, child_person_id)`.

The conditional rules (§2.3) are CHECK constraints rather than service code:
each decided status owns its timestamp, a decided status names its decider, and
a refusal or revocation says why. §5.3's *distinct approver* rule is not here,
because the database cannot know whether two account ids belong to the same
human — that one is enforced where the decision is made.

Revision ID: c9e92c7c4e5d
Revises: 70ef87173323
Create Date: 2026-09-19 19:11:05.829368
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'c9e92c7c4e5d'
down_revision: str | None = '70ef87173323'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('guardian_child_link',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('school_id', sa.String(length=64), nullable=False),
    sa.Column('guardian_person_id', sa.String(length=64), nullable=False),
    sa.Column('child_person_id', sa.String(length=64), nullable=False),
    sa.Column('guardian_school_membership_id', sa.String(length=64), nullable=False),
    sa.Column('child_school_membership_id', sa.String(length=64), nullable=False),
    sa.Column('guardian_membership_type', sa.String(length=40), nullable=False),
    sa.Column('child_membership_type', sa.String(length=40), nullable=False),
    sa.Column('relationship_kind', sa.Enum('PARENT', 'LEGAL_GUARDIAN', 'AUTHORIZED_CAREGIVER', 'OTHER_VERIFIED', name='relationshipkind', native_enum=False, length=40), nullable=False),
    sa.Column('status', sa.Enum('PENDING_VERIFICATION', 'ACTIVE', 'REJECTED', 'REVOKED', name='linkstatus', native_enum=False, length=40), nullable=False),
    sa.Column('requested_by_account_id', sa.String(length=64), nullable=False),
    sa.Column('requested_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('rejected_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('decision_by_account_id', sa.String(length=64), nullable=True),
    sa.Column('decision_reason_code', sa.String(length=64), nullable=True),
    sa.Column('version', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(status = 'ACTIVE') = (activated_at IS NOT NULL)", name='ck_guardian_child_link_activated_at'),
    sa.CheckConstraint("(status = 'PENDING_VERIFICATION') = (decision_by_account_id IS NULL)", name='ck_guardian_child_link_decider'),
    sa.CheckConstraint("(status = 'REJECTED') = (rejected_at IS NOT NULL)", name='ck_guardian_child_link_rejected_at'),
    sa.CheckConstraint("(status = 'REVOKED') = (revoked_at IS NOT NULL)", name='ck_guardian_child_link_revoked_at'),
    sa.CheckConstraint("(status IN ('REJECTED', 'REVOKED')) = (decision_reason_code IS NOT NULL)", name='ck_guardian_child_link_decision_reason'),
    sa.CheckConstraint("child_membership_type = 'PARTICIPANT'", name='ck_guardian_child_link_child_type'),
    sa.CheckConstraint("guardian_membership_type = 'GUARDIAN'", name='ck_guardian_child_link_guardian_type'),
    sa.CheckConstraint('guardian_person_id <> child_person_id', name='ck_guardian_child_link_distinct_people'),
    sa.CheckConstraint('version >= 1', name='ck_guardian_child_link_version'),
    sa.ForeignKeyConstraint(['child_person_id'], ['person.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['guardian_person_id'], ['person.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['school_id', 'child_school_membership_id', 'child_membership_type'], ['school_membership.school_id', 'school_membership.id', 'school_membership.membership_type'], name='fk_guardian_child_link_child_membership', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['school_id', 'guardian_school_membership_id', 'guardian_membership_type'], ['school_membership.school_id', 'school_membership.id', 'school_membership.membership_type'], name='fk_guardian_child_link_guardian_membership', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['school_id'], ['school.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('school_id', 'id', name='uq_guardian_child_link_tenant')
    )
    op.create_index('ix_guardian_child_link_child', 'guardian_child_link', ['school_id', 'child_person_id', 'status'], unique=False)
    op.create_index('ix_guardian_child_link_guardian', 'guardian_child_link', ['school_id', 'guardian_person_id', 'status'], unique=False)
    op.create_index('uq_guardian_child_link_open', 'guardian_child_link', ['school_id', 'guardian_person_id', 'child_person_id'], unique=True, postgresql_where=sa.text("status IN ('PENDING_VERIFICATION', 'ACTIVE')"))


def downgrade() -> None:
    op.drop_index('uq_guardian_child_link_open', table_name='guardian_child_link', postgresql_where=sa.text("status IN ('PENDING_VERIFICATION', 'ACTIVE')"))
    op.drop_index('ix_guardian_child_link_guardian', table_name='guardian_child_link')
    op.drop_index('ix_guardian_child_link_child', table_name='guardian_child_link')
    op.drop_table('guardian_child_link')
