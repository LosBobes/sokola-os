"""Seed helpers for tests. Everything is committed so HTTP requests (which use a
separate session) observe it."""

from __future__ import annotations

from dataclasses import dataclass

from app.domains.identity.enums import RoleCode
from app.domains.identity.models import Person, RoleAssignment
from app.domains.organization.enums import OrganizationType
from app.domains.organization.models import Organization, OrganizationMembership
from app.security.auth import DEV_PERSON_HEADER
from app.security.deps import CONTEXT_HEADER
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


def add_membership(db: Session, *, person: Person, organization: Organization) -> None:
    db.add(OrganizationMembership(organization_id=organization.id, person_id=person.id))
    db.commit()


@dataclass
class Actor:
    person: Person
    organization: Organization
    assignment: RoleAssignment

    @property
    def headers(self) -> dict[str, str]:
        return {DEV_PERSON_HEADER: self.person.id, CONTEXT_HEADER: self.assignment.id}


def bootstrap_actor(
    db: Session,
    *,
    org_name: str = "Klub Soko",
    role: RoleCode = RoleCode.MANAGER,
    given: str = "Šef",
) -> Actor:
    """A person with a role (and membership) in a fresh organization, plus ready
    auth headers for HTTP tests."""
    person = make_person(db, given=given, family="Uprava")
    org = make_organization(db, name=org_name)
    add_membership(db, person=person, organization=org)
    assignment = assign_role(db, person=person, organization=org, role=role)
    return Actor(person=person, organization=org, assignment=assignment)
