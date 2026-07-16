from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from app.domains.events.enums import (
    EventCapacityMode,
    EventCategory,
    EventStatus,
    EventType,
    RegistrationStatus,
)


class CreateEventRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    type: EventType = EventType.OTHER
    category: EventCategory = EventCategory.INTERNAL
    starts_at: dt.datetime
    ends_at: dt.datetime | None = None
    capacity_mode: EventCapacityMode = EventCapacityMode.UNLIMITED
    capacity: int | None = Field(default=None, ge=1)


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    type: EventType
    category: EventCategory
    status: EventStatus
    starts_at: dt.datetime
    capacity_mode: EventCapacityMode
    capacity: int | None


class RegisterChildrenRequest(BaseModel):
    child_person_ids: list[str] = Field(min_length=1)


class RegistrationResponse(BaseModel):
    registration_id: str
    child_person_id: str
    display_name: str
    status: RegistrationStatus
