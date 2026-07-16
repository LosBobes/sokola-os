from __future__ import annotations

import pytest
from app.common.errors import ForbiddenError, UnauthorizedError
from app.config import get_settings
from app.domains.identity.enums import RoleCode, RoleScopeType
from app.security.auth import DEV_PERSON_HEADER, Principal, resolve_principal
from app.security.context import RequestContext
from app.security.deps import CONTEXT_HEADER, get_context, require_roles
from sqlalchemy.orm import Session
from starlette.requests import Request

from tests.factories import assign_role, make_organization, make_person


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


def test_context_resolves_org_role_and_scope(db: Session) -> None:
    person = make_person(db)
    org = make_organization(db)
    assignment = assign_role(db, person=person, organization=org, role=RoleCode.MANAGER)

    ctx = get_context(
        make_request({CONTEXT_HEADER: assignment.id}), db, Principal(person.id)
    )
    assert isinstance(ctx, RequestContext)
    assert ctx.organization_id == org.id
    assert ctx.role_code is RoleCode.MANAGER
    assert ctx.person_id == person.id


def test_context_requires_a_selection(db: Session) -> None:
    person = make_person(db)
    with pytest.raises(ForbiddenError):
        get_context(make_request({}), db, Principal(person.id))


def test_cannot_use_another_persons_context(db: Session) -> None:
    owner = make_person(db, given="Ana")
    intruder = make_person(db, given="Marko")
    org = make_organization(db)
    assignment = assign_role(db, person=owner, organization=org)

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
        organization_id="org_1",
        role_code=RoleCode.TRAINER,
        scope_type=RoleScopeType.ORGANIZATION,
    )
    require_roles(RoleCode.TRAINER)(ctx)  # allowed → no raise
    with pytest.raises(ForbiddenError):
        require_roles(RoleCode.MANAGER, RoleCode.OWNER)(ctx)
