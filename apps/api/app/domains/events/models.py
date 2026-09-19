from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, RecordStatusMixin, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.events.enums import (
    CancellationReasonCode,
    EventCapacityMode,
    EventCategory,
    EventStatus,
    EventType,
    RegistrationStatus,
)


class Event(Base, TimestampMixin, RecordStatusMixin):
    """A light event: a thing children can be registered for. (The full Events ERP
    (venues, ticketing, POS) is explicitly out of P0 scope.)

    Events share the Raspored calendar with training sessions, so they carry the
    same handful of facts a session does , when, where, who is responsible , plus
    a free-text description. ``location_id`` is the one structured place;
    ``location_note`` carries the detail a single row cannot ("Zlatibor , hotel
    'X', teren 'Y'"), because a multi-venue camp is one event, not several.
    """

    __tablename__ = "event"
    __table_args__ = (
        # M03 §7.3: an event cannot name another school's location.
        ForeignKeyConstraint(
            ["school_id", "location_id"],
            ["structure_location.school_id", "structure_location.id"],
            name="fk_event_location_tenant",
            ondelete="SET NULL (location_id)",
        ),
        # M03 §7.2: the composite target another tenant table's foreign key
        # names. It adds no uniqueness — `id` is already the primary key — but
        # it lets a child's reference carry the tenant *as part of the
        # reference*, which is what makes a cross-tenant link impossible rather
        # than merely incorrect.
        UniqueConstraint("school_id", "id", name="uq_event_tenant"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("evt"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[EventType] = mapped_column(
        enum_type(EventType), nullable=False, default=EventType.OTHER
    )
    category: Mapped[EventCategory] = mapped_column(
        enum_type(EventCategory), nullable=False, default=EventCategory.INTERNAL
    )
    status: Mapped[EventStatus] = mapped_column(
        enum_type(EventStatus), nullable=False, default=EventStatus.PUBLISHED
    )
    capacity_mode: Mapped[EventCapacityMode] = mapped_column(
        enum_type(EventCapacityMode), nullable=False, default=EventCapacityMode.UNLIMITED
    )
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    starts_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # SET NULL: archiving a location must never delete the event's history.
    location_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location_note: Mapped[str | None] = mapped_column(String(400), nullable=True)
    responsible_person_id: Mapped[str | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class EventRegistration(Base, TimestampMixin):
    """A child's registration for an event. Registration is child-membership based;
    cancellation is a status change, never a deletion (history stays canonical)."""

    __tablename__ = "event_registration"
    __table_args__ = (
        UniqueConstraint("event_id", "child_person_id", name="uq_event_registration"),
        # A child cannot be registered for another school's event. §7.3.
        ForeignKeyConstraint(
            ["school_id", "event_id"],
            ["event.school_id", "event.id"],
            name="fk_event_registration_event_tenant",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("erg"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    child_person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    registered_by_person_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[RegistrationStatus] = mapped_column(
        enum_type(RegistrationStatus), nullable=False, default=RegistrationStatus.REGISTERED
    )
    cancellation_reason: Mapped[CancellationReasonCode | None] = mapped_column(
        enum_type(CancellationReasonCode), nullable=True
    )
