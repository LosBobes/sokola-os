"""M07 fix: an activated link must remain revokable

M07 §2.3, §2.5, §5.3.

`guardian_child_link` and `payer_child_link` each shipped with

```sql
CHECK ((status = 'ACTIVE') = (activated_at IS NOT NULL))
```

which reads correctly and is wrong. §5.3 allows `ACTIVE -> REVOKED`, and under
a biconditional that transition is impossible: the only way to satisfy the
constraint while leaving ACTIVE is to set `activated_at` back to NULL, erasing
the record of when the guardianship or the payment arrangement actually began.
A revocation is precisely the moment that record matters most.

The replacement is two implications rather than one equivalence:

* a link that is ACTIVE must say when it was activated;
* only a link that *was* activated may carry the timestamp — which REVOKED
  inherits, because a revoked link that was once active still happened.

`PENDING_VERIFICATION` and `REJECTED` still cannot carry one, so a link that
was never activated cannot claim to have been.

**Why no test caught this.** The schema tests for both tables built rows
directly, one status at a time, and every such row satisfied the biconditional.
The defect needs a *transition* to show itself, and there was nothing capable
of performing one until the GRD commands in this change. The lesson is narrow
and worth stating: a constraint over `status` cannot be validated by rows, only
by moves between them.

No data is touched. Every existing row satisfies the new form — it is strictly
weaker than the old one, which is why this is safe to apply without inspecting
anything first.

Revision ID: e41b0c9d72a6
Revises: 97ee92540c4d
Create Date: 2026-09-19 20:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = 'e41b0c9d72a6'
down_revision: str | None = '97ee92540c4d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = ("guardian_child_link", "payer_child_link")

_NEW = (
    "(status <> 'ACTIVE' OR activated_at IS NOT NULL) "
    "AND (activated_at IS NULL OR status IN ('ACTIVE', 'REVOKED'))"
)
_OLD = "(status = 'ACTIVE') = (activated_at IS NOT NULL)"


def upgrade() -> None:
    for table in _TABLES:
        name = f"ck_{table}_activated_at"
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, _NEW)


def downgrade() -> None:
    # Going back re-imposes the biconditional, so any row that is REVOKED with
    # an `activated_at` — every link revoked while active — would violate it.
    # The downgrade therefore clears those timestamps, which is lossy and the
    # honest reason not to run it on data that matters.
    for table in _TABLES:
        name = f"ck_{table}_activated_at"
        op.execute(
            f"UPDATE {table} SET activated_at = NULL "  # noqa: S608 - fixed names
            f"WHERE status <> 'ACTIVE' AND activated_at IS NOT NULL"
        )
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, _OLD)
