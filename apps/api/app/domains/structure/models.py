from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, RecordStatusMixin, TimestampMixin
from app.common.ids import new_id


class Category(Base, TimestampMixin, RecordStatusMixin):
    """A program category (kategorija programa) inside one organization. A light
    grouping label for programs; carries no schedule or finance of its own."""

    __tablename__ = "structure_category"
    __table_args__ = (Index("ix_structure_category_org", "organization_id"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("cat"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)


class Program(Base, TimestampMixin, RecordStatusMixin):
    """A program offered by one organization (e.g. a discipline or course). May
    be grouped under a :class:`Category`. Its optional internal code is unique
    among the organization's active programs."""

    __tablename__ = "structure_program"
    __table_args__ = (
        Index("ix_structure_program_org", "organization_id"),
        Index("ix_structure_program_org_code", "organization_id", "internal_code"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("prg"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[str | None] = mapped_column(
        ForeignKey("structure_category.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    internal_code: Mapped[str | None] = mapped_column(String(60), nullable=True)


class Location(Base, TimestampMixin, RecordStatusMixin):
    """A branch (ogranak) of an organization: a physical place where activities
    happen. Rooms belong to it. Its optional internal code is unique among the
    organization's active locations."""

    __tablename__ = "structure_location"
    __table_args__ = (
        Index("ix_structure_location_org", "organization_id"),
        Index("ix_structure_location_org_code", "organization_id", "internal_code"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("loc"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    address: Mapped[str | None] = mapped_column(String(400), nullable=True)
    internal_code: Mapped[str | None] = mapped_column(String(60), nullable=True)


class Room(Base, TimestampMixin, RecordStatusMixin):
    """A space (prostor) inside a :class:`Location`. Carries a capacity and an
    optional internal code unique among the organization's active rooms."""

    __tablename__ = "structure_room"
    __table_args__ = (
        Index("ix_structure_room_org", "organization_id"),
        Index("ix_structure_room_org_code", "organization_id", "internal_code"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("room"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[str] = mapped_column(
        ForeignKey("structure_location.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    internal_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
