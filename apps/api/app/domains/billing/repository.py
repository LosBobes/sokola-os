from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.common.pagination import PageParams
from app.domains.billing.enums import ChargeStatus
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


def active_group_members_with_discount(
    db: Session, group_id: str
) -> list[tuple[Person, int]]:
    """Same roster as :func:`active_group_people`, paired with each member's
    per-membership discount — the pricing source for :func:`billing.service.
    _compute` when no explicit ``amount_minor`` override is supplied."""
    stmt = (
        select(Person, GroupMembership.discount_minor)
        .join(GroupMembership, GroupMembership.person_id == Person.id)
        .where(
            GroupMembership.group_id == group_id,
            GroupMembership.ended_at.is_(None),
            Person.record_status == RecordStatus.ACTIVE,
        )
        .order_by(Person.display_name)
    )
    return [(row[0], row[1]) for row in db.execute(stmt).all()]


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


# ---------------------------------------------------------------------------
# Debts / dugovanja — aggregated outstanding balance. A charge's own
# ``amount_due_minor - amount_paid_minor`` is never negative (payments are
# rejected past the outstanding balance), and CANCELLED charges never owe
# anything, so both queries below simply exclude CANCELLED and sum the rest.
# ---------------------------------------------------------------------------

_OUTSTANDING = Charge.amount_due_minor - Charge.amount_paid_minor


def person_debts(
    db: Session, organization_id: str, params: PageParams
) -> tuple[list[tuple[str, str, str, int, int]], int]:
    """Per-person outstanding balance, grouped by (person, currency) — worst
    debtor first. Rows: (person_id, display_name, currency, outstanding_minor,
    open_charge_count)."""
    base = (
        select(
            Person.id,
            Person.display_name,
            Charge.currency,
            func.sum(_OUTSTANDING),
            func.count(Charge.id),
        )
        .join(Charge, Charge.person_id == Person.id)
        .where(
            Charge.organization_id == organization_id,
            Charge.status != ChargeStatus.CANCELLED,
        )
        .group_by(Person.id, Person.display_name, Charge.currency)
        .having(func.sum(_OUTSTANDING) > 0)
    )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(
        base.order_by(func.sum(_OUTSTANDING).desc(), Person.display_name)
        .limit(params.limit)
        .offset(params.offset)
    ).all()
    return [(r[0], r[1], r[2], r[3], r[4]) for r in rows], total


def debt_summary(db: Session, organization_id: str) -> tuple[int, int]:
    """Org-wide (total_outstanding_minor, people_with_debt)."""
    stmt = select(func.sum(_OUTSTANDING), func.count(func.distinct(Charge.person_id))).where(
        Charge.organization_id == organization_id,
        Charge.status != ChargeStatus.CANCELLED,
        _OUTSTANDING > 0,
    )
    total_minor, people = db.execute(stmt).one()
    return int(total_minor or 0), int(people or 0)
