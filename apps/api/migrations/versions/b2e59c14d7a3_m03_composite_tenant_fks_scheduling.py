"""M03 composite tenant foreign keys for the scheduling and roster cluster

M03 §7.2–7.3, the second F-26 slice.

The first slice (`a1d47f38e6c2`) closed the eight references that point at the
structure domain. These are the seven that point at `group`, `session` and
`session_series` — the rows a school's day is actually made of:

* `session.group_id`, `session.series_id`, `session_series.group_id`
* `group_membership.group_id`
* `attendance_record.session_id`
* `progress_note.group_id`, `progress_note.session_id`

Same shape as the first slice: the parent gains `UNIQUE(school_id, id)` so the
child's foreign key can name the tenant as part of what it points at, and the
single-column key is replaced by `(school_id, child_column) → (school_id, id)`.
After this, enrolling a person into another school's group — or taking
attendance for another school's session — is impossible rather than merely
incorrect.

`ON DELETE SET NULL (column)` names the column on the two nullable ones, since
the plain form would try to null `school_id` and that column is NOT NULL. The
five NOT NULL ones keep CASCADE, which is what they had.

Like the first slice, this **refuses to run on data that already crosses a
tenant** rather than repairing it: §7.10 forbids quietly reassigning an
ambiguous row, and a cross-tenant reference is an incident an operator should
see.

Revision ID: b2e59c14d7a3
Revises: a1d47f38e6c2
Create Date: 2026-09-19 17:05:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b2e59c14d7a3'
down_revision: str | None = 'a1d47f38e6c2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (child table, child column, parent table, new constraint name, on-delete)
_RELATIONS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "session", "group_id", "group",
        "fk_session_group_tenant", "CASCADE",
    ),
    (
        "session", "series_id", "session_series",
        "fk_session_series_tenant", "SET NULL (series_id)",
    ),
    (
        "session_series", "group_id", "group",
        "fk_session_series_group_tenant", "CASCADE",
    ),
    (
        "group_membership", "group_id", "group",
        "fk_group_membership_group_tenant", "CASCADE",
    ),
    (
        "attendance_record", "session_id", "session",
        "fk_attendance_record_session_tenant", "CASCADE",
    ),
    (
        "progress_note", "group_id", "group",
        "fk_progress_note_group_tenant", "CASCADE",
    ),
    (
        "progress_note", "session_id", "session",
        "fk_progress_note_session_tenant", "SET NULL (session_id)",
    ),
)

_PARENTS: tuple[tuple[str, str], ...] = (
    ("group", "uq_group_tenant"),
    ("session", "uq_session_tenant"),
    ("session_series", "uq_session_series_tenant"),
)

#: The single-column constraints being replaced, under the names the database
#: actually holds them by. All seven fell back to PostgreSQL's default here,
#: but the names are still read from `pg_constraint` rather than derived, for
#: the same reason as in the first slice: the default is not a rule this repo
#: guarantees.
_OLD_FK_NAMES: dict[tuple[str, str], str] = {
    ("session", "group_id"): "session_group_id_fkey",
    ("session", "series_id"): "session_series_id_fkey",
    ("session_series", "group_id"): "session_series_group_id_fkey",
    ("group_membership", "group_id"): "group_membership_group_id_fkey",
    ("attendance_record", "session_id"): "attendance_record_session_id_fkey",
    ("progress_note", "group_id"): "progress_note_group_id_fkey",
    ("progress_note", "session_id"): "progress_note_session_id_fkey",
}


def _refuse_on_existing_cross_tenant_rows() -> None:
    """§7.10: report, never repair."""
    bind = op.get_bind()
    offenders = []
    for child, column, parent, _, _ in _RELATIONS:
        count = bind.execute(
            sa.text(
                f'SELECT count(*) FROM "{child}" c '
                f'JOIN "{parent}" p ON p.id = c."{column}" '
                f'WHERE c."{column}" IS NOT NULL AND p.school_id <> c.school_id'
            )
        ).scalar_one()
        if count:
            offenders.append(f"{child}.{column} -> {parent}: {count}")
    if offenders:
        raise RuntimeError(
            "Cross-tenant references already exist and must be resolved by an "
            "operator before this migration can run (M03 §7.10 forbids "
            "reassigning them automatically):\n  " + "\n  ".join(offenders)
        )


def upgrade() -> None:
    _refuse_on_existing_cross_tenant_rows()

    for table, name in _PARENTS:
        op.create_unique_constraint(name, table, ["school_id", "id"])

    for child, column, _, _, _ in _RELATIONS:
        op.drop_constraint(_OLD_FK_NAMES[(child, column)], child, type_="foreignkey")

    for child, column, parent, name, ondelete in _RELATIONS:
        # `create_foreign_key` does not take the `SET NULL (col)` column list,
        # so the composite constraints go in as explicit DDL.
        op.execute(
            f'ALTER TABLE "{child}" ADD CONSTRAINT {name} '
            f'FOREIGN KEY (school_id, "{column}") '
            f'REFERENCES "{parent}" (school_id, id) ON DELETE {ondelete}'
        )


def downgrade() -> None:
    for child, _, _, name, _ in _RELATIONS:
        op.drop_constraint(name, child, type_="foreignkey")

    for child, column, parent, _, ondelete in _RELATIONS:
        action = "CASCADE" if ondelete == "CASCADE" else "SET NULL"
        old_name = _OLD_FK_NAMES[(child, column)]
        op.execute(
            f'ALTER TABLE "{child}" ADD CONSTRAINT {old_name} '
            f'FOREIGN KEY ("{column}") REFERENCES "{parent}" (id) '
            f"ON DELETE {action}"
        )

    for table, name in _PARENTS:
        op.drop_constraint(name, table, type_="unique")
