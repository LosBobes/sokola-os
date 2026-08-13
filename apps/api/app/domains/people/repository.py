from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.common.pagination import PageParams
from app.domains.identity.enums import PersonMergeStatus, RoleAssignmentStatus, RoleCode
from app.domains.identity.models import Person, PersonMergeRecord, RoleAssignment
from app.domains.organization.enums import MembershipStatus
from app.domains.organization.models import OrganizationMembership
from app.domains.people.models import GuardianOrganizationAccess, GuardianRelationship


def find_duplicate_candidates(
    db: Session, organization_id: str, given_name: str, family_name: str
) -> list[Person]:
    """People already in THIS organization whose name matches (case-insensitive).
    Global identities in other orgs are intentionally invisible here."""
    stmt = (
        select(Person)
        .join(OrganizationMembership, OrganizationMembership.person_id == Person.id)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.record_status == RecordStatus.ACTIVE,
            func.lower(Person.given_name) == given_name.strip().lower(),
            func.lower(Person.family_name) == family_name.strip().lower(),
            Person.record_status == RecordStatus.ACTIVE,
        )
        .order_by(Person.display_name)
    )
    return list(db.execute(stmt).scalars().all())


def list_org_people(
    db: Session, organization_id: str, params: PageParams
) -> tuple[list[Person], int]:
    base = (
        select(Person)
        .join(OrganizationMembership, OrganizationMembership.person_id == Person.id)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.status == MembershipStatus.ACTIVE,
            OrganizationMembership.record_status == RecordStatus.ACTIVE,
            Person.record_status == RecordStatus.ACTIVE,
        )
    )
    total = db.execute(
        select(func.count()).select_from(base.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(
            base.order_by(Person.display_name).limit(params.limit).offset(params.offset)
        )
        .scalars()
        .all()
    )
    return list(rows), total


def get_org_person(db: Session, organization_id: str, person_id: str) -> Person | None:
    """A person is visible only through an active membership in the active org.
    Membership *status* (active/suspended/ended) does not affect visibility, a
    suspended member is still administrable."""
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
# Membership lifecycle & school-local data
# ---------------------------------------------------------------------------


def get_membership(
    db: Session, organization_id: str, person_id: str
) -> OrganizationMembership | None:
    """The one membership row tying a person to this org (unique per tenant)."""
    stmt = select(OrganizationMembership).where(
        OrganizationMembership.organization_id == organization_id,
        OrganizationMembership.person_id == person_id,
        OrganizationMembership.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def count_active_owners(db: Session, organization_id: str) -> int:
    """Active OWNER role assignments in this org, the protected-last-owner set."""
    stmt = select(func.count()).select_from(RoleAssignment).where(
        RoleAssignment.organization_id == organization_id,
        RoleAssignment.role_code == RoleCode.OWNER,
        RoleAssignment.status == RoleAssignmentStatus.ACTIVE,
        RoleAssignment.record_status == RecordStatus.ACTIVE,
    )
    return int(db.execute(stmt).scalar_one())


def is_active_owner(db: Session, organization_id: str, person_id: str) -> bool:
    stmt = select(RoleAssignment.id).where(
        RoleAssignment.organization_id == organization_id,
        RoleAssignment.person_id == person_id,
        RoleAssignment.role_code == RoleCode.OWNER,
        RoleAssignment.status == RoleAssignmentStatus.ACTIVE,
        RoleAssignment.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).first() is not None


def find_local_code_owner(
    db: Session, organization_id: str, local_member_code: str, exclude_person_id: str
) -> OrganizationMembership | None:
    """Another member in this org already holding ``local_member_code`` (§9)."""
    stmt = select(OrganizationMembership).where(
        OrganizationMembership.organization_id == organization_id,
        OrganizationMembership.local_member_code == local_member_code,
        OrganizationMembership.person_id != exclude_person_id,
        OrganizationMembership.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Guardian access
# ---------------------------------------------------------------------------


def get_guardian_access(
    db: Session, organization_id: str, child_person_id: str, guardian_person_id: str
) -> GuardianOrganizationAccess | None:
    stmt = select(GuardianOrganizationAccess).where(
        GuardianOrganizationAccess.organization_id == organization_id,
        GuardianOrganizationAccess.child_person_id == child_person_id,
        GuardianOrganizationAccess.guardian_person_id == guardian_person_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_guardians_for_child(
    db: Session, organization_id: str, child_person_id: str
) -> list[tuple[GuardianOrganizationAccess, Person, GuardianRelationship | None]]:
    """Guardian contacts a school holds for a child, with the guardian person and
    the (global) relationship type when one is recorded."""
    stmt = (
        select(GuardianOrganizationAccess, Person, GuardianRelationship)
        .join(Person, Person.id == GuardianOrganizationAccess.guardian_person_id)
        .outerjoin(
            GuardianRelationship,
            (GuardianRelationship.guardian_person_id
             == GuardianOrganizationAccess.guardian_person_id)
            & (GuardianRelationship.child_person_id
               == GuardianOrganizationAccess.child_person_id),
        )
        .where(
            GuardianOrganizationAccess.organization_id == organization_id,
            GuardianOrganizationAccess.child_person_id == child_person_id,
        )
        .order_by(Person.display_name)
    )
    return [tuple(row) for row in db.execute(stmt).all()]


def child_primary_contacts(
    db: Session, organization_id: str, child_person_id: str
) -> list[GuardianOrganizationAccess]:
    """Rows currently flagged primary for a child (normally 0 or 1)."""
    stmt = select(GuardianOrganizationAccess).where(
        GuardianOrganizationAccess.organization_id == organization_id,
        GuardianOrganizationAccess.child_person_id == child_person_id,
        GuardianOrganizationAccess.is_primary_contact.is_(True),
    )
    return list(db.execute(stmt).scalars().all())


# ---------------------------------------------------------------------------
# Duplicate detection & review
# ---------------------------------------------------------------------------


def list_duplicate_clusters(db: Session, organization_id: str) -> list[tuple[str, str]]:
    """Normalized (given, family) name keys that more than one active member in
    this org shares, the likely-duplicate buckets (§13)."""
    given = func.lower(func.trim(Person.given_name))
    family = func.lower(func.trim(Person.family_name))
    stmt = (
        select(given, family)
        .join(OrganizationMembership, OrganizationMembership.person_id == Person.id)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.record_status == RecordStatus.ACTIVE,
            Person.record_status == RecordStatus.ACTIVE,
        )
        .group_by(given, family)
        .having(func.count() > 1)
        .order_by(family, given)
    )
    return [(row[0], row[1]) for row in db.execute(stmt).all()]


def get_merge_review(
    db: Session, organization_id: str, review_id: str
) -> PersonMergeRecord | None:
    stmt = select(PersonMergeRecord).where(
        PersonMergeRecord.id == review_id,
        PersonMergeRecord.organization_id == organization_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def find_open_review(
    db: Session, organization_id: str, source_person_id: str, target_person_id: str
) -> PersonMergeRecord | None:
    stmt = select(PersonMergeRecord).where(
        PersonMergeRecord.organization_id == organization_id,
        PersonMergeRecord.status == PersonMergeStatus.FLAGGED,
        PersonMergeRecord.source_person_id == source_person_id,
        PersonMergeRecord.target_person_id == target_person_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_open_merge_reviews(
    db: Session, organization_id: str
) -> list[PersonMergeRecord]:
    stmt = (
        select(PersonMergeRecord)
        .where(
            PersonMergeRecord.organization_id == organization_id,
            PersonMergeRecord.status == PersonMergeStatus.FLAGGED,
        )
        .order_by(PersonMergeRecord.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())
