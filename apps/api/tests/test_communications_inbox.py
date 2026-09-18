"""Event-driven notifications + in-app inbox (PRD 08 M1-M3): outbox events from
scheduling/billing/events produce Notification rows for the right people, the
inbox is scoped to the caller alone, and marking read works."""

from __future__ import annotations

import app.handlers  # noqa: F401  (registers outbox handlers on import)
import pytest
from app.domains.identity.enums import RoleCode
from app.platform.outbox import worker as outbox_worker
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import (
    Actor,
    add_actor,
    add_membership,
    assign_role,
    bootstrap_actor,
    make_child_with_guardian,
    make_person,
)

SESSION_DRAFT = {
    "starts_at": "2026-09-01T17:00:00+00:00",
    "ends_at": "2026-09-01T18:00:00+00:00",
}


@pytest.fixture(autouse=True)
def _handlers_registered() -> None:
    # Defensive: guarantees the communications outbox handlers are bound even
    # if another test module cleared the global handler registry.
    app.handlers.register_all()


def _drain_outbox() -> None:
    while outbox_worker.process_available("test-worker", batch_size=50):
        pass


def _group(client: TestClient, staff: Actor, name: str = "G") -> str:
    return client.post("/groups", headers=staff.headers, json={"name": name}).json()["id"]


def _add_member(client: TestClient, staff: Actor, group_id: str, person_id: str) -> None:
    resp = client.post(
        f"/groups/{group_id}/members", headers=staff.headers, json={"person_id": person_id}
    )
    assert resp.status_code == 201, resp.text


def _schedule_session(client: TestClient, staff: Actor, group_id: str) -> str:
    resp = client.post(
        "/schedule/sessions", headers=staff.headers, json={"group_id": group_id, **SESSION_DRAFT}
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


def test_session_cancelled_notifies_group_members_and_guardians(
    client: TestClient, db: Session
) -> None:
    staff = bootstrap_actor(db)
    org = staff.school
    member = add_actor(db, school=org, role=RoleCode.STUDENT, given="Marko")
    guardian = add_actor(db, school=org, role=RoleCode.PARENT, given="Roditelj")
    child = make_child_with_guardian(db, school=org, guardian=guardian.person, given="Dete")

    group_id = _group(client, staff)
    _add_member(client, staff, group_id, member.person.id)
    _add_member(client, staff, group_id, child.id)
    session_id = _schedule_session(client, staff, group_id)

    cancelled = client.post(
        f"/schedule/sessions/{session_id}/cancel",
        headers=staff.headers,
        json={"reason": "WEATHER", "note": "Padavine"},
    )
    assert cancelled.status_code == 200
    _drain_outbox()

    member_inbox = client.get("/communications/inbox", headers=member.headers).json()
    assert member_inbox["total"] == 1
    item = member_inbox["items"][0]
    assert item["event_type"] == "session.cancelled"
    assert item["entity_type"] == "session"
    assert item["entity_id"] == session_id
    assert item["delivery_status"] == "DELIVERED"
    assert item["read_at"] is None

    # The guardian is notified on the child's behalf even though the child
    # itself has no login.
    guardian_inbox = client.get("/communications/inbox", headers=guardian.headers).json()
    assert guardian_inbox["total"] == 1
    assert guardian_inbox["items"][0]["entity_id"] == session_id

    # Staff never joined the group, so they get nothing from this event.
    staff_inbox = client.get("/communications/inbox", headers=staff.headers).json()
    assert staff_inbox["total"] == 0


def test_session_reactivated_notifies_group(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    member = add_actor(db, school=staff.school, role=RoleCode.STUDENT)
    group_id = _group(client, staff)
    _add_member(client, staff, group_id, member.person.id)
    session_id = _schedule_session(client, staff, group_id)

    client.post(
        f"/schedule/sessions/{session_id}/cancel", headers=staff.headers, json={"reason": "OTHER"}
    )
    client.post(f"/schedule/sessions/{session_id}/reactivate", headers=staff.headers)
    _drain_outbox()

    events = {
        item["event_type"]
        for item in client.get("/communications/inbox", headers=member.headers).json()["items"]
    }
    assert events == {"session.cancelled", "session.reactivated"}


def test_billing_run_posted_notifies_charged_person_and_guardian(
    client: TestClient, db: Session
) -> None:
    staff = bootstrap_actor(db)
    org = staff.school
    member = add_actor(db, school=org, role=RoleCode.STUDENT, given="Marko")
    guardian = add_actor(db, school=org, role=RoleCode.PARENT, given="Roditelj")
    child = make_child_with_guardian(db, school=org, guardian=guardian.person, given="Dete")

    group_id = _group(client, staff)
    _add_member(client, staff, group_id, member.person.id)
    _add_member(client, staff, group_id, child.id)

    run_body = {
        "group_id": group_id,
        "amount": 100000,
        "description": "Članarina",
        "period_label": "2026-09",
    }
    preview = client.post("/billing/runs/preview", headers=staff.headers, json=run_body).json()
    posted = client.post(
        "/billing/runs",
        headers=staff.headers,
        json={**run_body, "preview_hash": preview["preview_hash"]},
    )
    assert posted.status_code == 201
    _drain_outbox()

    member_inbox = client.get("/communications/inbox", headers=member.headers).json()
    assert member_inbox["total"] == 1
    assert member_inbox["items"][0]["event_type"] == "billing_run.posted"

    guardian_inbox = client.get("/communications/inbox", headers=guardian.headers).json()
    assert guardian_inbox["total"] == 1
    assert guardian_inbox["items"][0]["event_type"] == "billing_run.posted"


def test_event_registration_notifies_registrant_once(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    org = staff.school
    parent = add_actor(db, school=org, role=RoleCode.PARENT, given="Roditelj")
    child = make_child_with_guardian(db, school=org, guardian=parent.person, given="Dete")

    event_id = client.post(
        "/events",
        headers=staff.headers,
        json={"title": "Zimski kamp", "starts_at": "2026-12-20T09:00:00+00:00"},
    ).json()["id"]

    reg = client.post(
        f"/events/{event_id}/registrations",
        headers=parent.headers,
        json={"child_person_ids": [child.id]},
    )
    assert reg.status_code == 201
    _drain_outbox()

    # The parent is both the registrant and the child's guardian, but the
    # recipient set is deduplicated, exactly one notification, not two.
    parent_inbox = client.get("/communications/inbox", headers=parent.headers).json()
    assert parent_inbox["total"] == 1
    assert parent_inbox["items"][0]["event_type"] == "event.registered"
    assert parent_inbox["items"][0]["entity_id"] == event_id


def test_inbox_scoped_to_caller_only(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    member_a = add_actor(db, school=staff.school, role=RoleCode.STUDENT, given="A")
    member_b = add_actor(db, school=staff.school, role=RoleCode.STUDENT, given="B")
    group_id = _group(client, staff)
    _add_member(client, staff, group_id, member_a.person.id)
    session_id = _schedule_session(client, staff, group_id)
    client.post(
        f"/schedule/sessions/{session_id}/cancel", headers=staff.headers, json={"reason": "OTHER"}
    )
    _drain_outbox()

    assert client.get("/communications/inbox", headers=member_a.headers).json()["total"] == 1
    # member_b was never in the group, so their inbox stays empty.
    assert client.get("/communications/inbox", headers=member_b.headers).json()["total"] == 0


def test_mark_read_is_idempotent_and_scoped(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    member = add_actor(db, school=staff.school, role=RoleCode.STUDENT)
    other = add_actor(db, school=staff.school, role=RoleCode.STUDENT, given="Other")
    group_id = _group(client, staff)
    _add_member(client, staff, group_id, member.person.id)
    session_id = _schedule_session(client, staff, group_id)
    client.post(
        f"/schedule/sessions/{session_id}/cancel", headers=staff.headers, json={"reason": "OTHER"}
    )
    _drain_outbox()

    notif_id = client.get("/communications/inbox", headers=member.headers).json()["items"][0]["id"]

    read_once = client.post(f"/communications/inbox/{notif_id}/read", headers=member.headers)
    assert read_once.status_code == 200
    assert read_once.json()["read_at"] is not None

    # Idempotent: reading again is a no-op, not an error.
    read_twice = client.post(f"/communications/inbox/{notif_id}/read", headers=member.headers)
    assert read_twice.status_code == 200
    assert read_twice.json()["read_at"] == read_once.json()["read_at"]

    # Another person in the same org cannot reach someone else's notification.
    forbidden = client.post(f"/communications/inbox/{notif_id}/read", headers=other.headers)
    assert forbidden.status_code == 404


def test_inbox_is_tenant_isolated(client: TestClient, db: Session) -> None:
    """The same person can hold role assignments in two schools; a
    notification from org 1 must never surface under the org 2 context."""
    staff1 = bootstrap_actor(db, org_name="Klub 1")
    staff2 = bootstrap_actor(db, org_name="Klub 2")

    person = make_person(db, given="Dvostruki")
    add_membership(db, person=person, school=staff1.school)
    assignment1 = assign_role(
        db, person=person, school=staff1.school, role=RoleCode.STUDENT
    )
    add_membership(db, person=person, school=staff2.school)
    assignment2 = assign_role(
        db, person=person, school=staff2.school, role=RoleCode.STUDENT
    )
    actor_org1 = Actor(person=person, school=staff1.school, assignment=assignment1)
    actor_org2 = Actor(person=person, school=staff2.school, assignment=assignment2)

    group_id = _group(client, staff1)
    _add_member(client, staff1, group_id, person.id)
    session_id = _schedule_session(client, staff1, group_id)
    client.post(
        f"/schedule/sessions/{session_id}/cancel", headers=staff1.headers, json={"reason": "OTHER"}
    )
    _drain_outbox()

    assert client.get("/communications/inbox", headers=actor_org1.headers).json()["total"] == 1
    assert client.get("/communications/inbox", headers=actor_org2.headers).json()["total"] == 0
