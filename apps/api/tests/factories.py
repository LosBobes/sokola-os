"""Seed helpers for tests. Everything is committed so HTTP requests (which use a
separate session) observe it."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from app.domains.identity.enums import AuthAccountStatus, AuthIdentifierType, RoleCode
from app.domains.identity.models import AuthAccount, AuthIdentifier, Person, RoleAssignment
from app.domains.organization.enums import MembershipStatus, OrganizationType
from app.domains.organization.models import Organization, OrganizationMembership
from app.domains.people.enums import GuardianAccessStatus, GuardianRelationshipType
from app.domains.people.models import GuardianOrganizationAccess, GuardianRelationship
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
    granted_areas: list[str] | None = None,
) -> RoleAssignment:
    assignment = RoleAssignment(
        person_id=person.id,
        organization_id=organization.id,
        role_code=role,
        granted_areas=granted_areas,
    )
    db.add(assignment)
    db.commit()
    return assignment


def add_membership(
    db: Session,
    *,
    person: Person,
    organization: Organization,
    status: MembershipStatus = MembershipStatus.ACTIVE,
    created_at: dt.datetime | None = None,
) -> OrganizationMembership:
    membership = OrganizationMembership(
        organization_id=organization.id, person_id=person.id, status=status
    )
    if created_at is not None:
        membership.created_at = created_at
    db.add(membership)
    db.commit()
    return membership


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


def add_actor(
    db: Session,
    *,
    organization: Organization,
    role: RoleCode,
    given: str = "Osoba",
    granted_areas: list[str] | None = None,
) -> Actor:
    """Another actor in an EXISTING organization (same tenant as another actor)."""
    person = make_person(db, given=given, family="X")
    add_membership(db, person=person, organization=organization)
    assignment = assign_role(
        db, person=person, organization=organization, role=role, granted_areas=granted_areas
    )
    return Actor(person=person, organization=organization, assignment=assignment)


def link_login_email(db: Session, *, person: Person, email: str) -> None:
    """Simulate the email a person has verified sign-in with (as Google OIDC's
    ``jit_provision`` would record it) — the surface invite acceptance checks
    for "wrong account" rejection (§23), independent of the auth adapter used
    to reach the request (dev header in tests, session cookie in prod)."""
    account = AuthAccount(person_id=person.id, provider="google", status=AuthAccountStatus.ACTIVE)
    db.add(account)
    db.flush()
    db.add(
        AuthIdentifier(auth_account_id=account.id, type=AuthIdentifierType.EMAIL, value=email)
    )
    db.commit()


def make_child_with_guardian(
    db: Session, *, organization: Organization, guardian: Person, given: str = "Dete"
) -> Person:
    """A child who is an org member and to whom ``guardian`` has active access."""
    child = make_person(db, given=given, family="D")
    add_membership(db, person=child, organization=organization)
    db.add(
        GuardianRelationship(
            guardian_person_id=guardian.id,
            child_person_id=child.id,
            relationship_type=GuardianRelationshipType.PARENT,
        )
    )
    db.add(
        GuardianOrganizationAccess(
            organization_id=organization.id,
            guardian_person_id=guardian.id,
            child_person_id=child.id,
            status=GuardianAccessStatus.ACTIVE,
        )
    )
    db.commit()
    return child
