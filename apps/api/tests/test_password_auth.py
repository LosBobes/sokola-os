from __future__ import annotations

import pytest
from app.common.errors import ConflictError, UnauthorizedError
from app.domains.identity.accounts import find_local_password_identity
from app.domains.identity.auth_enums import LOCAL_PASSWORD_PROVIDER
from app.domains.identity.auth_models import LocalPasswordCredential
from app.domains.identity.enums import PersonIdentityStatus
from app.security.oidc import jit_provision
from app.security.password import hash_password, verify_password
from app.security.password_auth import authenticate_with_password, register_with_password
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


def test_hash_password_roundtrips() -> None:
    stored = hash_password("correct horse battery")
    assert stored.startswith("scrypt$")
    assert verify_password("correct horse battery", stored)
    assert not verify_password("wrong", stored)


def test_verify_password_rejects_garbage() -> None:
    assert not verify_password("x", "not-a-valid-hash")
    assert not verify_password("x", "")


def test_register_with_password_creates_verified_person(db: Session) -> None:
    person = register_with_password(db, "Ana@Example.com", "s3cretpw!", "Ana", "Marković")
    assert person.identity_status is PersonIdentityStatus.VERIFIED
    assert person.display_name == "Ana Marković"

    identity = find_local_password_identity(db, "ana@example.com")
    assert identity is not None
    assert identity.provider_key == LOCAL_PASSWORD_PROVIDER
    # §3.2: this provider proves nothing about the address, so it is a label.
    assert identity.email_verified_at is None

    credential = db.get(LocalPasswordCredential, identity.id)
    assert credential is not None
    assert verify_password("s3cretpw!", credential.password_hash)


def test_register_then_authenticate(db: Session) -> None:
    register_with_password(db, "user@example.com", "hunter2pw", "U", "Ser")
    person = authenticate_with_password(db, "USER@example.com", "hunter2pw")
    assert person.display_name == "U Ser"


def test_register_duplicate_email_conflicts(db: Session) -> None:
    register_with_password(db, "dup@example.com", "hunter2pw", "D", "Up")
    with pytest.raises(ConflictError):
        register_with_password(db, "Dup@Example.com", "otherpass", "D", "Two")


def test_authenticate_wrong_password_unauthorized(db: Session) -> None:
    register_with_password(db, "u2@example.com", "rightpass", "U", "Two")
    with pytest.raises(UnauthorizedError):
        authenticate_with_password(db, "u2@example.com", "wrongpass")


def test_authenticate_unknown_email_unauthorized(db: Session) -> None:
    with pytest.raises(UnauthorizedError):
        authenticate_with_password(db, "nobody@example.com", "whatever")


def test_authenticate_google_only_account_unauthorized(db: Session) -> None:
    """A person provisioned via Google (no password) cannot be logged into with
    a password, and the failure is the same generic one, no enumeration."""
    jit_provision(db, {"sub": "g-nopw", "email": "nopw@example.com", "name": "No PW"})
    with pytest.raises(UnauthorizedError):
        authenticate_with_password(db, "nopw@example.com", "anything")


def test_password_register_endpoint_issues_session(client: TestClient) -> None:
    resp = client.post(
        "/auth/password/register",
        json={
            "email": "new@example.com",
            "password": "longenough1",
            "given_name": "New",
            "family_name": "User",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["display_name"] == "New User"
    assert "session" in resp.cookies


def test_password_register_short_password_rejected(client: TestClient) -> None:
    resp = client.post(
        "/auth/password/register",
        json={
            "email": "short@example.com",
            "password": "short",
            "given_name": "S",
            "family_name": "P",
        },
    )
    assert resp.status_code == 422


def test_password_login_endpoint_flow(client: TestClient) -> None:
    client.post(
        "/auth/password/register",
        json={
            "email": "flow@example.com",
            "password": "longenough1",
            "given_name": "Flow",
            "family_name": "User",
        },
    )
    ok = client.post(
        "/auth/password/login", json={"email": "flow@example.com", "password": "longenough1"}
    )
    assert ok.status_code == 200
    assert "session" in ok.cookies

    bad = client.post(
        "/auth/password/login", json={"email": "flow@example.com", "password": "nope"}
    )
    assert bad.status_code == 401


def test_auth_config_reports_password_enabled(client: TestClient) -> None:
    resp = client.get("/auth/config")
    assert resp.status_code == 200
    assert resp.json()["password_enabled"] is True
