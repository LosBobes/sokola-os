"""M03 §5.2: one security record per school.

`School.status` stays M04's and remains the authority on whether a school is
operating (§5.1). This table answers a different question: *when did this
school's access last have to become stale immediately?*

The two are needed together. Reading `School.status` on every request is what
makes a deactivation take effect — and that already happens. But a status column
cannot express "everything issued before this moment is now suspect", which is
what a security revision is for: a monotone number that any cached context,
secondary projection or open channel can be compared against and found old.

Deliberately not here: any per-person state. §5.2 is one row per school, and a
table that also knew who was in the school would make M03 a second owner of
M06's membership.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.domains.tenancy.enums import TenantInvalidationReason


class TenantSecurityState(Base, TimestampMixin):
    """§5.2. Exactly one row per school, created with the school itself."""

    __tablename__ = "tenant_security_state"
    __table_args__ = (
        # §5.2 verbatim. A reason without a time (or the reverse) is a
        # half-written invalidation, and the reason is the only part that
        # survives into the audit trail.
        CheckConstraint(
            "(last_invalidated_at IS NULL) = (last_invalidation_reason_code IS NULL)",
            name="ck_tenant_security_invalidation_pair",
        ),
        CheckConstraint(
            "tenant_access_version >= 1", name="ck_tenant_security_access_version"
        ),
        CheckConstraint("version >= 1", name="ck_tenant_security_version"),
    )

    #: PK *and* FK: §5.2 says exactly 1:1, and a surrogate key would allow two
    #: security states for one school — which is two answers to a question that
    #: must have one.
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="RESTRICT"), primary_key=True
    )
    #: Monotone, +1 per tenant-wide invalidation. Compared rather than trusted:
    #: §5.2 is explicit that reading `School.status` stays mandatory, and this
    #: is what additionally lets a stale context be recognised as stale.
    tenant_access_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    last_invalidated_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_invalidation_reason_code: Mapped[TenantInvalidationReason | None] = mapped_column(
        enum_type(TenantInvalidationReason), nullable=True
    )
    #: Optimistic concurrency for the row. Separate from the access version for
    #: the same reason M01 separates them: a harmless concurrent edit must not
    #: read as a security event.
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


__all__ = ["TenantSecurityState"]
