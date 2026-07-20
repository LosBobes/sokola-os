from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass, RecordStatus
from app.common.errors import ConflictError, ForbiddenError, NotFoundError
from app.common.slug import slugify
from app.domains.identity.enums import RoleAssignmentStatus, RoleCode, RoleScopeType
from app.domains.identity.models import RoleAssignment
from app.domains.organization.models import Organization, OrganizationMembership
from app.domains.organization.schemas import (
    CreateOrganizationRequest,
    OrganizationResponse,
    TenantPublic,
)
from app.platform.audit.service import record_audit
from app.platform.outbox.service import enqueue
from app.security.auth import Principal
from app.security.context import RequestContext


def _unique_slug(db: Session, name: str) -> str:
    base = slugify(name)
    slug = base
    while db.execute(
        select(Organization.id).where(Organization.slug == slug)
    ).scalar_one_or_none():
        slug = f"{base}-{secrets.token_hex(2)}"
    return slug


def create_organization(
    db: Session, principal: Principal, req: CreateOrganizationRequest
) -> OrganizationResponse:
    """Bootstrap a new tenant. The creating person becomes its OWNER and first
    member, all in one transaction."""
    org = Organization(
        name=req.name, slug=_unique_slug(db, req.name), type=req.type, timezone=req.timezone
    )
    db.add(org)
    db.flush()

    db.add(OrganizationMembership(organization_id=org.id, person_id=principal.person_id))
    db.add(
        RoleAssignment(
            person_id=principal.person_id,
            organization_id=org.id,
            role_code=RoleCode.OWNER,
            scope_type=RoleScopeType.ORGANIZATION,
        )
    )
    record_audit(
        db,
        data_class=AuditDataClass.ROLE,
        action="organization.created",
        entity_type="organization",
        entity_id=org.id,
        summary=f"Osnovana organizacija „{org.name}“.",
        organization_id=org.id,
        actor_person_id=principal.person_id,
    )
    enqueue(
        db,
        event_type="organization.created",
        payload={"organization_id": org.id, "owner_person_id": principal.person_id},
        organization_id=org.id,
    )
    db.commit()
    return OrganizationResponse.model_validate(org)


def get_organization(db: Session, organization_id: str) -> OrganizationResponse:
    org = db.get(Organization, organization_id)
    assert org is not None  # context guarantees the active org exists
    return OrganizationResponse.model_validate(org)


def lookup_tenant(db: Session, slug: str) -> TenantPublic:
    """Public: resolve a school code to the tenant a login should target."""
    org = db.execute(
        select(Organization).where(
            Organization.slug == slug,
            Organization.record_status == RecordStatus.ACTIVE,
        )
    ).scalar_one_or_none()
    if org is None or org.slug is None:
        raise NotFoundError("Škola sa ovim kodom nije pronađena.")
    return TenantPublic(organization_id=org.id, name=org.name, slug=org.slug)


# ---------------------------------------------------------------------------
# Deactivate / reactivate (§31) — P1
# ---------------------------------------------------------------------------


def _is_active_owner(db: Session, organization_id: str, person_id: str) -> bool:
    stmt = select(RoleAssignment.id).where(
        RoleAssignment.organization_id == organization_id,
        RoleAssignment.person_id == person_id,
        RoleAssignment.role_code == RoleCode.OWNER,
        RoleAssignment.status == RoleAssignmentStatus.ACTIVE,
        RoleAssignment.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).first() is not None


def deactivate_organization(db: Session, context: RequestContext) -> OrganizationResponse:
    """Deactivating a school locks out every future context resolution against
    it (``app.security.deps.get_context`` rejects an ARCHIVED org) — so
    reactivation cannot go through that same context-gated path; see
    :func:`reactivate_organization`."""
    org = db.get(Organization, context.organization_id)
    assert org is not None  # context guarantees the active org exists
    if org.record_status is RecordStatus.ARCHIVED:
        raise ConflictError("Škola je već deaktivirana.")

    org.record_status = RecordStatus.ARCHIVED
    record_audit(
        db,
        data_class=AuditDataClass.ROLE,
        action="organization.deactivated",
        entity_type="organization",
        entity_id=org.id,
        summary=f"Škola „{org.name}“ je deaktivirana.",
        organization_id=org.id,
        actor_person_id=context.person_id,
    )
    enqueue(
        db,
        event_type="organization.deactivated",
        payload={"organization_id": org.id},
        organization_id=org.id,
    )
    db.commit()
    return OrganizationResponse.model_validate(org)


def reactivate_organization(
    db: Session, principal: Principal, organization_id: str
) -> OrganizationResponse:
    """A deactivated org blocks ordinary context resolution (§31), so this is
    authorized directly against an ACTIVE OWNER role assignment for the named
    org — the same authority ``require_permission(ROLES)`` grants an OWNER,
    evaluated without the context the deactivation itself makes unreachable."""
    org = db.get(Organization, organization_id)
    if org is None:
        raise NotFoundError("Škola nije pronađena.")
    if not _is_active_owner(db, organization_id, principal.person_id):
        raise ForbiddenError("Nemate ovlašćenje za ovu radnju.")
    if org.record_status is RecordStatus.ACTIVE:
        raise ConflictError("Škola je već aktivna.")

    org.record_status = RecordStatus.ACTIVE
    record_audit(
        db,
        data_class=AuditDataClass.ROLE,
        action="organization.reactivated",
        entity_type="organization",
        entity_id=org.id,
        summary=f"Škola „{org.name}“ je ponovo aktivirana.",
        organization_id=org.id,
        actor_person_id=principal.person_id,
    )
    enqueue(
        db,
        event_type="organization.reactivated",
        payload={"organization_id": org.id},
        organization_id=org.id,
    )
    db.commit()
    return OrganizationResponse.model_validate(org)
