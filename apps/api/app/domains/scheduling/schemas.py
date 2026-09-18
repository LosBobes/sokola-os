from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domains.scheduling.enums import (
    SessionCancellationReasonCode,
    SessionChangeReasonCode,
    SessionEditScope,
    SessionSeriesFrequency,
    SessionStatus,
)
from app.platform import clock

_MAX_SCHEDULING_PAST = dt.timedelta(days=730)
_MAX_SCHEDULING_FUTURE = dt.timedelta(days=1825)


class SessionDraft(BaseModel):
    """The proposed shape of a session, used for both conflict preview and create.

    ``trainer_person_id`` and ``location_id`` are optional *overrides*: omit them
    and the group's own defaults are copied onto the session (see
    :func:`app.domains.scheduling.service.create_session`). Send an explicit
    ``null`` to create the session deliberately unassigned.
    """

    group_id: str
    title: str | None = Field(default=None, max_length=160)
    trainer_person_id: str | None = None
    location_id: str | None = None
    starts_at: dt.datetime
    ends_at: dt.datetime

    @model_validator(mode="after")
    def _time_order(self) -> SessionDraft:
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        now = clock.now()
        starts = self.starts_at if self.starts_at.tzinfo else self.starts_at.replace(tzinfo=dt.UTC)
        if starts < now - _MAX_SCHEDULING_PAST or starts > now + _MAX_SCHEDULING_FUTURE:
            # Catches malformed client input (e.g. a partially-typed datetime-local
            # value silently producing a year like 1111) before it becomes a
            # session that's created successfully but invisible in every view.
            raise ValueError("starts_at nije u razumnom opsegu za zakazivanje.")
        return self


class SessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    group_id: str
    series_id: str | None = None
    trainer_person_id: str | None = None
    location_id: str | None = None
    title: str | None
    starts_at: dt.datetime
    ends_at: dt.datetime
    status: SessionStatus
    cancellation_reason: SessionCancellationReasonCode | None = None


class ConflictCheckResponse(BaseModel):
    has_conflict: bool
    conflicts: list[SessionSummary]


# --- Recurring series -------------------------------------------------------


class SessionSeriesCreate(BaseModel):
    """A weekly recurrence rule: weekday(s) + local time + start date, bound to a
    group and (optionally) a trainer."""

    group_id: str
    trainer_person_id: str | None = None
    location_id: str | None = None
    title: str = Field(max_length=160)
    frequency: SessionSeriesFrequency = SessionSeriesFrequency.WEEKLY
    weekdays: list[int] = Field(min_length=1)
    start_date: dt.date
    timezone: str = Field(default="Europe/Belgrade", max_length=64)
    local_time: dt.time
    duration_minutes: int = Field(gt=0, le=24 * 60)

    @model_validator(mode="after")
    def _validate(self) -> SessionSeriesCreate:
        if any(d < 0 or d > 6 for d in self.weekdays):
            raise ValueError("weekdays must be integers 0 (Monday) .. 6 (Sunday)")
        # Normalize to a sorted, de-duplicated set so generation is deterministic.
        self.weekdays = sorted(set(self.weekdays))
        return self


class SessionSeriesSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    group_id: str
    trainer_person_id: str | None
    location_id: str | None
    title: str
    frequency: SessionSeriesFrequency
    weekdays: list[int]
    start_date: dt.date
    timezone: str
    local_time: dt.time
    duration_minutes: int


class SeriesGenerateRequest(BaseModel):
    """Generate / top-up concrete sessions over a rolling horizon. Idempotent:
    occurrences that already exist for the series are left untouched."""

    from_date: dt.date | None = None
    weeks: int = Field(default=12, ge=1, le=104)


class SkippedOccurrence(BaseModel):
    starts_at: dt.datetime
    reason: str


class SeriesGenerateResult(BaseModel):
    series_id: str
    created_count: int
    skipped_existing: int
    skipped_conflicts: list[SkippedOccurrence]
    horizon_start: dt.date
    horizon_end: dt.date


class SessionEdit(BaseModel):
    """Edit a generated session at the chosen scope. Any field left ``None`` is
    unchanged. ``local_time``/``duration_minutes`` re-materialize UTC instants."""

    scope: SessionEditScope
    reason: SessionChangeReasonCode = SessionChangeReasonCode.OTHER
    title: str | None = Field(default=None, max_length=160)
    trainer_person_id: str | None = None
    location_id: str | None = None
    local_time: dt.time | None = None
    duration_minutes: int | None = Field(default=None, gt=0, le=24 * 60)

    @model_validator(mode="after")
    def _at_least_one(self) -> SessionEdit:
        if (
            self.title is None
            and self.trainer_person_id is None
            and self.location_id is None
            and self.local_time is None
            and self.duration_minutes is None
        ):
            raise ValueError("at least one field must be provided to edit")
        return self


class SessionCancel(BaseModel):
    reason: SessionCancellationReasonCode
    note: str | None = Field(default=None, max_length=500)
