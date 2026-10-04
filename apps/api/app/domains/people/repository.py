from __future__ import annotations

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.common.pagination import PageParams
from app.domains.identity.enums import (
    OPEN_ROLE_ASSIGNMENT_STATUSES,
    PersonMergeStatus,
    RoleAssignmentStatus,
    RoleCode,
    RoleRevokeReason,
)
from app.domains.identity.models import Person, PersonMergeRecord, RoleAssignment
from app.domains.people.models import GuardianRelationship, GuardianSchoolAccess
from app.domains.people.profile_models import (
    SchoolPersonProfile,
    normalize_local_person_code,
)
from app.domains.school.enums import MembershipStatus, MembershipType
from app.domains.school.models import SchoolMembership
from app.platform import clock


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
    member_type: MembershipType | None = None,
) -> tuple[list[tuple[Person, MembershipType]], int]:
    """People visible in this school, each paired with what they are to it.

    ``member_type`` narrows the page to one kind (e.g. ``STAFF`` to populate a
    trainer picker). ``total`` is the count *after* that filter, so a filtered
    page never reports the whole roster's size.
    """
    base = (
        select(Person, SchoolMembership.membership_type)
        .join(SchoolMembership, SchoolMembership.person_id == Person.id)
        .where(
            SchoolMembership.school_id == school_id,
            SchoolMembership.status == MembershipStatus.ACTIVE,
            SchoolMembership.record_status == RecordStatus.ACTIVE,
            Person.record_status == RecordStatus.ACTIVE,
        )
    )
    if member_type is not None:
        base = base.where(SchoolMembership.membership_type == member_type)
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


def revoke_open_role_assignments(
    db: Session, school_id: str, person_id: str, *, actor_person_id: str
) -> list[RoleAssignment]:
    """Close every open role assignment this person holds in this school.

    Returns the rows it changed, so the caller can audit each one. Flushes
    rather than commits: §7.1 requires this to land in the same transaction as
    the membership transition that caused it, and a commit here would make a
    half-done termination durable.

    `actor_person_id` is `str`, not `str | None`. §2.5's revocation triple is
    all-or-none, so an actor-less revocation carrying a reason is precisely the
    half-triple `ck_role_assignment_revoke_triple` refuses — and an optional
    parameter would let a future caller write one and discover it at commit
    time. `RequestContext.person_id` is non-optional, so nothing is lost by
    saying so here.
    """
    rows = list(
        db.execute(
            select(RoleAssignment).where(
                RoleAssignment.school_id == school_id,
                RoleAssignment.person_id == person_id,
                RoleAssignment.status.in_(OPEN_ROLE_ASSIGNMENT_STATUSES),
            )
        ).scalars()
    )
    now = clock.now()
    for row in rows:
        # §2.5's triple, and `ck_role_assignment_revoked_stamp` refuses a
        # REVOKED row without it. `MEMBERSHIP_ENDED` is the code §2.10 lists
        # for exactly this cause, which is why the cascade needs no note.
        row.status = RoleAssignmentStatus.REVOKED
        row.revoked_by_person_id = actor_person_id
        row.revoked_at = now
        row.revoke_reason_code = RoleRevokeReason.MEMBERSHIP_ENDED
    if rows:
        db.flush()
    return rows


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
) -> SchoolPersonProfile | None:
    """Another person in this school already holding this local code.

    Reads the M06 §2.4 profile rather than the membership: the code identifies a
    *person* to the school, so someone who is both a parent and a coach has one
    code, not one per membership type.
    """
    normalized = normalize_local_person_code(local_member_code)
    stmt = select(SchoolPersonProfile).where(
        SchoolPersonProfile.school_id == school_id,
        SchoolPersonProfile.normalized_local_person_code == normalized,
        SchoolPersonProfile.person_id != exclude_person_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def get_or_create_profile(db: Session, school_id: str, person_id: str) -> SchoolPersonProfile:
    """The school's view of this person, created on first need (§2.4)."""
    existing = db.execute(
        select(SchoolPersonProfile).where(
            SchoolPersonProfile.school_id == school_id,
            SchoolPersonProfile.person_id == person_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    profile = SchoolPersonProfile(school_id=school_id, person_id=person_id)
    db.add(profile)
    db.flush()
    return profile


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
