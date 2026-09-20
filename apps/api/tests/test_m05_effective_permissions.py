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
# F-29 — ADMIN is decided; STUDENT still refuses loudly
# ---------------------------------------------------------------------------


def test_a_role_with_no_counterpart_raises_rather_than_returning_nothing(
    db: Session,
) -> None:
    """`STUDENT` is the one left, and the refusal still matters.

    Returning an empty set would read as a correct fail-closed answer while
    actually meaning "nobody has decided yet". M05 has no student role at all,
    so there is nothing to resolve to and an empty set would be a guess
    wearing a safe-looking face.
    """
    with pytest.raises(RoleMappingUnavailableError):
        canonical_role_key(RoleCode.STUDENT)

    person, school = _with_roles(db, RoleCode.STUDENT)
    with pytest.raises(RoleMappingUnavailableError):
        effective_permissions(db, person_id=person.id, school_id=school.id)


def test_admin_resolves_to_manager_and_keeps_todays_access(db: Session) -> None:
    """F-29, decided: `ADMIN` → `MANAGER`.

    The assertion that carries the decision is the *equivalence*, not the
    number. `security/permissions.py` gives `OWNER`, `MANAGER` and `ADMIN` the
    identical `_STAFF_AREAS` set today, so the two roles are indistinguishable
    under the live guard. Mapping to `MANAGER` keeps them indistinguishable
    once this resolver is wired; mapping to `LIMITED_ADMIN` — which holds no
    permissions in revision 1.3 — would have stripped every administrator at
    that moment.

    Asserted against MANAGER's live set rather than a hard-coded count, so the
    day someone adds a permission to MANAGER this keeps meaning "the same as
    MANAGER" instead of quietly becoming "seven".
    """
    assert canonical_role_key(RoleCode.ADMIN) == "MANAGER"

    admin_person, admin_school = _with_roles(db, RoleCode.ADMIN)
    manager_person, manager_school = _with_roles(db, RoleCode.MANAGER)

    admin_perms = effective_permissions(
        db, person_id=admin_person.id, school_id=admin_school.id
    )
    manager_perms = effective_permissions(
        db, person_id=manager_person.id, school_id=manager_school.id
    )
    assert admin_perms == manager_perms
    assert admin_perms, "revision 1.3 must bind MANAGER, or this proves nothing"


def test_the_live_guard_already_treats_admin_and_manager_alike() -> None:
    """The evidence F-29 was decided on, asserted so it cannot drift.

    If someone narrows `ADMIN` in `ROLE_DEFAULT_AREAS` without revisiting the
    canonical map, the justification above stops being true and this fails —
    which is the point. The decision rests on the two being equivalent today;
    it does not survive that ceasing to be so silently.
    """
    from app.security.permissions import ROLE_DEFAULT_AREAS

    assert ROLE_DEFAULT_AREAS[RoleCode.ADMIN] == ROLE_DEFAULT_AREAS[RoleCode.MANAGER]


@pytest.mark.parametrize(
    "role, expected",
    [
        (RoleCode.OWNER, "OWNER"),
        (RoleCode.MANAGER, "MANAGER"),
        (RoleCode.ADMIN, "MANAGER"),
        (RoleCode.TRAINER, "INSTRUCTOR"),
        (RoleCode.PARENT, "GUARDIAN"),
    ],
)
def test_the_settled_mappings(role: RoleCode, expected: str) -> None:
    """§2.4 names TRAINER → INSTRUCTOR outright; PARENT → GUARDIAN is the only
    role with the same meaning; OWNER and MANAGER carry across unchanged."""
    assert canonical_role_key(role) == expected


def test_the_permission_map_is_not_the_workspace_map() -> None:
    """Still two maps, even though both now send ADMIN to MANAGER.

    Agreeing today is not the same as being one thing. The workspace answer is
    *forced* — §2.4 puts MANAGER and LIMITED_ADMIN in the same ADMIN
    workspace, so the choice cannot matter there. The permission answer is a
    judgement (F-29). The day someone narrows ADMIN to LIMITED_ADMIN for
    permissions, the workspace answer must not move with it, and it will not,
    because these are two dictionaries with two reasons.
    """
    from app.application.available_contexts import _WORKSPACE_ROLE_KEY
    from app.application.effective_permissions import _CANONICAL_ROLE_KEY

    assert _WORKSPACE_ROLE_KEY is not _CANONICAL_ROLE_KEY
    assert RoleCode.ADMIN in _WORKSPACE_ROLE_KEY
    assert RoleCode.ADMIN in _CANONICAL_ROLE_KEY
    # STUDENT is in neither: no workspace, no role to resolve to.
    assert RoleCode.STUDENT not in _WORKSPACE_ROLE_KEY
    assert RoleCode.STUDENT not in _CANONICAL_ROLE_KEY


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
