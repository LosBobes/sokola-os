"""M05 §2: who holds a platform role, and for how long.

One table, and the shape of it is the contract. §2 requires that a platform
assignment have **no `school_id`, no `Person` and no `SchoolMembership`** — it
attaches to a `UserAccount` and nothing else. A platform actor is not a member
of anything, and the absence of those columns is what stops a later reader
treating platform access as a tenant membership with a wider radius.

The lifecycle is append-and-stamp, never edit-in-place: a suspension records
who and why, a revoke the same, and the row keeps both. Rewriting status alone
would lose the one thing a security review needs — which decision happened
when, and on whose authority.
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
from app.domains.authorization.platform_enums import (
    PlatformRoleKey,
    PlatformRoleRevokeReason,
    PlatformRoleStatus,
    PlatformRoleSuspendReason,
)

#: The SQL fragment naming the non-terminal statuses, used by the partial
#: unique index below. Kept as one string so the index and
#: `OPEN_PLATFORM_ROLE_STATUSES` cannot describe different sets — a test
#: asserts they agree.
_OPEN_STATUSES_SQL = "status IN ('SCHEDULED', 'ACTIVE', 'SUSPENDED')"


class PlatformRoleAssignment(Base, TimestampMixin):
    """§2. One account's hold on one platform role, over one period."""

    __tablename__ = "platform_role_assignment"
    __table_args__ = (
        # §2: at most one *open* assignment per (account, role). Partial,
        # because a revoked or expired row is history — several per key are
        # expected, and a plain unique index would make re-granting the same
        # role to the same person impossible forever.
        Index(
            "uq_platform_role_assignment_open",
            "user_account_id",
            "role_key",
            unique=True,
            postgresql_where=text(_OPEN_STATUSES_SQL),
        ),
        Index("ix_platform_role_assignment_account", "user_account_id"),
        # §2: "Suspend/revoke trojke su sva polja ili nijedno." A half-written
        # suspension is a row that says someone lost access with no record of
        # who decided or why.
        CheckConstraint(
            "(suspended_at IS NULL) = (suspended_by_account_id IS NULL) "
            "AND (suspended_at IS NULL) = (suspend_reason_code IS NULL)",
            name="ck_platform_role_suspend_triple",
        ),
        CheckConstraint(
            "(revoked_at IS NULL) = (revoked_by_account_id IS NULL) "
            "AND (revoked_at IS NULL) = (revoke_reason_code IS NULL)",
            name="ck_platform_role_revoke_triple",
        ),
        # A terminal row carries its stamp, and a non-terminal one does not.
        CheckConstraint(
            "(status = 'REVOKED') = (revoked_at IS NOT NULL)",
            name="ck_platform_role_revoked_stamp",
        ),
        CheckConstraint(
            "(status = 'SUSPENDED') = (suspended_at IS NOT NULL)",
            name="ck_platform_role_suspended_stamp",
        ),
        # §2: PLATFORM_SECURITY_ADMIN is non-temporal. Expressed here rather
        # than only in the service, because an import or a fixture would
        # otherwise be able to create a security admin that quietly expires.
        CheckConstraint(
            "role_key <> 'PLATFORM_SECURITY_ADMIN' OR valid_until IS NULL",
            name="ck_platform_role_security_admin_not_temporal",
        ),
        CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name="ck_platform_role_window",
        ),
        CheckConstraint("version >= 1", name="ck_platform_role_version"),
        CheckConstraint(
            "length(btrim(source_ticket_ref)) BETWEEN 1 AND 100",
            name="ck_platform_role_ticket_ref",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: new_id("pra")
    )
    #: §2: an account, never a Person. A platform actor has no membership.
    user_account_id: Mapped[str] = mapped_column(
        ForeignKey("user_account.id", ondelete="RESTRICT"), nullable=False
    )
    role_key: Mapped[PlatformRoleKey] = mapped_column(
        enum_type(PlatformRoleKey), nullable=False
    )
    status: Mapped[PlatformRoleStatus] = mapped_column(
        enum_type(PlatformRoleStatus), nullable=False, default=PlatformRoleStatus.ACTIVE
    )
    valid_from: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    #: Null means open-ended, and for `PLATFORM_SECURITY_ADMIN` the CHECK above
    #: makes it the only legal value.
    valid_until: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: §2. The change-management record this grant answers to. Mandatory:
    #: platform access granted with no stated reason is the thing an audit is
    #: supposed to make impossible.
    source_ticket_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    created_by_account_id: Mapped[str] = mapped_column(
        ForeignKey("user_account.id", ondelete="RESTRICT"), nullable=False
    )

    suspended_by_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="RESTRICT"), nullable=True
    )
    suspended_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    suspend_reason_code: Mapped[PlatformRoleSuspendReason | None] = mapped_column(
        enum_type(PlatformRoleSuspendReason), nullable=True
    )

    revoked_by_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("user_account.id", ondelete="RESTRICT"), nullable=True
    )
    revoked_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoke_reason_code: Mapped[PlatformRoleRevokeReason | None] = mapped_column(
        enum_type(PlatformRoleRevokeReason), nullable=True
    )

    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
