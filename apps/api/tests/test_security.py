from __future__ import annotations

import pytest
from app.common.errors import ForbiddenError, UnauthorizedError
from app.config import get_settings
from app.domains.identity.enums import RoleCode, RoleScopeType
from app.domains.people import membership as membership_service
from app.security.auth import DEV_PERSON_HEADER, Principal, resolve_principal
from app.security.context import RequestContext
from app.security.deps import CONTEXT_HEADER, get_context, require_roles
from sqlalchemy.orm import Session
from starlette.requests import Request

from tests.factories import add_membership, assign_role, make_person, make_school


def make_request(headers: dict[str, str]) -> Request:
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": raw,
        "query_string": b"",
        "scheme": "http",
        "server": ("test", 80),
    }
    return Request(scope)


# --- principal resolution -------------------------------------------------


def test_dev_header_resolves_principal(db: Session) -> None:
    person = make_person(db)
    principal = resolve_principal(
        make_request({DEV_PERSON_HEADER: person.id}), db, get_settings()
    )
    assert principal.person_id == person.id


def test_missing_auth_is_unauthorized(db: Session) -> None:
    with pytest.raises(UnauthorizedError):
        resolve_principal(make_request({}), db, get_settings())


def test_unknown_person_is_unauthorized(db: Session) -> None:
    with pytest.raises(UnauthorizedError):
        resolve_principal(make_request({DEV_PERSON_HEADER: "per_nope"}), db, get_settings())


# --- context resolution ---------------------------------------------------


def test_context_resolves_school_role_and_scope(db: Session) -> None:
    person = make_person(db)
    org = make_school(db)
    # M03 §6.1 point 4 needs *both*: an active role assignment and current M06
    # `ACTIVE` membership evidence. This test used to grant only the role,
    # which the guard accepted — see the next test for why it no longer does.
    add_membership(db, person=person, school=org)
    assignment = assign_role(db, person=person, school=org, role=RoleCode.MANAGER)

    ctx = get_context(
        make_request({CONTEXT_HEADER: assignment.id}), db, Principal(person.id)
    )
    assert isinstance(ctx, RequestContext)
    assert ctx.school_id == org.id
    assert ctx.role_code is RoleCode.MANAGER
    assert ctx.person_id == person.id


def test_a_role_without_membership_grants_nothing(db: Session) -> None:
    """M03 §6.1 point 4: a role assignment is not membership evidence.

    §3 separates them deliberately — membership answers "does this person
    belong to this school right now", the role answers "what may they do here"
    — and §6.1 requires both. Before this guard existed, a role assignment left
    behind after someone's membership was terminated still opened the school:
    the role is what an admin screen revokes, and the membership is what a
    person's departure ends, and they are not always done together.
    """
    person = make_person(db)
    org = make_school(db)
    assignment = assign_role(db, person=person, school=org, role=RoleCode.MANAGER)

    with pytest.raises(ForbiddenError):
        get_context(
            make_request({CONTEXT_HEADER: assignment.id}), db, Principal(person.id)
        )


def test_a_terminated_membership_closes_the_school(db: Session) -> None:
    """§6.1: "M06 `DRAFT`, `SUSPENDED` i `TERMINATED` članstvo ne daju redovan
    workspace pristup." The role assignment is untouched and still active."""
    person = make_person(db)
    org = make_school(db)
    membership = add_membership(db, person=person, school=org)
    assignment = assign_role(db, person=person, school=org, role=RoleCode.MANAGER)
    request = make_request({CONTEXT_HEADER: assignment.id})
    assert get_context(request, db, Principal(person.id)).school_id == org.id

    # Terminated through the M06 command rather than by writing columns, so
    # the test exercises the same transition production does.
    membership_service.terminate_membership(db, membership, reason_code="LEFT_SCHOOL")
    db.commit()

    with pytest.raises(ForbiddenError):
        get_context(request, db, Principal(person.id))

def test_context_requires_a_selection(db: Session) -> None:
    person = make_person(db)
    with pytest.raises(ForbiddenError):
        get_context(make_request({}), db, Principal(person.id))


def test_cannot_use_another_persons_context(db: Session) -> None:
    owner = make_person(db, given="Ana")
    intruder = make_person(db, given="Marko")
    org = make_school(db)
    assignment = assign_role(db, person=owner, school=org)

    # The intruder authenticates as themselves but names the owner's assignment.
    with pytest.raises(ForbiddenError):
        get_context(
            make_request({CONTEXT_HEADER: assignment.id}), db, Principal(intruder.id)
        )


# --- role guard -----------------------------------------------------------


def test_require_roles_allows_and_blocks() -> None:
    ctx = RequestContext(
        person_id="per_1",
        role_assignment_id="rol_1",
        school_id="org_1",
        role_code=RoleCode.TRAINER,
        scope_type=RoleScopeType.SCHOOL,
    )
    require_roles(RoleCode.TRAINER)(ctx)  # allowed → no raise
    with pytest.raises(ForbiddenError):
        require_roles(RoleCode.MANAGER, RoleCode.OWNER)(ctx)
