from __future__ import annotations

from sqlalchemy import (
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, RecordStatusMixin, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.structure.enums import LocationKind


class Category(Base, TimestampMixin, RecordStatusMixin):
    """A program category (kategorija programa) inside one school. A light
    grouping label for programs; carries no schedule or finance of its own."""

    __tablename__ = "structure_category"
    __table_args__ = (
        Index("ix_structure_category_school", "school_id"),
        # M03 §7.2: the composite target another tenant table's foreign key
        # names. It adds no uniqueness — `id` is already the primary key — but
        # it lets a child's reference carry the tenant *as part of the
        # reference*, which is what makes a cross-tenant link impossible rather
        # than merely incorrect.
        UniqueConstraint("school_id", "id", name="uq_structure_category_tenant"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("cat"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)


class Program(Base, TimestampMixin, RecordStatusMixin):
    """A program offered by one school (e.g. a discipline or course). May
    be grouped under a :class:`Category`. Its optional internal code is unique
    among the school's active programs."""

    __tablename__ = "structure_program"
    __table_args__ = (
        Index("ix_structure_program_school", "school_id"),
        Index("ix_structure_program_school_code", "school_id", "internal_code"),
        # M03 §7.2: the composite target another tenant table's foreign key
        # names. It adds no uniqueness — `id` is already the primary key — but
        # it lets a child's reference carry the tenant *as part of the
        # reference*, which is what makes a cross-tenant link impossible rather
        # than merely incorrect.
        UniqueConstraint("school_id", "id", name="uq_structure_program_tenant"),
        # `SET NULL (category_id)` names the column, because the default would
        # try to null `school_id` too and that column is NOT NULL. Postgres 15+
        # takes the column list; the repo runs 16.
        ForeignKeyConstraint(
            ["school_id", "category_id"],
            ["structure_category.school_id", "structure_category.id"],
            name="fk_structure_program_category_tenant",
            ondelete="SET NULL (category_id)",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("prg"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    category_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    internal_code: Mapped[str | None] = mapped_column(String(60), nullable=True)


class Location(Base, TimestampMixin, RecordStatusMixin):
    """A place (lokacija) where an school's activities happen: a branch, a
    hall, a pitch, a kindergarten, a theatre, the outdoors, or an online room.
    Rooms belong to it. Its optional internal code is unique among the
    school's active locations.

    ``kind`` classifies the place (see :class:`LocationKind`). It is descriptive
    only, nothing in scheduling, billing or attendance branches on it, so adding
    a kind later never changes behaviour of existing rows.
    """

    __tablename__ = "structure_location"
    __table_args__ = (
        Index("ix_structure_location_school", "school_id"),
        Index("ix_structure_location_school_code", "school_id", "internal_code"),
        # M03 §7.2: the composite target another tenant table's foreign key
        # names. It adds no uniqueness — `id` is already the primary key — but
        # it lets a child's reference carry the tenant *as part of the
        # reference*, which is what makes a cross-tenant link impossible rather
        # than merely incorrect.
        UniqueConstraint("school_id", "id", name="uq_structure_location_tenant"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("loc"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[LocationKind] = mapped_column(
        enum_type(LocationKind), nullable=False, default=LocationKind.OTHER
    )
    address: Mapped[str | None] = mapped_column(String(400), nullable=True)
    internal_code: Mapped[str | None] = mapped_column(String(60), nullable=True)


class Room(Base, TimestampMixin, RecordStatusMixin):
    """A space (prostor) inside a :class:`Location`. Carries a capacity and an
    optional internal code unique among the school's active rooms."""

    __tablename__ = "structure_room"
    __table_args__ = (
        Index("ix_structure_room_school", "school_id"),
        Index("ix_structure_room_school_code", "school_id", "internal_code"),
        # A room in another school's location is now impossible rather than
        # merely wrong. CASCADE is kept: deleting a location still takes its
        # rooms, which is the existing behaviour and the sensible one.
        ForeignKeyConstraint(
            ["school_id", "location_id"],
            ["structure_location.school_id", "structure_location.id"],
            name="fk_structure_room_location_tenant",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("room"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    internal_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
