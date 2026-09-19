"""M03 session tenant context

M03 §5.3, §8 step 3, TEN-01/TEN-02.

Which school one signed-in session is currently working in, with the version
snapshots that make "still valid" a question the server can answer.

At most one row per M01 session (`UNIQUE(session_id)`): §5.3 keeps earlier
choices in the audit trail rather than as parallel active rows, because "which
school is this session in" must have exactly one answer at any moment.

The three snapshot columns are the point of the table. §8 step 3 compares each
against its live authority before any protected work:

* `context_version` — this session's own select/switch/clear counter, so a slow
  response from school A cannot commit after a switch to B (§10);
* `tenant_access_version_at_selection` — M03's, moved when a school's access is
  invalidated wholesale;
* `authorization_version_at_selection` — M01's, moved when the account's is.

None of them grants anything (§5.3: "nije trajni allow dokaz"). They can make a
context stale; they can never make one sufficient.

No backfill. A context is a *choice someone made*, and there is no record of
any live session having made one — inventing a school for existing sessions
would be inventing the one fact this table exists to hold. Sessions simply
select on their next protected request.

Revision ID: f8c21e64b0a7
Revises: e5f83a19d24b
Create Date: 2026-09-19 17:55:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f8c21e64b0a7'
down_revision: str | None = 'e5f83a19d24b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REASONS = (
    "('USER_CLEARED', 'CONTEXT_STALE', 'SESSION_ENDED', 'MEMBERSHIP_REVOKED', "
    "'SCHOOL_UNAVAILABLE', 'TENANT_ACCESS_INVALIDATED', 'SWITCHED_AWAY')"
)


def upgrade() -> None:
    op.create_table(
        "session_tenant_context",
        sa.Column("id", sa.String(64), primary_key=True),
        # CASCADE from the session: §5.3 says the row must not stay active once
        # the M01 session is gone, and the cheapest way to guarantee that is for
        # it not to outlive the session at all.
        sa.Column(
            "session_id", sa.String(64),
            sa.ForeignKey("auth_session.id", ondelete="CASCADE"),
            nullable=False, unique=True,
        ),
        sa.Column(
            "user_account_id", sa.String(64),
            sa.ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "school_id", sa.String(64),
            sa.ForeignKey("school.id", ondelete="RESTRICT"), nullable=False,
        ),
        # No foreign key to anything in M05, per §5.3 — a foreign key is how a
        # display field quietly becomes a permission field.
        sa.Column("workspace_key", sa.String(64), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("context_version", sa.BigInteger(), nullable=False),
        sa.Column("tenant_access_version_at_selection", sa.BigInteger(), nullable=False),
        sa.Column("authorization_version_at_selection", sa.BigInteger(), nullable=False),
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidation_reason_code", sa.String(40), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'INVALIDATED')", name="ck_session_context_status_enum"
        ),
        sa.CheckConstraint(
            f"invalidation_reason_code IS NULL OR invalidation_reason_code IN {_REASONS}",
            name="ck_session_context_reason_enum",
        ),
        # §5.3 verbatim: ACTIVE has neither stamp, INVALIDATED has both. A
        # context that ended without a recorded reason is the one a security
        # review most needs and least often gets.
        sa.CheckConstraint(
            "(status = 'ACTIVE'"
            " AND invalidated_at IS NULL AND invalidation_reason_code IS NULL)"
            " OR (status = 'INVALIDATED'"
            " AND invalidated_at IS NOT NULL AND invalidation_reason_code IS NOT NULL)",
            name="ck_session_context_status_pair",
        ),
        sa.CheckConstraint("context_version >= 1", name="ck_session_context_version"),
        sa.CheckConstraint(
            "tenant_access_version_at_selection >= 1",
            name="ck_session_context_tenant_version",
        ),
        sa.CheckConstraint(
            "authorization_version_at_selection >= 1",
            name="ck_session_context_auth_version",
        ),
        sa.CheckConstraint("version >= 1", name="ck_session_context_row_version"),
    )
    op.create_index(
        "ix_session_context_school_live",
        "session_tenant_context",
        ["school_id"],
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )


def downgrade() -> None:
    # Dropping the table drops every session's school choice, which is the
    # correct direction: going back may cost people a re-selection, and must
    # never resurrect a context that was invalidated.
    op.drop_index("ix_session_context_school_live", table_name="session_tenant_context")
    op.drop_table("session_tenant_context")
