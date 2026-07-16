from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.errors import UnauthorizedError
from app.domains.identity import repository
from app.domains.identity.schemas import ContextSummary, MeResponse
from app.security.auth import Principal


def get_me(db: Session, principal: Principal) -> MeResponse:
    person = repository.get_person(db, principal.person_id)
    if person is None:
        raise UnauthorizedError("Nepoznata osoba.")

    contexts = [
        ContextSummary(
            role_assignment_id=assignment.id,
            organization_id=organization.id,
            organization_name=organization.name,
            role_code=assignment.role_code,
            scope_type=assignment.scope_type,
            scope_ref_id=assignment.scope_ref_id,
        )
        for assignment, organization in repository.list_active_contexts(db, person.id)
    ]
    return MeResponse(
        person_id=person.id,
        display_name=person.display_name,
        identity_status=person.identity_status,
        contexts=contexts,
    )
