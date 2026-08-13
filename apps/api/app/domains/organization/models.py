from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, RecordStatusMixin, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.organization.enums import (
    MembershipStatus,
    OrganizationLifecycleStatus,
    OrganizationType,
)


class Organization(Base, TimestampMixin, RecordStatusMixin):
    """A tenant. The root of the isolation boundary: nearly every other row
    carries this id and is filtered by it server-side."""

    __tablename__ = "organization"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("org"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Tenant discovery code used at login (unique). Nullable for legacy rows.
    slug: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    type: Mapped[OrganizationType] = mapped_column(
        enum_type(OrganizationType), nullable=False, default=OrganizationType.OTHER
    )
    # IANA timezone; recurring schedules are interpreted against this.
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Belgrade")
    # Guided-onboarding state (§24/§25), see OrganizationLifecycleStatus. Defaults
    # to ACTIVE so every row created outside the real signup path (fixtures,
    # legacy data) behaves normally; only ``create_organization`` opts a fresh
    # school into IN_PREPARATION.
    lifecycle_status: Mapped[OrganizationLifecycleStatus] = mapped_column(
        enum_type(OrganizationLifecycleStatus),
        nullable=False,
        default=OrganizationLifecycleStatus.ACTIVE,
    )


class OrganizationMembership(Base, TimestampMixin, RecordStatusMixin):
    """A person's belonging to an organization. This is the relationship that
    makes a global Person visible inside a tenant. Ending it opens no new period;
    reactivation is a new membership period (see billing/attendance patterns)."""

    __tablename__ = "organization_membership"
    __table_args__ = (
        UniqueConstraint("organization_id", "person_id", name="uq_org_membership"),
        # School-local member code is unique within the tenant *when set* (§8/§9).
        Index(
            "uq_org_local_member_code",
            "organization_id",
            "local_member_code",
            unique=True,
            postgresql_where=text("local_member_code IS NOT NULL"),
        ),
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
    # School-local ("na ruke") member data. Lives on the org-scoped membership, so
    # it is never shared across tenants and never touches the global Person.
    local_member_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    admin_note: Mapped[str | None] = mapped_column(Text, nullable=True)
