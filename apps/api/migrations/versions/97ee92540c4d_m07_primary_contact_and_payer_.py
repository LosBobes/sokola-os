"""M07 primary contact and payer designations

M07 §2.6, §2.7.

The last two of §2's seven entities. With these, M07's schema is complete —
though still unread by anything, as the rest of M07 is.

Both are **history rows**. Replacing a primary contact writes a new row and
marks the old one `SUPERSEDED`; it never updates one row in place. Six months
later "who was the primary contact when this happened" has an answer, and an
in-place update would have made that question unanswerable — the one question
an incident actually raises.

Two terminal statuses, because the two ways a primacy ends mean different
things. `SUPERSEDED` is an ordinary replacement: someone else is primary now.
`REVOKED` is the primacy withdrawn with nothing in its place, which §3.1 says
happens the moment the underlying link is revoked. Collapsing them would lose
the difference between "the other parent is primary now" and "this child has no
primary contact at present" — and §3.1 is explicit that the latter is allowed:
"primarni kontakt može privremeno biti nula, nikad stale".

**The foreign keys name the child.** §2.6 requires the link to be "za isto
dete/školu", and this migration adds
`UNIQUE(school_id, id, child_person_id)` to both link tables so the designation
can say so as part of the reference:

```sql
FOREIGN KEY (school_id, guardian_child_link_id, child_person_id)
  REFERENCES guardian_child_link (school_id, id, child_person_id)
```

With only `(school_id, id)` in the key, a designation could name a perfectly
valid link belonging to a *different* child in the same school — designating
the school's first call about one child to an adult verified only for another.
That the two children share a school is exactly what would make such a row
plausible enough to survive review. The two added unique constraints add no
uniqueness (`id` is already the primary key); they exist to make the reference
expressible.

Separate tables rather than one with a discriminator, unlike
`relationship_verification_record`. There the contract gives one entity with a
`link_kind`; here §2.6 and §2.7 are two entities, and the reason shows in the
keys: each child may have one active primary contact **and** one active primary
payer, independently. A shared table would need the kind inside the unique
index to express that — the discriminator earning nothing and costing a column.

What the database cannot do is require the referenced link to be ACTIVE, since
status changes after the row is written. §3.10 puts that where it belongs,
making revocation of a link and closure of every designation referencing it one
transaction. `ON DELETE CASCADE` is the backstop for the case where a link goes
entirely: a designation pointing at nothing is not a record of anything.

§3.8 and §3.9 draw the line neither table may cross. A primary contact "je samo
redosled službene komunikacije škole; ne daje dodatne child permissions", and a
primary payer "ne određuje procenat odgovornosti" — M12 may split an obligation
across several ACTIVE payer links, and nothing here says how.

Revision ID: 97ee92540c4d
Revises: 1a3d585a311b
Create Date: 2026-09-19 20:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '97ee92540c4d'
down_revision: str | None = '1a3d585a311b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The composite targets go in first: the designation tables' foreign
    # keys reference them, and Postgres refuses a key with no matching
    # unique constraint. Autogenerate emitted these last.
    op.create_unique_constraint('uq_guardian_child_link_tenant_child', 'guardian_child_link', ['school_id', 'id', 'child_person_id'])
    op.create_unique_constraint('uq_payer_child_link_tenant_child', 'payer_child_link', ['school_id', 'id', 'child_person_id'])
    op.create_table('primary_guardian_contact_designation',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('school_id', sa.String(length=64), nullable=False),
    sa.Column('child_person_id', sa.String(length=64), nullable=False),
    sa.Column('guardian_child_link_id', sa.String(length=64), nullable=False),
    sa.Column('status', sa.Enum('ACTIVE', 'SUPERSEDED', 'REVOKED', name='designationstatus', native_enum=False, length=40), nullable=False),
    sa.Column('designated_by_account_id', sa.String(length=64), nullable=False),
    sa.Column('designated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('end_reason_code', sa.String(length=64), nullable=True),
    sa.Column('version', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(status <> 'ACTIVE') = (end_reason_code IS NOT NULL)", name='ck_primary_guardian_contact_end_reason'),
    sa.CheckConstraint("(status <> 'ACTIVE') = (ended_at IS NOT NULL)", name='ck_primary_guardian_contact_ended_at'),
    sa.CheckConstraint('version >= 1', name='ck_primary_guardian_contact_version'),
    sa.ForeignKeyConstraint(['school_id', 'guardian_child_link_id', 'child_person_id'], ['guardian_child_link.school_id', 'guardian_child_link.id', 'guardian_child_link.child_person_id'], name='fk_primary_guardian_contact_link', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['school_id'], ['school.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('school_id', 'id', name='uq_primary_guardian_contact_tenant')
    )
    op.create_index('ix_primary_guardian_contact_child', 'primary_guardian_contact_designation', ['school_id', 'child_person_id', 'status'], unique=False)
    op.create_index('uq_primary_guardian_contact_active', 'primary_guardian_contact_designation', ['school_id', 'child_person_id'], unique=True, postgresql_where=sa.text("status = 'ACTIVE'"))
    op.create_table('primary_payer_designation',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('school_id', sa.String(length=64), nullable=False),
    sa.Column('child_person_id', sa.String(length=64), nullable=False),
    sa.Column('payer_child_link_id', sa.String(length=64), nullable=False),
    sa.Column('status', sa.Enum('ACTIVE', 'SUPERSEDED', 'REVOKED', name='designationstatus', native_enum=False, length=40), nullable=False),
    sa.Column('designated_by_account_id', sa.String(length=64), nullable=False),
    sa.Column('designated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('end_reason_code', sa.String(length=64), nullable=True),
    sa.Column('version', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(status <> 'ACTIVE') = (end_reason_code IS NOT NULL)", name='ck_primary_payer_end_reason'),
    sa.CheckConstraint("(status <> 'ACTIVE') = (ended_at IS NOT NULL)", name='ck_primary_payer_ended_at'),
    sa.CheckConstraint('version >= 1', name='ck_primary_payer_version'),
    sa.ForeignKeyConstraint(['school_id', 'payer_child_link_id', 'child_person_id'], ['payer_child_link.school_id', 'payer_child_link.id', 'payer_child_link.child_person_id'], name='fk_primary_payer_link', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['school_id'], ['school.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('school_id', 'id', name='uq_primary_payer_tenant')
    )
    op.create_index('ix_primary_payer_child', 'primary_payer_designation', ['school_id', 'child_person_id', 'status'], unique=False)
    op.create_index('uq_primary_payer_active', 'primary_payer_designation', ['school_id', 'child_person_id'], unique=True, postgresql_where=sa.text("status = 'ACTIVE'"))


def downgrade() -> None:
    op.drop_index('uq_primary_payer_active', table_name='primary_payer_designation', postgresql_where=sa.text("status = 'ACTIVE'"))
    op.drop_index('ix_primary_payer_child', table_name='primary_payer_designation')
    op.drop_table('primary_payer_designation')
    op.drop_index('uq_primary_guardian_contact_active', table_name='primary_guardian_contact_designation', postgresql_where=sa.text("status = 'ACTIVE'"))
    op.drop_index('ix_primary_guardian_contact_child', table_name='primary_guardian_contact_designation')
    op.drop_table('primary_guardian_contact_designation')
    # The composite targets come out last, mirroring upgrade: while the
    # designation tables exist their foreign keys depend on these, and
    # Postgres refuses to drop a constraint a key still needs.
    op.drop_constraint('uq_payer_child_link_tenant_child', 'payer_child_link', type_='unique')
    op.drop_constraint('uq_guardian_child_link_tenant_child', 'guardian_child_link', type_='unique')
