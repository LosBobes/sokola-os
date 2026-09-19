"""M01 server-side session, so a sign-in can be ended

M01 §3.2, §4.7, §6 AUTH-03/04/08.

Before this, a session was a signed cookie holding a person id. A signed cookie
is a claim the server re-verifies, never a record the server owns: "log me out
everywhere" had nothing to act on, and a cookie issued on a borrowed laptop
stayed valid until its signature aged out, whatever happened to the account in
between. `auth_session` is the record.

Two enforced expiries with §3.2's fail-closed defaults — 30 minutes idle, 12
hours absolute, whichever first — and a CHECK that the sliding one can never
outlive the hard one, because an idle window that could push past the absolute
deadline would make the absolute deadline advisory.

`authorization_version_at_issue` is what makes §4.7 true. Every protected
request compares it against `user_account.authorization_version` in its own
transaction, so a bump ends every session on the next request with no cache
between the two to go stale (M01-QA-021).

No backfill, and this is the point rather than an omission: §15 requires that
active old sessions without a proven identity link be revoked at cutover. The
signed cookies in flight have no `auth_session` row and no way to acquire one,
so they stop validating the moment this ships. Everyone signs in again once.

Revision ID: b8d3f60a51c7
Revises: a7e4c2f91b08
Create Date: 2026-09-19 14:20:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b8d3f60a51c7'
down_revision: str | None = 'a7e4c2f91b08'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REVOKE_REASONS = (
    "('LOGOUT', 'LOGOUT_ALL', 'ACCOUNT_SUSPENDED', 'ACCOUNT_DISABLED', "
    "'ACCOUNT_MERGED', 'IDENTITY_LINKED', 'IDENTITY_UNLINKED', "
    "'PROVIDER_REVOKED', 'ACCESS_CHANGED', 'SECURITY_EVENT', 'EXPIRED')"
)


def upgrade() -> None:
    op.create_table(
        "auth_session",
        sa.Column("id", sa.String(64), primary_key=True),
        # Only the digest. A copy of this table yields no working sessions.
        sa.Column("credential_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "user_account_id", sa.String(64),
            sa.ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "auth_identity_id", sa.String(64),
            sa.ForeignKey("auth_identity.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("idle_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason_code", sa.String(40), nullable=True),
        sa.Column("authorization_version_at_issue", sa.BigInteger(), nullable=False),
        sa.Column("auth_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "assurance_context", sa.dialects.postgresql.JSONB(), nullable=False
        ),
        sa.Column("device_label", sa.String(120), nullable=True),
        sa.CheckConstraint(
            f"revoke_reason_code IS NULL OR revoke_reason_code IN {_REVOKE_REASONS}",
            name="ck_auth_session_revoke_reason_enum",
        ),
        sa.CheckConstraint(
            "(revoked_at IS NULL) = (revoke_reason_code IS NULL)",
            name="ck_auth_session_revoke_pair",
        ),
        sa.CheckConstraint(
            "idle_expires_at <= absolute_expires_at", name="ck_auth_session_expiry_order"
        ),
        sa.CheckConstraint(
            "authorization_version_at_issue > 0", name="ck_auth_session_version"
        ),
    )
    op.create_index(
        "ix_auth_session_account_live",
        "auth_session",
        ["user_account_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "ix_auth_session_absolute_expiry", "auth_session", ["absolute_expires_at"]
    )


def downgrade() -> None:
    # Dropping the table ends every session, which is the correct direction for
    # a security rollback: going back may lose sessions, never revive them (§15).
    op.drop_index("ix_auth_session_absolute_expiry", table_name="auth_session")
    op.drop_index("ix_auth_session_account_live", table_name="auth_session")
    op.drop_table("auth_session")
