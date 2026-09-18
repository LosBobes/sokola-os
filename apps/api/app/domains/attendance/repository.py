from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.common.enums import RecordStatus
from app.domains.attendance.models import AttendanceRecord
from app.domains.groups.enums import GroupMemberRole
from app.domains.groups.models import GroupMembership
from app.domains.identity.models import Person
from app.domains.scheduling.models import Session as TrainingSession


def get_session(
    db: DbSession, school_id: str, session_id: str, *, for_update: bool = False
) -> TrainingSession | None:
    stmt = select(TrainingSession).where(
        TrainingSession.id == session_id,
        TrainingSession.school_id == school_id,
        TrainingSession.record_status == RecordStatus.ACTIVE,
    )
    if for_update:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def list_roster(db: DbSession, group_id: str) -> list[Person]:
    """Active *participants* of the session's group, in display order.

    Attendance is a record of who trained, so the roster is participants only:
    a trainer or assistant attached to the same group is running the session,
    not attending it, and must never appear as a row to be marked present.
    """
    stmt = (
        select(Person)
        .join(GroupMembership, GroupMembership.person_id == Person.id)
        .where(
            GroupMembership.group_id == group_id,
            GroupMembership.role == GroupMemberRole.MEMBER,
            GroupMembership.ended_at.is_(None),
            Person.record_status == RecordStatus.ACTIVE,
        )
        .order_by(Person.display_name)
    )
    return list(db.execute(stmt).scalars().all())


def records_by_person(db: DbSession, session_id: str) -> dict[str, AttendanceRecord]:
    stmt = select(AttendanceRecord).where(AttendanceRecord.session_id == session_id)
    return {r.person_id: r for r in db.execute(stmt).scalars().all()}
