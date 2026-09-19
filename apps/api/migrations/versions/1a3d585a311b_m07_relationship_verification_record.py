"""M07 relationship verification record

M07 §2.4.

The immutable proof that a school checked a link before activating it. §3.5
makes this and the activation one transaction — a link becomes ACTIVE "i tačno
jedan odgovarajući immutable verification record nastaju atomarno tek posle
school approval-a" — so a link that is ACTIVE with no record is an activation
nobody can account for afterwards. That is the state this table exists to make
impossible.

One table with a `link_kind` discriminator rather than one per link type. The
evidence has the same shape either way: a method, a moment, an authorized
verifier, a policy version. What it *proves* differs, which is what the
discriminator carries. Keeping them together is what lets §5.3's "exactly one
activation proof per link" be a single pair of partial unique indexes instead
of an invariant maintained in two places that can drift apart.

**Nothing here stores what was seen.** §2.4 is explicit about the document
case: "čuva se samo činjenica provere i opcioni keyed case digest; nema slike,
broja ili običnog hash-a dokumenta u M07." A school that inspected an identity
document records *that* it did, under a method code.

`evidence_reference_digest` is a **keyed** HMAC, and the key is the whole
point. §2.4 forbids "broj dokumenta, ime ili hash niskoentropijskog PII-ja",
and those two clauses are one rule: a plain SHA-256 of a national ID number is
the number. Those formats are short, structured and often checksummed, so the
space a brute-forcer walks is small enough to walk. The key removes that, which
leaves the column useful for the one thing §2.4 wants — "is this the same case
reference I filed before" — and useless for recovering what it was made from.
`school_id` is mixed into the message too, so one reference filed at two
schools does not digest alike and become a cross-tenant correlation handle in a
module whose §4 works hard to keep schools from learning about one another.
The key derives from `session_secret` under its own domain separator, matching
what the rate limiter and the tenant-context etag already do, rather than
adding a deployment variable whose absence would be discovered in production.
The CHECK requiring 64 hex characters is what stops the column quietly
accepting a raw reference someone forgot to hash.

Two CHECKs guard the discriminator and both are needed. "Exactly one link"
alone would let a GUARDIAN_CHILD record hold a payer link; the agreement clause
alone would let a record hold both or neither.

Not enforced here: §2.4's rule that the verifier may not be the account of the
person whose link is being checked (`M07_SELF_VERIFICATION_FORBIDDEN`). The
database cannot know which human an account belongs to — the same reason the
guardian link's distinct-approver rule lives in the service.

Nothing reads this table yet, as with the rest of M07 so far.

Revision ID: 1a3d585a311b
Revises: bdad70475e88
Create Date: 2026-09-19 19:52:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '1a3d585a311b'
down_revision: str | None = 'bdad70475e88'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('relationship_verification_record',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('school_id', sa.String(length=64), nullable=False),
    sa.Column('link_kind', sa.Enum('GUARDIAN_CHILD', 'PAYER_CHILD', name='linkkind', native_enum=False, length=40), nullable=False),
    sa.Column('guardian_child_link_id', sa.String(length=64), nullable=True),
    sa.Column('payer_child_link_id', sa.String(length=64), nullable=True),
    sa.Column('verification_method', sa.Enum('SCHOOL_RECORD', 'IN_PERSON_DOCUMENT_CHECK', 'SIGNED_DECLARATION', 'MIGRATION_VERIFIED', name='verificationmethod', native_enum=False, length=40), nullable=False),
    sa.Column('evidence_reference_digest', sa.String(length=64), nullable=True),
    sa.Column('verified_by_account_id', sa.String(length=64), nullable=False),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('policy_version', sa.String(length=64), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("(link_kind = 'GUARDIAN_CHILD') = (guardian_child_link_id IS NOT NULL)", name='ck_relationship_verification_link_kind'),
    sa.CheckConstraint("evidence_reference_digest IS NULL OR evidence_reference_digest ~ '^[0-9a-f]{64}$'", name='ck_relationship_verification_digest_shape'),
    sa.CheckConstraint('(guardian_child_link_id IS NOT NULL)::int + (payer_child_link_id IS NOT NULL)::int = 1', name='ck_relationship_verification_one_link'),
    sa.ForeignKeyConstraint(['school_id', 'guardian_child_link_id'], ['guardian_child_link.school_id', 'guardian_child_link.id'], name='fk_relationship_verification_guardian_link', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['school_id', 'payer_child_link_id'], ['payer_child_link.school_id', 'payer_child_link.id'], name='fk_relationship_verification_payer_link', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['school_id'], ['school.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('school_id', 'id', name='uq_relationship_verification_record_tenant')
    )
    op.create_index('ix_relationship_verification_school', 'relationship_verification_record', ['school_id', 'link_kind', 'verified_at'], unique=False)
    op.create_index('uq_relationship_verification_guardian_link', 'relationship_verification_record', ['guardian_child_link_id'], unique=True, postgresql_where=sa.text('guardian_child_link_id IS NOT NULL'))
    op.create_index('uq_relationship_verification_payer_link', 'relationship_verification_record', ['payer_child_link_id'], unique=True, postgresql_where=sa.text('payer_child_link_id IS NOT NULL'))


def downgrade() -> None:
    op.drop_index('uq_relationship_verification_payer_link', table_name='relationship_verification_record', postgresql_where=sa.text('payer_child_link_id IS NOT NULL'))
    op.drop_index('uq_relationship_verification_guardian_link', table_name='relationship_verification_record', postgresql_where=sa.text('guardian_child_link_id IS NOT NULL'))
    op.drop_index('ix_relationship_verification_school', table_name='relationship_verification_record')
    op.drop_table('relationship_verification_record')
