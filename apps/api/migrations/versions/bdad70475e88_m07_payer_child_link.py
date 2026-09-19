"""M07 payer child link

M07 §2.5.

The table whose *absence* was the sharpest gap in this repo (F-32): until now
the only way to record that an adult pays for a child was to make them that
child's guardian, which handed them the child's attendance, documents, health
records and profile as a side effect of a billing arrangement.

§3.7 forbids exactly that. A payer link grants access to "samo M12 finansijskim
operacijama koje izričito prihvataju `PAYER_CHILD_LINK` basis", and M05 §3.2
point 9 says a `PAYER` subject basis "nikad ne daje
attendance/document/health/profile/guardian pravo". Nothing in this migration
enforces that — a table cannot stop a reader joining to it. What it does is
make the financial link **expressible on its own**, so the readers that must
not see child data have a basis to resolve that is not guardianship. The guard
belongs to M05, and §7.2's `PayerSubjectBasisPort` is required to answer
`FINANCE_ONLY` with no guardian implication.

Nothing reads this table yet, as with the rest of M07 so far.

Two shapes differ from `guardian_child_link`, both on purpose:

* the payer's membership type is a **pair** — `CONTACT` or `GUARDIAN` — where
  the guardian link pins one value. A payer need not be a guardian; that is the
  entity's whole reason for existing, and a school records a non-guardian payer
  as a `CONTACT`. The triple foreign key still requires the recorded type to be
  the membership's real type, and a CHECK requires it to be one of the two. One
  half alone would let a `STAFF` membership through.
* there is **no distinct-people CHECK**. §2.3 says of the guardian link "ne sme
  biti isti ID"; §2.5 says nothing of the kind, and the asymmetry reads as
  intentional — an adult who trains at the school and pays their own fees holds
  both a `PARTICIPANT` membership and a `CONTACT` one, and both sides of the
  row would be satisfied. Adding the constraint would refuse a case the
  contract leaves open, so it is recorded here rather than decided.

`family_id` is mandatory per §2.5 and its foreign key is `RESTRICT`, not
`CASCADE`: §3.13 makes an open link a *blocker* on archiving a family, so the
database must not quietly remove the evidence that the blocker exists. Which
family, and whether both people are ACTIVE in it, stays a service rule — §3.1
refuses a payer in family A for a child in family B with
`M07_PAYER_BASIS_INVALID` unless the sponsor process verified it, and checking
that needs two `family_membership` rows, which a CHECK cannot read.

The partial unique names the **payer**, not the child alone: §2.5 allows
several different ACTIVE payers for one child, and M12 decides how an
obligation is split.

Revision ID: bdad70475e88
Revises: b3756f18889e
Create Date: 2026-09-19 19:40:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'bdad70475e88'
down_revision: str | None = 'b3756f18889e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('payer_child_link',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('school_id', sa.String(length=64), nullable=False),
    sa.Column('payer_person_id', sa.String(length=64), nullable=False),
    sa.Column('child_person_id', sa.String(length=64), nullable=False),
    sa.Column('payer_school_membership_id', sa.String(length=64), nullable=False),
    sa.Column('child_school_membership_id', sa.String(length=64), nullable=False),
    sa.Column('payer_membership_type', sa.String(length=40), nullable=False),
    sa.Column('child_membership_type', sa.String(length=40), nullable=False),
    sa.Column('family_id', sa.String(length=64), nullable=False),
    sa.Column('basis_kind', sa.Enum('FAMILY_ADULT', 'SPONSOR_VERIFIED', 'OTHER_VERIFIED', name='payerbasiskind', native_enum=False, length=40), nullable=False),
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
    sa.CheckConstraint("(status = 'ACTIVE') = (activated_at IS NOT NULL)", name='ck_payer_child_link_activated_at'),
    sa.CheckConstraint("(status = 'PENDING_VERIFICATION') = (decision_by_account_id IS NULL)", name='ck_payer_child_link_decider'),
    sa.CheckConstraint("(status = 'REJECTED') = (rejected_at IS NOT NULL)", name='ck_payer_child_link_rejected_at'),
    sa.CheckConstraint("(status = 'REVOKED') = (revoked_at IS NOT NULL)", name='ck_payer_child_link_revoked_at'),
    sa.CheckConstraint("(status IN ('REJECTED', 'REVOKED')) = (decision_reason_code IS NOT NULL)", name='ck_payer_child_link_decision_reason'),
    sa.CheckConstraint("child_membership_type = 'PARTICIPANT'", name='ck_payer_child_link_child_type'),
    sa.CheckConstraint("payer_membership_type IN ('CONTACT', 'GUARDIAN')", name='ck_payer_child_link_payer_type'),
    sa.CheckConstraint('version >= 1', name='ck_payer_child_link_version'),
    sa.ForeignKeyConstraint(['child_person_id'], ['person.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['payer_person_id'], ['person.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['school_id', 'child_school_membership_id', 'child_membership_type'], ['school_membership.school_id', 'school_membership.id', 'school_membership.membership_type'], name='fk_payer_child_link_child_membership', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['school_id', 'family_id'], ['family.school_id', 'family.id'], name='fk_payer_child_link_family', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['school_id', 'payer_school_membership_id', 'payer_membership_type'], ['school_membership.school_id', 'school_membership.id', 'school_membership.membership_type'], name='fk_payer_child_link_payer_membership', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['school_id'], ['school.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('school_id', 'id', name='uq_payer_child_link_tenant')
    )
    op.create_index('ix_payer_child_link_child', 'payer_child_link', ['school_id', 'child_person_id', 'status'], unique=False)
    op.create_index('ix_payer_child_link_payer', 'payer_child_link', ['school_id', 'payer_person_id', 'status'], unique=False)
    op.create_index('uq_payer_child_link_open', 'payer_child_link', ['school_id', 'payer_person_id', 'child_person_id'], unique=True, postgresql_where=sa.text("status IN ('PENDING_VERIFICATION', 'ACTIVE')"))


def downgrade() -> None:
    op.drop_index('uq_payer_child_link_open', table_name='payer_child_link', postgresql_where=sa.text("status IN ('PENDING_VERIFICATION', 'ACTIVE')"))
    op.drop_index('ix_payer_child_link_payer', table_name='payer_child_link')
    op.drop_index('ix_payer_child_link_child', table_name='payer_child_link')
    op.drop_table('payer_child_link')
