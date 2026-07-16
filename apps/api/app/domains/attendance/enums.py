from __future__ import annotations

import enum


class AttendanceStatus(enum.StrEnum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    EXCUSED = "EXCUSED"
    LATE = "LATE"


class AttendanceOverrideReasonCode(enum.StrEnum):
    LATE_ARRIVAL = "LATE_ARRIVAL"
    EARLY_LEAVE = "EARLY_LEAVE"
    EXCUSED_ABSENCE = "EXCUSED_ABSENCE"
    OTHER = "OTHER"
