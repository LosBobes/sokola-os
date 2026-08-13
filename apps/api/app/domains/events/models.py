from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
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
    (venues, ticketing, POS) is explicitly out of P0 scope.)"""

    __tablename__ = "event"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("evt"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
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


class EventRegistration(Base, TimestampMixin):
    """A child's registration for an event. Registration is child-membership based;
    cancellation is a status change, never a deletion (history stays canonical)."""

    __tablename__ = "event_registration"
    __table_args__ = (
        UniqueConstraint("event_id", "child_person_id", name="uq_event_registration"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("erg"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[str] = mapped_column(
        ForeignKey("event.id", ondelete="CASCADE"), nullable=False
    )
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
