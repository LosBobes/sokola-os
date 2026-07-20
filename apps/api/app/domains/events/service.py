from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass
from app.common.errors import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.domains.events import repository
from app.domains.events.enums import (
    CancellationReasonCode,
    EventCapacityMode,
    EventStatus,
    RegistrationStatus,
)
from app.domains.events.models import Event, EventRegistration
from app.domains.events.schemas import (
    CreateEventRequest,
    EventResponse,
    RegistrationResponse,
    UpdateEventRequest,
)
from app.platform.audit.service import record_audit
from app.platform.idempotency import service as idempotency
from app.platform.outbox.service import enqueue
from app.security.context import RequestContext


def create_event(db: Session, context: RequestContext, req: CreateEventRequest) -> EventResponse:
    event = Event(
        organization_id=context.organization_id,
        title=req.title,
        type=req.type,
        category=req.category,
        starts_at=req.starts_at,
        ends_at=req.ends_at,
        capacity_mode=req.capacity_mode,
        capacity=req.capacity,
    )
    db.add(event)
    db.commit()
    return EventResponse.model_validate(event)


def list_events(db: Session, context: RequestContext) -> list[EventResponse]:
    return [
        EventResponse.model_validate(e)
        for e in repository.list_published(db, context.organization_id)
    ]


def _require_editable(event: Event) -> None:
    """An event may only be edited while it is still upcoming: not cancelled, not
    completed, and not already started."""
    if event.status is EventStatus.CANCELLED:
        raise ConflictError("Otkazan događaj se ne može izmeniti.")
    if event.status is EventStatus.COMPLETED:
        raise ConflictError("Završen događaj se ne može izmeniti.")
    if event.starts_at <= repository.now():
        raise ConflictError("Prošli događaj se ne može izmeniti.")


def update_event(
    db: Session, context: RequestContext, event_id: str, req: UpdateEventRequest
) -> EventResponse:
    """M1. Edit an event's title, start time, or capacity while it is still
    upcoming. Refused once the event has started, finished, or been cancelled."""
    event = repository.get_event(db, context.organization_id, event_id, for_update=True)
    if event is None:
        raise NotFoundError("Događaj nije pronađen.")
    _require_editable(event)

    fields = req.model_fields_set
    if "title" in fields:
        if req.title is None:
            raise BadRequestError("Naziv događaja je obavezan.")
        event.title = req.title
    if "starts_at" in fields:
        if req.starts_at is None:
            raise BadRequestError("Datum i vreme početka su obavezni.")
        if req.starts_at <= repository.now():
            raise ConflictError("Novi termin događaja mora biti u budućnosti.")
        event.starts_at = req.starts_at
    if "capacity_mode" in fields:
        if req.capacity_mode is None:
            raise BadRequestError("Režim kapaciteta je obavezan.")
        event.capacity_mode = req.capacity_mode
    if "capacity" in fields:
        event.capacity = req.capacity

    if event.capacity_mode is EventCapacityMode.LIMITED:
        if event.capacity is None:
            raise BadRequestError("Ograničen kapacitet zahteva definisan broj mesta.")
        active = repository.count_active_registrations(db, event.id)
        if event.capacity < active:
            raise ConflictError(
                "Novi kapacitet je manji od broja aktivnih prijava.",
                details={"code": "CAPACITY_BELOW_REGISTERED"},
            )

    record_audit(
        db,
        data_class=AuditDataClass.OPERATIONAL,
        action="event.updated",
        entity_type="event",
        entity_id=event.id,
        summary=f"Izmenjen događaj „{event.title}“.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )
    db.commit()
    return EventResponse.model_validate(event)


def cancel_event(db: Session, context: RequestContext, event_id: str) -> EventResponse:
    """M1. Cancel the whole event — distinct from cancelling a single
    registration. Cascades: every active (REGISTERED) registration is cancelled
    too, atomically in the same transaction as the event's own status change."""
    event = repository.get_event(db, context.organization_id, event_id, for_update=True)
    if event is None:
        raise NotFoundError("Događaj nije pronađen.")
    if event.status is EventStatus.CANCELLED:
        raise ConflictError("Događaj je već otkazan.")
    if event.status is EventStatus.COMPLETED:
        raise ConflictError("Završen događaj se ne može otkazati.")

    event.status = EventStatus.CANCELLED

    active = repository.list_active_registrations(db, event.id)
    for registration in active:
        registration.status = RegistrationStatus.CANCELLED
        registration.cancellation_reason = CancellationReasonCode.ORGANIZER
    db.flush()

    record_audit(
        db,
        data_class=AuditDataClass.RELATIONSHIP,
        action="event.cancelled",
        entity_type="event",
        entity_id=event.id,
        summary=f"Otkazan događaj „{event.title}“ ({len(active)} prijava otkazano).",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"cancelled_registrations": len(active)},
    )
    enqueue(
        db,
        event_type="event.cancelled",
        payload={
            "event_id": event.id,
            "organization_id": context.organization_id,
            "cancelled_registrations": len(active),
        },
        organization_id=context.organization_id,
    )
    db.commit()
    return EventResponse.model_validate(event)


def register_children(
    db: Session,
    context: RequestContext,
    event_id: str,
    child_ids: list[str],
    idempotency_key: str | None,
) -> list[RegistrationResponse]:
    """Journey 3. A parent registers one or more of their own children in a single
    command. Capacity is enforced atomically — if the batch would overflow, none
    are registered."""
    unique_ids = list(dict.fromkeys(child_ids))
    params = {"event_id": event_id, "child_ids": sorted(unique_ids)}
    guard = None
    if idempotency_key:
        guard = idempotency.begin(
            db, context.organization_id, "events.register", idempotency_key, params
        )
        if guard.replay is not None:
            return [RegistrationResponse.model_validate(r) for r in guard.replay["body"]]

    event = repository.get_event(db, context.organization_id, event_id, for_update=True)
    if event is None:
        raise NotFoundError("Događaj nije pronađen.")
    if event.status is not EventStatus.PUBLISHED:
        raise ConflictError("Prijave za ovaj događaj nisu otvorene.")

    allowed = repository.guardian_children(db, context.organization_id, context.person_id)
    not_allowed = [cid for cid in unique_ids if cid not in allowed]
    if not_allowed:
        # Reveal nothing about children the caller doesn't guardian.
        raise ForbiddenError("Nemate pravo prijave za neko od navedene dece.")

    existing = repository.registrations_for_children(db, event_id, unique_ids)
    newly_active = [
        cid
        for cid in unique_ids
        if cid not in existing or existing[cid].status is RegistrationStatus.CANCELLED
    ]

    if event.capacity_mode is EventCapacityMode.LIMITED and event.capacity is not None:
        projected = repository.count_active_registrations(db, event_id) + len(newly_active)
        if projected > event.capacity:
            raise ConflictError(
                "Nema dovoljno slobodnih mesta za sve prijave.",
                details={"code": "EVENT_FULL"},
            )

    results: list[EventRegistration] = []
    for cid in unique_ids:
        registration = existing.get(cid)
        if registration is None:
            registration = EventRegistration(
                organization_id=context.organization_id,
                event_id=event_id,
                child_person_id=cid,
                registered_by_person_id=context.person_id,
                status=RegistrationStatus.REGISTERED,
            )
            db.add(registration)
        else:
            registration.status = RegistrationStatus.REGISTERED
            registration.cancellation_reason = None
        results.append(registration)
    db.flush()

    payload = [
        RegistrationResponse(
            registration_id=r.id,
            child_person_id=r.child_person_id,
            display_name=allowed[r.child_person_id].display_name,
            status=r.status,
        )
        for r in results
    ]
    record_audit(
        db,
        data_class=AuditDataClass.RELATIONSHIP,
        action="event.registered",
        entity_type="event",
        entity_id=event_id,
        summary=f"Prijavljeno {len(results)} dete/dece na događaj.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )
    enqueue(
        db,
        event_type="event.registered",
        payload={"event_id": event_id, "organization_id": context.organization_id},
        organization_id=context.organization_id,
    )
    if guard is not None:
        idempotency.complete(
            db, guard, status=201, body=[p.model_dump(mode="json") for p in payload]
        )
    db.commit()
    return payload


def cancel_registration(
    db: Session, context: RequestContext, event_id: str, registration_id: str
) -> RegistrationResponse:
    """Journey 4. Cancellation is a status change, not a deletion; history stays
    canonical and no automatic refund is promised."""
    registration = repository.get_registration(
        db, context.organization_id, event_id, registration_id
    )
    if registration is None:
        raise NotFoundError("Prijava nije pronađena.")

    allowed = repository.guardian_children(db, context.organization_id, context.person_id)
    if registration.child_person_id not in allowed:
        raise ForbiddenError("Nedostupna prijava.")

    if registration.status is not RegistrationStatus.CANCELLED:
        registration.status = RegistrationStatus.CANCELLED
        registration.cancellation_reason = CancellationReasonCode.PARENT_REQUEST
        record_audit(
            db,
            data_class=AuditDataClass.RELATIONSHIP,
            action="event.registration_cancelled",
            entity_type="event_registration",
            entity_id=registration.id,
            summary="Otkazana prijava na događaj.",
            organization_id=context.organization_id,
            actor_person_id=context.person_id,
        )
        db.commit()

    return RegistrationResponse(
        registration_id=registration.id,
        child_person_id=registration.child_person_id,
        display_name=allowed[registration.child_person_id].display_name,
        status=registration.status,
    )
