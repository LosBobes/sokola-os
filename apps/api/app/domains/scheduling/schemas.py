from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domains.scheduling.enums import SessionStatus


class SessionDraft(BaseModel):
    """The proposed shape of a session — used for both conflict preview and create."""

    group_id: str
    title: str | None = Field(default=None, max_length=160)
    starts_at: dt.datetime
    ends_at: dt.datetime

    @model_validator(mode="after")
    def _time_order(self) -> SessionDraft:
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class SessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    group_id: str
    title: str | None
    starts_at: dt.datetime
    ends_at: dt.datetime
    status: SessionStatus


class ConflictCheckResponse(BaseModel):
    has_conflict: bool
    conflicts: list[SessionSummary]
