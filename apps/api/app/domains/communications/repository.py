from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.common.pagination import PageParams
from app.domains.communications.models import Notification
from app.domains.groups.models import Group, GroupMembership
from app.domains.organization.enums import MembershipStatus
from app.domains.organization.models import OrganizationMembership


def organization_recipient_ids(db: Session, organization_id: str) -> list[str]:
    stmt = (
        select(OrganizationMembership.person_id)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.status == MembershipStatus.ACTIVE,
            OrganizationMembership.record_status == RecordStatus.ACTIVE,
        )
        .order_by(OrganizationMembership.person_id)
    )
    return list(db.execute(stmt).scalars().all())


def group_exists(db: Session, organization_id: str, group_id: str) -> bool:
    stmt = select(Group.id).where(
        Group.id == group_id,
        Group.organization_id == organization_id,
        Group.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none() is not None


def group_recipient_ids(db: Session, group_id: str) -> list[str]:
    stmt = (
        select(GroupMembership.person_id)
        .where(GroupMembership.group_id == group_id, GroupMembership.ended_at.is_(None))
        .order_by(GroupMembership.person_id)
    )
    return list(db.execute(stmt).scalars().all())


def list_inbox(
    db: Session, organization_id: str, person_id: str, params: PageParams
) -> tuple[list[Notification], int]:
    """A person's own inbox, always scoped to both the caller's tenant and
    their own ``person_id``; nothing here is reachable cross-person."""
    base = select(Notification).where(
        Notification.organization_id == organization_id,
        Notification.person_id == person_id,
    )
    total = db.execute(
        select(func.count()).select_from(base.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(
            base.order_by(Notification.created_at.desc(), Notification.id.desc())
            .limit(params.limit)
            .offset(params.offset)
        )
        .scalars()
        .all()
    )
    return list(rows), total


def get_inbox_notification(
    db: Session, organization_id: str, person_id: str, notification_id: str
) -> Notification | None:
    stmt = select(Notification).where(
        Notification.id == notification_id,
        Notification.organization_id == organization_id,
        Notification.person_id == person_id,
    )
    return db.execute(stmt).scalar_one_or_none()
