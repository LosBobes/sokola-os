from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from app.domains.progress.enums import ProgressLevel


class CreateProgressNoteRequest(BaseModel):
    group_id: str
    note: str = Field(min_length=1, max_length=2000)
    level: ProgressLevel | None = None


class ProgressNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    person_id: str
    group_id: str
    author_person_id: str
    session_id: str | None
    note: str
    level: ProgressLevel | None
    created_at: dt.datetime
