"""M07 family and family membership

M07 §2.1, §2.2.

Two more M07 tables, and like `guardian_child_link` nothing reads them yet.

`family` is almost empty on purpose. §3.1 says a family grouping, a membership
in it, a guardian link, a payer link and primacy are **five separate facts**,
none derived from a surname, an email, an address or another table. So the row
holds a status, who created it, and an optional internal label the school may
set for its own lists — and §2.1 is explicit that the label "ne koristi se za
identitet": not a key, not a search handle, not a way to reach a family you
were not already allowed to see.

It grants nothing. Two adults in one family see nothing of each other because
of it, and §3.2 says even a shared child leaves two families invisible to one
another. Whether an adult may act for a child is `guardian_child_link`.

`family_membership` carries the interesting key:

```sql
FOREIGN KEY (school_id, school_membership_id, person_id)
  REFERENCES school_membership (school_id, id, person_id)
```

against M06's `uq_school_membership_tenant_person`. Naming the **person** as
part of the reference is what stops `person_id` being a denormalized copy that
can drift: the database will not hold a row whose `person_id` disagrees with
the membership sitting beside it. `ON DELETE RESTRICT` for the same reason the
guardian link uses it — M06 ends a membership with a `TERMINATED` status, not
by deleting the row, and a delete that silently took the household record with
it would be tidying away evidence.

`uq_family_membership_open` is partial over `status = 'ACTIVE'`, and scoped to
one family. §2.2 says the same person may belong to several families in one
school — separated households are the normal case — and §5.2 makes a return a
new row, so a family someone left and rejoined holds two.

**Not enforced here, deliberately:** §3.13's rule that a family may only be
archived when it has no ACTIVE membership, no guardian or payer link resting
solely on it, and no open M12 obligation. That check reads across modules and
the contract routes it through application orchestration specifically to avoid
an M12 -> M07 cycle. A CHECK constraint cannot see any of it, and a trigger
that tried would be that cycle in the database instead of the code.

Revision ID: b3756f18889e
Revises: c9e92c7c4e5d
Create Date: 2026-09-19 19:26:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = 'b3756f18889e'
down_revision: str | None = 'c9e92c7c4e5d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('family',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('school_id', sa.String(length=64), nullable=False),
    sa.Column('display_label', sa.String(length=100), nullable=True),
    sa.Column('status', sa.Enum('ACTIVE', 'ARCHIVED', name='familystatus', native_enum=False, length=40), nullable=False),
    sa.Column('created_by_account_id', sa.String(length=64), nullable=False),
    sa.Column('archive_reason_code', sa.String(length=64), nullable=True),
    sa.Column('version', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(status = 'ARCHIVED') = (archive_reason_code IS NOT NULL)", name='ck_family_archive_reason'),
    sa.CheckConstraint('display_label IS NULL OR length(display_label) BETWEEN 1 AND 100', name='ck_family_display_label_length'),
    sa.CheckConstraint('version >= 1', name='ck_family_version'),
    sa.ForeignKeyConstraint(['school_id'], ['school.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('school_id', 'id', name='uq_family_tenant')
    )
    op.create_index('ix_family_school_status', 'family', ['school_id', 'status'], unique=False)
    op.create_table('family_membership',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('school_id', sa.String(length=64), nullable=False),
    sa.Column('family_id', sa.String(length=64), nullable=False),
    sa.Column('person_id', sa.String(length=64), nullable=False),
    sa.Column('school_membership_id', sa.String(length=64), nullable=False),
    sa.Column('member_kind', sa.Enum('ADULT', 'DEPENDENT', name='memberkind', native_enum=False, length=40), nullable=False),
    sa.Column('status', sa.Enum('ACTIVE', 'ENDED', name='familymembershipstatus', native_enum=False, length=40), nullable=False),
    sa.Column('effective_from', sa.Date(), nullable=False),
    sa.Column('effective_until', sa.Date(), nullable=True),
    sa.Column('end_reason_code', sa.String(length=64), nullable=True),
    sa.Column('version', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(status = 'ENDED') = (effective_until IS NOT NULL)", name='ck_family_membership_effective_until'),
    sa.CheckConstraint("(status = 'ENDED') = (end_reason_code IS NOT NULL)", name='ck_family_membership_end_reason'),
    sa.CheckConstraint('effective_until IS NULL OR effective_until >= effective_from', name='ck_family_membership_period'),
    sa.CheckConstraint('version >= 1', name='ck_family_membership_version'),
    sa.ForeignKeyConstraint(['person_id'], ['person.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['school_id', 'family_id'], ['family.school_id', 'family.id'], name='fk_family_membership_family', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['school_id', 'school_membership_id', 'person_id'], ['school_membership.school_id', 'school_membership.id', 'school_membership.person_id'], name='fk_family_membership_school_membership', ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['school_id'], ['school.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('school_id', 'id', name='uq_family_membership_tenant')
    )
    op.create_index('ix_family_membership_person', 'family_membership', ['school_id', 'person_id', 'status'], unique=False)
    op.create_index('uq_family_membership_open', 'family_membership', ['school_id', 'family_id', 'person_id'], unique=True, postgresql_where=sa.text("status = 'ACTIVE'"))


def downgrade() -> None:
    op.drop_index('uq_family_membership_open', table_name='family_membership', postgresql_where=sa.text("status = 'ACTIVE'"))
    op.drop_index('ix_family_membership_person', table_name='family_membership')
    op.drop_table('family_membership')
    op.drop_index('ix_family_school_status', table_name='family')
    op.drop_table('family')
