"""M05 §3.1 steps 4–5: the effective permission union.

Tested against the registry as revision 1.3 actually publishes it — 38 keys,
OWNER holding 14 and MANAGER 7 — rather than against a fixture arranged to
make the arithmetic tidy. If the seeded registry changes, these numbers are
supposed to move with it, and a test that invented its own bindings would go on
passing while the real answer drifted.

Nothing is wired to this resolver yet. `app.security.permissions` is still the
live guard, and this cannot replace it until the continuation registries land
(F-30).
"""

from __future__ import annotations

import pathlib

import pytest
from app.application.effective_permissions import (
    RoleMappingUnavailableError,
    canonical_role_key,
    effective_permissions,
    permissions_for_role_keys,
)
from app.domains.identity.enums import RoleCode
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.factories import add_membership, assign_role, make_person, make_school


def _with_roles(db: Session, *roles: RoleCode):
    person = make_person(db)
    school = make_school(db)
    add_membership(db, person=person, school=school)
    for role in roles:
        assign_role(db, person=person, school=school, role=role)
    db.commit()
    return person, school


# ---------------------------------------------------------------------------
# §3.2 — union, never rank
# ---------------------------------------------------------------------------


def test_one_role_gives_exactly_its_bindings(db: Session) -> None:
    person, school = _with_roles(db, RoleCode.MANAGER)
    held = effective_permissions(db, person_id=person.id, school_id=school.id)

    expected = {
        row[0]
        for row in db.execute(
            text("SELECT permission_key FROM role_permission_binding WHERE role_key='MANAGER'")
        ).all()
    }
    assert held == expected
    assert held, "the seeded registry should give MANAGER something"


def test_two_roles_union_rather_than_intersect(db: Session) -> None:
    """§3.2 point 1. OWNER holds every MANAGER permission and seven more in
    this revision, so an intersection would silently equal MANAGER's set and
    look plausible — which is why the assertion names the superset."""
    person, school = _with_roles(db, RoleCode.OWNER, RoleCode.MANAGER)
    both = effective_permissions(db, person_id=person.id, school_id=school.id)

    owner_only, _ = _with_roles(db, RoleCode.OWNER)
    owner = permissions_for_role_keys(db, role_keys=frozenset({"OWNER"}))
    manager = permissions_for_role_keys(db, role_keys=frozenset({"MANAGER"}))

    assert both == owner | manager
    assert both == owner, "OWNER is a superset of MANAGER in revision 1.3"
    assert manager < owner


def test_rank_inherits_nothing(db: Session) -> None:
    """§3.2 point 2: "Role rank služi samo za administriranje dodela; ne
    nasleđuje permissions."

    GUARDIAN sits below MANAGER by administrative rank and holds no binding at
    all in this revision. If rank leaked, it would pick some up.
    """
    person, school = _with_roles(db, RoleCode.PARENT)
    assert effective_permissions(db, person_id=person.id, school_id=school.id) == frozenset()


def test_no_roles_gives_nothing(db: Session) -> None:
    person = make_person(db)
    school = make_school(db)
    add_membership(db, person=person, school=school)
    db.commit()
    assert effective_permissions(db, person_id=person.id, school_id=school.id) == frozenset()


def test_another_schools_role_grants_nothing_here(db: Session) -> None:
    """The tenant property. A role is held *in a school*, and reading
    assignments without the school filter is how that gets lost."""
    person = make_person(db)
    mine = make_school(db, name="Moja")
    theirs = make_school(db, name="Tudja")
    add_membership(db, person=person, school=mine)
    add_membership(db, person=person, school=theirs)
    assign_role(db, person=person, school=theirs, role=RoleCode.OWNER)
    db.commit()

    assert effective_permissions(db, person_id=person.id, school_id=mine.id) == frozenset()
    assert effective_permissions(db, person_id=person.id, school_id=theirs.id)


def test_a_revoked_assignment_grants_nothing(db: Session) -> None:
    person, school = _with_roles(db, RoleCode.OWNER)
    db.execute(
        text(
            "UPDATE role_assignment SET status = 'REVOKED'"
            " WHERE person_id = :p AND school_id = :s"
        ),
        {"p": person.id, "s": school.id},
    )
    db.commit()
    assert effective_permissions(db, person_id=person.id, school_id=school.id) == frozenset()


# ---------------------------------------------------------------------------
# F-29 — the unmapped roles refuse loudly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", [RoleCode.ADMIN, RoleCode.STUDENT])
def test_an_unmapped_role_raises_rather_than_returning_nothing(
    db: Session, role: RoleCode
) -> None:
    """The whole point of F-29 being open.

    Returning an empty set would read as a correct fail-closed answer while
    actually meaning "nobody has decided yet" — and the first caller to wire
    this up would silently strip every administrator, which is the outcome the
    finding exists to prevent.
    """
    with pytest.raises(RoleMappingUnavailableError):
        canonical_role_key(role)

    person, school = _with_roles(db, role)
    with pytest.raises(RoleMappingUnavailableError):
        effective_permissions(db, person_id=person.id, school_id=school.id)


@pytest.mark.parametrize(
    "role, expected",
    [
        (RoleCode.OWNER, "OWNER"),
        (RoleCode.MANAGER, "MANAGER"),
        (RoleCode.TRAINER, "INSTRUCTOR"),
        (RoleCode.PARENT, "GUARDIAN"),
    ],
)
def test_the_settled_mappings(role: RoleCode, expected: str) -> None:
    """§2.4 names TRAINER → INSTRUCTOR outright; PARENT → GUARDIAN is the only
    role with the same meaning; OWNER and MANAGER carry across unchanged."""
    assert canonical_role_key(role) == expected


def test_the_permission_map_is_not_the_workspace_map() -> None:
    """These two must stay separate.

    `available_contexts` maps ADMIN → MANAGER safely, because §2.4 puts
    MANAGER and LIMITED_ADMIN in the same workspace. For permissions they are
    as different as two roles get — MANAGER holds seven in this revision,
    LIMITED_ADMIN none. Sharing the map would grant ADMIN a permission set on
    the strength of a mapping chosen for a different question entirely.
    """
    from app.application.available_contexts import _WORKSPACE_ROLE_KEY
    from app.application.effective_permissions import _CANONICAL_ROLE_KEY

    assert RoleCode.ADMIN in _WORKSPACE_ROLE_KEY
    assert RoleCode.ADMIN not in _CANONICAL_ROLE_KEY


# ---------------------------------------------------------------------------
# Fail closed
# ---------------------------------------------------------------------------


def test_no_active_revision_is_a_refusal_not_an_empty_set(db: Session) -> None:
    """§3.1: an unavailable policy store is a deny. An empty set would be
    indistinguishable from "this person may do nothing", and the two need
    very different handling."""
    person, school = _with_roles(db, RoleCode.OWNER)
    db.execute(text("UPDATE authorization_policy_revision SET status = 'SUPERSEDED'"))
    db.commit()

    with pytest.raises(RoleMappingUnavailableError):
        effective_permissions(db, person_id=person.id, school_id=school.id)


def test_the_live_guard_is_untouched() -> None:
    """Nothing is wired to this resolver yet: `app.security.permissions` is
    still what every router uses, and it must not have grown a dependency on
    the registry while this was built."""
    import app.security.permissions as live

    source = live.__file__
    assert source is not None
    text_ = pathlib.Path(source).read_text(encoding="utf-8")
    assert "authorization" not in text_
    assert "effective_permissions" not in text_
