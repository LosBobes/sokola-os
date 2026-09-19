from __future__ import annotations

from sqlalchemy import ForeignKey, ForeignKeyConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.attendance.enums import AttendanceOverrideReasonCode, AttendanceStatus


class AttendanceRecord(Base, TimestampMixin):
    """One person's attendance for one session. Written as a batch keyed by the
    session's ``attendance_version`` for optimistic concurrency."""

    __tablename__ = "attendance_record"
    __table_args__ = (
        UniqueConstraint("session_id", "person_id", name="uq_attendance_record"),
        # Attendance is taken for one of the school's own sessions. §7.3.
        ForeignKeyConstraint(
            ["school_id", "session_id"],
            ["session.school_id", "session.id"],
            name="fk_attendance_record_session_tenant",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("att"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(String(64), nullable=False)
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[AttendanceStatus] = mapped_column(
        enum_type(AttendanceStatus), nullable=False, default=AttendanceStatus.PRESENT
    )
    override_reason: Mapped[AttendanceOverrideReasonCode | None] = mapped_column(
        enum_type(AttendanceOverrideReasonCode), nullable=True
    )
