from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.common.http import IdempotencyKey
from app.domains.events import service
from app.domains.events.schemas import (
    CreateEventRequest,
    EventResponse,
    RegisterChildrenRequest,
    RegistrationResponse,
    UpdateEventRequest,
)
from app.security.deps import ContextDep, DbDep
from app.security.permissions import PermissionArea, require_permission

router = APIRouter(tags=["events"])

_staff = require_permission(PermissionArea.EVENTS)
# The merged Raspored calendar is the timetable surface, so its feed is gated on
# the two areas the timetable is worked from: SCHEDULING (managing staff) or
# ATTENDANCE (trainers, whose only area this is). A trainer therefore sees the
# school's events on their calendar without gaining event *management* rights,
# while PARENT holds neither area and keeps seeing published events only, via
# the separate parent-facing list.
_calendar = require_permission(PermissionArea.SCHEDULING, PermissionArea.ATTENDANCE)
# Parent-facing routes are the parent surface, not staff event management:
# guard on PARENTS so staff cannot reach them and PARENT cannot reach _staff.
_parent = require_permission(PermissionArea.PARENTS)
StaffContext = Annotated[ContextDep, Depends(_staff)]
ParentContext = Annotated[ContextDep, Depends(_parent)]
CalendarContext = Annotated[ContextDep, Depends(_calendar)]


@router.post(
    "/events",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createEvent",
)
def create_event(body: CreateEventRequest, db: DbDep, context: StaffContext) -> EventResponse:
    return service.create_event(db, context, body)


@router.get("/events", response_model=list[EventResponse], operation_id="listEvents")
def list_events(db: DbDep, context: ContextDep) -> list[EventResponse]:
    return service.list_events(db, context)


@router.get(
    "/events/calendar",
    response_model=list[EventResponse],
    operation_id="listEventCalendar",
)
def list_event_calendar(
    db: DbDep,
    context: CalendarContext,
    date_from: Annotated[dt.datetime, Query()],
    date_to: Annotated[dt.datetime, Query()],
) -> list[EventResponse]:
    return service.list_calendar(db, context, date_from, date_to)


@router.patch(
    "/events/{event_id}",
    response_model=EventResponse,
    operation_id="updateEvent",
    responses={409: {"description": "Event is cancelled, completed, or already past."}},
)
def update_event(
    event_id: str, body: UpdateEventRequest, db: DbDep, context: StaffContext
) -> EventResponse:
    return service.update_event(db, context, event_id, body)


@router.post(
    "/events/{event_id}/cancel",
    response_model=EventResponse,
    operation_id="cancelEvent",
    responses={409: {"description": "Event is already cancelled or completed."}},
)
def cancel_event(event_id: str, db: DbDep, context: StaffContext) -> EventResponse:
    return service.cancel_event(db, context, event_id)


@router.post(
    "/events/{event_id}/registrations",
    response_model=list[RegistrationResponse],
    status_code=status.HTTP_201_CREATED,
    operation_id="registerChildren",
    responses={409: {"description": "Event full or registration closed."}},
)
def register_children(
    event_id: str,
    body: RegisterChildrenRequest,
    db: DbDep,
    context: ParentContext,
    idempotency_key: IdempotencyKey = None,
) -> list[RegistrationResponse]:
    return service.register_children(
        db, context, event_id, body.child_person_ids, idempotency_key
    )


@router.post(
    "/events/{event_id}/registrations/{registration_id}/cancel",
    response_model=RegistrationResponse,
    operation_id="cancelRegistration",
)
def cancel_registration(
    event_id: str, registration_id: str, db: DbDep, context: ParentContext
) -> RegistrationResponse:
    return service.cancel_registration(db, context, event_id, registration_id)
