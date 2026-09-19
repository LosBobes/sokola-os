"""Seed helpers for tests. Everything is committed so HTTP requests (which use a
separate session) observe it."""

from __future__ import annotations

import datetime as dt
import secrets
from dataclasses import dataclass

from app.common.ids import new_id
from app.common.slug import slugify
from app.domains.identity.enums import AuthAccountStatus, AuthIdentifierType, RoleCode
from app.domains.identity.models import AuthAccount, AuthIdentifier, Person, RoleAssignment
from app.domains.organization.enums import OrganizationSchoolChangeReason
from app.domains.organization.models import Organization
from app.domains.people.enums import GuardianAccessStatus, GuardianRelationshipType
from app.domains.people.models import GuardianRelationship, GuardianSchoolAccess
from app.domains.people.profile_models import SchoolPersonProfile
from app.domains.school import anchor
from app.domains.school.enums import (
    LocatorKind,
    MembershipStatus,
    SchoolStatus,
    SchoolType,
)
from app.domains.school.models import School, SchoolMembership
from app.platform import clock
from app.security.auth import DEV_PERSON_HEADER
from app.security.deps import CONTEXT_HEADER
from sqlalchemy import select
from sqlalchemy.orm import Session


def make_person(db: Session, *, given: str = "Ana", family: str = "Marković") -> Person:
    person = Person(given_name=given, family_name=family, display_name=f"{given} {family}")
    db.add(person)
    db.commit()
    return person


def make_school(
    db: Session, *, name: str = "Klub Soko", status: SchoolStatus = SchoolStatus.ACTIVE
) -> School:
    """A school with its full M04 anchor, because a school without one cannot
    exist in production: §3.1.3 and §3.7.1 require a current organization link
    and one active locator of each kind from the moment it is created. A factory
    that skipped them would let tests pass against rows the database would reject.
    """
    org = School(name=name, type=SchoolType.SPORTS_CLUB, status=status)
    db.add(org)
    db.flush()

    holder = Organization(
        organization_ref=new_id("oref"),
        legal_name=name,
        country_code="RS",
        created_by_actor_ref="test",
        updated_by_actor_ref="test",
    )
    db.add(holder)
    db.flush()
    anchor.open_organization_link(
        db,
        school_id=org.id,
        organization=holder,
        reason=OrganizationSchoolChangeReason.INITIAL_PROVISIONING,
        case_reference="TEST",
        actor_ref="test",
    )
    anchor.issue_locator(
        db,
        school_id=org.id,
        kind=LocatorKind.SLUG,
        value=f"{slugify(name)}-{secrets.token_hex(3)}",
        actor_ref="test",
    )
    anchor.issue_school_code(db, school_id=org.id, actor_ref="test")
    anchor.record_creation(db, school=org, actor_ref="test", correlation_id=new_id("corr"))
    db.commit()
    return org


def assign_role(
    db: Session,
    *,
    person: Person,
    school: School,
    role: RoleCode = RoleCode.MANAGER,
    granted_areas: list[str] | None = None,
) -> RoleAssignment:
    assignment = RoleAssignment(
        person_id=person.id,
        school_id=school.id,
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
    school: School,
    status: MembershipStatus = MembershipStatus.ACTIVE,
    created_at: dt.datetime | None = None,
) -> SchoolMembership:
    membership = SchoolMembership(
        school_id=school.id, person_id=person.id, status=status
    )
    # A suspended or terminated membership carries why, and a terminated one
    # carries when — the §2.3 CHECKs say so, and a fixture that sidesteps them
    # would be testing against rows production cannot hold.
    if status is MembershipStatus.SUSPENDED:
        membership.suspension_reason_code = "TEST_SUSPENDED"
    elif status is MembershipStatus.TERMINATED:
        membership.termination_reason_code = "TEST_TERMINATED"
        membership.end_date = membership.start_date or clock.now().date()
    if created_at is not None:
        membership.created_at = created_at
    db.add(membership)
    ensure_person_profile(db, school=school, person=person)
    db.commit()
    return membership


def ensure_person_profile(
    db: Session, *, school: School, person: Person
) -> SchoolPersonProfile:
    """The M06 §2.4 row that makes a person visible inside one school.

    One per (school, person) however many membership types they hold, so this
    is idempotent: a person who is both a parent and a coach is still someone
    the school knows once.
    """
    existing = db.execute(
        select(SchoolPersonProfile).where(
            SchoolPersonProfile.school_id == school.id,
            SchoolPersonProfile.person_id == person.id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    profile = SchoolPersonProfile(school_id=school.id, person_id=person.id)
    db.add(profile)
    db.flush()
    return profile


@dataclass
class Actor:
    person: Person
    school: School
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
    """A person with a role (and membership) in a fresh school, plus ready
    auth headers for HTTP tests."""
    person = make_person(db, given=given, family="Uprava")
    org = make_school(db, name=org_name)
    add_membership(db, person=person, school=org)
    assignment = assign_role(db, person=person, school=org, role=role)
    return Actor(person=person, school=org, assignment=assignment)


def add_actor(
    db: Session,
    *,
    school: School,
    role: RoleCode,
    given: str = "Osoba",
    granted_areas: list[str] | None = None,
) -> Actor:
    """Another actor in an EXISTING school (same tenant as another actor)."""
    person = make_person(db, given=given, family="X")
    add_membership(db, person=person, school=school)
    assignment = assign_role(
        db, person=person, school=school, role=role, granted_areas=granted_areas
    )
    return Actor(person=person, school=school, assignment=assignment)


def link_login_email(db: Session, *, person: Person, email: str) -> None:
    """Simulate the email a person has verified sign-in with (as Google OIDC's
    ``jit_provision`` would record it), the surface invite acceptance checks
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
    db: Session, *, school: School, guardian: Person, given: str = "Dete"
) -> Person:
    """A child who is an org member and to whom ``guardian`` has active access."""
    child = make_person(db, given=given, family="D")
    add_membership(db, person=child, school=school)
    db.add(
        GuardianRelationship(
            guardian_person_id=guardian.id,
            child_person_id=child.id,
            relationship_type=GuardianRelationshipType.PARENT,
        )
    )
    db.add(
        GuardianSchoolAccess(
            school_id=school.id,
            guardian_person_id=guardian.id,
            child_person_id=child.id,
            status=GuardianAccessStatus.ACTIVE,
        )
    )
    db.commit()
    return child
