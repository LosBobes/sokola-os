"""M06 participant and staff profiles, and the person merge history

M06 §2.5–2.7.

Three tables that each hang off something else and have no status of their own:
§5's last line says a profile's effectiveness follows its membership, so a
suspended member's participant profile is not separately suspended. One answer
to "is this person active here", and it lives on the membership.

`school_membership` gains UNIQUE(school_id, id, membership_type) so the profiles'
foreign keys can require the membership's *type* as part of the reference. That
is what makes a participant profile on a STAFF membership impossible rather than
merely incorrect — §6 has an error code for the latter
(`M06_PROFILE_TYPE_MISMATCH`), and this migration is about not needing it.

`person_merge_history_entry` is immutable by construction: no updated_at and no
version, because there is nothing here that should ever change and a correctable
merge record would be worse than none.

No backfill. There are no participant or staff profiles to create — the repo has
never recorded a discipline, a level or an engagement type — and inventing them
would be inventing facts about real people. The existing `person_merge_record`
table stays where it is: it is the *review case* (flagged, merged, dismissed),
a different thing from §2.7's record that a merge happened, and conflating them
would lose the review history.

Revision ID: f3c92d81ab45
Revises: e6b1d47a2c98
Create Date: 2026-09-19 11:10:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f3c92d81ab45'
down_revision: str | None = 'e6b1d47a2c98'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DISCIPLINES = "('SPORT', 'DANCE', 'DRAMA', 'MUSIC', 'EDUCATION', 'OTHER')"
_ENGAGEMENTS = "('EMPLOYEE', 'CONTRACTOR', 'VOLUNTEER', 'OTHER')"
_MERGE_REASONS = (
    "('DUPLICATE_DATA_ENTRY', 'DUPLICATE_FROM_IMPORT', "
    "'SAME_PERSON_CONFIRMED_BY_SCHOOL')"
)
MAX_SPECIALIZATION_CODES = 50


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_school_membership_tenant_type",
        "school_membership",
        ["school_id", "id", "membership_type"],
    )

    for table, prefix, extra_columns, extra_constraints in (
        (
            "participant_profile",
            "PARTICIPANT",
            [
                sa.Column("discipline_category", sa.String(40), nullable=True),
                sa.Column("level_label", sa.String(100), nullable=True),
                sa.Column("prior_experience_note", sa.Text(), nullable=True),
                sa.Column("safety_note_ciphertext", sa.Text(), nullable=True),
            ],
            [
                sa.CheckConstraint(
                    f"discipline_category IS NULL OR discipline_category IN {_DISCIPLINES}",
                    name="ck_participant_profile_discipline",
                ),
                sa.CheckConstraint(
                    "prior_experience_note IS NULL OR length(prior_experience_note) <= 500",
                    name="ck_participant_profile_note_length",
                ),
            ],
        ),
        (
            "staff_profile",
            "STAFF",
            [
                sa.Column("engagement_type", sa.String(40), nullable=True),
                sa.Column("specialization_codes", sa.ARRAY(sa.String(64)), nullable=True),
                sa.Column("qualification_note", sa.Text(), nullable=True),
            ],
            [
                sa.CheckConstraint(
                    f"engagement_type IS NULL OR engagement_type IN {_ENGAGEMENTS}",
                    name="ck_staff_profile_engagement",
                ),
                sa.CheckConstraint(
                    f"specialization_codes IS NULL OR "
                    f"array_length(specialization_codes, 1) <= {MAX_SPECIALIZATION_CODES}",
                    name="ck_staff_profile_specialization_count",
                ),
                sa.CheckConstraint(
                    "qualification_note IS NULL OR length(qualification_note) <= 500",
                    name="ck_staff_profile_note_length",
                ),
            ],
        ),
    ):
        short = "participant" if prefix == "PARTICIPANT" else "staff"
        op.create_table(
            table,
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("school_id", sa.String(64), nullable=False),
            sa.Column("school_membership_id", sa.String(64), nullable=False),
            sa.Column("membership_type", sa.String(40), nullable=False),
            *extra_columns,
            sa.Column("version", sa.BigInteger(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            # The membership must be this school's and of this type. Naming the
            # type in the key is the whole point.
            sa.ForeignKeyConstraint(
                ["school_id", "school_membership_id", "membership_type"],
                [
                    "school_membership.school_id",
                    "school_membership.id",
                    "school_membership.membership_type",
                ],
                name=f"fk_{short}_profile_membership",
                ondelete="CASCADE",
            ),
            sa.UniqueConstraint(
                "school_id", "school_membership_id", name=f"uq_{short}_profile_membership"
            ),
            sa.CheckConstraint(
                f"membership_type = '{prefix}'", name=f"ck_{short}_profile_type"
            ),
            sa.CheckConstraint("version >= 1", name=f"ck_{short}_profile_version"),
            *extra_constraints,
        )

    op.create_table(
        "person_merge_history_entry",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("school_id", sa.String(64), sa.ForeignKey("school.id", ondelete="CASCADE"), nullable=False),
        sa.Column("surviving_person_id", sa.String(64), nullable=False),
        sa.Column("merged_person_id", sa.String(64), nullable=False),
        sa.Column("reason_code", sa.String(40), nullable=False),
        sa.Column("merged_by_account_id", sa.String(64), nullable=False),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("surviving_person_id <> merged_person_id", name="ck_person_merge_distinct"),
        sa.CheckConstraint(f"reason_code IN {_MERGE_REASONS}", name="ck_person_merge_reason"),
    )
    op.create_index("ix_person_merge_history_school", "person_merge_history_entry", ["school_id", "merged_at"])
    op.create_index("ix_person_merge_history_merged", "person_merge_history_entry", ["merged_person_id"])


def downgrade() -> None:
    op.drop_table("person_merge_history_entry")
    op.drop_table("staff_profile")
    op.drop_table("participant_profile")
    op.drop_constraint("uq_school_membership_tenant_type", "school_membership", type_="unique")
