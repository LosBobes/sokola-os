"""M03 tenant security state, and the dead workspace table goes

M03 §5.2, §5.5 (TEN-05), TEN-04.

`School.status` stays M04's and remains the authority on whether a school
operates. This table answers a different question: *when did this school's
access last have to become stale immediately?*

Both are needed. Re-reading `School.status` on every request is what makes a
deactivation take effect, and that already happens. But a status column cannot
express "everything issued before this moment is now suspect", which is what a
security revision is for — a monotone number that any cached context, secondary
projection or open channel can be compared against and found old.

Backfill: one row per existing school at `tenant_access_version = 1`. That is a
statement of fact, not a guess — nothing has ever invalidated a tenant here, so
one is the true count, and §5.2's default is 1.

Also drops `workspace`. It was a reserved placeholder ("present so the model is
future-shaped, not future-built"), never written, never read, with no inbound
foreign keys and no reference anywhere in the API, tests, scripts or the web
app. M04's `organization` and `school_product_entitlement` have since taken the
role it was holding, and its name now collides with M03 §3's `workspace_key`,
which is a display focus with no table — two concepts under one name is how the
next reader gets confused about which one guards anything.

Revision ID: e5f83a19d24b
Revises: d7b25c48a139
Create Date: 2026-09-19 17:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e5f83a19d24b'
down_revision: str | None = 'd7b25c48a139'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REASONS = (
    "('SCHOOL_DEACTIVATED', 'SCHOOL_REACTIVATED', 'SECURITY_INCIDENT', "
    "'OWNERSHIP_TRANSFERRED', 'SUPPORT_ACCESS_REVOKED', 'PLATFORM_POLICY', "
    "'LEGAL_HOLD')"
)


def upgrade() -> None:
    op.create_table(
        "tenant_security_state",
        # PK *and* FK: §5.2 says exactly 1:1, and a surrogate key would allow
        # two security states for one school — two answers to a question that
        # must have one.
        sa.Column(
            "school_id", sa.String(64),
            sa.ForeignKey("school.id", ondelete="RESTRICT"), primary_key=True,
        ),
        sa.Column("tenant_access_version", sa.BigInteger(), nullable=False),
        sa.Column("last_invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_invalidation_reason_code", sa.String(40), nullable=True),
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
            f"last_invalidation_reason_code IS NULL "
            f"OR last_invalidation_reason_code IN {_REASONS}",
            name="ck_tenant_security_reason_enum",
        ),
        sa.CheckConstraint(
            "(last_invalidated_at IS NULL) = (last_invalidation_reason_code IS NULL)",
            name="ck_tenant_security_invalidation_pair",
        ),
        sa.CheckConstraint(
            "tenant_access_version >= 1", name="ck_tenant_security_access_version"
        ),
        sa.CheckConstraint("version >= 1", name="ck_tenant_security_version"),
    )

    # One row per school that already exists. Nothing has ever invalidated a
    # tenant here, so 1 is the true count rather than a placeholder.
    op.execute(
        """
        INSERT INTO tenant_security_state (
            school_id, tenant_access_version, version
        )
        SELECT id, 1, 1 FROM school
        ON CONFLICT (school_id) DO NOTHING
        """
    )

    op.drop_table("workspace")


def downgrade() -> None:
    op.create_table(
        "workspace",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("owner_person_id", sa.String(64), nullable=True),
        sa.Column("record_status", sa.String(40), nullable=False, server_default="ACTIVE"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
            nullable=False,
        ),
    )
    # Recreated empty, which loses nothing: the table never held a row, and a
    # downgrade that invented data to look thorough would be worse than one that
    # is honest about there being none.
    op.drop_table("tenant_security_state")
