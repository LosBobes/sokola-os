"""M05 platform role assignment

M05 §2. The table that says which `UserAccount` holds which platform role,
and for how long.

The shape is the contract. §2 requires **no `school_id`, no `Person` and no
`SchoolMembership`**: a platform actor is not a member of anything, and the
absence of those columns is what stops a later reader treating platform access
as a tenant membership with a wider radius. §3 adds that a platform permission
"ne otvara podatke dece, attendance, dokumente ili school finance".

Two constraint choices worth reading:

* the uniqueness is **partial** — one *open* assignment per
  `(user_account_id, role_key)`, where open means SCHEDULED, ACTIVE or
  SUSPENDED. A revoked or expired row is history, and several per key are
  expected; a plain unique index would make re-granting the same role to the
  same person impossible forever.
* `PLATFORM_SECURITY_ADMIN` may not carry a `valid_until`. §2 makes it
  non-temporal, and expressing that only in service code would hold until the
  first import, backfill or fixture created a security admin that quietly
  expires.

Nothing is seeded. There is deliberately no bootstrap row: the first
assignment is created by `scripts/grant_platform_role.py`, which needs a
database connection rather than a session, so no API caller can mint platform
access from nothing.

Revision ID: a71f3c9b5d28
Revises: e41b0c9d72a6
Create Date: 2026-10-04 07:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'a71f3c9b5d28'
down_revision: str | None = 'e41b0c9d72a6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OPEN_STATUSES = "status IN ('SCHEDULED', 'ACTIVE', 'SUSPENDED')"


def upgrade() -> None:
    op.create_table(
        "platform_role_assignment",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_account_id",
            sa.String(64),
            sa.ForeignKey("user_account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("role_key", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_ticket_ref", sa.String(100), nullable=False),
        sa.Column(
            "created_by_account_id",
            sa.String(64),
            sa.ForeignKey("user_account.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "suspended_by_account_id",
            sa.String(64),
            sa.ForeignKey("user_account.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspend_reason_code", sa.String(40), nullable=True),
        sa.Column(
            "revoked_by_account_id",
            sa.String(64),
            sa.ForeignKey("user_account.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason_code", sa.String(40), nullable=True),
        # No server default: the model sets `version` in Python, and a server
        # default here is schema drift `alembic check` rejects.
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "(suspended_at IS NULL) = (suspended_by_account_id IS NULL) "
            "AND (suspended_at IS NULL) = (suspend_reason_code IS NULL)",
            name="ck_platform_role_suspend_triple",
        ),
        sa.CheckConstraint(
            "(revoked_at IS NULL) = (revoked_by_account_id IS NULL) "
            "AND (revoked_at IS NULL) = (revoke_reason_code IS NULL)",
            name="ck_platform_role_revoke_triple",
        ),
        sa.CheckConstraint(
            "(status = 'REVOKED') = (revoked_at IS NOT NULL)",
            name="ck_platform_role_revoked_stamp",
        ),
        sa.CheckConstraint(
            "(status = 'SUSPENDED') = (suspended_at IS NOT NULL)",
            name="ck_platform_role_suspended_stamp",
        ),
        sa.CheckConstraint(
            "role_key <> 'PLATFORM_SECURITY_ADMIN' OR valid_until IS NULL",
            name="ck_platform_role_security_admin_not_temporal",
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name="ck_platform_role_window",
        ),
        sa.CheckConstraint("version >= 1", name="ck_platform_role_version"),
        sa.CheckConstraint(
            "length(btrim(source_ticket_ref)) BETWEEN 1 AND 100",
            name="ck_platform_role_ticket_ref",
        ),
    )
    op.create_index(
        "uq_platform_role_assignment_open",
        "platform_role_assignment",
        ["user_account_id", "role_key"],
        unique=True,
        postgresql_where=sa.text(_OPEN_STATUSES),
    )
    op.create_index(
        "ix_platform_role_assignment_account",
        "platform_role_assignment",
        ["user_account_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_platform_role_assignment_account", table_name="platform_role_assignment"
    )
    op.drop_index(
        "uq_platform_role_assignment_open", table_name="platform_role_assignment"
    )
    op.drop_table("platform_role_assignment")
