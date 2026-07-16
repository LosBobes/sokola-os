from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass
from app.common.errors import ConflictError, NotFoundError
from app.common.pagination import Page, PageParams
from app.domains.identity.enums import PersonIdentityStatus
from app.domains.identity.models import Person
from app.domains.organization.models import OrganizationMembership
from app.domains.people import repository
from app.domains.people.schemas import (
    CreatePersonRequest,
    PersonResponse,
    PersonSummary,
)
from app.platform.audit.service import record_audit
from app.platform.outbox.service import enqueue
from app.security.context import RequestContext


def create_provisional_person(
    db: Session, context: RequestContext, req: CreatePersonRequest
) -> PersonResponse:
    """Journey 8. Create a provisional person and attach them to the active org.

    If a same-named member already exists, refuse with a 409 that lists the
    candidates — unless the caller has explicitly confirmed the duplicate with a
    written reason.
    """
    candidates = repository.find_duplicate_candidates(
        db, context.organization_id, req.given_name, req.family_name
    )
    if candidates and not req.allow_possible_duplicate:
        raise ConflictError(
            "Moguć duplikat: osoba sa istim imenom već postoji u ovoj školi.",
            details={
                "code": "POSSIBLE_DUPLICATE",
                "candidates": [
                    {"person_id": p.id, "display_name": p.display_name} for p in candidates
                ],
            },
        )

    given = req.given_name.strip()
    family = req.family_name.strip()
    person = Person(
        given_name=given,
        family_name=family,
        display_name=f"{given} {family}",
        identity_status=PersonIdentityStatus.PROVISIONAL,
    )
    db.add(person)
    db.flush()

    db.add(OrganizationMembership(organization_id=context.organization_id, person_id=person.id))

    summary = f"Dodata osoba „{person.display_name}“."
    if req.allow_possible_duplicate:
        summary += f" Potvrđen mogući duplikat: {req.duplicate_reason}"
    record_audit(
        db,
        data_class=AuditDataClass.IDENTITY,
        action="person.created",
        entity_type="person",
        entity_id=person.id,
        summary=summary,
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"duplicate_override": req.allow_possible_duplicate},
    )
    enqueue(
        db,
        event_type="person.created",
        payload={"person_id": person.id, "organization_id": context.organization_id},
        organization_id=context.organization_id,
    )
    db.commit()
    return PersonResponse.model_validate(person)


def list_people(db: Session, context: RequestContext, params: PageParams) -> Page[PersonSummary]:
    people, total = repository.list_org_people(db, context.organization_id, params)
    items = [PersonSummary.model_validate(p) for p in people]
    return Page.build(items, total, params)


def get_person(db: Session, context: RequestContext, person_id: str) -> PersonResponse:
    person = repository.get_org_person(db, context.organization_id, person_id)
    if person is None:
        raise NotFoundError("Osoba nije pronađena.")
    return PersonResponse.model_validate(person)
