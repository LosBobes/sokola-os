from __future__ import annotations

from sqlalchemy.orm import Session as DbSession

from app.common.enums import AuditDataClass
from app.common.errors import BadRequestError, NotFoundError
from app.domains.progress import repository
from app.domains.progress.models import ProgressNote
from app.domains.progress.schemas import CreateProgressNoteRequest, ProgressNoteResponse
from app.platform.audit.service import record_audit
from app.security.context import RequestContext


def create_note(
    db: DbSession, context: RequestContext, person_id: str, req: CreateProgressNoteRequest
) -> ProgressNoteResponse:
    """M1. A trainer/staff member writes a note about a student in one of their
    groups. The student must be an active member of that group, a note is
    always honest about who it's about and in what context."""
    person = repository.get_school_person(db, context.school_id, person_id)
    if person is None:
        raise NotFoundError("Osoba nije pronađena.")

    group = repository.get_group(db, context.school_id, req.group_id)
    if group is None:
        raise NotFoundError("Grupa nije pronađena.")

    if not repository.is_active_group_member(db, req.group_id, person_id):
        raise BadRequestError("Osoba nije aktivan član navedene grupe.")

    note = ProgressNote(
        school_id=context.school_id,
        person_id=person_id,
        group_id=req.group_id,
        author_person_id=context.person_id,
        note=req.note,
        level=req.level,
    )
    db.add(note)
    record_audit(
        db,
        data_class=AuditDataClass.OPERATIONAL,
        action="progress_note.created",
        entity_type="person",
        entity_id=person_id,
        summary="Dodata beleška o napretku.",
        school_id=context.school_id,
        actor_person_id=context.person_id,
    )
    db.commit()
    db.refresh(note)
    return ProgressNoteResponse.model_validate(note)


def list_notes(
    db: DbSession, context: RequestContext, person_id: str, group_id: str | None
) -> list[ProgressNoteResponse]:
    """Staff view: every note for a person, optionally narrowed to one group."""
    person = repository.get_school_person(db, context.school_id, person_id)
    if person is None:
        raise NotFoundError("Osoba nije pronađena.")
    notes = repository.list_for_person(db, context.school_id, person_id, group_id)
    return [ProgressNoteResponse.model_validate(n) for n in notes]
