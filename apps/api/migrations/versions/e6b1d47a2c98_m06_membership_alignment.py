"""M06 membership alignment, and the school-local code moves to the profile

M06 §2.3 and §2.4.

`school_membership` takes the §2.3 shape: `member_type` becomes
`membership_type` with `ATTENDEE` renamed to `PARTICIPANT`, `status` gains
`DRAFT` and renames `ENDED` to `TERMINATED`, and the row gains `start_date`,
`end_date`, the two reason codes, `is_first_activation` and `version`.

Both renames are renames, not new columns: the values are rewritten in place so
no row exists under two vocabularies at once, and nothing is copied.

`local_member_code` and `admin_note` move to `school_person_profile` as
`local_person_code` and `administrative_note`. They describe the *person* as
this school files them, not one of their memberships — someone who is both a
parent and a coach has one code, not two. Leaving them on the membership while
the profile also had them would be the same two-fields-one-question problem the
school status consolidation removed.

The API keeps its field names (`local_member_code`, `admin_note`): those are the
existing public contract and M06 does not dictate an API shape. Only the storage
moves.

`is_first_activation` is backfilled `true` for every existing membership,
because these are the only episodes the repo has ever had: there is no earlier
history for any of them to be a return from. Later episodes get `false` from
`app.domains.people.membership`, which derives it and then freezes it.

`start_date` is backfilled from `created_at` in the school's own timezone rather
than UTC. A membership created at 23:30 Belgrade time is a member from that day,
not from the next one, and converting in UTC would file roughly a tenth of them
under the wrong date.

Revision ID: e6b1d47a2c98
Revises: d2a95e13c7f4
Create Date: 2026-09-19 10:55:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e6b1d47a2c98'
down_revision: str | None = 'd2a95e13c7f4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TYPES = "('PARTICIPANT', 'GUARDIAN', 'STAFF', 'CONTACT')"
_STATUSES = "('DRAFT', 'ACTIVE', 'SUSPENDED', 'TERMINATED')"


def upgrade() -> None:
    # --- The school-local code and note move to the profile, before the old
    # columns are dropped. Ordering matters: read then write then drop. ---
    op.execute(
        "UPDATE school_person_profile p SET "
        "  local_person_code = m.local_member_code, "
        "  normalized_local_person_code = m.local_member_code, "
        "  administrative_note = m.admin_note "
        "FROM school_membership m "
        "WHERE m.school_id = p.school_id AND m.person_id = p.person_id "
        "  AND (m.local_member_code IS NOT NULL OR m.admin_note IS NOT NULL)"
    )
    op.drop_index("uq_school_local_member_code", table_name="school_membership")
    op.drop_column("school_membership", "local_member_code")
    op.drop_column("school_membership", "admin_note")

    # --- §2.3 vocabulary. Renames in place; no row is ever under two names. ---
    op.alter_column("school_membership", "member_type", new_column_name="membership_type")
    op.execute("UPDATE school_membership SET membership_type = 'PARTICIPANT' WHERE membership_type = 'ATTENDEE'")
    op.execute("UPDATE school_membership SET status = 'TERMINATED' WHERE status = 'ENDED'")

    op.add_column("school_membership", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("school_membership", sa.Column("end_date", sa.Date(), nullable=True))
    op.add_column("school_membership", sa.Column("suspension_reason_code", sa.String(64), nullable=True))
    op.add_column("school_membership", sa.Column("termination_reason_code", sa.String(64), nullable=True))
    op.add_column("school_membership", sa.Column("is_first_activation", sa.Boolean(), nullable=True))
    op.add_column("school_membership", sa.Column("version", sa.BigInteger(), nullable=True))

    # The school's own timezone, not UTC: a membership created at 23:30 in
    # Belgrade belongs to that day, and UTC would file it under the next one.
    op.execute(
        "UPDATE school_membership m SET "
        "  start_date = (m.created_at AT TIME ZONE s.timezone)::date, "
        "  is_first_activation = true, version = 1 "
        "FROM school s WHERE s.id = m.school_id"
    )
    # Any membership whose school vanished (there should be none; the FK says
    # so) still needs a date rather than a failed NOT NULL.
    op.execute(
        "UPDATE school_membership SET start_date = created_at::date, "
        "is_first_activation = true, version = 1 WHERE start_date IS NULL"
    )

    # Existing terminated rows need the end date and reason their new CHECKs
    # require. The reason is explicitly a migration marker, not an invented
    # business reason: the repo never recorded why these ended.
    op.execute(
        "UPDATE school_membership SET end_date = (updated_at)::date, "
        "termination_reason_code = 'MIGRATED_WITHOUT_RECORDED_REASON' "
        "WHERE status = 'TERMINATED'"
    )
    op.execute(
        "UPDATE school_membership SET end_date = start_date "
        "WHERE status = 'TERMINATED' AND end_date < start_date"
    )
    op.execute(
        "UPDATE school_membership SET suspension_reason_code = 'MIGRATED_WITHOUT_RECORDED_REASON' "
        "WHERE status = 'SUSPENDED' AND suspension_reason_code IS NULL"
    )

    for column in ("start_date", "is_first_activation", "version"):
        op.alter_column("school_membership", column, nullable=False)

    # The old UNIQUE(school_id, person_id) has to go: §3.2 says one person may
    # hold several membership types in one school — a parent who also coaches is
    # both — and that constraint made the second one impossible.
    op.drop_constraint("uq_school_membership", "school_membership", type_="unique")
    op.create_index(
        "uq_school_membership_open_episode",
        "school_membership",
        ["school_id", "person_id", "membership_type"],
        unique=True,
        postgresql_where=sa.text("status <> 'TERMINATED'"),
    )
    op.create_unique_constraint("uq_school_membership_tenant", "school_membership", ["school_id", "id"])
    for name, expression in (
        ("ck_school_membership_type", f"membership_type IN {_TYPES}"),
        ("ck_school_membership_status", f"status IN {_STATUSES}"),
        ("ck_school_membership_suspension_reason", "(status = 'SUSPENDED') = (suspension_reason_code IS NOT NULL)"),
        ("ck_school_membership_termination_reason", "(status = 'TERMINATED') = (termination_reason_code IS NOT NULL)"),
        ("ck_school_membership_end_date", "(status = 'TERMINATED') = (end_date IS NOT NULL)"),
        ("ck_school_membership_period", "end_date IS NULL OR end_date >= start_date"),
        ("ck_school_membership_version", "version >= 1"),
    ):
        op.execute(f'ALTER TABLE school_membership ADD CONSTRAINT "{name}" CHECK ({expression})')


def downgrade() -> None:
    for name in (
        "ck_school_membership_type", "ck_school_membership_status",
        "ck_school_membership_suspension_reason", "ck_school_membership_termination_reason",
        "ck_school_membership_end_date", "ck_school_membership_period",
        "ck_school_membership_version",
    ):
        op.execute(f'ALTER TABLE school_membership DROP CONSTRAINT IF EXISTS "{name}"')
    op.drop_constraint("uq_school_membership_tenant", "school_membership", type_="unique")
    op.drop_index("uq_school_membership_open_episode", table_name="school_membership")
    op.create_unique_constraint(
        "uq_school_membership", "school_membership", ["school_id", "person_id"]
    )

    for column in (
        "start_date", "end_date", "suspension_reason_code",
        "termination_reason_code", "is_first_activation", "version",
    ):
        op.drop_column("school_membership", column)

    op.execute("UPDATE school_membership SET status = 'ENDED' WHERE status = 'TERMINATED'")
    op.execute("UPDATE school_membership SET status = 'ACTIVE' WHERE status = 'DRAFT'")
    op.execute("UPDATE school_membership SET membership_type = 'ATTENDEE' WHERE membership_type = 'PARTICIPANT'")
    op.alter_column("school_membership", "membership_type", new_column_name="member_type")

    op.add_column("school_membership", sa.Column("local_member_code", sa.String(60), nullable=True))
    op.add_column("school_membership", sa.Column("admin_note", sa.Text(), nullable=True))
    op.execute(
        "UPDATE school_membership m SET local_member_code = p.local_person_code, "
        "  admin_note = p.administrative_note "
        "FROM school_person_profile p "
        "WHERE p.school_id = m.school_id AND p.person_id = m.person_id"
    )
    op.create_index(
        "uq_school_local_member_code",
        "school_membership",
        ["school_id", "local_member_code"],
        unique=True,
        postgresql_where=sa.text("local_member_code IS NOT NULL"),
    )
