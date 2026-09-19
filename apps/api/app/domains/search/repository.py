"""Read-only fan-out queries backing unified search (PRD 15).

No local models: this domain only ever reads rows other domains already own.
Cross-domain imports are limited to those domains' MODELS (always allowed by
the architecture gate), never their service/repository/router. Every query
below filters on ``school_id`` itself (never relies on a join alone to
establish tenant scope), because that is the invariant this whole endpoint
exists to prove.

v1 search is deliberately simple, per the PRD: ``ILIKE '%term%'`` and no search
index. Ranking is a single case expression, exact-prefix matches (rank 0)
before other substring matches (rank 1), then capped to
:data:`RESULTS_PER_TYPE` per entity type so the combined payload stays small
and fast without full pagination (noted as a v1 limitation, not built here).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import ColumnElement, case, func, or_, select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.domains.billing.models import Charge
from app.domains.events.models import Event
from app.domains.groups.models import Group
from app.domains.identity.models import Person
from app.domains.people.profile_models import SchoolPersonProfile
from app.domains.scheduling.models import Session as ScheduledSession
from app.domains.school.enums import MembershipStatus
from app.domains.school.models import SchoolMembership

RESULTS_PER_TYPE = 5


def _prefix_rank(*columns: Any, term: str) -> ColumnElement[int]:
    """0 if any of ``columns`` starts with ``term`` (case-insensitive), else 1."""
    starts_with = or_(*(func.lower(col).like(f"{term.lower()}%") for col in columns))
    return case((starts_with, 0), else_=1)


def search_people(
    db: Session, school_id: str, term: str
) -> list[tuple[Person, str | None]]:
    """People visible to this org via an active membership (mirrors
    ``people.repository.list_school_people``) whose display name matches.

    Returns the school-local code alongside, read from the M06 §2.4 profile
    rather than the membership: the code identifies the person to the school,
    and an outer join keeps people who have no profile row visible rather than
    silently dropping them from search.
    """
    like = f"%{term}%"
    stmt = (
        select(Person, SchoolPersonProfile.local_person_code)
        .join(SchoolMembership, SchoolMembership.person_id == Person.id)
        .outerjoin(
            SchoolPersonProfile,
            (SchoolPersonProfile.person_id == Person.id)
            & (SchoolPersonProfile.school_id == school_id),
        )
        .where(
            SchoolMembership.school_id == school_id,
            SchoolMembership.status == MembershipStatus.ACTIVE,
            SchoolMembership.record_status == RecordStatus.ACTIVE,
            Person.record_status == RecordStatus.ACTIVE,
            Person.display_name.ilike(like),
        )
        .order_by(_prefix_rank(Person.display_name, term=term), Person.display_name)
        .limit(RESULTS_PER_TYPE)
    )
    return [tuple(row) for row in db.execute(stmt).all()]


def search_groups(db: Session, school_id: str, term: str) -> list[Group]:
    like = f"%{term}%"
    stmt = (
        select(Group)
        .where(
            Group.school_id == school_id,
            Group.record_status == RecordStatus.ACTIVE,
            Group.name.ilike(like),
        )
        .order_by(_prefix_rank(Group.name, term=term), Group.name)
        .limit(RESULTS_PER_TYPE)
    )
    return list(db.execute(stmt).scalars().all())


def search_sessions(
    db: Session, school_id: str, term: str
) -> list[tuple[ScheduledSession, Group]]:
    """Sessions matched by their own title or their group's name. Both the
    session and its group are re-checked against ``school_id``, a
    session's ``group_id`` should always already belong to the same org, but
    this endpoint re-verifies rather than trusting that invariant silently."""
    like = f"%{term}%"
    stmt = (
        select(ScheduledSession, Group)
        .join(Group, Group.id == ScheduledSession.group_id)
        .where(
            ScheduledSession.school_id == school_id,
            Group.school_id == school_id,
            ScheduledSession.record_status == RecordStatus.ACTIVE,
            or_(ScheduledSession.title.ilike(like), Group.name.ilike(like)),
        )
        .order_by(
            _prefix_rank(ScheduledSession.title, Group.name, term=term),
            ScheduledSession.starts_at.desc(),
        )
        .limit(RESULTS_PER_TYPE)
    )
    return [tuple(row) for row in db.execute(stmt).all()]


def search_events(db: Session, school_id: str, term: str) -> list[Event]:
    like = f"%{term}%"
    stmt = (
        select(Event)
        .where(
            Event.school_id == school_id,
            Event.record_status == RecordStatus.ACTIVE,
            Event.title.ilike(like),
        )
        .order_by(_prefix_rank(Event.title, term=term), Event.starts_at.desc())
        .limit(RESULTS_PER_TYPE)
    )
    return list(db.execute(stmt).scalars().all())


def search_charges(
    db: Session, school_id: str, term: str
) -> list[tuple[Charge, Person]]:
    """Charges matched by description or the owing person's name. ``Charge``
    carries no ``record_status`` column (mirrors ``billing.repository.
    list_charges``, which does not filter on it either)."""
    like = f"%{term}%"
    stmt = (
        select(Charge, Person)
        .join(Person, Person.id == Charge.person_id)
        .where(
            Charge.school_id == school_id,
            or_(Charge.description.ilike(like), Person.display_name.ilike(like)),
        )
        .order_by(
            _prefix_rank(Charge.description, Person.display_name, term=term),
            Charge.created_at.desc(),
        )
        .limit(RESULTS_PER_TYPE)
    )
    return [tuple(row) for row in db.execute(stmt).all()]
