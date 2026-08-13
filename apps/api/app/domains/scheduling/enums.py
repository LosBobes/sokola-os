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
    TRAINER_CHANGE = "TRAINER_CHANGE"
    OTHER = "OTHER"


class SessionEditScope(enum.StrEnum):
    """Calendar-style edit scope for a session that belongs to a series.

    * ``SINGLE``, change only this one occurrence; the series is untouched.
    * ``THIS_AND_FUTURE``, change the series template and every scheduled
      occurrence from this one forward; past occurrences keep their old values.
    * ``ALL_FUTURE``, change the series template and every upcoming scheduled
      occurrence (from now on), regardless of which occurrence was edited.
    """

    SINGLE = "SINGLE"
    THIS_AND_FUTURE = "THIS_AND_FUTURE"
    ALL_FUTURE = "ALL_FUTURE"
