from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.common.pagination import PageParams
from app.domains.billing.models import Charge
from app.domains.groups.models import Group, GroupMembership
from app.domains.identity.models import Person


def get_org_group(db: Session, organization_id: str, group_id: str) -> Group | None:
    stmt = select(Group).where(
        Group.id == group_id,
        Group.organization_id == organization_id,
        Group.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def active_group_people(db: Session, group_id: str) -> list[Person]:
    stmt = (
        select(Person)
        .join(GroupMembership, GroupMembership.person_id == Person.id)
        .where(
            GroupMembership.group_id == group_id,
            GroupMembership.ended_at.is_(None),
            Person.record_status == RecordStatus.ACTIVE,
        )
        .order_by(Person.display_name)
    )
    return list(db.execute(stmt).scalars().all())


def get_charge(db: Session, organization_id: str, charge_id: str) -> Charge | None:
    stmt = select(Charge).where(
        Charge.id == charge_id, Charge.organization_id == organization_id
    )
    return db.execute(stmt).scalar_one_or_none()


def get_charge_for_update(db: Session, organization_id: str, charge_id: str) -> Charge | None:
    stmt = (
        select(Charge)
        .where(Charge.id == charge_id, Charge.organization_id == organization_id)
        .with_for_update()
    )
    return db.execute(stmt).scalar_one_or_none()


def list_charges(
    db: Session, organization_id: str, params: PageParams, person_id: str | None
) -> tuple[list[Charge], int]:
    base = select(Charge).where(Charge.organization_id == organization_id)
    if person_id is not None:
        base = base.where(Charge.person_id == person_id)
    total = db.execute(
        select(func.count()).select_from(base.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(
            base.order_by(Charge.created_at.desc()).limit(params.limit).offset(params.offset)
        )
        .scalars()
        .all()
    )
    return list(rows), total
