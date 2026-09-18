"""Read-only aggregate queries backing the reporting domain.

This domain owns no tables of its own, everything here is a live aggregate
over other domains' rows. Per the architecture gate, only *models* (never
another domain's ``service``/``repository``/``router``) may be imported across
a domain boundary, so every query below is written against the source domains'
SQLAlchemy models directly. Every query is filtered by ``organization_id`` (or,
for join tables, transitively via a tenant-scoped join), reports are
read-only, but tenant isolation is never relaxed.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.domains.attendance.enums import AttendanceStatus
from app.domains.attendance.models import AttendanceRecord
from app.domains.billing.enums import ChargeStatus
from app.domains.billing.models import Charge
from app.domains.groups.enums import GroupMembershipStatus
from app.domains.groups.models import Group, GroupMembership
from app.domains.organization.enums import MembershipStatus, OrgMemberType
from app.domains.organization.models import OrganizationMembership
from app.domains.payments.enums import PaymentRecordStatus
from app.domains.payments.models import PaymentRecord
from app.domains.scheduling.models import Session as ScheduleSession

_OPEN_CHARGE_STATUSES = (ChargeStatus.OPEN, ChargeStatus.PARTIALLY_PAID)


def get_org_group(db: Session, organization_id: str, group_id: str) -> Group | None:
    stmt = select(Group).where(
        Group.id == group_id,
        Group.organization_id == organization_id,
        Group.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


# --- Membership --------------------------------------------------------------


def active_member_count(db: Session, organization_id: str) -> int:
    """The school's headline member figure: active *participants* only.

    Owners, trainers, guardians and plain contacts all hold an organization
    membership too, so counting memberships flatters the number by everyone who
    merely works at or is related to the school. Filtering on
    :class:`OrgMemberType.ATTENDEE` counts polaznici and nobody else; archived
    and ended people are already excluded by the status filters.
    """
    stmt = select(func.count()).select_from(OrganizationMembership).where(
        OrganizationMembership.organization_id == organization_id,
        OrganizationMembership.member_type == OrgMemberType.ATTENDEE,
        OrganizationMembership.status == MembershipStatus.ACTIVE,
        OrganizationMembership.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one()


def active_membership_count_as_of(db: Session, organization_id: str, as_of: dt.datetime) -> int:
    """Currently-active *participant* memberships that had already joined by
    ``as_of``. Same ATTENDEE-only rule as :func:`active_member_count`, so the
    trend curve and the headline figure can never disagree."""
    stmt = select(func.count()).select_from(OrganizationMembership).where(
        OrganizationMembership.organization_id == organization_id,
        OrganizationMembership.member_type == OrgMemberType.ATTENDEE,
        OrganizationMembership.status == MembershipStatus.ACTIVE,
        OrganizationMembership.record_status == RecordStatus.ACTIVE,
        OrganizationMembership.created_at < as_of,
    )
    return db.execute(stmt).scalar_one()


def active_group_membership_count_as_of(
    db: Session, organization_id: str, group_id: str, as_of: dt.datetime
) -> int:
    stmt = select(func.count()).select_from(GroupMembership).where(
        GroupMembership.organization_id == organization_id,
        GroupMembership.group_id == group_id,
        GroupMembership.status == GroupMembershipStatus.ACTIVE,
        GroupMembership.created_at < as_of,
    )
    return db.execute(stmt).scalar_one()


def active_membership_by_group(
    db: Session, organization_id: str
) -> list[tuple[str, str, int]]:
    stmt = (
        select(Group.id, Group.name, func.count(GroupMembership.id))
        .select_from(GroupMembership)
        .join(Group, Group.id == GroupMembership.group_id)
        .where(
            GroupMembership.organization_id == organization_id,
            GroupMembership.status == GroupMembershipStatus.ACTIVE,
        )
        .group_by(Group.id, Group.name)
        .order_by(Group.name)
    )
    return [(g_id, g_name, count) for g_id, g_name, count in db.execute(stmt).all()]


# --- Billing / payments --------------------------------------------------------


def billed_total(
    db: Session, organization_id: str, start: dt.datetime, end: dt.datetime
) -> Decimal:
    stmt = select(func.coalesce(func.sum(Charge.amount_due), 0)).where(
        Charge.organization_id == organization_id,
        Charge.status != ChargeStatus.CANCELLED,
        Charge.created_at >= start,
        Charge.created_at < end,
    )
    return db.execute(stmt).scalar_one()


def collected_total(
    db: Session, organization_id: str, start: dt.datetime, end: dt.datetime
) -> Decimal:
    stmt = select(func.coalesce(func.sum(PaymentRecord.amount), 0)).where(
        PaymentRecord.organization_id == organization_id,
        PaymentRecord.status == PaymentRecordStatus.RECORDED,
        PaymentRecord.created_at >= start,
        PaymentRecord.created_at < end,
    )
    return db.execute(stmt).scalar_one()


def outstanding_debt_total(db: Session, organization_id: str) -> Decimal:
    stmt = select(
        func.coalesce(func.sum(Charge.amount_due - Charge.amount_paid), 0)
    ).where(
        Charge.organization_id == organization_id,
        Charge.status.in_(_OPEN_CHARGE_STATUSES),
    )
    return db.execute(stmt).scalar_one()


def outstanding_by_status(
    db: Session, organization_id: str
) -> list[tuple[ChargeStatus, int, int]]:
    stmt = (
        select(
            Charge.status,
            func.count(),
            func.coalesce(func.sum(Charge.amount_due - Charge.amount_paid), 0),
        )
        .where(
            Charge.organization_id == organization_id,
            Charge.status.in_(_OPEN_CHARGE_STATUSES),
        )
        .group_by(Charge.status)
    )
    return [tuple(row) for row in db.execute(stmt).all()]


# --- Attendance ----------------------------------------------------------------


def attendance_counts(
    db: Session,
    organization_id: str,
    start: dt.datetime,
    end: dt.datetime,
    group_id: str | None = None,
) -> dict[AttendanceStatus, int]:
    stmt = (
        select(AttendanceRecord.status, func.count())
        .select_from(AttendanceRecord)
        .join(ScheduleSession, ScheduleSession.id == AttendanceRecord.session_id)
        .where(
            AttendanceRecord.organization_id == organization_id,
            ScheduleSession.organization_id == organization_id,
            ScheduleSession.starts_at >= start,
            ScheduleSession.starts_at < end,
        )
        .group_by(AttendanceRecord.status)
    )
    if group_id is not None:
        stmt = stmt.where(ScheduleSession.group_id == group_id)
    return dict(tuple(row) for row in db.execute(stmt).all())


def attendance_by_group(
    db: Session,
    organization_id: str,
    start: dt.datetime,
    end: dt.datetime,
    group_id: str | None = None,
) -> list[tuple[str, str, AttendanceStatus, int]]:
    stmt = (
        select(Group.id, Group.name, AttendanceRecord.status, func.count())
        .select_from(AttendanceRecord)
        .join(ScheduleSession, ScheduleSession.id == AttendanceRecord.session_id)
        .join(Group, Group.id == ScheduleSession.group_id)
        .where(
            AttendanceRecord.organization_id == organization_id,
            ScheduleSession.organization_id == organization_id,
            Group.organization_id == organization_id,
            ScheduleSession.starts_at >= start,
            ScheduleSession.starts_at < end,
        )
        .group_by(Group.id, Group.name, AttendanceRecord.status)
    )
    if group_id is not None:
        stmt = stmt.where(Group.id == group_id)
    return [tuple(row) for row in db.execute(stmt).all()]
