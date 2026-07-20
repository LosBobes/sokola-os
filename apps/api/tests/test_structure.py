from __future__ import annotations

from app.domains.identity.enums import RoleCode
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import add_actor, bootstrap_actor

# ---------------------------------------------------------------------------
# Location CRUD + deactivation
# ---------------------------------------------------------------------------


def test_location_crud_and_safe_deactivation(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)

    created = client.post(
        "/locations",
        headers=actor.headers,
        json={"name": "Centrala", "address": "Knez Mihailova 1", "internal_code": "C1"},
    )
    assert created.status_code == 201
    loc = created.json()
    assert loc["name"] == "Centrala"
    assert loc["status"] == "ACTIVE"

    fetched = client.get(f"/locations/{loc['id']}", headers=actor.headers)
    assert fetched.status_code == 200
    assert fetched.json()["address"] == "Knez Mihailova 1"

    updated = client.patch(
        f"/locations/{loc['id']}", headers=actor.headers, json={"name": "Glavni ogranak"}
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Glavni ogranak"

    listed = client.get("/locations", headers=actor.headers).json()
    assert listed["total"] == 1

    # Deactivation is a soft-delete: the row is archived, not removed.
    deact = client.post(f"/locations/{loc['id']}/deactivate", headers=actor.headers)
    assert deact.status_code == 200
    assert deact.json()["status"] == "ARCHIVED"

    # Archived resources drop out of normal reads.
    assert client.get(f"/locations/{loc['id']}", headers=actor.headers).status_code == 404
    assert client.get("/locations", headers=actor.headers).json()["total"] == 0


def test_location_unique_internal_code_conflict(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    first = client.post(
        "/locations", headers=actor.headers, json={"name": "A", "internal_code": "DUP"}
    )
    assert first.status_code == 201

    clash = client.post(
        "/locations", headers=actor.headers, json={"name": "B", "internal_code": "DUP"}
    )
    assert clash.status_code == 409

    # The same code frees up once the holder is deactivated.
    client.post(f"/locations/{first.json()['id']}/deactivate", headers=actor.headers)
    reuse = client.post(
        "/locations", headers=actor.headers, json={"name": "C", "internal_code": "DUP"}
    )
    assert reuse.status_code == 201


def test_location_tenant_isolation(client: TestClient, db: Session) -> None:
    org_a = bootstrap_actor(db, org_name="Klub A")
    org_b = bootstrap_actor(db, org_name="Klub B")

    loc_b = client.post("/locations", headers=org_b.headers, json={"name": "B ogranak"}).json()

    # Org A cannot see, update, or deactivate org B's location.
    assert client.get(f"/locations/{loc_b['id']}", headers=org_a.headers).status_code == 404
    assert (
        client.patch(
            f"/locations/{loc_b['id']}", headers=org_a.headers, json={"name": "hakovano"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/locations/{loc_b['id']}/deactivate", headers=org_a.headers
        ).status_code
        == 404
    )
    assert client.get("/locations", headers=org_a.headers).json()["total"] == 0

    # Duplicate internal codes are allowed ACROSS organizations.
    client.post("/locations", headers=org_a.headers, json={"name": "A1", "internal_code": "X"})
    other = client.post(
        "/locations", headers=org_b.headers, json={"name": "B1", "internal_code": "X"}
    )
    assert other.status_code == 201


# ---------------------------------------------------------------------------
# Room CRUD + relationship to Location
# ---------------------------------------------------------------------------


def test_room_belongs_to_location_and_crud(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    loc = client.post("/locations", headers=actor.headers, json={"name": "Ogranak"}).json()

    created = client.post(
        "/rooms",
        headers=actor.headers,
        json={"location_id": loc["id"], "name": "Sala 1", "capacity": 20, "internal_code": "S1"},
    )
    assert created.status_code == 201
    room = created.json()
    assert room["location_id"] == loc["id"]
    assert room["capacity"] == 20

    updated = client.patch(
        f"/rooms/{room['id']}", headers=actor.headers, json={"capacity": 30}
    )
    assert updated.status_code == 200
    assert updated.json()["capacity"] == 30

    # Filter rooms by location.
    filtered = client.get(
        "/rooms", headers=actor.headers, params={"location_id": loc["id"]}
    ).json()
    assert filtered["total"] == 1

    deact = client.post(f"/rooms/{room['id']}/deactivate", headers=actor.headers)
    assert deact.status_code == 200
    assert deact.json()["status"] == "ARCHIVED"
    assert client.get(f"/rooms/{room['id']}", headers=actor.headers).status_code == 404


def test_room_requires_visible_location(client: TestClient, db: Session) -> None:
    org_a = bootstrap_actor(db, org_name="Klub A")
    org_b = bootstrap_actor(db, org_name="Klub B")
    loc_b = client.post("/locations", headers=org_b.headers, json={"name": "B ogranak"}).json()

    # Org A cannot attach a room to org B's location.
    resp = client.post(
        "/rooms", headers=org_a.headers, json={"location_id": loc_b["id"], "name": "Sala"}
    )
    assert resp.status_code == 404


def test_room_unique_internal_code_conflict(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    loc = client.post("/locations", headers=actor.headers, json={"name": "Ogranak"}).json()
    client.post(
        "/rooms",
        headers=actor.headers,
        json={"location_id": loc["id"], "name": "Sala 1", "internal_code": "R1"},
    )
    clash = client.post(
        "/rooms",
        headers=actor.headers,
        json={"location_id": loc["id"], "name": "Sala 2", "internal_code": "R1"},
    )
    assert clash.status_code == 409


# ---------------------------------------------------------------------------
# Program + Category
# ---------------------------------------------------------------------------


def test_program_with_category_crud(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    cat = client.post(
        "/categories", headers=actor.headers, json={"name": "Borilački sportovi"}
    )
    assert cat.status_code == 201
    cat_id = cat.json()["id"]

    created = client.post(
        "/programs",
        headers=actor.headers,
        json={"name": "Džudo", "category_id": cat_id, "internal_code": "JUDO"},
    )
    assert created.status_code == 201
    prog = created.json()
    assert prog["category_id"] == cat_id
    assert prog["internal_code"] == "JUDO"

    # Clearing the category link via PATCH null.
    cleared = client.patch(
        f"/programs/{prog['id']}", headers=actor.headers, json={"category_id": None}
    )
    assert cleared.status_code == 200
    assert cleared.json()["category_id"] is None

    deact = client.post(f"/programs/{prog['id']}/deactivate", headers=actor.headers)
    assert deact.status_code == 200
    assert deact.json()["status"] == "ARCHIVED"


def test_program_unknown_category_rejected(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    resp = client.post(
        "/programs",
        headers=actor.headers,
        json={"name": "Program", "category_id": "cat_does_not_exist"},
    )
    assert resp.status_code == 404


def test_program_unique_internal_code_conflict(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    client.post(
        "/programs", headers=actor.headers, json={"name": "P1", "internal_code": "CODE"}
    )
    clash = client.post(
        "/programs", headers=actor.headers, json={"name": "P2", "internal_code": "CODE"}
    )
    assert clash.status_code == 409


def test_program_and_category_tenant_isolation(client: TestClient, db: Session) -> None:
    org_a = bootstrap_actor(db, org_name="Klub A")
    org_b = bootstrap_actor(db, org_name="Klub B")

    cat_b = client.post("/categories", headers=org_b.headers, json={"name": "Kat B"}).json()
    prog_b = client.post("/programs", headers=org_b.headers, json={"name": "Prog B"}).json()

    # Org A sees none of org B's structure.
    assert client.get("/categories", headers=org_a.headers).json()["total"] == 0
    assert client.get("/programs", headers=org_a.headers).json()["total"] == 0
    assert client.get(f"/categories/{cat_b['id']}", headers=org_a.headers).status_code == 404
    assert client.get(f"/programs/{prog_b['id']}", headers=org_a.headers).status_code == 404

    # Org A cannot reference org B's category.
    cross = client.post(
        "/programs",
        headers=org_a.headers,
        json={"name": "Prog A", "category_id": cat_b["id"]},
    )
    assert cross.status_code == 404


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def test_non_staff_cannot_write(client: TestClient, db: Session) -> None:
    owner = bootstrap_actor(db, org_name="Klub", role=RoleCode.OWNER)
    trainer = add_actor(db, organization=owner.organization, role=RoleCode.TRAINER)

    # A trainer may read but not create structural entities.
    assert client.get("/locations", headers=trainer.headers).status_code == 200
    denied = client.post("/locations", headers=trainer.headers, json={"name": "X"})
    assert denied.status_code == 403
