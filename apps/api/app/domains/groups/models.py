from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, RecordStatusMixin, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.common.money import zero
from app.domains.groups.enums import (
    GroupCapacityMode,
    GroupMemberRole,
    GroupMembershipEndReason,
    GroupMembershipStatus,
)


class Group(Base, TimestampMixin, RecordStatusMixin):
    """A training group inside one organization. Rosters for scheduling and
    attendance are derived from active group memberships.

    ``program_id``/``location_id`` link the group into the structure domain
    (PRD 04 M4), nullable so a group can exist before either is assigned, and
    ``SET NULL`` so archiving a program/location never destroys group history.
    Only the *models* are imported here (cross-domain model imports are
    allowed); validation that an id belongs to the caller's org happens in this
    domain's own repository/service, never by calling structure's service.

    ``base_monthly_price`` is the group's list price as an exact decimal
    amount (PRD 04 M1), ``None`` means pricing has
    not been configured yet. Billing (PRD 07) reads this directly; per-member
    discounts live on :class:`GroupMembership`.
    """

    __tablename__ = "group"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("grp"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    capacity_mode: Mapped[GroupCapacityMode] = mapped_column(
        enum_type(GroupCapacityMode), nullable=False, default=GroupCapacityMode.UNLIMITED
    )
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    program_id: Mapped[str | None] = mapped_column(
        ForeignKey("structure_program.id", ondelete="SET NULL"), nullable=True
    )
    location_id: Mapped[str | None] = mapped_column(
        ForeignKey("structure_location.id", ondelete="SET NULL"), nullable=True
    )
    base_monthly_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    # Defaults a new session for this group inherits (PRD note "grupa kao osnova").
    # They are a starting value copied onto the session at create time, never a
    # live link: changing a group's default trainer must not silently rewrite
    # who led last Tuesday's training. Whoever creates the session may override
    # both for that occurrence alone.
    default_trainer_person_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
    default_location_id: Mapped[str | None] = mapped_column(
        ForeignKey("structure_location.id", ondelete="SET NULL"), nullable=True
    )


class GroupMembership(Base, TimestampMixin):
    """A person's place in a group. Never hard-deleted: lifecycle transitions
    (PRD 04 M2) update ``status`` in place, and ending records ``end_reason``
    and closes the period via ``ended_at``. ``status`` is the source of truth;
    ``ENDED`` is terminal, so a partial unique index (not a plain unique
    constraint) lets the same person rejoin the same group as a fresh row after
    a prior membership ended.

    ``discount`` is a per-member discount against ``Group.base_monthly_price``,
    expressed as an ABSOLUTE amount in the same currency
    unit (not a percentage), billing computes what this member owes as
    ``max(base_monthly_price - discount, 0)``. An absolute amount
    keeps that arithmetic exact and rounding-free, unlike a percentage.
    """

    __tablename__ = "group_membership"
    __table_args__ = (
        Index(
            "uq_group_membership_active",
            "group_id",
            "person_id",
            unique=True,
            postgresql_where=text("status != 'ENDED'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("gmb"))
    group_id: Mapped[str] = mapped_column(
        ForeignKey("group.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    # Participant vs. staff. See :class:`GroupMemberRole`: only MEMBER rows are
    # rostered for attendance and billed.
    role: Mapped[GroupMemberRole] = mapped_column(
        enum_type(GroupMemberRole), nullable=False, default=GroupMemberRole.MEMBER
    )
    joined_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[GroupMembershipStatus] = mapped_column(
        enum_type(GroupMembershipStatus), nullable=False, default=GroupMembershipStatus.ACTIVE
    )
    discount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=zero)
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_reason: Mapped[GroupMembershipEndReason | None] = mapped_column(
        enum_type(GroupMembershipEndReason), nullable=True
    )
