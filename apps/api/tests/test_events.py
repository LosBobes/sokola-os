from __future__ import annotations

import datetime as dt

from app.domains.events.enums import RegistrationStatus
from app.domains.events.models import EventRegistration
from app.domains.identity.enums import RoleCode
from app.domains.identity.models import Person
from app.domains.school.models import School
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from tests.factories import Actor, add_actor, bootstrap_actor, make_child_with_guardian

EVENT = {"title": "Zimski kamp", "starts_at": "2026-12-20T09:00:00+00:00"}


def _event(client: TestClient, staff: Actor, **overrides: object) -> str:
    return client.post("/events", headers=staff.headers, json={**EVENT, **overrides}).json()["id"]


def _parent_of(db: Session, org: School, given: str = "R") -> Actor:
    return add_actor(db, school=org, role=RoleCode.PARENT, given=given)


def _child(db: Session, org: School, guardian: Actor, given: str) -> Person:
    return make_child_with_guardian(db, school=org, guardian=guardian.person, given=given)


def test_register_and_cancel_children_journeys_3_and_4(client: TestClient, db: Session) -> None:
    manager = bootstrap_actor(db)
    org = manager.school
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
    org = manager.school
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
    org = manager.school
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
    org = manager.school
    parent = _parent_of(db, org)
    child = _child(db, org, parent, "Dete")
    event_id = _event(client, manager)
    headers = {**parent.headers, "Idempotency-Key": "reg-key-1"}
    body = {"child_person_ids": [child.id]}

    first = client.post(f"/events/{event_id}/registrations", headers=headers, json=body)
    second = client.post(f"/events/{event_id}/registrations", headers=headers, json=body)
    assert first.status_code == 201
    assert first.json()[0]["registration_id"] == second.json()[0]["registration_id"]


def test_capacity_boundary_rejects_the_registration_over_the_limit(
    client: TestClient, db: Session
) -> None:
    """P1: once capacity is reached one at a time, the N+1th registration is
    rejected, not just the batch-overflow case."""
    manager = bootstrap_actor(db)
    org = manager.school
    parent = _parent_of(db, org)
    c1 = _child(db, org, parent, "Prvi")
    c2 = _child(db, org, parent, "Drugi")
    event_id = _event(client, manager, capacity_mode="LIMITED", capacity=1)

    first = client.post(
        f"/events/{event_id}/registrations",
        headers=parent.headers,
        json={"child_person_ids": [c1.id]},
    )
    assert first.status_code == 201

    over = client.post(
        f"/events/{event_id}/registrations",
        headers=parent.headers,
        json={"child_person_ids": [c2.id]},
    )
    assert over.status_code == 409
    assert over.json()["error"]["details"]["code"] == "EVENT_FULL"


# ---------------------------------------------------------------------------
# M1, event lifecycle edges: edit and whole-event cancel
# ---------------------------------------------------------------------------


def test_update_event_happy_path(client: TestClient, db: Session) -> None:
    manager = bootstrap_actor(db)
    event_id = _event(client, manager)

    resp = client.patch(
        f"/events/{event_id}",
        headers=manager.headers,
        json={
            "title": "Prolećni kamp",
            "starts_at": "2027-01-15T10:00:00+00:00",
            "capacity_mode": "LIMITED",
            "capacity": 20,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Prolećni kamp"
    assert dt.datetime.fromisoformat(body["starts_at"]) == dt.datetime(
        2027, 1, 15, 10, 0, tzinfo=dt.UTC
    )
    assert body["capacity_mode"] == "LIMITED"
    assert body["capacity"] == 20


def test_update_event_rejects_cancelled_event(client: TestClient, db: Session) -> None:
    manager = bootstrap_actor(db)
    event_id = _event(client, manager)

    cancelled = client.post(f"/events/{event_id}/cancel", headers=manager.headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"

    resp = client.patch(
        f"/events/{event_id}", headers=manager.headers, json={"title": "Novi naziv"}
    )
    assert resp.status_code == 409


def test_update_event_rejects_past_event(client: TestClient, db: Session) -> None:
    manager = bootstrap_actor(db)
    event_id = _event(client, manager, starts_at="2020-01-01T09:00:00+00:00")

    resp = client.patch(
        f"/events/{event_id}", headers=manager.headers, json={"title": "Novi naziv"}
    )
    assert resp.status_code == 409


def test_update_event_rejects_capacity_below_active_registrations(
    client: TestClient, db: Session
) -> None:
    manager = bootstrap_actor(db)
    org = manager.school
    parent = _parent_of(db, org)
    c1 = _child(db, org, parent, "Prvi")
    c2 = _child(db, org, parent, "Drugi")
    event_id = _event(client, manager, capacity_mode="LIMITED", capacity=5)
    reg = client.post(
        f"/events/{event_id}/registrations",
        headers=parent.headers,
        json={"child_person_ids": [c1.id, c2.id]},
    )
    assert reg.status_code == 201

    resp = client.patch(
        f"/events/{event_id}", headers=manager.headers, json={"capacity": 1}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["code"] == "CAPACITY_BELOW_REGISTERED"


def test_cancel_event_cascades_all_active_registrations_atomically(
    client: TestClient, db: Session
) -> None:
    manager = bootstrap_actor(db)
    org = manager.school
    parent = _parent_of(db, org)
    c1 = _child(db, org, parent, "Prvi")
    c2 = _child(db, org, parent, "Drugi")
    event_id = _event(client, manager)
    reg = client.post(
        f"/events/{event_id}/registrations",
        headers=parent.headers,
        json={"child_person_ids": [c1.id, c2.id]},
    )
    registration_ids = {r["registration_id"] for r in reg.json()}

    resp = client.post(f"/events/{event_id}/cancel", headers=manager.headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"

    stmt = select(EventRegistration).where(EventRegistration.event_id == event_id)
    registrations = db.execute(stmt).scalars().all()
    assert {r.id for r in registrations} == registration_ids
    assert {r.status for r in registrations} == {RegistrationStatus.CANCELLED}
    assert {r.cancellation_reason for r in registrations} == {"ORGANIZER"}

    # The event dropped out of the published list.
    listed = client.get("/events", headers=manager.headers)
    assert event_id not in {e["id"] for e in listed.json()}


def test_cancel_event_rejects_when_already_cancelled(client: TestClient, db: Session) -> None:
    manager = bootstrap_actor(db)
    event_id = _event(client, manager)

    first = client.post(f"/events/{event_id}/cancel", headers=manager.headers)
    assert first.status_code == 200

    second = client.post(f"/events/{event_id}/cancel", headers=manager.headers)
    assert second.status_code == 409


def test_event_edit_and_cancel_reject_foreign_school(
    client: TestClient, db: Session
) -> None:
    org_a = bootstrap_actor(db, org_name="Klub A")
    org_b = bootstrap_actor(db, org_name="Klub B")
    event_id = _event(client, org_a)

    edit = client.patch(
        f"/events/{event_id}", headers=org_b.headers, json={"title": "Tuđi naziv"}
    )
    assert edit.status_code == 404

    cancel = client.post(f"/events/{event_id}/cancel", headers=org_b.headers)
    assert cancel.status_code == 404
