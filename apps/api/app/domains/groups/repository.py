from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.common.pagination import PageParams
from app.domains.groups.models import Group, GroupMembership
from app.domains.identity.models import Person
from app.domains.organization.models import OrganizationMembership


def get_org_group(db: Session, organization_id: str, group_id: str) -> Group | None:
    stmt = select(Group).where(
        Group.id == group_id,
        Group.organization_id == organization_id,
        Group.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_org_groups(
    db: Session, organization_id: str, params: PageParams
) -> tuple[list[Group], int]:
    base = select(Group).where(
        Group.organization_id == organization_id,
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


def get_member_person(db: Session, organization_id: str, person_id: str) -> Person | None:
    """A person visible to this organization via an active membership. Groups
    reads the shared Person/OrganizationMembership records directly rather than
    calling the people domain's service."""
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


def count_active_members(db: Session, group_id: str) -> int:
    return db.execute(
        select(func.count())
        .select_from(GroupMembership)
        .where(GroupMembership.group_id == group_id, GroupMembership.ended_at.is_(None))
    ).scalar_one()


def get_active_membership(
    db: Session, group_id: str, person_id: str
) -> GroupMembership | None:
    stmt = select(GroupMembership).where(
        GroupMembership.group_id == group_id,
        GroupMembership.person_id == person_id,
        GroupMembership.ended_at.is_(None),
    )
    return db.execute(stmt).scalar_one_or_none()


def list_members_with_people(
    db: Session, group_id: str
) -> list[tuple[GroupMembership, Person]]:
    stmt = (
        select(GroupMembership, Person)
        .join(Person, Person.id == GroupMembership.person_id)
        .where(GroupMembership.group_id == group_id, GroupMembership.ended_at.is_(None))
        .order_by(Person.display_name)
    )
    return [tuple(row) for row in db.execute(stmt).all()]
