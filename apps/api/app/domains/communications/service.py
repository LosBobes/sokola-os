from __future__ import annotations

import datetime as dt
import hashlib
import json

from sqlalchemy.orm import Session

from app.common.context import RequestContext
from app.common.enums import AuditDataClass
from app.common.errors import ConflictError, NotFoundError
from app.domains.communications import repository
from app.domains.communications.enums import AnnouncementStatus, AnnouncementTargetType
from app.domains.communications.models import Announcement, AnnouncementRecipient
from app.domains.communications.schemas import (
    AnnouncementDraft,
    AnnouncementPreviewResponse,
    AnnouncementResponse,
    PublishAnnouncementRequest,
)
from app.platform.audit.service import record_audit
from app.platform.idempotency import service as idempotency
from app.platform.outbox.service import enqueue


def _resolve_recipients(
    db: Session, context: RequestContext, draft: AnnouncementDraft
) -> list[str]:
    if draft.target_type is AnnouncementTargetType.GROUP:
        assert draft.target_group_id is not None
        if not repository.group_exists(db, context.organization_id, draft.target_group_id):
            raise NotFoundError("Grupa nije pronađena.")
        return repository.group_recipient_ids(db, draft.target_group_id)
    return repository.organization_recipient_ids(db, context.organization_id)


def _snapshot_hash(recipient_ids: list[str]) -> str:
    canonical = json.dumps(sorted(recipient_ids), separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def preview(
    db: Session, context: RequestContext, draft: AnnouncementDraft
) -> AnnouncementPreviewResponse:
    recipients = _resolve_recipients(db, context, draft)
    return AnnouncementPreviewResponse(
        recipient_count=len(recipients), snapshot_hash=_snapshot_hash(recipients)
    )


def publish(
    db: Session,
    context: RequestContext,
    req: PublishAnnouncementRequest,
    idempotency_key: str | None,
) -> AnnouncementResponse:
    """Journey 7. Publish only if the recipient snapshot still matches what the
    author reviewed. Delivery is handled asynchronously via the outbox; a delivery
    failure is a partial state, never a reason to re-publish."""
    params = req.model_dump()
    guard = None
    if idempotency_key:
        guard = idempotency.begin(
            db, context.organization_id, "communications.publish", idempotency_key, params
        )
        if guard.replay is not None:
            return AnnouncementResponse.model_validate(guard.replay["body"])

    recipients = _resolve_recipients(db, context, req)
    if _snapshot_hash(recipients) != req.snapshot_hash:
        raise ConflictError(
            "Spisak primalaca se promenio u međuvremenu. Pregledajte ponovo.",
            details={"code": "SNAPSHOT_STALE"},
        )
    if not recipients:
        raise ConflictError("Nema primalaca za ovu poruku.")

    announcement = Announcement(
        organization_id=context.organization_id,
        title=req.title,
        body=req.body,
        target_type=req.target_type,
        target_group_id=req.target_group_id,
        status=AnnouncementStatus.PUBLISHED,
        recipient_count=len(recipients),
        snapshot_hash=req.snapshot_hash,
        published_at=dt.datetime.now(tz=dt.UTC),
    )
    db.add(announcement)
    db.flush()
    for person_id in recipients:
        db.add(
            AnnouncementRecipient(
                announcement_id=announcement.id,
                organization_id=context.organization_id,
                person_id=person_id,
            )
        )

    result = AnnouncementResponse(
        id=announcement.id,
        title=announcement.title,
        status=announcement.status,
        recipient_count=announcement.recipient_count,
    )
    record_audit(
        db,
        data_class=AuditDataClass.OPERATIONAL,
        action="announcement.published",
        entity_type="announcement",
        entity_id=announcement.id,
        summary=f"Objavljena poruka „{req.title}“ ({len(recipients)} primalaca).",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )
    enqueue(
        db,
        event_type="announcement.published",
        payload={"announcement_id": announcement.id, "organization_id": context.organization_id},
        organization_id=context.organization_id,
    )
    if guard is not None:
        idempotency.complete(db, guard, status=201, body=result.model_dump(mode="json"))
    db.commit()
    return result
