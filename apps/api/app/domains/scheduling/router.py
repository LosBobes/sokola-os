from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from app.common.http import IdempotencyKey
from app.domains.scheduling import service
from app.domains.scheduling.schemas import (
    ConflictCheckResponse,
    SeriesGenerateRequest,
    SeriesGenerateResult,
    SessionCancel,
    SessionDraft,
    SessionEdit,
    SessionSeriesCreate,
    SessionSeriesSummary,
    SessionSummary,
)
from app.security.deps import ContextDep, DbDep
from app.security.permissions import PermissionArea, require_permission

router = APIRouter(tags=["schedule"])

_staff = require_permission(PermissionArea.SCHEDULING)
StaffContext = Annotated[ContextDep, Depends(_staff)]

_CONFLICT_RESPONSE: dict[int | str, dict[str, Any]] = {
    409: {"description": "Time conflict with an existing session."}
}


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
    responses=_CONFLICT_RESPONSE,
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


# --- Recurring series -------------------------------------------------------


@router.post(
    "/schedule/series",
    response_model=SessionSeriesSummary,
    status_code=status.HTTP_201_CREATED,
    operation_id="createSessionSeries",
)
def create_series(
    body: SessionSeriesCreate, db: DbDep, context: StaffContext
) -> SessionSeriesSummary:
    return service.create_series(db, context, body)


@router.get(
    "/schedule/series",
    response_model=list[SessionSeriesSummary],
    operation_id="listSessionSeries",
)
def list_series(db: DbDep, context: StaffContext) -> list[SessionSeriesSummary]:
    return service.list_series(db, context)


@router.post(
    "/schedule/series/{series_id}/generate",
    response_model=SeriesGenerateResult,
    operation_id="generateSeriesSessions",
)
def generate_series_sessions(
    series_id: str, body: SeriesGenerateRequest, db: DbDep, context: StaffContext
) -> SeriesGenerateResult:
    return service.generate_sessions(db, context, series_id, body)


@router.patch(
    "/schedule/sessions/{session_id}",
    response_model=list[SessionSummary],
    operation_id="editSession",
    responses=_CONFLICT_RESPONSE,
)
def edit_session(
    session_id: str, body: SessionEdit, db: DbDep, context: StaffContext
) -> list[SessionSummary]:
    return service.edit_session(db, context, session_id, body)


@router.post(
    "/schedule/sessions/{session_id}/cancel",
    response_model=SessionSummary,
    operation_id="cancelSession",
)
def cancel_session(
    session_id: str, body: SessionCancel, db: DbDep, context: StaffContext
) -> SessionSummary:
    return service.cancel_session(db, context, session_id, body)


@router.post(
    "/schedule/sessions/{session_id}/reactivate",
    response_model=SessionSummary,
    operation_id="reactivateSession",
    responses=_CONFLICT_RESPONSE,
)
def reactivate_session(
    session_id: str, db: DbDep, context: StaffContext
) -> SessionSummary:
    return service.reactivate_session(db, context, session_id)
