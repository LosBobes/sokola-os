from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.common.http import IdempotencyKey
from app.domains.communications import service
from app.domains.communications.schemas import (
    AnnouncementDraft,
    AnnouncementPreviewResponse,
    AnnouncementResponse,
    PublishAnnouncementRequest,
)
from app.security.deps import ContextDep, DbDep
from app.security.permissions import PermissionArea, require_permission

router = APIRouter(tags=["communications"])

_staff = require_permission(PermissionArea.COMMUNICATIONS)
StaffContext = Annotated[ContextDep, Depends(_staff)]


@router.post(
    "/communications/announcements/preview",
    response_model=AnnouncementPreviewResponse,
    operation_id="previewAnnouncement",
)
def preview_announcement(
    body: AnnouncementDraft, db: DbDep, context: StaffContext
) -> AnnouncementPreviewResponse:
    return service.preview(db, context, body)


@router.post(
    "/communications/announcements",
    response_model=AnnouncementResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="publishAnnouncement",
    responses={409: {"description": "Recipient snapshot changed; review again."}},
)
def publish_announcement(
    body: PublishAnnouncementRequest,
    db: DbDep,
    context: StaffContext,
    idempotency_key: IdempotencyKey = None,
) -> AnnouncementResponse:
    return service.publish(db, context, body, idempotency_key)
