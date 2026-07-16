from __future__ import annotations

from collections import Counter

from sqlalchemy.orm import Session as DbSession

from app.common.context import RequestContext
from app.common.enums import AuditDataClass
from app.common.errors import BadRequestError, NotFoundError, VersionConflictError
from app.domains.attendance import repository
from app.domains.attendance.enums import AttendanceStatus
from app.domains.attendance.models import AttendanceRecord
from app.domains.attendance.schemas import (
    AttendanceEntry,
    AttendanceSheet,
    SaveAttendanceRequest,
    SaveAttendanceResponse,
)
from app.platform.audit.service import record_audit


def get_sheet(db: DbSession, context: RequestContext, session_id: str) -> AttendanceSheet:
    session = repository.get_session(db, context.organization_id, session_id)
    if session is None:
        raise NotFoundError("Termin nije pronađen.")

    roster = repository.list_roster(db, session.group_id)
    records = repository.records_by_person(db, session_id)
    entries = [
        AttendanceEntry(
            person_id=p.id,
            display_name=p.display_name,
            status=records[p.id].status if p.id in records else AttendanceStatus.PRESENT,
        )
        for p in roster
    ]
    return AttendanceSheet(
        session_id=session.id,
        attendance_version=session.attendance_version,
        entries=entries,
    )


def save_attendance(
    db: DbSession, context: RequestContext, session_id: str, req: SaveAttendanceRequest
) -> SaveAttendanceResponse:
    """Journey 2. Optimistic-concurrency save: the caller echoes the version they
    read; a mismatch means someone else saved first — reload and review, never
    silently overwrite. The session row is locked to serialize concurrent saves.
    """
    session = repository.get_session(
        db, context.organization_id, session_id, for_update=True
    )
    if session is None:
        raise NotFoundError("Termin nije pronađen.")
    if req.attendance_version != session.attendance_version:
        raise VersionConflictError(
            "Podaci o prisustvu su promenjeni u međuvremenu. Osvežite i pregledajte."
        )

    roster = repository.list_roster(db, session.group_id)
    roster_ids = {p.id for p in roster}

    exceptions = {e.person_id: e for e in req.exceptions}
    unknown = set(exceptions) - roster_ids
    if unknown:
        raise BadRequestError("Neka od navedenih osoba nisu na spisku ove grupe.")

    existing = repository.records_by_person(db, session_id)
    tally: Counter[AttendanceStatus] = Counter()
    for person_id in roster_ids:
        exception = exceptions.get(person_id)
        status = exception.status if exception else AttendanceStatus.PRESENT
        reason = exception.override_reason if exception else None
        tally[status] += 1

        record = existing.get(person_id)
        if record is None:
            db.add(
                AttendanceRecord(
                    organization_id=context.organization_id,
                    session_id=session_id,
                    person_id=person_id,
                    status=status,
                    override_reason=reason,
                )
            )
        else:
            record.status = status
            record.override_reason = reason

    session.attendance_version += 1
    record_audit(
        db,
        data_class=AuditDataClass.OPERATIONAL,
        action="attendance.saved",
        entity_type="session",
        entity_id=session_id,
        summary=f"Sačuvano prisustvo ({len(roster_ids)} osoba).",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )
    db.commit()
    return SaveAttendanceResponse(
        session_id=session_id,
        attendance_version=session.attendance_version,
        present=tally[AttendanceStatus.PRESENT],
        absent=tally[AttendanceStatus.ABSENT],
        excused=tally[AttendanceStatus.EXCUSED],
        late=tally[AttendanceStatus.LATE],
    )
