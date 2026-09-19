"""M01 command receipts for the security commands

M01 §6 AUTH-05 and §12.

Security commands have a problem ordinary idempotency does not: the command can
revoke the caller's own session. §6 spells out the consequence — after
`LogoutAll` succeeds, the identical retry arrives holding a credential that no
longer authenticates anything, and it must still receive the first result
rather than a 401 or a second execution.

So `auth_command_receipt` is account-scoped rather than school-scoped (one
account reaches many schools, and §8 keeps tenancy off the authentication path),
and it carries `revoked_credential_hash`: the digest of the credential the
command revoked, which lets that credential's holder collect this one stored
result and nothing else.

`retain_until` is stored rather than computed at sweep time, so shortening the
session lifetime later cannot retroactively delete receipts a client may still
be entitled to retry against (§12: kept at least to the session+retry limit).

Revision ID: c4a71e8b35d2
Revises: b8d3f60a51c7
Create Date: 2026-09-19 15:40:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c4a71e8b35d2'
down_revision: str | None = 'b8d3f60a51c7'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMMANDS = "('AUTH-05', 'AUTH-06', 'AUTH-07', 'AUTH-09', 'AUTH-10', 'AUTH-11')"
_STATUSES = "('IN_PROGRESS', 'COMPLETED')"


def upgrade() -> None:
    op.create_table(
        "auth_command_receipt",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_account_id", sa.String(64),
            sa.ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("command", sa.String(40), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("revoked_credential_hash", sa.String(64), nullable=True),
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_account_id", "command", "request_id", name="uq_auth_command_receipt"
        ),
        sa.CheckConstraint(f"command IN {_COMMANDS}", name="ck_auth_command_receipt_command"),
        sa.CheckConstraint(f"status IN {_STATUSES}", name="ck_auth_command_receipt_status"),
        # A completed receipt has a result; an in-progress one does not yet.
        # Without this, a crash mid-command could leave a row that replays
        # `null` as though it were the answer.
        sa.CheckConstraint(
            "(status = 'COMPLETED') = (response_status IS NOT NULL)",
            name="ck_auth_command_receipt_result",
        ),
    )
    op.create_index(
        "ix_auth_command_receipt_revoked", "auth_command_receipt",
        ["revoked_credential_hash"],
    )
    op.create_index(
        "ix_auth_command_receipt_retention", "auth_command_receipt", ["retain_until"]
    )


def downgrade() -> None:
    op.drop_index("ix_auth_command_receipt_retention", table_name="auth_command_receipt")
    op.drop_index("ix_auth_command_receipt_revoked", table_name="auth_command_receipt")
    op.drop_table("auth_command_receipt")
