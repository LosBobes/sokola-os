from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, RecordStatusMixin, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.scheduling.enums import (
    SessionCancellationReasonCode,
    SessionSeriesFrequency,
    SessionStatus,
)


class SessionSeries(Base, TimestampMixin, RecordStatusMixin):
    """A recurring template. Stores LOCAL time + timezone; concrete sessions are
    materialized to UTC. (Generation is future work; the record is present so the
    model is future-shaped.)"""

    __tablename__ = "session_series"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("ses"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    group_id: Mapped[str] = mapped_column(
        ForeignKey("group.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    frequency: Mapped[SessionSeriesFrequency] = mapped_column(
        enum_type(SessionSeriesFrequency), nullable=False
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Belgrade")
    local_time: Mapped[dt.time] = mapped_column(Time, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)


class Session(Base, TimestampMixin, RecordStatusMixin):
    """A concrete training session. Times are stored in UTC. A single-instance
    edit of a generated session is a *change* to that Session, never a
    destructive edit of its series."""

    __tablename__ = "session"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("ssn"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    group_id: Mapped[str] = mapped_column(
        ForeignKey("group.id", ondelete="CASCADE"), nullable=False
    )
    series_id: Mapped[str | None] = mapped_column(
        ForeignKey("session_series.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    starts_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[SessionStatus] = mapped_column(
        enum_type(SessionStatus), nullable=False, default=SessionStatus.SCHEDULED
    )
    cancellation_reason: Mapped[SessionCancellationReasonCode | None] = mapped_column(
        enum_type(SessionCancellationReasonCode), nullable=True
    )
    # Optimistic-concurrency guard for attendance edits.
    attendance_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
