from __future__ import annotations

import pytest
from app.common.errors import UnauthorizedError
from app.config import get_settings
from app.domains.identity.enums import AuthAccountStatus, PersonIdentityStatus
from app.domains.identity.models import AuthAccount
from app.security.auth import resolve_principal
from app.security.csrf import csrf_ok, csrf_required
from app.security.oidc import jit_provision
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from starlette.requests import Request

from tests.factories import make_person


def _request(*, session: dict | None = None) -> Request:
    scope: dict = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "query_string": b"",
        "scheme": "http",
        "server": ("test", 80),
    }
    if session is not None:
        scope["session"] = session
    return Request(scope)


def test_jit_provision_creates_verified_person(db: Session) -> None:
    claims = {
        "sub": "google-abc-123",
        "email": "ana@example.com",
        "given_name": "Ana",
        "family_name": "Marković",
        "name": "Ana Marković",
    }
    person = jit_provision(db, claims)
    assert person.identity_status is PersonIdentityStatus.VERIFIED
    assert person.display_name == "Ana Marković"


def test_jit_provision_is_idempotent_on_subject(db: Session) -> None:
    claims = {"sub": "google-xyz", "email": "x@example.com", "name": "X Y"}
    first = jit_provision(db, claims)
    second = jit_provision(db, dict(claims))
    assert second.id == first.id


def test_session_cookie_resolves_principal(db: Session) -> None:
    person = make_person(db)
    principal = resolve_principal(
        _request(session={"person_id": person.id}), db, get_settings()
    )
    assert principal.person_id == person.id


def test_no_auth_is_unauthorized(db: Session) -> None:
    with pytest.raises(UnauthorizedError):
        resolve_principal(_request(), db, get_settings())


def test_auth_config_reports_methods(client: TestClient) -> None:
    body = client.get("/auth/config").json()
    assert body["google_enabled"] is False  # no Google creds in tests
    assert body["dev_auth_enabled"] is True


def test_google_login_hidden_when_disabled(client: TestClient) -> None:
    assert client.get("/auth/google/login").status_code == 404


def test_disabled_account_revokes_session(db: Session) -> None:
    person = jit_provision(db, {"sub": "google-rev", "email": "r@e.com", "name": "R E"})
    account = (
        db.query(AuthAccount).filter(AuthAccount.person_id == person.id).one()
    )
    account.status = AuthAccountStatus.DISABLED
    db.commit()

    with pytest.raises(UnauthorizedError):
        resolve_principal(
            _request(session={"person_id": person.id}), db, get_settings()
        )


def test_active_account_session_still_resolves(db: Session) -> None:
    person = jit_provision(db, {"sub": "google-ok", "email": "o@e.com", "name": "O K"})
    principal = resolve_principal(
        _request(session={"person_id": person.id}), db, get_settings()
    )
    assert principal.person_id == person.id


def test_csrf_required_only_for_unsafe_non_auth() -> None:
    assert csrf_required("POST", "/people") is True
    assert csrf_required("DELETE", "/groups/x") is True
    assert csrf_required("GET", "/people") is False
    assert csrf_required("POST", "/auth/logout") is False  # login flow exempt


def test_csrf_ok_skips_non_session_requests() -> None:
    # No session-cookie person → dev-header request → CSRF not enforced.
    assert csrf_ok({}, None) is True


def test_csrf_ok_requires_matching_token() -> None:
    session = {"person_id": "per_1", "csrf": "secret-token"}
    assert csrf_ok(session, "secret-token") is True
    assert csrf_ok(session, "wrong") is False
    assert csrf_ok(session, None) is False
    assert csrf_ok({"person_id": "per_1"}, "anything") is False  # no token issued
