from __future__ import annotations

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.people.enums import GuardianAccessStatus, GuardianRelationshipType


class GuardianRelationship(Base, TimestampMixin):
    """A guardian↔child link at the global identity level (not org-scoped)."""

    __tablename__ = "guardian_relationship"
    __table_args__ = (
        UniqueConstraint("guardian_person_id", "child_person_id", name="uq_guardian_relationship"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("gdn"))
    guardian_person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    child_person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[GuardianRelationshipType] = mapped_column(
        enum_type(GuardianRelationshipType), nullable=False
    )


class GuardianOrganizationAccess(Base, TimestampMixin):
    """Scopes a guardian's access to a child's data to a specific organization.
    A parent sees a child only through an ACTIVE access row in the active org."""

    __tablename__ = "guardian_organization_access"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "guardian_person_id",
            "child_person_id",
            name="uq_guardian_org_access",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("goa"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    guardian_person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    child_person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[GuardianAccessStatus] = mapped_column(
        enum_type(GuardianAccessStatus), nullable=False, default=GuardianAccessStatus.ACTIVE
    )


class ExternalPersonReference(Base, TimestampMixin):
    """An organization's external/legacy identifier for a person (import lineage)."""

    __tablename__ = "external_person_reference"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "source", "external_id", name="uq_external_person_ref"
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("epr"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    external_id: Mapped[str] = mapped_column(String(120), nullable=False)
