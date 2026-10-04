from __future__ import annotations

import datetime as dt

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.common.pagination import PageParams
from app.domains.identity.accounts import login_emails_for_person
from app.domains.identity.enums import (
    OPEN_ROLE_ASSIGNMENT_STATUSES,
    InvitationStatus,
    RoleAssignmentStatus,
    RoleCode,
    RoleScopeType,
)
from app.domains.identity.models import (
    Invitation,
    Person,
    RoleAssignment,
)
from app.domains.people.models import GuardianRelationship, GuardianSchoolAccess
from app.domains.school.enums import SchoolStatus
from app.domains.school.models import School, SchoolMembership


def get_person(db: Session, person_id: str) -> Person | None:
    return db.get(Person, person_id)


def list_active_contexts(db: Session, person_id: str) -> list[tuple[RoleAssignment, School]]:
    """Active role assignments for a person, paired with their school.

    This is the only source of a person's selectable contexts; a person is never
    granted access just because an school exists.
    """
    stmt = (
        select(RoleAssignment, School)
        .join(School, School.id == RoleAssignment.school_id)
        .where(
            RoleAssignment.person_id == person_id,
            RoleAssignment.status == RoleAssignmentStatus.ACTIVE,
            RoleAssignment.record_status == RecordStatus.ACTIVE,
            School.status != SchoolStatus.DEACTIVATED,
        )
        .order_by(School.name, RoleAssignment.role_code)
    )
    return [tuple(row) for row in db.execute(stmt).all()]


# ---------------------------------------------------------------------------
# School membership (visibility check only, full lifecycle is owned by
# the people domain; this domain only needs to know "is this person in the
# org" and "open a membership on acceptance").
# ---------------------------------------------------------------------------


def get_membership(
    db: Session, school_id: str, person_id: str
) -> SchoolMembership | None:
    stmt = select(SchoolMembership).where(
        SchoolMembership.school_id == school_id,
        SchoolMembership.person_id == person_id,
        SchoolMembership.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def is_school_member(db: Session, school_id: str, person_id: str) -> bool:
    return get_membership(db, school_id, person_id) is not None


def get_school_person(db: Session, school_id: str, person_id: str) -> Person | None:
    """A person visible through an active membership in this org."""
    stmt = (
        select(Person)
        .join(SchoolMembership, SchoolMembership.person_id == Person.id)
        .where(
            Person.id == person_id,
            SchoolMembership.school_id == school_id,
            SchoolMembership.record_status == RecordStatus.ACTIVE,
            Person.record_status == RecordStatus.ACTIVE,
        )
    )
    return db.execute(stmt).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Invitations
# ---------------------------------------------------------------------------


def get_invitation(db: Session, school_id: str, invitation_id: str) -> Invitation | None:
    stmt = select(Invitation).where(
        Invitation.id == invitation_id, Invitation.school_id == school_id
    )
    return db.execute(stmt).scalar_one_or_none()


def get_invitation_by_token_hash(db: Session, token_hash: str) -> Invitation | None:
    stmt = select(Invitation).where(Invitation.token_hash == token_hash)
    return db.execute(stmt).scalar_one_or_none()


def list_school_invitations(
    db: Session, school_id: str, params: PageParams
) -> tuple[list[Invitation], int]:
    base = select(Invitation).where(Invitation.school_id == school_id)
    count_stmt = select(func.count()).select_from(base.order_by(None).subquery())
    total = db.execute(count_stmt).scalar_one()
    page_stmt = (
        base.order_by(Invitation.created_at.desc()).limit(params.limit).offset(params.offset)
    )
    rows = db.execute(page_stmt).scalars().all()
    return list(rows), total


def list_principal_emails(db: Session, person_id: str) -> set[str]:
    """Every address this person's linked identities sign in with (lowercased).

    The surface that decides "wrong account" on invite acceptance (§23). It
    refuses; it never admits — see M01 §4.5 and
    :func:`app.domains.identity.accounts.login_emails_for_person`.
    """
    return login_emails_for_person(db, person_id)


# ---------------------------------------------------------------------------
# Role assignments
# ---------------------------------------------------------------------------


def get_assignment(db: Session, school_id: str, assignment_id: str) -> RoleAssignment | None:
    stmt = select(RoleAssignment).where(
        RoleAssignment.id == assignment_id, RoleAssignment.school_id == school_id
    )
    return db.execute(stmt).scalar_one_or_none()


def find_open_assignment(
    db: Session,
    *,
    school_id: str,
    person_id: str,
    role_code: RoleCode,
    scope_type: RoleScopeType,
    scope_ref_id: str | None,
) -> RoleAssignment | None:
    """The one *open* assignment for this natural key, or none.

    "Open" is `ACTIVE` or `SUSPENDED`, matching `uq_role_assignment_open`
    exactly — so this returns at most one row by construction rather than by
    hope. The predecessor filtered on status not at all and ended in
    `scalar_one_or_none()`, which was correct only while a revoked row could
    not coexist with a live one. It can now, deliberately: §5.2 makes REVOKED
    terminal and history stays beside the new grant.
    """
    stmt = select(RoleAssignment).where(
        RoleAssignment.school_id == school_id,
        RoleAssignment.person_id == person_id,
        RoleAssignment.role_code == role_code,
        RoleAssignment.scope_type == scope_type,
        RoleAssignment.scope_ref_id == scope_ref_id,
        RoleAssignment.status.in_(OPEN_ROLE_ASSIGNMENT_STATUSES),
    )
    return db.execute(stmt).scalar_one_or_none()


def list_school_assignments(
    db: Session, school_id: str, params: PageParams
) -> tuple[list[tuple[RoleAssignment, Person]], int]:
    base = (
        select(RoleAssignment, Person)
        .join(Person, Person.id == RoleAssignment.person_id)
        .where(RoleAssignment.school_id == school_id)
    )
    count_stmt = select(func.count()).select_from(base.order_by(None).subquery())
    total = db.execute(count_stmt).scalar_one()
    rows = db.execute(
        base.order_by(Person.display_name).limit(params.limit).offset(params.offset)
    ).all()
    return [tuple(row) for row in rows], total


def count_active_owners(db: Session, school_id: str) -> int:
    """How many *people* actively own this school — the protected-last-owner set.

    Distinct persons, not rows. The last-owner guard asks "would this leave the
    school ownerless", which is a question about people; counting assignments
    answered it correctly only while one person could not hold two. Until
    `uq_role_assignment_open` they could, because the old unique constraint did
    not bind when `scope_ref_id` was null (F-51) — so a duplicated row read as
    a second owner and made the guard's answer depend on a bug elsewhere.
    Counting people is right regardless of what the schema permits.
    """
    stmt = select(func.count(distinct(RoleAssignment.person_id))).where(
        RoleAssignment.school_id == school_id,
        RoleAssignment.role_code == RoleCode.OWNER,
        RoleAssignment.status == RoleAssignmentStatus.ACTIVE,
        RoleAssignment.record_status == RecordStatus.ACTIVE,
    )
    return int(db.execute(stmt).scalar_one())


def has_active_owner_assignment(db: Session, school_id: str, person_id: str) -> bool:
    stmt = select(RoleAssignment.id).where(
        RoleAssignment.school_id == school_id,
        RoleAssignment.person_id == person_id,
        RoleAssignment.role_code == RoleCode.OWNER,
        RoleAssignment.status == RoleAssignmentStatus.ACTIVE,
        RoleAssignment.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).first() is not None


# ---------------------------------------------------------------------------
# Guardian access (PARENT invitation acceptance, §19.4/19.5)
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
    db: Session, school_id: str, guardian_person_id: str, child_person_id: str
) -> GuardianSchoolAccess | None:
    stmt = select(GuardianSchoolAccess).where(
        GuardianSchoolAccess.school_id == school_id,
        GuardianSchoolAccess.guardian_person_id == guardian_person_id,
        GuardianSchoolAccess.child_person_id == child_person_id,
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
    "find_open_assignment",
    "get_assignment",
    "get_guardian_access",
    "get_guardian_relationship",
    "get_invitation",
    "get_invitation_by_token_hash",
    "get_membership",
    "get_school_person",
    "get_person",
    "has_active_owner_assignment",
    "is_school_member",
    "list_active_contexts",
    "list_school_assignments",
    "list_school_invitations",
    "list_principal_emails",
]
