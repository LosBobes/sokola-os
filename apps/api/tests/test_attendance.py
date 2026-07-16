from __future__ import annotations

from app.domains.identity.enums import RoleCode
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import Actor, add_membership, assign_role, bootstrap_actor, make_person

SLOT = {"starts_at": "2026-09-05T10:00:00+00:00", "ends_at": "2026-09-05T11:00:00+00:00"}


def _session_with_two_members(client: TestClient, actor: Actor) -> tuple[str, str, str]:
    group_id = client.post("/groups", headers=actor.headers, json={"name": "G"}).json()["id"]
    ids = []
    for name in ("Ana", "Bane"):
        pid = client.post(
            "/people", headers=actor.headers, json={"given_name": name, "family_name": "T"}
        ).json()["id"]
        client.post(
            f"/groups/{group_id}/members", headers=actor.headers, json={"person_id": pid}
        )
        ids.append(pid)
    session_id = client.post(
        "/schedule/sessions", headers=actor.headers, json={"group_id": group_id, **SLOT}
    ).json()["id"]
    return session_id, ids[0], ids[1]


def test_record_attendance_journey2(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    session_id, ana, _bane = _session_with_two_members(client, actor)

    sheet = client.get(
        f"/schedule/sessions/{session_id}/attendance", headers=actor.headers
    ).json()
    assert sheet["attendance_version"] == 0
    assert {e["status"] for e in sheet["entries"]} == {"PRESENT"}
    assert len(sheet["entries"]) == 2

    # Send only the exception; everyone else stays PRESENT.
    saved = client.put(
        f"/schedule/sessions/{session_id}/attendance",
        headers=actor.headers,
        json={"attendance_version": 0, "exceptions": [{"person_id": ana, "status": "ABSENT"}]},
    )
    assert saved.status_code == 200
    body = saved.json()
    assert body["attendance_version"] == 1
    assert body["present"] == 1 and body["absent"] == 1

    reloaded = client.get(
        f"/schedule/sessions/{session_id}/attendance", headers=actor.headers
    ).json()
    statuses = {e["person_id"]: e["status"] for e in reloaded["entries"]}
    assert statuses[ana] == "ABSENT"


def test_stale_version_is_rejected(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    session_id, ana, _ = _session_with_two_members(client, actor)

    client.put(
        f"/schedule/sessions/{session_id}/attendance",
        headers=actor.headers,
        json={"attendance_version": 0, "exceptions": []},
    )
    # Second save still claims version 0 → conflict, never a silent overwrite.
    stale = client.put(
        f"/schedule/sessions/{session_id}/attendance",
        headers=actor.headers,
        json={"attendance_version": 0, "exceptions": [{"person_id": ana, "status": "LATE"}]},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"


def test_trainer_can_record_parent_cannot(client: TestClient, db: Session) -> None:
    manager = bootstrap_actor(db, org_name="Klub")
    session_id, _, _ = _session_with_two_members(client, manager)

    # A trainer in the same org may record.
    trainer = make_person(db, given="Trener")
    add_membership(db, person=trainer, organization=manager.organization)
    trainer_assign = assign_role(
        db, person=trainer, organization=manager.organization, role=RoleCode.TRAINER
    )
    from app.security.auth import DEV_PERSON_HEADER
    from app.security.deps import CONTEXT_HEADER

    trainer_headers = {DEV_PERSON_HEADER: trainer.id, CONTEXT_HEADER: trainer_assign.id}
    ok = client.put(
        f"/schedule/sessions/{session_id}/attendance",
        headers=trainer_headers,
        json={"attendance_version": 0, "exceptions": []},
    )
    assert ok.status_code == 200

    # A parent may not.
    parent = bootstrap_actor(db, org_name="Klub2", role=RoleCode.PARENT, given="Roditelj")
    denied = client.get(
        f"/schedule/sessions/{session_id}/attendance", headers=parent.headers
    )
    assert denied.status_code == 403
