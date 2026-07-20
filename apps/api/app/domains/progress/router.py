from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.domains.progress import service
from app.domains.progress.schemas import CreateProgressNoteRequest, ProgressNoteResponse
from app.security.deps import ContextDep, DbDep
from app.security.permissions import PermissionArea, require_permission

router = APIRouter(tags=["progress"])

# Same guard as attendance recording (PRD 06): trainers write progress notes for
# their groups, as does managing staff.
_recorders = require_permission(PermissionArea.ATTENDANCE)
RecorderContext = Annotated[ContextDep, Depends(_recorders)]


@router.post(
    "/people/{person_id}/progress-notes",
    response_model=ProgressNoteResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createProgressNote",
)
def create_progress_note(
    person_id: str,
    body: CreateProgressNoteRequest,
    db: DbDep,
    context: RecorderContext,
) -> ProgressNoteResponse:
    return service.create_note(db, context, person_id, body)


@router.get(
    "/people/{person_id}/progress-notes",
    response_model=list[ProgressNoteResponse],
    operation_id="listProgressNotes",
)
def list_progress_notes(
    person_id: str,
    db: DbDep,
    context: RecorderContext,
    group_id: Annotated[str | None, Query()] = None,
) -> list[ProgressNoteResponse]:
    return service.list_notes(db, context, person_id, group_id)
