from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass, RecordStatus
from app.common.errors import NotFoundError
from app.common.slug import slugify
from app.domains.identity.enums import RoleCode, RoleScopeType
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
