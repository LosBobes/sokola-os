from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.common.enums import RecordStatus
from app.domains.groups.models import Group, GroupMembership
from app.domains.identity.models import Person
from app.domains.organization.models import OrganizationMembership
from app.domains.progress.models import ProgressNote


def get_org_person(db: DbSession, organization_id: str, person_id: str) -> Person | None:
    """A person is visible only through an active membership in this org.

    This mirrors ``people.repository.get_org_person`` exactly, duplicated
    rather than imported — the architecture gate allows domains to share
    ``models`` but never another domain's ``repository``.
    """
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


def get_group(db: DbSession, organization_id: str, group_id: str) -> Group | None:
    stmt = select(Group).where(
        Group.id == group_id,
        Group.organization_id == organization_id,
        Group.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def is_active_group_member(db: DbSession, group_id: str, person_id: str) -> bool:
    stmt = select(GroupMembership.id).where(
        GroupMembership.group_id == group_id,
        GroupMembership.person_id == person_id,
        GroupMembership.ended_at.is_(None),
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def list_for_person(
    db: DbSession, organization_id: str, person_id: str, group_id: str | None
) -> list[ProgressNote]:
    stmt = select(ProgressNote).where(
        ProgressNote.organization_id == organization_id,
        ProgressNote.person_id == person_id,
    )
    if group_id is not None:
        stmt = stmt.where(ProgressNote.group_id == group_id)
    stmt = stmt.order_by(ProgressNote.created_at.desc())
    return list(db.execute(stmt).scalars().all())
