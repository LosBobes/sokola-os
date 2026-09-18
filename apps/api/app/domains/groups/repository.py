from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.common.pagination import PageParams
from app.domains.groups.enums import GroupMemberRole, GroupMembershipStatus
from app.domains.groups.models import Group, GroupMembership
from app.domains.identity.models import Person
from app.domains.school.models import SchoolMembership

# Structure is a different domain; only its MODELS are imported (allowed by the
# architecture gate). Its service/repository are never called from here.
from app.domains.structure.models import Location, Program


def get_school_group(db: Session, school_id: str, group_id: str) -> Group | None:
    stmt = select(Group).where(
        Group.id == group_id,
        Group.school_id == school_id,
        Group.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_school_groups(
    db: Session, school_id: str, params: PageParams
) -> tuple[list[Group], int]:
    base = select(Group).where(
        Group.school_id == school_id,
        Group.record_status == RecordStatus.ACTIVE,
    )
    total = db.execute(
        select(func.count()).select_from(base.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(base.order_by(Group.name).limit(params.limit).offset(params.offset))
        .scalars()
        .all()
    )
    return list(rows), total


def get_member_person(db: Session, school_id: str, person_id: str) -> Person | None:
    """A person visible to this school via an active membership. Groups
    reads the shared Person/SchoolMembership records directly rather than
    calling the people domain's service."""
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


def count_active_members(db: Session, group_id: str) -> int:
    """Participants currently holding a place in the group. Staff attached to the
    same group (trainer/assistant rows) are not participants and never count
    against its capacity."""
    return db.execute(
        select(func.count())
        .select_from(GroupMembership)
        .where(
            GroupMembership.group_id == group_id,
            GroupMembership.role == GroupMemberRole.MEMBER,
            GroupMembership.status != GroupMembershipStatus.ENDED,
        )
    ).scalar_one()


def get_active_membership(
    db: Session, group_id: str, person_id: str
) -> GroupMembership | None:
    stmt = select(GroupMembership).where(
        GroupMembership.group_id == group_id,
        GroupMembership.person_id == person_id,
        GroupMembership.status != GroupMembershipStatus.ENDED,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_members_with_people(
    db: Session, group_id: str
) -> list[tuple[GroupMembership, Person]]:
    stmt = (
        select(GroupMembership, Person)
        .join(Person, Person.id == GroupMembership.person_id)
        .where(
            GroupMembership.group_id == group_id,
            GroupMembership.status != GroupMembershipStatus.ENDED,
        )
        .order_by(Person.display_name)
    )
    return [tuple(row) for row in db.execute(stmt).all()]


def get_school_membership(
    db: Session, school_id: str, group_id: str, membership_id: str
) -> tuple[GroupMembership, Person] | None:
    """Loaded without a status filter, lifecycle transitions must be able to
    find an already-ended membership too, in order to raise a clean conflict
    rather than a not-found."""
    stmt = (
        select(GroupMembership, Person)
        .join(Person, Person.id == GroupMembership.person_id)
        .where(
            GroupMembership.id == membership_id,
            GroupMembership.group_id == group_id,
            GroupMembership.school_id == school_id,
        )
    )
    row = db.execute(stmt).first()
    return (row[0], row[1]) if row is not None else None


# ---------------------------------------------------------------------------
# Structure links (program/location), models only, per the architecture gate.
# ---------------------------------------------------------------------------


def get_school_program(db: Session, school_id: str, program_id: str) -> Program | None:
    stmt = select(Program).where(
        Program.id == program_id,
        Program.school_id == school_id,
        Program.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def get_school_location(db: Session, school_id: str, location_id: str) -> Location | None:
    stmt = select(Location).where(
        Location.id == location_id,
        Location.school_id == school_id,
        Location.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()
