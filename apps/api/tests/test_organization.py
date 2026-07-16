from __future__ import annotations

from app.security.auth import DEV_PERSON_HEADER
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import make_person


def test_create_organization_makes_caller_owner(client: TestClient, db: Session) -> None:
    person = make_person(db, given="Osnivač")
    headers = {DEV_PERSON_HEADER: person.id}

    resp = client.post(
        "/organizations",
        headers=headers,
        json={"name": "Plesni Studio Ritam", "type": "DANCE_SCHOOL"},
    )
    assert resp.status_code == 201
    org = resp.json()
    assert org["name"] == "Plesni Studio Ritam"

    # The creator now has an OWNER context for that organization.
    contexts = client.get("/me/contexts", headers=headers).json()
    match = [c for c in contexts if c["organization_id"] == org["id"]]
    assert len(match) == 1
    assert match[0]["role_code"] == "OWNER"


def test_get_current_organization_uses_context(client: TestClient, db: Session) -> None:
    from tests.factories import bootstrap_actor

    actor = bootstrap_actor(db, org_name="Klub Soko")
    resp = client.get("/organizations/current", headers=actor.headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == actor.organization.id


def test_tenant_lookup_by_slug(client: TestClient, db: Session) -> None:
    person = make_person(db, given="Osnivač")
    created = client.post(
        "/organizations",
        headers={DEV_PERSON_HEADER: person.id},
        json={"name": "Plesni Studio Ritam", "type": "DANCE_SCHOOL"},
    ).json()
    assert created["slug"]

    # Public discovery resolves the code to the tenant (no auth required).
    found = client.get(f"/tenants/{created['slug']}")
    assert found.status_code == 200
    assert found.json()["organization_id"] == created["id"]

    assert client.get("/tenants/ne-postoji").status_code == 404
