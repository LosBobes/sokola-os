from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.domains.attendance import service
from app.domains.attendance.schemas import (
    AttendanceSheet,
    SaveAttendanceRequest,
    SaveAttendanceResponse,
)
from app.security.deps import ContextDep, DbDep
from app.security.permissions import PermissionArea, require_permission

router = APIRouter(tags=["attendance"])

# Trainers record attendance, as do managing staff.
_recorders = require_permission(PermissionArea.ATTENDANCE)
RecorderContext = Annotated[ContextDep, Depends(_recorders)]


@router.get(
    "/schedule/sessions/{session_id}/attendance",
    response_model=AttendanceSheet,
    operation_id="getAttendanceSheet",
)
def get_attendance(
    session_id: str, db: DbDep, context: RecorderContext
) -> AttendanceSheet:
    return service.get_sheet(db, context, session_id)


@router.put(
    "/schedule/sessions/{session_id}/attendance",
    response_model=SaveAttendanceResponse,
    operation_id="saveAttendance",
    responses={409: {"description": "Attendance changed since it was loaded; reload."}},
)
def save_attendance(
    session_id: str,
    body: SaveAttendanceRequest,
    db: DbDep,
    context: RecorderContext,
) -> SaveAttendanceResponse:
    return service.save_attendance(db, context, session_id, body)
