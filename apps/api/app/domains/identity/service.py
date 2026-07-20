from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass, RecordStatus
from app.common.errors import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
)
from app.common.pagination import Page, PageParams
from app.domains.identity import policy, repository
from app.domains.identity.enums import (
    InvitationStatus,
    InvitationType,
    RoleAssignmentStatus,
    RoleCode,
    RoleScopeType,
)
from app.domains.identity.invite_tokens import INVITATION_TTL_DAYS, generate_token, hash_token
from app.domains.identity.models import Invitation, RoleAssignment
from app.domains.identity.schemas import (
    AcceptInvitationRequest,
    AcceptInvitationResponse,
    ContextSummary,
    CreateInvitationRequest,
    InvitationCreatedResponse,
    InvitationResponse,
    MeResponse,
    RevokeInvitationRequest,
)
from app.domains.organization.enums import MembershipStatus
from app.domains.organization.models import Organization, OrganizationMembership
from app.domains.people.enums import GuardianAccessStatus, GuardianRelationshipType
from app.domains.people.models import GuardianOrganizationAccess, GuardianRelationship
from app.platform.audit.service import record_audit
from app.platform.outbox.service import enqueue
from app.security.auth import Principal
from app.security.context import RequestContext


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


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


# ---------------------------------------------------------------------------
# Invitations (§16-24, §19.3-19.5) — M1/M2/M7/M8
# ---------------------------------------------------------------------------


def send_invitation(
    db: Session, context: RequestContext, req: CreateInvitationRequest
) -> InvitationCreatedResponse:
    role_code = policy.role_code_for_invitation(req.type, req.role_code)
    policy.validate_scope(db, context.organization_id, role_code, req.scope_type, req.scope_ref_id)
    policy.validate_granted_areas(
        role_code,
        req.granted_areas,
        actor_role_code=context.role_code,
        actor_granted_areas=context.granted_areas,
    )

    if req.type is InvitationType.PARENT:
        if not req.target_child_person_id:
            raise BadRequestError("Potrebno je izabrati dete za pozivnicu roditelja.")
        child = repository.get_org_person(db, context.organization_id, req.target_child_person_id)
        if child is None:
            raise NotFoundError("Dete nije pronađeno u ovoj školi.")
    elif req.target_child_person_id:
        raise BadRequestError("Dete se navodi samo za pozivnicu roditelja.")

    raw_token, token_hash = generate_token()
    invitation = Invitation(
        organization_id=context.organization_id,
        type=req.type,
        status=InvitationStatus.PENDING,
        target_email=req.target_email,
        token_hash=token_hash,
        expires_at=_now() + dt.timedelta(days=INVITATION_TTL_DAYS),
        role_code=role_code,
        scope_type=req.scope_type,
        scope_ref_id=req.scope_ref_id,
        granted_areas=req.granted_areas,
        target_child_person_id=req.target_child_person_id,
        invited_by_person_id=context.person_id,
    )
    db.add(invitation)
    db.flush()
    record_audit(
        db,
        data_class=AuditDataClass.ROLE,
        action="invitation.sent",
        entity_type="invitation",
        entity_id=invitation.id,
        summary=f"Pozivnica poslata na {req.target_email} za ulogu {role_code.value}.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"type": req.type.value, "role_code": role_code.value},
    )
    enqueue(
        db,
        event_type="invitation.sent",
        payload={"invitation_id": invitation.id, "organization_id": context.organization_id},
        organization_id=context.organization_id,
    )
    db.commit()
    return InvitationCreatedResponse(
        invitation=InvitationResponse.model_validate(invitation), token=raw_token
    )


def list_invitations(
    db: Session, context: RequestContext, params: PageParams
) -> Page[InvitationResponse]:
    items, total = repository.list_org_invitations(db, context.organization_id, params)
    return Page.build([InvitationResponse.model_validate(i) for i in items], total, params)


def get_invitation(db: Session, context: RequestContext, invitation_id: str) -> InvitationResponse:
    invitation = repository.get_invitation(db, context.organization_id, invitation_id)
    if invitation is None:
        raise NotFoundError("Pozivnica nije pronađena.")
    return InvitationResponse.model_validate(invitation)


def revoke_invitation(
    db: Session, context: RequestContext, invitation_id: str, req: RevokeInvitationRequest
) -> InvitationResponse:
    invitation = repository.get_invitation(db, context.organization_id, invitation_id)
    if invitation is None:
        raise NotFoundError("Pozivnica nije pronađena.")
    if invitation.status is not InvitationStatus.PENDING:
        raise ConflictError("Samo pozivnica na čekanju može biti opozvana.")

    invitation.status = InvitationStatus.REVOKED
    summary = f"Pozivnica za {invitation.target_email} je opozvana."
    if req.reason and req.reason.strip():
        summary += f" Razlog: {req.reason.strip()}"
    record_audit(
        db,
        data_class=AuditDataClass.ROLE,
        action="invitation.revoked",
        entity_type="invitation",
        entity_id=invitation.id,
        summary=summary,
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )
    enqueue(
        db,
        event_type="invitation.revoked",
        payload={"invitation_id": invitation.id, "organization_id": context.organization_id},
        organization_id=context.organization_id,
    )
    db.commit()
    return InvitationResponse.model_validate(invitation)


def reissue_invitation(
    db: Session, context: RequestContext, invitation_id: str
) -> InvitationCreatedResponse:
    """Void a PENDING/EXPIRED invitation and send a fresh one in its place — a
    new token and a fresh 7-day window, chained via ``reissued_from_invitation_id``."""
    old = repository.get_invitation(db, context.organization_id, invitation_id)
    if old is None:
        raise NotFoundError("Pozivnica nije pronađena.")
    if old.status not in (InvitationStatus.PENDING, InvitationStatus.EXPIRED):
        raise ConflictError("Ova pozivnica se ne može ponovo poslati.")

    old.status = InvitationStatus.REISSUED
    raw_token, token_hash = generate_token()
    new = Invitation(
        organization_id=old.organization_id,
        type=old.type,
        status=InvitationStatus.PENDING,
        target_email=old.target_email,
        token_hash=token_hash,
        expires_at=_now() + dt.timedelta(days=INVITATION_TTL_DAYS),
        role_code=old.role_code,
        scope_type=old.scope_type,
        scope_ref_id=old.scope_ref_id,
        granted_areas=old.granted_areas,
        target_child_person_id=old.target_child_person_id,
        invited_by_person_id=context.person_id,
        reissued_from_invitation_id=old.id,
    )
    db.add(new)
    db.flush()
    record_audit(
        db,
        data_class=AuditDataClass.ROLE,
        action="invitation.reissued",
        entity_type="invitation",
        entity_id=new.id,
        summary=f"Pozivnica za {new.target_email} je ponovo poslata.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
        context={"reissued_from_invitation_id": old.id},
    )
    enqueue(
        db,
        event_type="invitation.reissued",
        payload={
            "invitation_id": new.id,
            "reissued_from_invitation_id": old.id,
            "organization_id": context.organization_id,
        },
        organization_id=context.organization_id,
    )
    db.commit()
    return InvitationCreatedResponse(
        invitation=InvitationResponse.model_validate(new), token=raw_token
    )


def _open_membership(db: Session, organization_id: str, person_id: str) -> None:
    membership = repository.get_membership(db, organization_id, person_id)
    if membership is None:
        db.add(OrganizationMembership(organization_id=organization_id, person_id=person_id))
        return
    if membership.status is MembershipStatus.ENDED:
        # A deliberate staff invitation re-opens access even though the generic
        # resume-membership endpoint treats ENDED as terminal (people/service.py) —
        # accepting a fresh, explicit invite is a distinct re-grant.
        membership.status = MembershipStatus.ACTIVE


def _grant_role(
    db: Session,
    *,
    organization_id: str,
    person_id: str,
    role_code: RoleCode,
    scope_type: RoleScopeType,
    scope_ref_id: str | None,
    granted_areas: list[str] | None,
) -> RoleAssignment:
    existing = repository.find_assignment(
        db,
        organization_id=organization_id,
        person_id=person_id,
        role_code=role_code,
        scope_type=scope_type,
        scope_ref_id=scope_ref_id,
    )
    if existing is not None:
        existing.status = RoleAssignmentStatus.ACTIVE
        existing.record_status = RecordStatus.ACTIVE
        existing.granted_areas = granted_areas
        return existing
    assignment = RoleAssignment(
        person_id=person_id,
        organization_id=organization_id,
        role_code=role_code,
        scope_type=scope_type,
        scope_ref_id=scope_ref_id,
        granted_areas=granted_areas,
    )
    db.add(assignment)
    db.flush()
    return assignment


def _link_guardian(
    db: Session, *, organization_id: str, guardian_person_id: str, child_person_id: str
) -> None:
    if repository.get_guardian_relationship(db, guardian_person_id, child_person_id) is None:
        db.add(
            GuardianRelationship(
                guardian_person_id=guardian_person_id,
                child_person_id=child_person_id,
                relationship_type=GuardianRelationshipType.PARENT,
            )
        )
    access = repository.get_guardian_access(
        db, organization_id, guardian_person_id, child_person_id
    )
    if access is None:
        db.add(
            GuardianOrganizationAccess(
                organization_id=organization_id,
                guardian_person_id=guardian_person_id,
                child_person_id=child_person_id,
                status=GuardianAccessStatus.ACTIVE,
            )
        )
    elif access.status is not GuardianAccessStatus.ACTIVE:
        access.status = GuardianAccessStatus.ACTIVE


def accept_invitation(
    db: Session, principal: Principal, req: AcceptInvitationRequest
) -> AcceptInvitationResponse:
    """Single accept path for both "existing person" and "new person" flows
    (§21/§22): by the time this is called the caller is already authenticated
    (via an existing session or a first-time Google sign-in that just
    provisioned their Person) — acceptance only needs to link that Person."""
    invitation = repository.get_invitation_by_token_hash(db, hash_token(req.token))
    if invitation is None:
        raise NotFoundError("Pozivnica nije pronađena ili je nevažeća.")

    now = _now()
    if repository.expire_stale_pending(db, invitation, now=now):
        db.commit()
        raise ConflictError("Pozivnica je istekla.")
    if invitation.status is InvitationStatus.ACCEPTED:
        raise ConflictError("Pozivnica je već iskorišćena.")
    if invitation.status is InvitationStatus.REVOKED:
        raise ConflictError("Pozivnica je opozvana.")
    if invitation.status is InvitationStatus.REISSUED:
        raise ConflictError("Pozivnica je zamenjena novom — koristite najnoviju.")
    if invitation.status is not InvitationStatus.PENDING:
        raise ConflictError("Pozivnica nije na čekanju.")

    # Wrong-account rejection (§23/M2): the accepting principal's verified
    # login emails must include the one this invitation was sent to.
    if invitation.target_email is not None:
        principal_emails = repository.list_principal_emails(db, principal.person_id)
        if invitation.target_email.strip().lower() not in principal_emails:
            raise ForbiddenError("Ova pozivnica je namenjena drugom nalogu.")

    person = repository.get_person(db, principal.person_id)
    if person is None:
        raise UnauthorizedError("Nepoznata osoba.")

    _open_membership(db, invitation.organization_id, person.id)
    assignment = _grant_role(
        db,
        organization_id=invitation.organization_id,
        person_id=person.id,
        role_code=invitation.role_code,
        scope_type=invitation.scope_type,
        scope_ref_id=invitation.scope_ref_id,
        granted_areas=invitation.granted_areas,
    )

    if invitation.type is InvitationType.PARENT and invitation.target_child_person_id:
        _link_guardian(
            db,
            organization_id=invitation.organization_id,
            guardian_person_id=person.id,
            child_person_id=invitation.target_child_person_id,
        )

    invitation.status = InvitationStatus.ACCEPTED
    invitation.person_id = person.id
    invitation.accepted_at = now

    record_audit(
        db,
        data_class=AuditDataClass.ROLE,
        action="invitation.accepted",
        entity_type="invitation",
        entity_id=invitation.id,
        summary=(
            f"„{person.display_name}“ je prihvatio/la pozivnicu za ulogu "
            f"{invitation.role_code.value}."
        ),
        organization_id=invitation.organization_id,
        actor_person_id=person.id,
    )
    enqueue(
        db,
        event_type="invitation.accepted",
        payload={
            "invitation_id": invitation.id,
            "person_id": person.id,
            "organization_id": invitation.organization_id,
            "role_assignment_id": assignment.id,
        },
        organization_id=invitation.organization_id,
    )
    db.commit()

    organization = db.get(Organization, invitation.organization_id)
    assert organization is not None
    return AcceptInvitationResponse(
        context=ContextSummary(
            role_assignment_id=assignment.id,
            organization_id=organization.id,
            organization_name=organization.name,
            role_code=assignment.role_code,
            scope_type=assignment.scope_type,
            scope_ref_id=assignment.scope_ref_id,
        )
    )

