from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.common.http import IdempotencyKey
from app.domains.events import service
from app.domains.events.schemas import (
    CreateEventRequest,
    EventResponse,
    RegisterChildrenRequest,
    RegistrationResponse,
)
from app.domains.identity.enums import RoleCode
from app.security.deps import ContextDep, DbDep, require_roles

router = APIRouter(tags=["events"])

_staff = require_roles(RoleCode.OWNER, RoleCode.MANAGER, RoleCode.ADMIN)
_parent = require_roles(RoleCode.PARENT)
StaffContext = Annotated[ContextDep, Depends(_staff)]
ParentContext = Annotated[ContextDep, Depends(_parent)]


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
