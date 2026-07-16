from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, RecordStatusMixin, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.organization.enums import MembershipStatus, OrganizationType


class Organization(Base, TimestampMixin, RecordStatusMixin):
    """A tenant. The root of the isolation boundary: nearly every other row
    carries this id and is filtered by it server-side."""

    __tablename__ = "organization"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("org"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[OrganizationType] = mapped_column(
        enum_type(OrganizationType), nullable=False, default=OrganizationType.OTHER
    )
    # IANA timezone; recurring schedules are interpreted against this.
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Belgrade")


class OrganizationMembership(Base, TimestampMixin, RecordStatusMixin):
    """A person's belonging to an organization. This is the relationship that
    makes a global Person visible inside a tenant. Ending it opens no new period;
    reactivation is a new membership period (see billing/attendance patterns)."""

    __tablename__ = "organization_membership"
    __table_args__ = (
        UniqueConstraint("organization_id", "person_id", name="uq_org_membership"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("mem"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[MembershipStatus] = mapped_column(
        enum_type(MembershipStatus), nullable=False, default=MembershipStatus.ACTIVE
    )
