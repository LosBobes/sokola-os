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
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_random_id
from app.domains.tenancy.enums import (
    ContextInvalidationReason,
    TenantContextStatus,
    TenantInvalidationReason,
)


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


class SessionTenantContext(Base, TimestampMixin):
    """§5.3. Which school one signed-in session is currently working in.

    At most one row per M01 session — §5.3 is explicit that earlier choices live
    in the audit trail, not as parallel active rows, because "which school is
    this session in" must have exactly one answer at any moment.

    This is **preference and routing state, not a proof of rights**. §5.3 says
    so directly, and it is the sentence that shapes every column here: there is
    no permission list, no guardian scope, no financial subject and no copy of
    tenant data. What the row holds is a choice, plus three version snapshots
    taken when the choice was made.

    Those snapshots are the point. §8 step 3 compares each against its live
    authority before any protected work, so a context survives only while the
    world it was chosen in still holds:

    * ``context_version`` — moved by this session's own select/switch/clear, so
      a slow response from school A cannot commit after a switch to B (§10);
    * ``tenant_access_version_at_selection`` — moved by M03 when the school's
      access is invalidated wholesale;
    * ``authorization_version_at_selection`` — moved by M01 when the account's
      access is invalidated.

    None of them is a standing permission. §5.3: "nije trajni allow dokaz" —
    they can only make a context *stale*, never make one sufficient.
    """

    __tablename__ = "session_tenant_context"
    __table_args__ = (
        # §5.3, written as the spec writes it: ACTIVE has neither stamp,
        # INVALIDATED has both. A context that ended without a recorded reason
        # is the one a security review most needs and least often gets.
        CheckConstraint(
            "(status = 'ACTIVE'"
            " AND invalidated_at IS NULL AND invalidation_reason_code IS NULL)"
            " OR (status = 'INVALIDATED'"
            " AND invalidated_at IS NOT NULL AND invalidation_reason_code IS NOT NULL)",
            name="ck_session_context_status_pair",
        ),
        CheckConstraint("context_version >= 1", name="ck_session_context_version"),
        CheckConstraint(
            "tenant_access_version_at_selection >= 1",
            name="ck_session_context_tenant_version",
        ),
        CheckConstraint(
            "authorization_version_at_selection >= 1",
            name="ck_session_context_auth_version",
        ),
        CheckConstraint("version >= 1", name="ck_session_context_row_version"),
        Index(
            "ix_session_context_school_live",
            "school_id",
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_random_id("stc")
    )
    #: `UNIQUE` per §5.3: at most one current context per session. Two rows
    #: would be two answers to "which school is this session in".
    session_id: Mapped[str] = mapped_column(
        ForeignKey("auth_session.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    #: Derived server-side from the session, never accepted from a client. §5.3
    #: requires it to match the session's account, and the only way to be sure
    #: of that is to not ask.
    user_account_id: Mapped[str] = mapped_column(
        ForeignKey("user_account.id", ondelete="CASCADE"), nullable=False
    )
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="RESTRICT"), nullable=False
    )
    #: Display focus only, from the closed registry in `enums`. Deliberately no
    #: foreign key to anything in M05: §5.3 says "nema FK ka M05 i nije
    #: authorization dokaz", and a foreign key is how a display field quietly
    #: becomes a permission field.
    workspace_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[TenantContextStatus] = mapped_column(
        enum_type(TenantContextStatus), nullable=False, default=TenantContextStatus.ACTIVE
    )
    context_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    tenant_access_version_at_selection: Mapped[int] = mapped_column(
        BigInteger, nullable=False
    )
    authorization_version_at_selection: Mapped[int] = mapped_column(
        BigInteger, nullable=False
    )
    selected_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    #: An operational trace, and §5.3 is careful to say it "ne dozvoljava
    #: preskakanje nove provere" — writing it down does not buy a request out
    #: of doing the checks again.
    last_validated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    invalidated_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    invalidation_reason_code: Mapped[ContextInvalidationReason | None] = mapped_column(
        enum_type(ContextInvalidationReason), nullable=True
    )
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)

    @property
    def is_active(self) -> bool:
        return self.status is TenantContextStatus.ACTIVE


__all__ = ["SessionTenantContext", "TenantSecurityState"]
