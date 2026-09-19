"""M01 rate-limit counters

M01 §6 AUTH-01 and §10.

A fixed-window counter in Postgres, because that is what this deployment has —
there is no Redis, and a limit that exists is worth more than a smoother one
that does not. The window boundary is the honest weakness: a burst timed across
two adjacent windows gets up to twice the budget in a short span. Acceptable,
because these limits blunt automated volume; the credential checks are what
stand between an attacker and an account.

What is stored is a **keyed digest** of the address or device signal, never the
signal (§10: "Limiti su keyed hash IP/device signal-a i kratko se čuvaju prema
M17; ne koriste se za profilisanje"). Keyed rather than plain, because the whole
IPv4 space can be hashed in minutes — an unkeyed digest of an address *is* the
address. The key is derived from the session secret by domain separation rather
than being its own deployment variable: a new required secret is a new way for
a deploy to fail, and the property wanted here is fully served by a key that is
already required in production.

`expires_at` exists so these rows do not have to be kept. They answer one
question about the last few minutes and have no reason to outlive it.

Revision ID: d7b25c48a139
Revises: c4a71e8b35d2
Create Date: 2026-09-19 16:50:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd7b25c48a139'
down_revision: str | None = 'c4a71e8b35d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCOPES = (
    "('LOGIN_START_IP', 'LOGIN_START_DEVICE', 'CALLBACK_FAILURE_IP', "
    "'PASSWORD_FAILURE_IP')"
)


def upgrade() -> None:
    op.create_table(
        "rate_limit_counter",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("scope", sa.String(40), nullable=False),
        sa.Column("subject_hash", sa.String(64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hits", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "scope", "subject_hash", "window_start", name="uq_rate_limit_bucket"
        ),
        sa.CheckConstraint(f"scope IN {_SCOPES}", name="ck_rate_limit_scope_enum"),
        sa.CheckConstraint("hits > 0", name="ck_rate_limit_hits"),
    )
    # The sweep's index. Without it retention becomes a table scan on the table
    # that grows fastest under attack — exactly when it must not.
    op.create_index("ix_rate_limit_expiry", "rate_limit_counter", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_rate_limit_expiry", table_name="rate_limit_counter")
    op.drop_table("rate_limit_counter")
