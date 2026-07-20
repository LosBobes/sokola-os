from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.common.pagination import PageParams
from app.domains.identity.enums import (
    AuthIdentifierType,
    InvitationStatus,
    RoleAssignmentStatus,
    RoleCode,
    RoleScopeType,
)
from app.domains.identity.models import (
    AuthAccount,
    AuthIdentifier,
    Invitation,
    Person,
    RoleAssignment,
)
from app.domains.organization.models import Organization, OrganizationMembership
from app.domains.people.models import GuardianOrganizationAccess, GuardianRelationship


def get_person(db: Session, person_id: str) -> Person | None:
    return db.get(Person, person_id)


def list_active_contexts(db: Session, person_id: str) -> list[tuple[RoleAssignment, Organization]]:
    """Active role assignments for a person, paired with their organization.

    This is the only source of a person's selectable contexts; a person is never
    granted access just because an organization exists.
    """
    stmt = (
        select(RoleAssignment, Organization)
        .join(Organization, Organization.id == RoleAssignment.organization_id)
        .where(
            RoleAssignment.person_id == person_id,
            RoleAssignment.status == RoleAssignmentStatus.ACTIVE,
            RoleAssignment.record_status == RecordStatus.ACTIVE,
            Organization.record_status == RecordStatus.ACTIVE,
        )
        .order_by(Organization.name, RoleAssignment.role_code)
    )
    return [tuple(row) for row in db.execute(stmt).all()]


# ---------------------------------------------------------------------------
# Organization membership (visibility check only — full lifecycle is owned by
# the people domain; this domain only needs to know "is this person in the
# org" and "open a membership on acceptance").
# ---------------------------------------------------------------------------


def get_membership(
    db: Session, organization_id: str, person_id: str
) -> OrganizationMembership | None:
    stmt = select(OrganizationMembership).where(
        OrganizationMembership.organization_id == organization_id,
        OrganizationMembership.person_id == person_id,
        OrganizationMembership.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def is_org_member(db: Session, organization_id: str, person_id: str) -> bool:
    return get_membership(db, organization_id, person_id) is not None


def get_org_person(db: Session, organization_id: str, person_id: str) -> Person | None:
    """A person visible through an active membership in this org."""
    stmt = (
        select(Person)
        .join(OrganizationMembership, OrganizationMembership.person_id == Person.id)
        .where(
            Person.id == person_id,
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.record_status == RecordStatus.ACTIVE,
            Person.record_status == RecordStatus.ACTIVE,
        )
    )
    return db.execute(stmt).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------


def get_invitation(db: Session, organization_id: str, invitation_id: str) -> Invitation | None:
    stmt = select(Invitation).where(
        Invitation.id == invitation_id, Invitation.organization_id == organization_id
    )
    return db.execute(stmt).scalar_one_or_none()


def get_invitation_by_token_hash(db: Session, token_hash: str) -> Invitation | None:
    stmt = select(Invitation).where(Invitation.token_hash == token_hash)
    return db.execute(stmt).scalar_one_or_none()


def list_org_invitations(
    db: Session, organization_id: str, params: PageParams
) -> tuple[list[Invitation], int]:
    base = select(Invitation).where(Invitation.organization_id == organization_id)
    count_stmt = select(func.count()).select_from(base.order_by(None).subquery())
    total = db.execute(count_stmt).scalar_one()
    page_stmt = (
        base.order_by(Invitation.created_at.desc()).limit(params.limit).offset(params.offset)
    )
    rows = db.execute(page_stmt).scalars().all()
    return list(rows), total


def list_principal_emails(db: Session, person_id: str) -> set[str]:
    """Every email this person has ever authenticated with (lowercased). The
    surface used to decide "wrong account" on invite acceptance (§23)."""
    stmt = (
        select(AuthIdentifier.value)
        .join(AuthAccount, AuthAccount.id == AuthIdentifier.auth_account_id)
        .where(AuthAccount.person_id == person_id, AuthIdentifier.type == AuthIdentifierType.EMAIL)
    )
    return {value.strip().lower() for value in db.execute(stmt).scalars().all()}


# ---------------------------------------------------------------------------
# Role assignments
# ---------------------------------------------------------------------------


def get_assignment(db: Session, organization_id: str, assignment_id: str) -> RoleAssignment | None:
    stmt = select(RoleAssignment).where(
        RoleAssignment.id == assignment_id, RoleAssignment.organization_id == organization_id
    )
    return db.execute(stmt).scalar_one_or_none()


def find_assignment(
    db: Session,
    *,
    organization_id: str,
    person_id: str,
    role_code: RoleCode,
    scope_type: RoleScopeType,
    scope_ref_id: str | None,
) -> RoleAssignment | None:
    """The one assignment matching the ``uq_role_assignment`` key, any status."""
    stmt = select(RoleAssignment).where(
        RoleAssignment.organization_id == organization_id,
        RoleAssignment.person_id == person_id,
        RoleAssignment.role_code == role_code,
        RoleAssignment.scope_type == scope_type,
        RoleAssignment.scope_ref_id == scope_ref_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_org_assignments(
    db: Session, organization_id: str, params: PageParams
) -> tuple[list[tuple[RoleAssignment, Person]], int]:
    base = (
        select(RoleAssignment, Person)
        .join(Person, Person.id == RoleAssignment.person_id)
        .where(RoleAssignment.organization_id == organization_id)
    )
    count_stmt = select(func.count()).select_from(base.order_by(None).subquery())
    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(
        base.order_by(Person.display_name).limit(params.limit).offset(params.offset)
    ).all()
    return [tuple(row) for row in rows], total


def count_active_owners(db: Session, organization_id: str) -> int:
    """Active OWNER role assignments in this org — the protected-last-owner set."""
    stmt = select(func.count()).select_from(RoleAssignment).where(
        RoleAssignment.organization_id == organization_id,
        RoleAssignment.role_code == RoleCode.OWNER,
        RoleAssignment.status == RoleAssignmentStatus.ACTIVE,
        RoleAssignment.record_status == RecordStatus.ACTIVE,
    )
    return int(db.execute(stmt).scalar_one())


def has_active_owner_assignment(db: Session, organization_id: str, person_id: str) -> bool:
    stmt = select(RoleAssignment.id).where(
        RoleAssignment.organization_id == organization_id,
        RoleAssignment.person_id == person_id,
        RoleAssignment.role_code == RoleCode.OWNER,
        RoleAssignment.status == RoleAssignmentStatus.ACTIVE,
        RoleAssignment.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).first() is not None


# ---------------------------------------------------------------------------
# Guardian access (PARENT invitation acceptance — §19.4/19.5)
# ---------------------------------------------------------------------------


def get_guardian_relationship(
    db: Session, guardian_person_id: str, child_person_id: str
) -> GuardianRelationship | None:
    stmt = select(GuardianRelationship).where(
        GuardianRelationship.guardian_person_id == guardian_person_id,
        GuardianRelationship.child_person_id == child_person_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def get_guardian_access(
    db: Session, organization_id: str, guardian_person_id: str, child_person_id: str
) -> GuardianOrganizationAccess | None:
    stmt = select(GuardianOrganizationAccess).where(
        GuardianOrganizationAccess.organization_id == organization_id,
        GuardianOrganizationAccess.guardian_person_id == guardian_person_id,
        GuardianOrganizationAccess.child_person_id == child_person_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def expire_stale_pending(db: Session, invitation: Invitation, *, now: dt.datetime) -> bool:
    """Lazily flip a PENDING invitation past its expiry to EXPIRED. Returns True
    if the invitation is (now) expired."""
    if invitation.status is InvitationStatus.PENDING and invitation.expires_at <= now:
        invitation.status = InvitationStatus.EXPIRED
        return True
    return invitation.status is InvitationStatus.EXPIRED


__all__ = [
    "count_active_owners",
    "expire_stale_pending",
    "find_assignment",
    "get_assignment",
    "get_guardian_access",
    "get_guardian_relationship",
    "get_invitation",
    "get_invitation_by_token_hash",
    "get_membership",
    "get_org_person",
    "get_person",
    "has_active_owner_assignment",
    "is_org_member",
    "list_active_contexts",
    "list_org_assignments",
    "list_org_invitations",
    "list_principal_emails",
]
