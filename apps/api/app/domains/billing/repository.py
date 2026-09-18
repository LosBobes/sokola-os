from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.common.pagination import PageParams
from app.domains.billing.enums import ChargeStatus
from app.domains.billing.models import Charge
from app.domains.groups.enums import GroupMemberRole
from app.domains.groups.models import Group, GroupMembership
from app.domains.identity.models import Person
from app.domains.people.enums import GuardianAccessStatus
from app.domains.people.models import GuardianSchoolAccess
from app.domains.school.enums import SchoolStatus
from app.domains.school.models import School


def get_school_group(db: Session, school_id: str, group_id: str) -> Group | None:
    stmt = select(Group).where(
        Group.id == group_id,
        Group.school_id == school_id,
        Group.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def active_group_people(db: Session, group_id: str) -> list[Person]:
    """Participants of the group, the only people a membership run may charge.
    Trainers and other staff attached to the group are excluded: they are paid
    by the school, not billed by it."""
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


def active_group_members_with_discount(
    db: Session, group_id: str
) -> list[tuple[Person, int]]:
    """Same roster as :func:`active_group_people`, paired with each member's
    per-membership discount, the pricing source for :func:`billing.service.
    _compute` when no explicit ``amount`` override is supplied."""
    stmt = (
        select(Person, GroupMembership.discount)
        .join(GroupMembership, GroupMembership.person_id == Person.id)
        .where(
            GroupMembership.group_id == group_id,
            GroupMembership.role == GroupMemberRole.MEMBER,
            GroupMembership.ended_at.is_(None),
            Person.record_status == RecordStatus.ACTIVE,
        )
        .order_by(Person.display_name)
    )
    return [(row[0], row[1]) for row in db.execute(stmt).all()]


def get_charge(db: Session, school_id: str, charge_id: str) -> Charge | None:
    stmt = select(Charge).where(
        Charge.id == charge_id, Charge.school_id == school_id
    )
    return db.execute(stmt).scalar_one_or_none()


def get_charge_for_update(db: Session, school_id: str, charge_id: str) -> Charge | None:
    stmt = (
        select(Charge)
        .where(Charge.id == charge_id, Charge.school_id == school_id)
        .with_for_update()
    )
    return db.execute(stmt).scalar_one_or_none()


def list_charges(
    db: Session, school_id: str, params: PageParams, person_id: str | None
) -> tuple[list[Charge], int]:
    base = select(Charge).where(Charge.school_id == school_id)
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
# Debts / dugovanja, aggregated outstanding balance. A charge's own
# ``amount_due - amount_paid`` is never negative (payments are
# rejected past the outstanding balance), and CANCELLED charges never owe
# anything, so both queries below simply exclude CANCELLED and sum the rest.
# ---------------------------------------------------------------------------

_OUTSTANDING = Charge.amount_due - Charge.amount_paid


def person_debts(
    db: Session, school_id: str, params: PageParams
) -> tuple[list[tuple[str, str, str, int, int]], int]:
    """Per-person outstanding balance, grouped by (person, currency), worst
    debtor first. Rows: (person_id, display_name, currency, outstanding,
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
            Charge.school_id == school_id,
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


def debt_summary(db: Session, school_id: str) -> tuple[int, int]:
    """Org-wide (total_outstanding, people_with_debt)."""
    stmt = select(func.sum(_OUTSTANDING), func.count(func.distinct(Charge.person_id))).where(
        Charge.school_id == school_id,
        Charge.status != ChargeStatus.CANCELLED,
        _OUTSTANDING > 0,
    )
    total, people = db.execute(stmt).one()
    return int(total or 0), int(people or 0)


def get_school(db: Session, school_id: str) -> School | None:
    """The paying-in party on a payment slip. Read directly from the shared
    model (cross-domain model access, never the school service)."""
    stmt = select(School).where(
        School.id == school_id,
        School.status != SchoolStatus.DEACTIVATED,
    )
    return db.execute(stmt).scalar_one_or_none()


def get_person(db: Session, person_id: str) -> Person | None:
    stmt = select(Person).where(
        Person.id == person_id, Person.record_status == RecordStatus.ACTIVE
    )
    return db.execute(stmt).scalar_one_or_none()


def get_charge_by_reference(
    db: Session, school_id: str, payment_reference: str
) -> Charge | None:
    """Reconciliation lookup: find the charge a bank statement's reference
    ("poziv na broj") points at, within this school only."""
    stmt = select(Charge).where(
        Charge.school_id == school_id,
        Charge.payment_reference == payment_reference,
    )
    return db.execute(stmt).scalar_one_or_none()


def is_guardian_of(
    db: Session, school_id: str, guardian_person_id: str, child_person_id: str
) -> bool:
    """Whether this guardian may act for this child inside this school."""
    stmt = select(GuardianSchoolAccess.id).where(
        GuardianSchoolAccess.school_id == school_id,
        GuardianSchoolAccess.guardian_person_id == guardian_person_id,
        GuardianSchoolAccess.child_person_id == child_person_id,
        GuardianSchoolAccess.status == GuardianAccessStatus.ACTIVE,
    )
    return db.execute(stmt).first() is not None
