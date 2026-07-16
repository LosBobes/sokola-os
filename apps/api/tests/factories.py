"""Seed helpers for tests. Everything is committed so HTTP requests (which use a
separate session) observe it."""

from __future__ import annotations

from app.domains.identity.enums import RoleCode
from app.domains.identity.models import Person, RoleAssignment
from app.domains.organization.enums import OrganizationType
from app.domains.organization.models import Organization
from sqlalchemy.orm import Session


def make_person(db: Session, *, given: str = "Ana", family: str = "Marković") -> Person:
    person = Person(given_name=given, family_name=family, display_name=f"{given} {family}")
    db.add(person)
    db.commit()
    return person


def make_organization(db: Session, *, name: str = "Klub Soko") -> Organization:
    org = Organization(name=name, type=OrganizationType.SPORTS_CLUB)
    db.add(org)
    db.commit()
    return org


def assign_role(
    db: Session,
    *,
    person: Person,
    organization: Organization,
    role: RoleCode = RoleCode.MANAGER,
) -> RoleAssignment:
    assignment = RoleAssignment(
        person_id=person.id,
        organization_id=organization.id,
        role_code=role,
    )
    db.add(assignment)
    db.commit()
    return assignment
