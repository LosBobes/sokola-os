"""M03 student login authorization becomes one decision per school

M03 §4.4–4.5, finding F-27.

`student_login_authorization` was globally unique on `student_person_id`: one
row per child, for all of SOKOLA. "May this child sign in" is not a global
fact about a person, though — it is one school's decision about its own
participant. With a global row the first school to decide decided for every
other school the child attends: school A could enable a login school B never
agreed to, or hold one back that school B wanted to grant, and neither school
could see or change the other's decision.

So the tenant becomes part of the key:

* `school_id` is added, NOT NULL, `ON DELETE CASCADE` to `school`;
* `UNIQUE(student_person_id)` is replaced by
  `UNIQUE(school_id, student_person_id)`.

`Person` stays global — §7.5 is explicit that a global table gets no false
`school_id`. It is the authorization that is tenant-scoped, not the child.

**This migration refuses to run if the table has any rows.** There is no
correct `school_id` to give an existing row: a global decision does not say
which school made it, and §7.10 forbids assigning an ambiguous legacy row to
the first or only school. In this repository the table is provably unwritten —
it has no service, router, test or web reference, and nothing points a foreign
key at it — so the guard should never fire. It exists because "should never"
is not "cannot", and because a deployment that *has* rows needs an operator to
decide, not a migration to guess.

Revision ID: d4b83c17e5f9
Revises: c3f16a80d95e
Create Date: 2026-09-19 17:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd4b83c17e5f9'
down_revision: str | None = 'c3f16a80d95e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_UNIQUE = "student_login_authorization_student_person_id_key"
_NEW_UNIQUE = "uq_student_login_authorization_school_person"


def _refuse_on_existing_rows() -> None:
    """§7.10: report, never guess.

    A row here predates the tenant column, so nothing in it says which school
    made the decision. Picking one would be inventing an authorization.
    """
    count = op.get_bind().execute(
        sa.text("SELECT count(*) FROM student_login_authorization")
    ).scalar_one()
    if count:
        raise RuntimeError(
            f"student_login_authorization has {count} row(s) written before this "
            "table was tenant-scoped, and nothing in them says which school made "
            "the decision. M03 §7.10 forbids assigning them to the first or only "
            "school automatically. An operator must decide, per row, which "
            "school each authorization belongs to (or remove them) before this "
            "migration can run."
        )


def upgrade() -> None:
    _refuse_on_existing_rows()

    op.add_column(
        "student_login_authorization",
        sa.Column("school_id", sa.String(length=64), nullable=False),
    )
    op.create_foreign_key(
        "student_login_authorization_school_id_fkey",
        "student_login_authorization",
        "school",
        ["school_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(_OLD_UNIQUE, "student_login_authorization", type_="unique")
    op.create_unique_constraint(
        _NEW_UNIQUE,
        "student_login_authorization",
        ["school_id", "student_person_id"],
    )


def downgrade() -> None:
    # Going back means one row per child again, and two schools' decisions
    # cannot both survive that. Refuse rather than silently drop one.
    count = op.get_bind().execute(
        sa.text(
            "SELECT count(*) FROM ("
            "  SELECT 1 FROM student_login_authorization"
            "  GROUP BY student_person_id HAVING count(*) > 1"
            ") d"
        )
    ).scalar_one()
    if count:
        raise RuntimeError(
            f"{count} child(ren) hold a login authorization in more than one "
            "school. Downgrading restores a global UNIQUE(student_person_id), "
            "which cannot hold both, and choosing which school's decision "
            "survives is not this migration's call."
        )

    op.drop_constraint(_NEW_UNIQUE, "student_login_authorization", type_="unique")
    op.create_unique_constraint(
        _OLD_UNIQUE, "student_login_authorization", ["student_person_id"]
    )
    op.drop_constraint(
        "student_login_authorization_school_id_fkey",
        "student_login_authorization",
        type_="foreignkey",
    )
    op.drop_column("student_login_authorization", "school_id")
