from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.domains.events.enums import EventStatus, RegistrationStatus
from app.domains.events.models import Event, EventRegistration
from app.domains.identity.models import Person
from app.domains.people.enums import GuardianAccessStatus
from app.domains.people.models import GuardianOrganizationAccess


def get_event(
    db: Session, organization_id: str, event_id: str, *, for_update: bool = False
) -> Event | None:
    stmt = select(Event).where(
        Event.id == event_id,
        Event.organization_id == organization_id,
        Event.record_status == RecordStatus.ACTIVE,
    )
    if for_update:
        stmt = stmt.with_for_update()
    return db.execute(stmt).scalar_one_or_none()


def list_published(db: Session, organization_id: str) -> list[Event]:
    stmt = (
        select(Event)
        .where(
            Event.organization_id == organization_id,
            Event.status == EventStatus.PUBLISHED,
            Event.record_status == RecordStatus.ACTIVE,
        )
        .order_by(Event.starts_at)
    )
    return list(db.execute(stmt).scalars().all())


def guardian_children(
    db: Session, organization_id: str, guardian_person_id: str
) -> dict[str, Person]:
    """The children this guardian may act for in THIS organization, keyed by id."""
    stmt = (
        select(Person)
        .join(
            GuardianOrganizationAccess,
            GuardianOrganizationAccess.child_person_id == Person.id,
        )
        .where(
            GuardianOrganizationAccess.organization_id == organization_id,
            GuardianOrganizationAccess.guardian_person_id == guardian_person_id,
            GuardianOrganizationAccess.status == GuardianAccessStatus.ACTIVE,
            Person.record_status == RecordStatus.ACTIVE,
        )
    )
    return {p.id: p for p in db.execute(stmt).scalars().all()}


def registrations_for_children(
    db: Session, event_id: str, child_ids: list[str]
) -> dict[str, EventRegistration]:
    if not child_ids:
        return {}
    stmt = select(EventRegistration).where(
        EventRegistration.event_id == event_id,
        EventRegistration.child_person_id.in_(child_ids),
    )
    return {r.child_person_id: r for r in db.execute(stmt).scalars().all()}


def count_active_registrations(db: Session, event_id: str) -> int:
    from sqlalchemy import func

    return db.execute(
        select(func.count())
        .select_from(EventRegistration)
        .where(
            EventRegistration.event_id == event_id,
            EventRegistration.status == RegistrationStatus.REGISTERED,
        )
    ).scalar_one()


def get_registration(
    db: Session, organization_id: str, event_id: str, registration_id: str
) -> EventRegistration | None:
    stmt = select(EventRegistration).where(
        EventRegistration.id == registration_id,
        EventRegistration.event_id == event_id,
        EventRegistration.organization_id == organization_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)
