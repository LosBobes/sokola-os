from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class UpdateEventRequest(BaseModel):
    """Partial update, only fields present in the request body are changed.
    ``capacity`` may be sent as ``null`` to clear it (pair with switching
    ``capacity_mode`` to UNLIMITED); omit a field entirely to leave it untouched.
    Only permitted while the event is still upcoming (published/draft and not yet
    started)."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    starts_at: dt.datetime | None = None
    capacity_mode: EventCapacityMode | None = None
    capacity: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _at_least_one(self) -> UpdateEventRequest:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided to edit")
        return self


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
