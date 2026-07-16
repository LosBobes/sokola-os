from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.common.pagination import PageParams
from app.domains.identity.models import Person
from app.domains.organization.enums import MembershipStatus
from app.domains.organization.models import OrganizationMembership


def find_duplicate_candidates(
    db: Session, organization_id: str, given_name: str, family_name: str
) -> list[Person]:
    """People already in THIS organization whose name matches (case-insensitive).
    Global identities in other orgs are intentionally invisible here."""
    stmt = (
        select(Person)
        .join(OrganizationMembership, OrganizationMembership.person_id == Person.id)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.record_status == RecordStatus.ACTIVE,
            func.lower(Person.given_name) == given_name.strip().lower(),
            func.lower(Person.family_name) == family_name.strip().lower(),
            Person.record_status == RecordStatus.ACTIVE,
        )
        .order_by(Person.display_name)
    )
    return list(db.execute(stmt).scalars().all())


def list_org_people(
    db: Session, organization_id: str, params: PageParams
) -> tuple[list[Person], int]:
    base = (
        select(Person)
        .join(OrganizationMembership, OrganizationMembership.person_id == Person.id)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.status == MembershipStatus.ACTIVE,
            OrganizationMembership.record_status == RecordStatus.ACTIVE,
            Person.record_status == RecordStatus.ACTIVE,
        )
    )
    total = db.execute(
        select(func.count()).select_from(base.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(
            base.order_by(Person.display_name).limit(params.limit).offset(params.offset)
        )
        .scalars()
        .all()
    )
    return list(rows), total


def get_org_person(db: Session, organization_id: str, person_id: str) -> Person | None:
    """A person is visible only through an active membership in the active org."""
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
