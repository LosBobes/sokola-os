from __future__ import annotations

import enum


class SessionSeriesFrequency(enum.StrEnum):
    WEEKLY = "WEEKLY"
    BIWEEKLY = "BIWEEKLY"
    MONTHLY = "MONTHLY"


class SessionStatus(enum.StrEnum):
    SCHEDULED = "SCHEDULED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class SessionCancellationReasonCode(enum.StrEnum):
    WEATHER = "WEATHER"
    TRAINER_UNAVAILABLE = "TRAINER_UNAVAILABLE"
    HOLIDAY = "HOLIDAY"
    LOW_ATTENDANCE = "LOW_ATTENDANCE"
    OTHER = "OTHER"


class SessionChangeReasonCode(enum.StrEnum):
    TIME_CHANGE = "TIME_CHANGE"
    LOCATION_CHANGE = "LOCATION_CHANGE"
    OTHER = "OTHER"
