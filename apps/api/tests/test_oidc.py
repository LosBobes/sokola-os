from __future__ import annotations

import pytest
from app.common.errors import UnauthorizedError
from app.config import get_settings
from app.domains.identity.enums import PersonIdentityStatus
from app.security.auth import resolve_principal
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
