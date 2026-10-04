"""M05 §2.5, §2.10: role transitions record who, when and why

`RoleTransitionRequest.reason` was `str | None` with a length limit and no
vocabulary, and the reason went only into an audit summary — interpolated into
its text, so the trail carried whatever the client sent. §2.10 fixes the
allowed codes per command and §2.5 wants the decision on the row itself as a
triple: actor, timestamp, code. This adds both triples plus their notes, and
the CHECKs that keep a half-written one from existing (F-49).

**Why one constraint is `NOT VALID`.** `ck_role_assignment_revoked_stamp`
says a REVOKED row carries its revocation stamp and a live one does not. That
is the right invariant going forward and it cannot be applied backwards: a row
revoked before this migration has no actor and no reason on record anywhere,
and the only way to satisfy a bidirectional CHECK would be to invent them.
Writing a fabricated attribution into the columns an audit reads is worse than
admitting the gap, so the constraint is added `NOT VALID` — Postgres enforces
it on every insert and update from here on, and does not re-validate rows that
predate it. The service stamps every transition it performs, and a test
asserts that, so the untrusted set is exactly "revocations that already
happened" and does not grow.

A fresh database has no such rows, so `create_all` building the same constraint
as fully valid is correct there and is why the model declares it plainly.

Suspension is deliberately not paired with the status the way revocation is.
§5.2 allows a suspended assignment to be reactivated, and the record of why it
was suspended should survive that — pairing it with `status = 'SUSPENDED'`
would force the reason to be erased on reactivation, leaving a history in which
the suspension never happened.

Revision ID: d4a7b2e01c69
Revises: c58d1f4e7a93
Create Date: 2026-10-04 12:05:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd4a7b2e01c69'
down_revision: str | None = 'c58d1f4e7a93'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SUSPEND_REASONS = ("SECURITY_REVIEW", "TEMPORARY_LEAVE", "ACCESS_PAUSE", "MEMBERSHIP_SUSPENDED")
_REVOKE_REASONS = (
    "MEMBERSHIP_ENDED",
    "RESPONSIBILITY_ENDED",
    "ROLE_REPLACED",
    "SECURITY_REVOKE",
    "OWNER_TRANSFER",
)


def _non_native(values: tuple[str, ...], name: str) -> sa.Enum:
    """The repo stores enums as VARCHAR + CHECK, not as native PG types.

    `app/common/columns.enum_type` is the single place that decides this, and a
    migration that reached for `sa.Enum(...)` with its defaults would create a
    native type instead — which `alembic check` catches as a type change on
    every run afterwards. Mirrored here rather than imported so the migration
    stays readable on its own and does not move when the helper does.
    """
    return sa.Enum(*values, name=name, native_enum=False, length=40)


def upgrade() -> None:
    suspend_enum = _non_native(_SUSPEND_REASONS, "rolesuspendreason")
    revoke_enum = _non_native(_REVOKE_REASONS, "rolerevokereason")

    op.add_column(
        "role_assignment",
        sa.Column("suspended_by_person_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "role_assignment",
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "role_assignment",
        sa.Column("suspend_reason_code", suspend_enum, nullable=True),
    )
    op.add_column(
        "role_assignment",
        sa.Column("suspend_reason_note", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "role_assignment",
        sa.Column("revoked_by_person_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "role_assignment",
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "role_assignment",
        sa.Column("revoke_reason_code", revoke_enum, nullable=True),
    )
    op.add_column(
        "role_assignment",
        sa.Column("revoke_reason_note", sa.String(length=500), nullable=True),
    )

    op.create_check_constraint(
        "ck_role_assignment_suspend_triple",
        "role_assignment",
        "(suspended_at IS NULL) = (suspended_by_person_id IS NULL)"
        " AND (suspended_at IS NULL) = (suspend_reason_code IS NULL)",
    )
    op.create_check_constraint(
        "ck_role_assignment_revoke_triple",
        "role_assignment",
        "(revoked_at IS NULL) = (revoked_by_person_id IS NULL)"
        " AND (revoked_at IS NULL) = (revoke_reason_code IS NULL)",
    )
    op.create_check_constraint(
        "ck_role_assignment_suspend_note_required",
        "role_assignment",
        "suspend_reason_code IS NULL"
        " OR suspend_reason_code NOT IN ('SECURITY_REVIEW', 'ACCESS_PAUSE')"
        " OR (suspend_reason_note IS NOT NULL AND length(trim(suspend_reason_note)) > 0)",
    )
    op.create_check_constraint(
        "ck_role_assignment_revoke_note_required",
        "role_assignment",
        "revoke_reason_code IS NULL"
        " OR revoke_reason_code <> 'SECURITY_REVOKE'"
        " OR (revoke_reason_note IS NOT NULL AND length(trim(revoke_reason_note)) > 0)",
    )
    # The one that cannot be applied backwards; see the module docstring.
    op.execute(
        "ALTER TABLE role_assignment ADD CONSTRAINT ck_role_assignment_revoked_stamp"
        " CHECK ((status = 'REVOKED') = (revoked_at IS NOT NULL)) NOT VALID"
    )


def downgrade() -> None:
    for name in (
        "ck_role_assignment_revoked_stamp",
        "ck_role_assignment_revoke_note_required",
        "ck_role_assignment_suspend_note_required",
        "ck_role_assignment_revoke_triple",
        "ck_role_assignment_suspend_triple",
    ):
        op.drop_constraint(name, "role_assignment", type_="check")
    for column in (
        "revoke_reason_note",
        "revoke_reason_code",
        "revoked_at",
        "revoked_by_person_id",
        "suspend_reason_note",
        "suspend_reason_code",
        "suspended_at",
        "suspended_by_person_id",
    ):
        op.drop_column("role_assignment", column)
    # Dropping the columns loses every recorded reason, which is the honest
    # cost of going back: the codes have nowhere else to live. There is no
    # native enum type to drop — the repo stores these as VARCHAR + CHECK, so
    # the constraint goes with the column.
