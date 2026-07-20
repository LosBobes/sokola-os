from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domains.communications.enums import (
    AnnouncementStatus,
    AnnouncementTargetType,
    NotificationDeliveryStatus,
)


class AnnouncementDraft(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    target_type: AnnouncementTargetType
    target_group_id: str | None = None

    @model_validator(mode="after")
    def _group_target_needs_group(self) -> AnnouncementDraft:
        if self.target_type is AnnouncementTargetType.GROUP and not self.target_group_id:
            raise ValueError("target_group_id is required when target_type is GROUP")
        if self.target_type is AnnouncementTargetType.ORGANIZATION and self.target_group_id:
            raise ValueError("target_group_id must be null when target_type is ORGANIZATION")
        return self


class AnnouncementPreviewResponse(BaseModel):
    recipient_count: int
    snapshot_hash: str


class PublishAnnouncementRequest(AnnouncementDraft):
    snapshot_hash: str


class AnnouncementResponse(BaseModel):
    id: str
    title: str
    status: AnnouncementStatus
    recipient_count: int


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    entity_type: str | None
    entity_id: str | None
    title: str
    body: str
    delivery_status: NotificationDeliveryStatus
    created_at: dt.datetime
    read_at: dt.datetime | None
