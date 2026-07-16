from __future__ import annotations

from pydantic import BaseModel, Field

from app.domains.attendance.enums import AttendanceOverrideReasonCode, AttendanceStatus


class AttendanceEntry(BaseModel):
    person_id: str
    display_name: str
    status: AttendanceStatus


class AttendanceSheet(BaseModel):
    """The roster to display. Everyone defaults to PRESENT; the trainer edits only
    exceptions. ``attendance_version`` must be echoed back on save."""

    session_id: str
    attendance_version: int
    entries: list[AttendanceEntry]


class AttendanceException(BaseModel):
    person_id: str
    status: AttendanceStatus
    override_reason: AttendanceOverrideReasonCode | None = None


class SaveAttendanceRequest(BaseModel):
    attendance_version: int = Field(ge=0)
    # Only the people who differ from the PRESENT default are sent.
    exceptions: list[AttendanceException] = Field(default_factory=list)


class SaveAttendanceResponse(BaseModel):
    session_id: str
    attendance_version: int
    present: int
    absent: int
    excused: int
    late: int
