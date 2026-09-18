from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.common.pagination import PageParams
from app.domains.identity.enums import PersonMergeStatus, RoleAssignmentStatus, RoleCode
from app.domains.identity.models import Person, PersonMergeRecord, RoleAssignment
from app.domains.people.models import GuardianRelationship, GuardianSchoolAccess
from app.domains.school.enums import MembershipStatus, OrgMemberType
from app.domains.school.models import SchoolMembership


def find_duplicate_candidates(
    db: Session, school_id: str, given_name: str, family_name: str
) -> list[Person]:
    """People already in THIS school whose name matches (case-insensitive).
    Global identities in other orgs are intentionally invisible here."""
    stmt = (
        select(Person)
        .join(SchoolMembership, SchoolMembership.person_id == Person.id)
        .where(
            SchoolMembership.school_id == school_id,
            SchoolMembership.record_status == RecordStatus.ACTIVE,
            func.lower(Person.given_name) == given_name.strip().lower(),
            func.lower(Person.family_name) == family_name.strip().lower(),
            Person.record_status == RecordStatus.ACTIVE,
        )
        .order_by(Person.display_name)
    )
    return list(db.execute(stmt).scalars().all())


def list_school_people(
    db: Session,
    school_id: str,
    params: PageParams,
    *,
    member_type: OrgMemberType | None = None,
) -> tuple[list[tuple[Person, OrgMemberType]], int]:
    """People visible in this school, each paired with what they are to it.

    ``member_type`` narrows the page to one kind (e.g. ``STAFF`` to populate a
    trainer picker). ``total`` is the count *after* that filter, so a filtered
    page never reports the whole roster's size.
    """
    base = (
        select(Person, SchoolMembership.member_type)
        .join(SchoolMembership, SchoolMembership.person_id == Person.id)
        .where(
            SchoolMembership.school_id == school_id,
            SchoolMembership.status == MembershipStatus.ACTIVE,
            SchoolMembership.record_status == RecordStatus.ACTIVE,
            Person.record_status == RecordStatus.ACTIVE,
        )
    )
    if member_type is not None:
        base = base.where(SchoolMembership.member_type == member_type)
    total = db.execute(
        select(func.count()).select_from(base.order_by(None).subquery())
    ).scalar_one()
    rows = db.execute(
        base.order_by(Person.display_name).limit(params.limit).offset(params.offset)
    ).all()
    return [(row[0], row[1]) for row in rows], total


def get_school_person(db: Session, school_id: str, person_id: str) -> Person | None:
    """A person is visible only through an active membership in the active org.
    Membership *status* (active/suspended/ended) does not affect visibility, a
    suspended member is still administrable."""
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
# Membership lifecycle & school-local data
# ---------------------------------------------------------------------------


def get_membership(
    db: Session, school_id: str, person_id: str
) -> SchoolMembership | None:
    """The one membership row tying a person to this org (unique per tenant)."""
    stmt = select(SchoolMembership).where(
        SchoolMembership.school_id == school_id,
        SchoolMembership.person_id == person_id,
        SchoolMembership.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def count_active_owners(db: Session, school_id: str) -> int:
    """Active OWNER role assignments in this org, the protected-last-owner set."""
    stmt = select(func.count()).select_from(RoleAssignment).where(
        RoleAssignment.school_id == school_id,
        RoleAssignment.role_code == RoleCode.OWNER,
        RoleAssignment.status == RoleAssignmentStatus.ACTIVE,
        RoleAssignment.record_status == RecordStatus.ACTIVE,
    )
    return int(db.execute(stmt).scalar_one())


def is_active_owner(db: Session, school_id: str, person_id: str) -> bool:
    stmt = select(RoleAssignment.id).where(
        RoleAssignment.school_id == school_id,
        RoleAssignment.person_id == person_id,
        RoleAssignment.role_code == RoleCode.OWNER,
        RoleAssignment.status == RoleAssignmentStatus.ACTIVE,
        RoleAssignment.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).first() is not None


def find_local_code_owner(
    db: Session, school_id: str, local_member_code: str, exclude_person_id: str
) -> SchoolMembership | None:
    """Another member in this org already holding ``local_member_code`` (§9)."""
    stmt = select(SchoolMembership).where(
        SchoolMembership.school_id == school_id,
        SchoolMembership.local_member_code == local_member_code,
        SchoolMembership.person_id != exclude_person_id,
        SchoolMembership.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Guardian access
# ---------------------------------------------------------------------------


def get_guardian_access(
    db: Session, school_id: str, child_person_id: str, guardian_person_id: str
) -> GuardianSchoolAccess | None:
    stmt = select(GuardianSchoolAccess).where(
        GuardianSchoolAccess.school_id == school_id,
        GuardianSchoolAccess.child_person_id == child_person_id,
        GuardianSchoolAccess.guardian_person_id == guardian_person_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_guardians_for_child(
    db: Session, school_id: str, child_person_id: str
) -> list[tuple[GuardianSchoolAccess, Person, GuardianRelationship | None]]:
    """Guardian contacts a school holds for a child, with the guardian person and
    the (global) relationship type when one is recorded."""
    stmt = (
        select(GuardianSchoolAccess, Person, GuardianRelationship)
        .join(Person, Person.id == GuardianSchoolAccess.guardian_person_id)
        .outerjoin(
            GuardianRelationship,
            (GuardianRelationship.guardian_person_id
             == GuardianSchoolAccess.guardian_person_id)
            & (GuardianRelationship.child_person_id
               == GuardianSchoolAccess.child_person_id),
        )
        .where(
            GuardianSchoolAccess.school_id == school_id,
            GuardianSchoolAccess.child_person_id == child_person_id,
        )
        .order_by(Person.display_name)
    )
    return [tuple(row) for row in db.execute(stmt).all()]


def child_primary_contacts(
    db: Session, school_id: str, child_person_id: str
) -> list[GuardianSchoolAccess]:
    """Rows currently flagged primary for a child (normally 0 or 1)."""
    stmt = select(GuardianSchoolAccess).where(
        GuardianSchoolAccess.school_id == school_id,
        GuardianSchoolAccess.child_person_id == child_person_id,
        GuardianSchoolAccess.is_primary_contact.is_(True),
    )
    return list(db.execute(stmt).scalars().all())


# ---------------------------------------------------------------------------
# Duplicate detection & review
# ---------------------------------------------------------------------------


def list_duplicate_clusters(db: Session, school_id: str) -> list[tuple[str, str]]:
    """Normalized (given, family) name keys that more than one active member in
    this org shares, the likely-duplicate buckets (§13)."""
    given = func.lower(func.trim(Person.given_name))
    family = func.lower(func.trim(Person.family_name))
    stmt = (
        select(given, family)
        .join(SchoolMembership, SchoolMembership.person_id == Person.id)
        .where(
            SchoolMembership.school_id == school_id,
            SchoolMembership.record_status == RecordStatus.ACTIVE,
            Person.record_status == RecordStatus.ACTIVE,
        )
        .group_by(given, family)
        .having(func.count() > 1)
        .order_by(family, given)
    )
    return [(row[0], row[1]) for row in db.execute(stmt).all()]


def get_merge_review(
    db: Session, school_id: str, review_id: str
) -> PersonMergeRecord | None:
    stmt = select(PersonMergeRecord).where(
        PersonMergeRecord.id == review_id,
        PersonMergeRecord.school_id == school_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def find_open_review(
    db: Session, school_id: str, source_person_id: str, target_person_id: str
) -> PersonMergeRecord | None:
    stmt = select(PersonMergeRecord).where(
        PersonMergeRecord.school_id == school_id,
        PersonMergeRecord.status == PersonMergeStatus.FLAGGED,
        PersonMergeRecord.source_person_id == source_person_id,
        PersonMergeRecord.target_person_id == target_person_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_open_merge_reviews(
    db: Session, school_id: str
) -> list[PersonMergeRecord]:
    stmt = (
        select(PersonMergeRecord)
        .where(
            PersonMergeRecord.school_id == school_id,
            PersonMergeRecord.status == PersonMergeStatus.FLAGGED,
        )
        .order_by(PersonMergeRecord.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())
