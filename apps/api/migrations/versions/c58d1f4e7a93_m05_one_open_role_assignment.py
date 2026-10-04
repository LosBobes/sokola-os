"""M05 §5.2, §7.1: one *open* role assignment, and nulls that actually collide

`role_assignment` shipped with

```sql
UNIQUE (person_id, school_id, role_code, scope_type, scope_ref_id)
```

which reads like "one assignment per person, school and role" and enforced
neither half of it.

**It did not constrain the ordinary case at all.** `scope_ref_id` is null for
every school-scoped role — the default `scope_type` is `SCHOOL` and nothing
fills the reference — and Postgres treats nulls as distinct inside a unique
index. So two ACTIVE OWNER rows for the same person in the same school were
accepted, and the only thing standing in the way was `assign_role`'s own
read-then-insert. That is precisely the race §7.1 says the database must catch
as a last resort (F-51). Measured before this change: inserting the second row
succeeded and left two ACTIVE OWNER rows for one person.

**And being total rather than partial forced a second defect.** §5.2 makes
`REVOKED` terminal and M05-QA-026 requires a later grant of the same role to
mint a *new* id. Under a total constraint that insert could never succeed, so
`assign_role` revived the revoked row instead — the same id carrying a
revocation and its reversal (F-48). Making the index partial over the open
statuses is what lets the terminal row stay as history beside a new one.

The replacement is one partial unique index over `ACTIVE` and `SUSPENDED` with
`NULLS NOT DISTINCT`, which Postgres has supported since 15 (this project runs
16).

**Pre-existing duplicates.** Creating the index fails outright if any open
duplicate already exists, so this checks first and raises with the offending
keys named. It deliberately does not deduplicate: choosing which of two ACTIVE
assignments to retire decides who keeps access, and the rows do not say which
was intended. An operator resolving it by hand is the correct outcome, and a
migration that guessed would be the wrong kind of convenient.

Revision ID: c58d1f4e7a93
Revises: a71f3c9b5d28
Create Date: 2026-10-04 09:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c58d1f4e7a93'
down_revision: str | None = 'a71f3c9b5d28'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OPEN = "status IN ('ACTIVE', 'SUSPENDED')"

_DUPLICATE_QUERY = sa.text(
    "SELECT person_id, school_id, role_code, scope_type, count(*) AS n"
    " FROM role_assignment"
    f" WHERE {_OPEN}"
    " GROUP BY person_id, school_id, role_code, scope_type, scope_ref_id"
    " HAVING count(*) > 1"
)


def upgrade() -> None:
    rows = op.get_bind().execute(_DUPLICATE_QUERY).all()
    if rows:
        listed = "; ".join(
            f"person={r.person_id} school={r.school_id} role={r.role_code}"
            f" scope={r.scope_type} rows={r.n}"
            for r in rows
        )
        raise RuntimeError(
            "role_assignment already holds open duplicates, which the new "
            "index would reject. Retire the assignments that should not be "
            "open, then re-run this migration. Deciding that here would "
            "decide who keeps access. Offending keys: " + listed
        )

    op.drop_constraint("uq_role_assignment", "role_assignment", type_="unique")
    op.create_index(
        "uq_role_assignment_open",
        "role_assignment",
        ["person_id", "school_id", "role_code", "scope_type", "scope_ref_id"],
        unique=True,
        postgresql_where=sa.text(_OPEN),
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    # Going back is only safe while no two rows differ *solely* by having one
    # revoked — the total constraint cannot express that, and would reject the
    # pair. Nothing is deleted here: the same reasoning as the upgrade applies,
    # so the failure is loud rather than lossy.
    op.drop_index("uq_role_assignment_open", table_name="role_assignment")
    op.create_unique_constraint(
        "uq_role_assignment",
        "role_assignment",
        ["person_id", "school_id", "role_code", "scope_type", "scope_ref_id"],
    )
