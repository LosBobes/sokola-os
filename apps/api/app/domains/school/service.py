from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass, RecordStatus
from app.common.errors import ConflictError, ForbiddenError, NotFoundError
from app.common.ids import new_id
from app.common.slug import slugify
from app.domains.identity.enums import RoleAssignmentStatus, RoleCode, RoleScopeType
from app.domains.identity.models import RoleAssignment
from app.domains.organization.enums import OrganizationSchoolChangeReason
from app.domains.organization.models import Organization
from app.domains.school import anchor
from app.domains.school.enums import (
    LocatorKind,
    MembershipType,
    SchoolStatus,
    SchoolStatusReason,
)
from app.domains.school.models import School, SchoolMembership
from app.domains.school.schemas import (
    CreateSchoolRequest,
    SchoolResponse,
    TenantPublic,
)
from app.platform.audit.service import record_audit
from app.platform.outbox.service import enqueue
from app.security.auth import Principal
from app.security.context import RequestContext

#: Marks an organization the platform created because a school needed one, not
#: because a legal entity was recorded. M04 §3.1.3 requires every school to hold
#: a current organization link from creation, and self-service signup has no real
#: organization to point at yet — so one is provisioned and later replaced by a
#: real one through an ORG-04 transfer, which is exactly what that command is for.
PLACEHOLDER_ORGANIZATION_CASE_REF = "SELF_PROVISIONED"


def _unique_slug(db: Session, name: str) -> str:
    base = slugify(name)
    slug = base
    while db.execute(
        select(School.id).where(School.slug == slug)
    ).scalar_one_or_none():
        slug = f"{base}-{secrets.token_hex(2)}"
    return slug


def create_school(
    db: Session, principal: Principal, req: CreateSchoolRequest
) -> SchoolResponse:
    """Bootstrap a new tenant. The creating person becomes its OWNER and first
    member, all in one transaction. The school starts ``IN_PREPARATION``
    ("u pripremi"), guided onboarding (app.domains.onboarding) walks it through
    structure setup and an optional co-owner invite before it may ``activate``.

    The M04 anchor is built here too, in the same transaction: a placeholder
    organization and its link, both locators, and status transition #1. A school
    that exists without them would violate §3.1.3 and §3.7.1 from the moment it
    is created, and there is no later step in this repository that would repair
    that — M04's own SCH-01 command needs M02/M05/M06 and is finding F-12.
    """
    org = School(
        name=req.name,
        slug=_unique_slug(db, req.name),
        provisioning_reference=new_id("prov"),
        type=req.type,
        timezone=req.timezone,
        status=SchoolStatus.IN_PREPARATION,
    )
    db.add(org)
    db.flush()

    holder = Organization(
        organization_ref=new_id("oref"),
        legal_name=org.name,
        country_code="RS",
        created_by_actor_ref=principal.person_id,
        updated_by_actor_ref=principal.person_id,
    )
    db.add(holder)
    db.flush()
    anchor.open_organization_link(
        db,
        school_id=org.id,
        organization=holder,
        reason=OrganizationSchoolChangeReason.INITIAL_PROVISIONING,
        case_reference=PLACEHOLDER_ORGANIZATION_CASE_REF,
        actor_ref=principal.person_id,
    )
    # The slug column stays the operative one for existing lookups; the locator
    # is its M04 authority and is issued from the same value so the two agree.
    assert org.slug is not None
    anchor.issue_locator(
        db,
        school_id=org.id,
        kind=LocatorKind.SLUG,
        value=org.slug,
        actor_ref=principal.person_id,
    )
    anchor.issue_school_code(db, school_id=org.id, actor_ref=principal.person_id)
    anchor.record_creation(
        db, school=org, actor_ref=principal.person_id, correlation_id=new_id("corr")
    )

    # The founder runs the school, they are not one of its polaznici, so the
    # first membership is STAFF. Otherwise every brand-new school would open
    # reporting "1 aktivan član" before a single child was enrolled.
    db.add(
        SchoolMembership(
            school_id=org.id,
            person_id=principal.person_id,
            membership_type=MembershipType.STAFF,
        )
    )
    db.add(
        RoleAssignment(
            person_id=principal.person_id,
            school_id=org.id,
            role_code=RoleCode.OWNER,
            scope_type=RoleScopeType.SCHOOL,
        )
    )
    record_audit(
        db,
        data_class=AuditDataClass.ROLE,
        action="school.created",
        entity_type="school",
        entity_id=org.id,
        summary=f"Osnovana organizacija „{org.name}“.",
        school_id=org.id,
        actor_person_id=principal.person_id,
    )
    enqueue(
        db,
        event_type="school.created",
        payload={"school_id": org.id, "owner_person_id": principal.person_id},
        school_id=org.id,
    )
    db.commit()
    return SchoolResponse.model_validate(org)


def get_school(db: Session, school_id: str) -> SchoolResponse:
    org = db.get(School, school_id)
    assert org is not None  # context guarantees the active org exists
    return SchoolResponse.model_validate(org)


def lookup_tenant(db: Session, slug: str) -> TenantPublic:
    """Public: resolve a school code to the tenant a login should target."""
    org = db.execute(
        select(School).where(
            School.slug == slug,
            School.status != SchoolStatus.DEACTIVATED,
        )
    ).scalar_one_or_none()
    if org is None or org.slug is None:
        raise NotFoundError("Škola sa ovim kodom nije pronađena.")
    return TenantPublic(school_id=org.id, name=org.name, slug=org.slug)


# ---------------------------------------------------------------------------
# Deactivate / reactivate (§31), P1
# ---------------------------------------------------------------------------


def _is_active_owner(db: Session, school_id: str, person_id: str) -> bool:
    stmt = select(RoleAssignment.id).where(
        RoleAssignment.school_id == school_id,
        RoleAssignment.person_id == person_id,
        RoleAssignment.role_code == RoleCode.OWNER,
        RoleAssignment.status == RoleAssignmentStatus.ACTIVE,
        RoleAssignment.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).first() is not None


def deactivate_school(db: Session, context: RequestContext) -> SchoolResponse:
    """Deactivating a school locks out every future context resolution against
    it (``app.security.deps.get_context`` rejects an ARCHIVED org), so
    reactivation cannot go through that same context-gated path; see
    :func:`reactivate_school`."""
    org = db.get(School, context.school_id)
    assert org is not None  # context guarantees the active org exists
    if org.status is SchoolStatus.DEACTIVATED:
        raise ConflictError("Škola je već deaktivirana.")

    anchor.transition_status(
        db,
        school=org,
        to_status=SchoolStatus.DEACTIVATED,
        reason_code=SchoolStatusReason.OPERATIONAL_PAUSE,
        reason_note="Deaktivacija iz školskog podešavanja.",
        actor_ref=context.person_id,
        correlation_id=new_id("corr"),
    )
    record_audit(
        db,
        data_class=AuditDataClass.ROLE,
        action="school.deactivated",
        entity_type="school",
        entity_id=org.id,
        summary=f"Škola „{org.name}“ je deaktivirana.",
        school_id=org.id,
        actor_person_id=context.person_id,
    )
    enqueue(
        db,
        event_type="school.deactivated",
        payload={"school_id": org.id},
        school_id=org.id,
    )
    db.commit()
    return SchoolResponse.model_validate(org)


def reactivate_school(
    db: Session, principal: Principal, school_id: str
) -> SchoolResponse:
    """A deactivated org blocks ordinary context resolution (§31), so this is
    authorized directly against an ACTIVE OWNER role assignment for the named
    org, the same authority ``require_permission(ROLES)`` grants an OWNER,
    evaluated without the context the deactivation itself makes unreachable."""
    org = db.get(School, school_id)
    if org is None:
        raise NotFoundError("Škola nije pronađena.")
    if not _is_active_owner(db, school_id, principal.person_id):
        raise ForbiddenError("Nemate ovlašćenje za ovu radnju.")
    if org.status is not SchoolStatus.DEACTIVATED:
        raise ConflictError("Škola je već aktivna.")

    anchor.transition_status(
        db,
        school=org,
        to_status=SchoolStatus.ACTIVE,
        reason_code=SchoolStatusReason.OPERATIONAL_RESUME,
        reason_note="Ponovno aktiviranje od strane vlasnika.",
        actor_ref=principal.person_id,
        correlation_id=new_id("corr"),
    )
    record_audit(
        db,
        data_class=AuditDataClass.ROLE,
        action="school.reactivated",
        entity_type="school",
        entity_id=org.id,
        summary=f"Škola „{org.name}“ je ponovo aktivirana.",
        school_id=org.id,
        actor_person_id=principal.person_id,
    )
    enqueue(
        db,
        event_type="school.reactivated",
        payload={"school_id": org.id},
        school_id=org.id,
    )
    db.commit()
    return SchoolResponse.model_validate(org)
