from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, RecordStatusMixin, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.groups.enums import GroupCapacityMode, GroupMembershipEndReason


class Group(Base, TimestampMixin, RecordStatusMixin):
    """A training group inside one organization. Rosters for scheduling and
    attendance are derived from active group memberships."""

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


class GroupMembership(Base, TimestampMixin):
    """A person's active place in a group. Ending it records a reason and closes
    the period; it is never hard-deleted."""

    __tablename__ = "group_membership"
    __table_args__ = (
        UniqueConstraint("group_id", "person_id", name="uq_group_membership"),
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
    joined_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_reason: Mapped[GroupMembershipEndReason | None] = mapped_column(
        enum_type(GroupMembershipEndReason), nullable=True
    )
