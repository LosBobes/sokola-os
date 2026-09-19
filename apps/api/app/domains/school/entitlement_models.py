"""`SchoolProductEntitlement` (M04 §2.8): what a school has been sold.

The contractual holder is the school's current organization; the *executable*
subject is always the school tenant. That split is the whole point of the table:
an organization can hold five schools and buy the product for one of them, and
nothing about the other four changes.

An entitlement grants nobody access (§2.8, §3.8.7). It is one layer of
``environment → product entitlement → tenant allowlist → capability flag →
M05 permission → M03/M07 guard``, and each layer still has to pass.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.school.entitlement_enums import (
    CapabilityKey,
    EntitlementGrantReason,
    EntitlementRevokeReason,
    EntitlementStatus,
)


class SchoolProductEntitlement(Base, TimestampMixin):
    """§2.8. One row per grant; history is never rewritten to hide a superseded
    commercial reference."""

    __tablename__ = "school_product_entitlement"
    __table_args__ = (
        # At most one ACTIVE grant per (school, capability). Partial, because
        # revoked and expired rows are the history this table exists to keep.
        #
        # Note what this does *not* say: ACTIVE is necessary for effectiveness,
        # never sufficient. A row inside its validity window is decided at read
        # time by `is_effective`, because `now >= valid_until` makes a grant
        # ineffective whether or not a job has stamped it EXPIRED (§3.8.3).
        Index(
            "uq_entitlement_active_capability",
            "school_id",
            "capability_key",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
        Index("ix_entitlement_school_capability", "school_id", "capability_key", "status"),
        CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from", name="ck_entitlement_period"
        ),
        CheckConstraint(
            "(status = 'REVOKED') = (revoked_at IS NOT NULL)", name="ck_entitlement_revoked_at"
        ),
        CheckConstraint(
            "(status = 'REVOKED') = (revocation_reason_code IS NOT NULL)",
            name="ck_entitlement_revoke_reason",
        ),
        CheckConstraint(
            "(status = 'EXPIRED') = (expired_at IS NOT NULL)", name="ck_entitlement_expired_at"
        ),
        # A materialized EXPIRED must be consistent with the window that caused
        # it: expiring a grant that has no end is a contradiction on its face.
        CheckConstraint(
            "status <> 'EXPIRED' OR valid_until IS NOT NULL",
            name="ck_entitlement_expired_needs_window",
        ),
        CheckConstraint("version >= 1", name="ck_entitlement_version"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("ent"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    #: Must have been the school's current organization at ``valid_from``. Kept
    #: on the row rather than derived, because an organization transfer later
    #: must not silently rewrite who sold this.
    source_organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="RESTRICT"), nullable=False
    )
    capability_key: Mapped[CapabilityKey] = mapped_column(
        enum_type(CapabilityKey), nullable=False
    )
    status: Mapped[EntitlementStatus] = mapped_column(
        enum_type(EntitlementStatus), nullable=False, default=EntitlementStatus.ACTIVE
    )
    valid_from: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Approved contract / pilot / plan reference. Carries no amount and no PII.
    commercial_reference: Mapped[str] = mapped_column(String(64), nullable=False)
    granted_by_actor_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    granted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: Why this grant was created. ``REPLACED`` is a system code.
    grant_reason_code: Mapped[EntitlementGrantReason] = mapped_column(
        enum_type(EntitlementGrantReason), nullable=False
    )
    revoked_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revocation_reason_code: Mapped[EntitlementRevokeReason | None] = mapped_column(
        enum_type(EntitlementRevokeReason), nullable=True
    )
    #: Set when a job materializes the expiry. Never what a reader consults.
    expired_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
