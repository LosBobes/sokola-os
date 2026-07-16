from __future__ import annotations

from app.domains.identity.enums import RoleCode
from app.domains.identity.models import Person
from app.domains.organization.models import Organization
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import Actor, add_actor, bootstrap_actor, make_child_with_guardian

EVENT = {"title": "Zimski kamp", "starts_at": "2026-12-20T09:00:00+00:00"}


def _event(client: TestClient, staff: Actor, **overrides: object) -> str:
    return client.post("/events", headers=staff.headers, json={**EVENT, **overrides}).json()["id"]


def _parent_of(db: Session, org: Organization, given: str = "R") -> Actor:
    return add_actor(db, organization=org, role=RoleCode.PARENT, given=given)


def _child(db: Session, org: Organization, guardian: Actor, given: str) -> Person:
    return make_child_with_guardian(db, organization=org, guardian=guardian.person, given=given)


def test_register_and_cancel_children_journeys_3_and_4(client: TestClient, db: Session) -> None:
    manager = bootstrap_actor(db)
    org = manager.organization
    parent = _parent_of(db, org, "Roditelj")
    child_a = _child(db, org, parent, "Ana")
    child_b = _child(db, org, parent, "Bane")
    event_id = _event(client, manager)

    # Journey 3: one command registers multiple children.
    reg = client.post(
        f"/events/{event_id}/registrations",
        headers=parent.headers,
        json={"child_person_ids": [child_a.id, child_b.id]},
    )
    assert reg.status_code == 201
    registrations = reg.json()
    assert {r["status"] for r in registrations} == {"REGISTERED"}
    assert len(registrations) == 2

    # Journey 4: cancel is a status change, not a deletion.
    reg_id = registrations[0]["registration_id"]
    cancelled = client.post(
        f"/events/{event_id}/registrations/{reg_id}/cancel", headers=parent.headers
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"


def test_capacity_blocks_batch_atomically(client: TestClient, db: Session) -> None:
    manager = bootstrap_actor(db)
    org = manager.organization
    parent = _parent_of(db, org)
    c1 = _child(db, org, parent, "Prvi")
    c2 = _child(db, org, parent, "Drugi")
    event_id = _event(client, manager, capacity_mode="LIMITED", capacity=1)

    full = client.post(
        f"/events/{event_id}/registrations",
        headers=parent.headers,
        json={"child_person_ids": [c1.id, c2.id]},
    )
    assert full.status_code == 409
    assert full.json()["error"]["details"]["code"] == "EVENT_FULL"
    # Nothing was registered (atomic).
    one = client.post(
        f"/events/{event_id}/registrations",
        headers=parent.headers,
        json={"child_person_ids": [c1.id]},
    )
    assert one.status_code == 201


def test_parent_cannot_register_unrelated_child(client: TestClient, db: Session) -> None:
    manager = bootstrap_actor(db)
    org = manager.organization
    parent = _parent_of(db, org)
    other_parent = _parent_of(db, org, "Drugi")
    other_child = _child(db, org, other_parent, "Tuđe")
    event_id = _event(client, manager)

    resp = client.post(
        f"/events/{event_id}/registrations",
        headers=parent.headers,
        json={"child_person_ids": [other_child.id]},
    )
    assert resp.status_code == 403


def test_registration_is_idempotent(client: TestClient, db: Session) -> None:
    manager = bootstrap_actor(db)
    org = manager.organization
    parent = _parent_of(db, org)
    child = _child(db, org, parent, "Dete")
    event_id = _event(client, manager)
    headers = {**parent.headers, "Idempotency-Key": "reg-key-1"}
    body = {"child_person_ids": [child.id]}

    first = client.post(f"/events/{event_id}/registrations", headers=headers, json=body)
    second = client.post(f"/events/{event_id}/registrations", headers=headers, json=body)
    assert first.status_code == 201
    assert first.json()[0]["registration_id"] == second.json()[0]["registration_id"]
