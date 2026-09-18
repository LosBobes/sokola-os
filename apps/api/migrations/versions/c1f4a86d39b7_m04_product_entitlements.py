"""M04 product entitlements: commercial availability, per school

M04 §2.8. One row per grant, history never rewritten.

The partial unique index on (school_id, capability_key) WHERE status = 'ACTIVE'
carries "at most one active grant per capability". It deliberately does not, and
cannot, carry *effectiveness*: §3.8.2–3.8.3 make that a read-time decision over
the validity window, the school's status and whether the granting organization
is still the school's current one. ACTIVE is necessary, never sufficient — see
app/domains/school/entitlements.py::is_effective.

No backfill. §3.8.1 and §9.5 together say it plainly: an entitlement is granted
by a platform actor with a commercial reference, and a school that lacks one
does not get an invented grant — it gets a remediation note. CORE_MVP in
particular does not arise from an organization link (§2.8). So every existing
school starts with no entitlement, and SCH-04 activation's CORE_MVP guard is
fail-closed until a platform actor grants one, which is what §3.5.6 intends.

Revision ID: c1f4a86d39b7
Revises: b9e3c05a74d2
Create Date: 2026-09-18 21:35:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c1f4a86d39b7'
down_revision: str | None = 'b9e3c05a74d2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CAPABILITIES = "('CORE_MVP', 'MYSOKOLA_BASIC', 'OPERATIONS')"
_STATUSES = "('ACTIVE', 'REVOKED', 'EXPIRED')"
_GRANT_REASONS = (
    "('CONTRACT_ACTIVATED', 'PILOT_APPROVED', 'PLAN_CHANGED', "
    "'ORGANIZATION_TRANSFER', 'REPLACED')"
)
_REVOKE_REASONS = (
    "('CONTRACT_SUSPENDED', 'CONTRACT_ENDED', 'PILOT_ENDED', 'PLAN_CHANGED', "
    "'ORGANIZATION_TRANSFER', 'SECURITY_RESTRICTION', 'REPLACED', 'ENTITLEMENT_EXPIRED')"
)


def upgrade() -> None:
    op.create_table(
        "school_product_entitlement",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("school_id", sa.String(64), sa.ForeignKey("school.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_organization_id", sa.String(64), sa.ForeignKey("organization.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("capability_key", sa.String(40), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("commercial_reference", sa.String(64), nullable=False),
        sa.Column("granted_by_actor_ref", sa.String(64), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("grant_reason_code", sa.String(40), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revocation_reason_code", sa.String(40), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(f"capability_key IN {_CAPABILITIES}", name="ck_entitlement_capability"),
        sa.CheckConstraint(f"status IN {_STATUSES}", name="ck_entitlement_status"),
        sa.CheckConstraint(f"grant_reason_code IN {_GRANT_REASONS}", name="ck_entitlement_grant_reason_value"),
        sa.CheckConstraint(
            f"revocation_reason_code IS NULL OR revocation_reason_code IN {_REVOKE_REASONS}",
            name="ck_entitlement_revoke_reason_value",
        ),
        sa.CheckConstraint("valid_until IS NULL OR valid_until > valid_from", name="ck_entitlement_period"),
        sa.CheckConstraint("(status = 'REVOKED') = (revoked_at IS NOT NULL)", name="ck_entitlement_revoked_at"),
        sa.CheckConstraint("(status = 'REVOKED') = (revocation_reason_code IS NOT NULL)", name="ck_entitlement_revoke_reason"),
        sa.CheckConstraint("(status = 'EXPIRED') = (expired_at IS NOT NULL)", name="ck_entitlement_expired_at"),
        sa.CheckConstraint("status <> 'EXPIRED' OR valid_until IS NOT NULL", name="ck_entitlement_expired_needs_window"),
        sa.CheckConstraint("version >= 1", name="ck_entitlement_version"),
    )
    op.create_index(
        "uq_entitlement_active_capability",
        "school_product_entitlement",
        ["school_id", "capability_key"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )
    op.create_index(
        "ix_entitlement_school_capability",
        "school_product_entitlement",
        ["school_id", "capability_key", "status"],
    )


def downgrade() -> None:
    op.drop_table("school_product_entitlement")
