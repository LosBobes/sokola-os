from __future__ import annotations

from pydantic import BaseModel, Field

from app.domains.attendance.enums import AttendanceOverrideReasonCode, AttendanceStatus
from app.domains.progress.enums import ProgressLevel


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


class AttendanceProgressNoteInput(BaseModel):
    """A progress note (PRD 06 M2) attached to this attendance save. Optional —
    a trainer taking attendance may jot a note about a roster member without
    leaving the sheet; equivalent to a standalone POST to
    ``/people/{person_id}/progress-notes`` scoped to this session's group."""

    person_id: str
    note: str = Field(min_length=1, max_length=2000)
    level: ProgressLevel | None = None


class SaveAttendanceRequest(BaseModel):
    attendance_version: int = Field(ge=0)
    # Only the people who differ from the PRESENT default are sent.
    exceptions: list[AttendanceException] = Field(default_factory=list)
    # Optional: notes for any roster member, saved atomically with attendance.
    progress_notes: list[AttendanceProgressNoteInput] = Field(default_factory=list)


class SaveAttendanceResponse(BaseModel):
    session_id: str
    attendance_version: int
    present: int
    absent: int
    excused: int
    late: int
    progress_notes_saved: int = 0
