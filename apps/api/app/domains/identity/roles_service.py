"""Role assignment + permission-change + ownership endpoints (§25/§26/§14).

Split out of ``service.py`` (which owns context resolution + invitations) to
stay under the service-size ratchet; both modules belong to the identity
domain and share its ``repository``/``policy``/``schemas``.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass, RecordStatus
from app.common.errors import BadRequestError, ConflictError, NotFoundError
from app.common.pagination import Page, PageParams
from app.domains.identity import policy, repository
from app.domains.identity.enums import RoleAssignmentStatus, RoleCode, RoleScopeType
from app.domains.identity.models import Person, RoleAssignment
from app.domains.identity.schemas import (
    AssignRoleRequest,
    RoleAssignmentResponse,
    RoleTransitionRequest,
    TransferOwnershipRequest,
    TransferOwnershipResponse,
    UpdateGrantedAreasRequest,
)
from app.platform.audit.service import record_audit
from app.platform.outbox.service import enqueue
from app.security.context import RequestContext

_LAST_OWNER_ERROR = "Škola mora imati bar jednog aktivnog vlasnika."


def _assignment_response(assignment: RoleAssignment, person: Person) -> RoleAssignmentResponse:
    return RoleAssignmentResponse(
        id=assignment.id,
        person_id=person.id,
        display_name=person.display_name,
        organization_id=assignment.organization_id,
        role_code=assignment.role_code,
        scope_type=assignment.scope_type,
        scope_ref_id=assignment.scope_ref_id,
        granted_areas=assignment.granted_areas,
        status=assignment.status,
    )


def assign_role(
    db: Session, context: RequestContext, req: AssignRoleRequest
) -> RoleAssignmentResponse:
    if req.role_code is RoleCode.OWNER:
        # Ownership is a controlled action of its own (§14/M5), granted only
        # through POST /roles/ownership/transfer, never the generic assign path.
        raise BadRequestError(
            "Vlasništvo se dodeljuje isključivo kroz prenos vlasništva (ownership/transfer)."
        )
    person = repository.get_org_person(db, context.organization_id, req.person_id)
    if person is None:
        raise NotFoundError("Osoba nije pronađena u ovoj školi.")
    policy.validate_scope(
        db, context.organization_id, req.role_code, req.scope_type, req.scope_ref_id
    )
    policy.validate_granted_areas(
        req.role_code,
        req.granted_areas,
        actor_role_code=context.role_code,
        actor_granted_areas=context.granted_areas,
    )

    existing = repository.find_assignment(
        db,
        organization_id=context.organization_id,
        person_id=req.person_id,
        role_code=req.role_code,
        scope_type=req.scope_type,
        scope_ref_id=req.scope_ref_id,
    )
    if existing is not None and existing.status is RoleAssignmentStatus.ACTIVE:
        raise ConflictError("Osoba već ima ovu ulogu.")

    if existing is not None:
        existing.status = RoleAssignmentStatus.ACTIVE
        existing.record_status = RecordStatus.ACTIVE
        existing.granted_areas = req.granted_areas
        assignment = existing
        action = "role_assignment.reactivated"
    else:
        assignment = RoleAssignment(
            person_id=req.person_id,
            organization_id=context.organization_id,
            role_code=req.role_code,
            scope_type=req.scope_type,
            scope_ref_id=req.scope_ref_id,
            granted_areas=req.granted_areas,
        )
        db.add(assignment)
        db.flush()
        action = "role_assignment.created"

    record_audit(
        db,
        data_class=AuditDataClass.ROLE,
        action=action,
        entity_type="role_assignment",
        entity_id=assignment.id,
        summary=f"„{person.display_name}“ je dobio/la ulogu {req.role_code.value}.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"person_id": person.id},
    )
    enqueue(
        db,
        event_type=action,
        payload={
            "role_assignment_id": assignment.id,
            "person_id": person.id,
            "organization_id": context.organization_id,
        },
        organization_id=context.organization_id,
    )
    db.commit()
    return _assignment_response(assignment, person)


def list_role_assignments(
    db: Session, context: RequestContext, params: PageParams
) -> Page[RoleAssignmentResponse]:
    rows, total = repository.list_org_assignments(db, context.organization_id, params)
    return Page.build([_assignment_response(a, p) for a, p in rows], total, params)


def _load_assignment(
    db: Session, context: RequestContext, assignment_id: str
) -> tuple[RoleAssignment, Person]:
    assignment = repository.get_assignment(db, context.organization_id, assignment_id)
    if assignment is None:
        raise NotFoundError("Dodela uloge nije pronađena.")
    person = repository.get_person(db, assignment.person_id)
    assert person is not None
    return assignment, person


def update_granted_areas(
    db: Session, context: RequestContext, assignment_id: str, req: UpdateGrantedAreasRequest
) -> RoleAssignmentResponse:
    assignment, person = _load_assignment(db, context, assignment_id)
    policy.validate_granted_areas(
        assignment.role_code,
        req.granted_areas,
        actor_role_code=context.role_code,
        actor_granted_areas=context.granted_areas,
    )
    assignment.granted_areas = req.granted_areas
    record_audit(
        db,
        data_class=AuditDataClass.ROLE,
        action="role_assignment.permissions_changed",
        entity_type="role_assignment",
        entity_id=assignment.id,
        summary=f"Ovlašćenja za „{person.display_name}“ su izmenjena.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"granted_areas": req.granted_areas},
    )
    db.commit()
    return _assignment_response(assignment, person)


def _guard_not_last_owner(db: Session, organization_id: str, assignment: RoleAssignment) -> None:
    """§14/M4, never strip the school of its last active owner."""
    if (
        assignment.role_code is RoleCode.OWNER
        and repository.count_active_owners(db, organization_id) <= 1
    ):
        raise ConflictError(_LAST_OWNER_ERROR)


def _emit_assignment_transition(
    db: Session,
    context: RequestContext,
    assignment: RoleAssignment,
    person: Person,
    action: str,
    reason: str | None,
) -> None:
    verb = {"suspended": "suspendovana", "revoked": "opozvana"}[action]
    summary = f"Dodela uloge {assignment.role_code.value} za „{person.display_name}“ je {verb}."
    if reason and reason.strip():
        summary += f" Razlog: {reason.strip()}"
    record_audit(
        db,
        data_class=AuditDataClass.ROLE,
        action=f"role_assignment.{action}",
        entity_type="role_assignment",
        entity_id=assignment.id,
        summary=summary,
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"person_id": person.id},
    )
    enqueue(
        db,
        event_type=f"role_assignment.{action}",
        payload={
            "role_assignment_id": assignment.id,
            "person_id": person.id,
            "organization_id": context.organization_id,
        },
        organization_id=context.organization_id,
    )


def suspend_assignment(
    db: Session, context: RequestContext, assignment_id: str, req: RoleTransitionRequest
) -> RoleAssignmentResponse:
    assignment, person = _load_assignment(db, context, assignment_id)
    if assignment.status is not RoleAssignmentStatus.ACTIVE:
        raise ConflictError("Dodela uloge nije aktivna.")
    _guard_not_last_owner(db, context.organization_id, assignment)
    assignment.status = RoleAssignmentStatus.SUSPENDED
    _emit_assignment_transition(db, context, assignment, person, "suspended", req.reason)
    db.commit()
    return _assignment_response(assignment, person)


def revoke_assignment(
    db: Session, context: RequestContext, assignment_id: str, req: RoleTransitionRequest
) -> RoleAssignmentResponse:
    assignment, person = _load_assignment(db, context, assignment_id)
    if assignment.status is RoleAssignmentStatus.REVOKED:
        raise ConflictError("Dodela uloge je već opozvana.")
    _guard_not_last_owner(db, context.organization_id, assignment)
    assignment.status = RoleAssignmentStatus.REVOKED
    _emit_assignment_transition(db, context, assignment, person, "revoked", req.reason)
    db.commit()
    return _assignment_response(assignment, person)


# ---------------------------------------------------------------------------
# Ownership add/transfer (§14), M5
# ---------------------------------------------------------------------------


def transfer_ownership(
    db: Session, context: RequestContext, req: TransferOwnershipRequest
) -> TransferOwnershipResponse:
    if req.revoke_from_person_id == req.new_owner_person_id:
        raise BadRequestError("Novi i prethodni vlasnik ne mogu biti ista osoba.")

    new_owner = repository.get_org_person(db, context.organization_id, req.new_owner_person_id)
    if new_owner is None:
        raise NotFoundError("Osoba nije pronađena u ovoj školi.")

    existing = repository.find_assignment(
        db,
        organization_id=context.organization_id,
        person_id=req.new_owner_person_id,
        role_code=RoleCode.OWNER,
        scope_type=RoleScopeType.ORGANIZATION,
        scope_ref_id=None,
    )
    if existing is not None and existing.status is RoleAssignmentStatus.ACTIVE:
        raise ConflictError("Osoba je već vlasnik.")
    if existing is not None:
        existing.status = RoleAssignmentStatus.ACTIVE
        existing.record_status = RecordStatus.ACTIVE
        new_assignment = existing
    else:
        new_assignment = RoleAssignment(
            person_id=req.new_owner_person_id,
            organization_id=context.organization_id,
            role_code=RoleCode.OWNER,
            scope_type=RoleScopeType.ORGANIZATION,
        )
        db.add(new_assignment)
        db.flush()

    record_audit(
        db,
        data_class=AuditDataClass.ROLE,
        action="ownership.granted",
        entity_type="role_assignment",
        entity_id=new_assignment.id,
        summary=f"„{new_owner.display_name}“ je postao/la vlasnik škole.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )

    revoked_response: RoleAssignmentResponse | None = None
    if req.revoke_from_person_id:
        old = repository.find_assignment(
            db,
            organization_id=context.organization_id,
            person_id=req.revoke_from_person_id,
            role_code=RoleCode.OWNER,
            scope_type=RoleScopeType.ORGANIZATION,
            scope_ref_id=None,
        )
        if old is None or old.status is not RoleAssignmentStatus.ACTIVE:
            raise NotFoundError("Prethodni vlasnik nije pronađen.")
        # Safe: the new owner is already in place, so this never leaves the
        # school without an active owner even for an instant (§14/M4).
        _guard_not_last_owner(db, context.organization_id, old)
        old.status = RoleAssignmentStatus.REVOKED
        old_person = repository.get_person(db, req.revoke_from_person_id)
        assert old_person is not None
        record_audit(
            db,
            data_class=AuditDataClass.ROLE,
            action="ownership.revoked",
            entity_type="role_assignment",
            entity_id=old.id,
            summary=f"Vlasništvo za „{old_person.display_name}“ je opozvano (preneto).",
            organization_id=context.organization_id,
            actor_person_id=context.person_id,
        )
        revoked_response = _assignment_response(old, old_person)

    enqueue(
        db,
        event_type="ownership.transferred",
        payload={
            "organization_id": context.organization_id,
            "new_owner_person_id": req.new_owner_person_id,
            "revoked_from_person_id": req.revoke_from_person_id,
        },
        organization_id=context.organization_id,
    )
    db.commit()
    return TransferOwnershipResponse(
        new_owner=_assignment_response(new_assignment, new_owner), revoked_owner=revoked_response
    )
