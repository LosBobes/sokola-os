from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session as DbSession

from app.common.enums import AuditDataClass
from app.common.errors import ConflictError, NotFoundError
from app.domains.scheduling import repository
from app.domains.scheduling.models import Session
from app.domains.scheduling.schemas import (
    ConflictCheckResponse,
    SessionDraft,
    SessionSummary,
)
from app.platform.audit.service import record_audit
from app.platform.idempotency import service as idempotency
from app.platform.outbox.service import enqueue
from app.security.context import RequestContext


def check_conflicts(
    db: DbSession, context: RequestContext, draft: SessionDraft
) -> ConflictCheckResponse:
    if repository.get_org_group(db, context.organization_id, draft.group_id) is None:
        raise NotFoundError("Grupa nije pronađena.")
    conflicts = repository.find_conflicts(
        db, context.organization_id, draft.group_id, draft.starts_at, draft.ends_at
    )
    return ConflictCheckResponse(
        has_conflict=bool(conflicts),
        conflicts=[SessionSummary.model_validate(s) for s in conflicts],
    )


def create_session(
    db: DbSession,
    context: RequestContext,
    draft: SessionDraft,
    idempotency_key: str | None,
) -> SessionSummary:
    """Journey 1. Idempotent one-off session create. A true time conflict for the
    same group is refused (409) — the client previewed it and keeps its draft."""
    params = {
        "group_id": draft.group_id,
        "starts_at": draft.starts_at.isoformat(),
        "ends_at": draft.ends_at.isoformat(),
        "title": draft.title,
    }
    guard = None
    if idempotency_key:
        guard = idempotency.begin(
            db, context.organization_id, "scheduling.create_session", idempotency_key, params
        )
        if guard.replay is not None:
            return SessionSummary.model_validate(guard.replay["body"])

    if repository.get_org_group(db, context.organization_id, draft.group_id) is None:
        raise NotFoundError("Grupa nije pronađena.")

    conflicts = repository.find_conflicts(
        db, context.organization_id, draft.group_id, draft.starts_at, draft.ends_at
    )
    if conflicts:
        raise ConflictError(
            "Termin se preklapa sa postojećim terminom grupe.",
            details={
                "code": "SESSION_CONFLICT",
                "conflicts": [
                    SessionSummary.model_validate(s).model_dump(mode="json") for s in conflicts
                ],
            },
        )

    session = Session(
        organization_id=context.organization_id,
        group_id=draft.group_id,
        title=draft.title,
        starts_at=draft.starts_at,
        ends_at=draft.ends_at,
    )
    db.add(session)
    db.flush()

    result = SessionSummary.model_validate(session)
    record_audit(
        db,
        data_class=AuditDataClass.OPERATIONAL,
        action="session.created",
        entity_type="session",
        entity_id=session.id,
        summary=f"Kreiran termin {session.starts_at.isoformat()}.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )
    enqueue(
        db,
        event_type="session.created",
        payload={"session_id": session.id, "organization_id": context.organization_id},
        organization_id=context.organization_id,
    )
    if guard is not None:
        idempotency.complete(db, guard, status=201, body=result.model_dump(mode="json"))
    db.commit()
    return result


def list_schedule(
    db: DbSession, context: RequestContext, start: dt.datetime, end: dt.datetime
) -> list[SessionSummary]:
    sessions = repository.list_sessions_in_range(db, context.organization_id, start, end)
    return [SessionSummary.model_validate(s) for s in sessions]
