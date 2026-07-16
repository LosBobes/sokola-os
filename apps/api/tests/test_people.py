from __future__ import annotations

from app.domains.identity.enums import RoleCode
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import bootstrap_actor


def test_create_provisional_person_journey8(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)

    resp = client.post(
        "/people",
        headers=actor.headers,
        json={"given_name": "Petar", "family_name": "Petrović"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["display_name"] == "Petar Petrović"
    assert body["identity_status"] == "PROVISIONAL"

    # The new person appears in the org roster.
    listing = client.get("/people", headers=actor.headers).json()
    assert any(p["id"] == body["id"] for p in listing["items"])


def test_duplicate_is_blocked_then_allowed_with_reason(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    payload = {"given_name": "Petar", "family_name": "Petrović"}
    first = client.post("/people", headers=actor.headers, json=payload)
    assert first.status_code == 201

    # Same name again → 409 with candidate list (the safety branch).
    dup = client.post("/people", headers=actor.headers, json=payload)
    assert dup.status_code == 409
    details = dup.json()["error"]["details"]
    assert details["code"] == "POSSIBLE_DUPLICATE"
    assert details["candidates"][0]["display_name"] == "Petar Petrović"

    # Overriding without a reason is rejected by validation.
    no_reason = client.post(
        "/people", headers=actor.headers, json={**payload, "allow_possible_duplicate": True}
    )
    assert no_reason.status_code == 422

    # Overriding with a written reason succeeds and creates a distinct person.
    ok = client.post(
        "/people",
        headers=actor.headers,
        json={**payload, "allow_possible_duplicate": True, "duplicate_reason": "Blizanci"},
    )
    assert ok.status_code == 201
    assert ok.json()["id"] != first.json()["id"]


def test_people_are_isolated_per_organization(client: TestClient, db: Session) -> None:
    org_a = bootstrap_actor(db, org_name="Klub A")
    org_b = bootstrap_actor(db, org_name="Klub B")

    created = client.post(
        "/people", headers=org_a.headers, json={"given_name": "Mila", "family_name": "Jovanović"}
    ).json()

    # Org B cannot see org A's person by id …
    assert client.get(f"/people/{created['id']}", headers=org_b.headers).status_code == 404
    # … nor in its listing.
    b_ids = {p["id"] for p in client.get("/people", headers=org_b.headers).json()["items"]}
    assert created["id"] not in b_ids


def test_parent_role_cannot_create_person(client: TestClient, db: Session) -> None:
    parent = bootstrap_actor(db, role=RoleCode.PARENT, given="Roditelj")
    resp = client.post(
        "/people", headers=parent.headers, json={"given_name": "X", "family_name": "Y"}
    )
    assert resp.status_code == 403
