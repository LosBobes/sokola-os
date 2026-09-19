"""M06 person contact protection and the school person profile

M06 §2.1 and §2.4.

`person` gains a birth date, field-encrypted contact columns with their blind
indexes, a dedupe status and a version. The contact columns are *contact*, never
a login key: `auth_identifier` remains what a sign-in resolves through, and the
two hold differently-protected values on purpose.

The blind-index columns are indexed but **not unique**. §3.4 is explicit that a
shared email is a candidate flag and never an auto-link: two real people do share
a family address, and a unique constraint here would refuse the second of them.

`school_person_profile` is new: one row per (school, person), the thing that
makes a global Person visible inside one tenant. It carries
UNIQUE(school_id, id, person_id) so other modules can foreign-key against it
tenant-safely — which is what M04 §2.6 requires of an owner nomination, and what
finding F-14 was standing in for. The nomination's composite FK moves from
`school_membership` to this table here; the constraint *shape* is unchanged, so
the guarantee it carried is not weakened for an instant.

Backfill: every distinct (school_id, person_id) that has a membership gets a
profile, with no local code and no note — the school already knows these people,
and the profile records exactly that and nothing invented. Profiles are created
before the FK is repointed, so the nomination constraint is never briefly
unsatisfiable.

Revision ID: d2a95e13c7f4
Revises: c1f4a86d39b7
Create Date: 2026-09-19 10:45:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from ulid import ULID

revision: str = 'd2a95e13c7f4'
down_revision: str | None = 'c1f4a86d39b7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEDUPE_STATUSES = "('CLEAR', 'POTENTIAL_DUPLICATE', 'REVIEWED_DISTINCT', 'MERGED')"


def _new_id(prefix: str) -> str:
    return f"{prefix}_{ULID()}"


def upgrade() -> None:
    bind = op.get_bind()

    # --- Person (§2.1) ---
    op.add_column("person", sa.Column("birth_date", sa.Date(), nullable=True))
    op.add_column("person", sa.Column("email_ciphertext", sa.Text(), nullable=True))
    op.add_column("person", sa.Column("email_blind_index", sa.String(64), nullable=True))
    op.add_column("person", sa.Column("email_blind_index_key_version", sa.BigInteger(), nullable=True))
    op.add_column("person", sa.Column("phone_ciphertext", sa.Text(), nullable=True))
    op.add_column("person", sa.Column("phone_blind_index", sa.String(64), nullable=True))
    op.add_column("person", sa.Column("phone_blind_index_key_version", sa.BigInteger(), nullable=True))
    op.add_column("person", sa.Column("dedupe_status", sa.String(40), nullable=True))
    op.add_column("person", sa.Column("merged_into_person_id", sa.String(64), nullable=True))
    op.add_column("person", sa.Column("version", sa.BigInteger(), nullable=True))

    # Existing people have no recorded contact, so no candidate has been looked
    # for: CLEAR is the honest value, not an assertion that they are unique.
    op.execute("UPDATE person SET dedupe_status = 'CLEAR', version = 1")
    op.alter_column("person", "dedupe_status", nullable=False)
    op.alter_column("person", "version", nullable=False)

    for name, expression in (
        ("ck_person_email_pair", "(email_ciphertext IS NULL) = (email_blind_index IS NULL)"),
        ("ck_person_phone_pair", "(phone_ciphertext IS NULL) = (phone_blind_index IS NULL)"),
        ("ck_person_merged_into", "(dedupe_status = 'MERGED') = (merged_into_person_id IS NOT NULL)"),
        ("ck_person_merged_not_self", "merged_into_person_id IS NULL OR merged_into_person_id <> id"),
        ("ck_person_version", "version >= 1"),
        ("ck_person_dedupe_status", f"dedupe_status IN {_DEDUPE_STATUSES}"),
    ):
        op.execute(f'ALTER TABLE person ADD CONSTRAINT "{name}" CHECK ({expression})')

    # Candidate lookup, never a uniqueness claim (§3.4).
    op.create_index("ix_person_email_blind_index", "person", ["email_blind_index"])
    op.create_index("ix_person_phone_blind_index", "person", ["phone_blind_index"])

    # --- SchoolPersonProfile (§2.4) ---
    op.create_table(
        "school_person_profile",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("school_id", sa.String(64), sa.ForeignKey("school.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", sa.String(64), sa.ForeignKey("person.id", ondelete="CASCADE"), nullable=False),
        sa.Column("local_person_code", sa.String(64), nullable=True),
        sa.Column("normalized_local_person_code", sa.String(64), nullable=True),
        sa.Column("administrative_note", sa.Text(), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("school_id", "person_id", name="uq_school_person_profile"),
        sa.UniqueConstraint("school_id", "id", "person_id", name="uq_school_person_profile_tenant_person"),
        sa.CheckConstraint(
            "(local_person_code IS NULL) = (normalized_local_person_code IS NULL)",
            name="ck_school_person_profile_code_pair",
        ),
        sa.CheckConstraint(
            "administrative_note IS NULL OR length(administrative_note) <= 500",
            name="ck_school_person_profile_note_length",
        ),
        sa.CheckConstraint("version >= 1", name="ck_school_person_profile_version"),
    )
    op.create_index(
        "uq_school_person_profile_code",
        "school_person_profile",
        ["school_id", "normalized_local_person_code"],
        unique=True,
        postgresql_where=sa.text("normalized_local_person_code IS NOT NULL"),
    )

    # A profile for everyone the school already knows. One per (school, person),
    # even where the person holds several membership types there.
    rows = bind.execute(
        sa.text(
            "SELECT DISTINCT school_id, person_id FROM school_membership ORDER BY school_id, person_id"
        )
    ).all()
    for row in rows:
        bind.execute(
            sa.text(
                "INSERT INTO school_person_profile (id, school_id, person_id, version, "
                "created_at, updated_at) VALUES (:id, :s, :p, 1, now(), now())"
            ),
            {"id": _new_id("spp"), "s": row.school_id, "p": row.person_id},
        )

    # --- Repoint M04's owner nomination (§2.6, closes F-14) ---
    # Profiles exist for every membership by now, so the new constraint is
    # satisfiable the moment it is added.
    op.drop_constraint("fk_owner_nomination_membership", "school_owner_nomination", type_="foreignkey")
    op.alter_column(
        "school_owner_nomination",
        "target_membership_id",
        new_column_name="target_school_person_profile_id",
    )
    op.execute(
        "UPDATE school_owner_nomination n SET target_school_person_profile_id = p.id "
        "FROM school_person_profile p "
        "WHERE p.school_id = n.school_id AND p.person_id = n.target_person_id"
    )
    op.create_foreign_key(
        "fk_owner_nomination_profile",
        "school_owner_nomination",
        "school_person_profile",
        ["school_id", "target_school_person_profile_id", "target_person_id"],
        ["school_id", "id", "person_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_owner_nomination_profile", "school_owner_nomination", type_="foreignkey")
    op.alter_column(
        "school_owner_nomination",
        "target_school_person_profile_id",
        new_column_name="target_membership_id",
    )
    op.execute(
        "UPDATE school_owner_nomination n SET target_membership_id = m.id "
        "FROM school_membership m "
        "WHERE m.school_id = n.school_id AND m.person_id = n.target_person_id"
    )
    op.create_foreign_key(
        "fk_owner_nomination_membership",
        "school_owner_nomination",
        "school_membership",
        ["school_id", "target_membership_id", "target_person_id"],
        ["school_id", "id", "person_id"],
        ondelete="CASCADE",
    )

    op.drop_table("school_person_profile")

    op.drop_index("ix_person_phone_blind_index", table_name="person")
    op.drop_index("ix_person_email_blind_index", table_name="person")
    for name in (
        "ck_person_email_pair", "ck_person_phone_pair", "ck_person_merged_into",
        "ck_person_merged_not_self", "ck_person_version", "ck_person_dedupe_status",
    ):
        op.execute(f'ALTER TABLE person DROP CONSTRAINT IF EXISTS "{name}"')
    for column in (
        "birth_date", "email_ciphertext", "email_blind_index", "email_blind_index_key_version",
        "phone_ciphertext", "phone_blind_index", "phone_blind_index_key_version",
        "dedupe_status", "merged_into_person_id", "version",
    ):
        op.drop_column("person", column)
