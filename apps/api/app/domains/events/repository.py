from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.domains.events.enums import EventStatus, RegistrationStatus
from app.domains.events.models import Event, EventRegistration
from app.domains.identity.models import Person
from app.domains.organization.models import OrganizationMembership
from app.domains.people.enums import GuardianAccessStatus
from app.domains.people.models import GuardianOrganizationAccess
from app.domains.structure.models import Location
from app.platform import clock


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


def list_in_range(
    db: Session, organization_id: str, start: dt.datetime, end: dt.datetime
) -> list[Event]:
    """Every non-archived event starting in ``[start, end)``, whatever its status.

    This is the staff calendar feed, so drafts and cancelled events are included
    on purpose , a planner needs to see the camp they have not published yet,
    and the one they called off. The parent-facing :func:`list_published` stays
    published-only.
    """
    stmt = (
        select(Event)
        .where(
            Event.organization_id == organization_id,
            Event.record_status == RecordStatus.ACTIVE,
            Event.starts_at >= start,
            Event.starts_at < end,
        )
        .order_by(Event.starts_at)
    )
    return list(db.execute(stmt).scalars().all())


def is_org_location(db: Session, organization_id: str, location_id: str) -> bool:
    stmt = select(Location.id).where(
        Location.id == location_id,
        Location.organization_id == organization_id,
        Location.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).first() is not None


def is_org_person(db: Session, organization_id: str, person_id: str) -> bool:
    stmt = (
        select(OrganizationMembership.id)
        .join(Person, Person.id == OrganizationMembership.person_id)
        .where(
            OrganizationMembership.person_id == person_id,
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.record_status == RecordStatus.ACTIVE,
            Person.record_status == RecordStatus.ACTIVE,
        )
    )
    return db.execute(stmt).first() is not None


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


def list_active_registrations(db: Session, event_id: str) -> list[EventRegistration]:
    """Every REGISTERED registration for an event, used to cascade-cancel them
    when the whole event is cancelled."""
    stmt = select(EventRegistration).where(
        EventRegistration.event_id == event_id,
        EventRegistration.status == RegistrationStatus.REGISTERED,
    )
    return list(db.execute(stmt).scalars().all())


def get_registration(
    db: Session, organization_id: str, event_id: str, registration_id: str
) -> EventRegistration | None:
    stmt = select(EventRegistration).where(
        EventRegistration.id == registration_id,
        EventRegistration.event_id == event_id,
        EventRegistration.organization_id == organization_id,
    )
    return db.execute(stmt).scalar_one_or_none()


def now() -> dt.datetime:
    return clock.now()
