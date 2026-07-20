from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.common.http import IdempotencyKey
from app.domains.scheduling import service
from app.domains.scheduling.schemas import (
    ConflictCheckResponse,
    SessionDraft,
    SessionSummary,
)
from app.security.deps import ContextDep, DbDep
from app.security.permissions import PermissionArea, require_permission

router = APIRouter(tags=["schedule"])

_staff = require_permission(PermissionArea.SCHEDULING)
StaffContext = Annotated[ContextDep, Depends(_staff)]


@router.post(
    "/schedule/conflict-check",
    response_model=ConflictCheckResponse,
    operation_id="checkSessionConflicts",
)
def conflict_check(
    body: SessionDraft, db: DbDep, context: StaffContext
) -> ConflictCheckResponse:
    return service.check_conflicts(db, context, body)


@router.post(
    "/schedule/sessions",
    response_model=SessionSummary,
    status_code=status.HTTP_201_CREATED,
    operation_id="createSession",
    responses={409: {"description": "Time conflict with an existing session."}},
)
def create_session(
    body: SessionDraft,
    db: DbDep,
    context: StaffContext,
    idempotency_key: IdempotencyKey = None,
) -> SessionSummary:
    return service.create_session(db, context, body, idempotency_key)


@router.get(
    "/schedule/sessions", response_model=list[SessionSummary], operation_id="listSchedule"
)
def list_schedule(
    db: DbDep,
    context: ContextDep,
    date_from: Annotated[dt.datetime, Query()],
    date_to: Annotated[dt.datetime, Query()],
) -> list[SessionSummary]:
    return service.list_schedule(db, context, date_from, date_to)
