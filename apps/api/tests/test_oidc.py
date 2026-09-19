from __future__ import annotations

import pytest
from app.common.errors import UnauthorizedError
from app.config import get_settings
from app.domains.identity import sessions
from app.domains.identity.accounts import live_account_for_person
from app.domains.identity.auth_enums import AccountDisableReason, UserAccountStatus
from app.domains.identity.auth_models import AuthIdentity, UserAccount
from app.domains.identity.enums import PersonIdentityStatus
from app.domains.identity.models import Person
from app.platform import clock
from app.security.auth import SESSION_CREDENTIAL_KEY, resolve_principal
from app.security.csrf import csrf_ok, csrf_required
from app.security.oidc import jit_provision
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.requests import Request

from tests.factories import make_person


def _issue(db: Session, person: Person) -> str:
    """Sign this person in for real, returning the cookie's credential."""
    account = live_account_for_person(db, person.id)
    identity = db.execute(
        select(AuthIdentity).where(AuthIdentity.user_account_id == account.id)
    ).scalars().first()
    _, credential = sessions.issue_session(db, account=account, identity=identity)
    db.commit()
    return credential


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
    """The cookie carries a credential now, not a person id.

    That is the whole change: a person id in a signed cookie is a claim the
    server re-checks, while a credential names a row the server owns and can
    end (M01 §3.2).
    """
    person = jit_provision(
        db, {"sub": "google-cookie", "email": "c@e.com", "name": "C K"}
    )
    credential = _issue(db, person)
    principal = resolve_principal(
        _request(session={SESSION_CREDENTIAL_KEY: credential}), db, get_settings()
    )
    assert principal.person_id == person.id
    assert principal.session_id is not None


def test_a_person_id_in_the_cookie_is_not_a_session(db: Session) -> None:
    """The old cookie shape must not authenticate anything.

    §15 requires active sessions with no proven identity link to be revoked at
    cutover; cookies in flight have no `auth_session` row and no way to get
    one, so they stop working rather than quietly keep working.
    """
    person = make_person(db)
    with pytest.raises(UnauthorizedError):
        resolve_principal(
            _request(session={"person_id": person.id}), db, get_settings()
        )


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
    credential = _issue(db, person)
    account = (
        db.query(UserAccount).filter(UserAccount.person_id == person.id).one()
    )
    account.status = UserAccountStatus.DISABLED
    account.disabled_at = clock.now()
    account.disabled_reason_code = AccountDisableReason.SECURITY_INCIDENT
    db.commit()

    with pytest.raises(UnauthorizedError):
        resolve_principal(
            _request(session={SESSION_CREDENTIAL_KEY: credential}), db, get_settings()
        )


def test_active_account_session_still_resolves(db: Session) -> None:
    person = jit_provision(db, {"sub": "google-ok", "email": "o@e.com", "name": "O K"})
    credential = _issue(db, person)
    principal = resolve_principal(
        _request(session={SESSION_CREDENTIAL_KEY: credential}), db, get_settings()
    )
    assert principal.person_id == person.id


def test_csrf_required_only_for_unsafe_non_auth() -> None:
    assert csrf_required("POST", "/people") is True
    assert csrf_required("DELETE", "/groups/x") is True
    assert csrf_required("GET", "/people") is False
    assert csrf_required("POST", "/auth/logout") is False  # login flow exempt


def test_csrf_ok_skips_non_session_requests() -> None:
    # No session credential → dev-header request → CSRF not enforced.
    assert csrf_ok({}, None) is True


def test_csrf_ok_requires_matching_token() -> None:
    session = {SESSION_CREDENTIAL_KEY: "cred", "csrf": "secret-token"}
    assert csrf_ok(session, "secret-token") is True
    assert csrf_ok(session, "wrong") is False
    assert csrf_ok(session, None) is False
    # A cookie-authenticated request with no token issued fails closed.
    assert csrf_ok({SESSION_CREDENTIAL_KEY: "cred"}, "anything") is False
