from __future__ import annotations

from app.domains.identity.enums import RoleCode
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import Actor, add_membership, assign_role, bootstrap_actor, make_person

SLOT = {"starts_at": "2026-09-05T10:00:00+00:00", "ends_at": "2026-09-05T11:00:00+00:00"}


def _group_with_member(
    client: TestClient, actor: Actor, *, group_name: str = "G", given: str = "Ana"
) -> tuple[str, str]:
    group_id = client.post(
        "/groups", headers=actor.headers, json={"name": group_name}
    ).json()["id"]
    person_id = client.post(
        "/people", headers=actor.headers, json={"given_name": given, "family_name": "T"}
    ).json()["id"]
    client.post(
        f"/groups/{group_id}/members", headers=actor.headers, json={"person_id": person_id}
    )
    return group_id, person_id


def test_create_and_list_progress_note(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id, person_id = _group_with_member(client, actor)

    created = client.post(
        f"/people/{person_id}/progress-notes",
        headers=actor.headers,
        json={
            "group_id": group_id,
            "note": "Great improvement on footwork.",
            "level": "DEVELOPING",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["person_id"] == person_id
    assert body["group_id"] == group_id
    assert body["author_person_id"] == actor.person.id
    assert body["level"] == "DEVELOPING"
    assert body["session_id"] is None

    listed = client.get(f"/people/{person_id}/progress-notes", headers=actor.headers)
    assert listed.status_code == 200
    notes = listed.json()
    assert len(notes) == 1
    assert notes[0]["id"] == body["id"]


def test_list_scoped_to_group(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_a, person_id = _group_with_member(client, actor, group_name="G1")
    group_b = client.post("/groups", headers=actor.headers, json={"name": "G2"}).json()["id"]
    client.post(
        f"/groups/{group_b}/members", headers=actor.headers, json={"person_id": person_id}
    )

    client.post(
        f"/people/{person_id}/progress-notes",
        headers=actor.headers,
        json={"group_id": group_a, "note": "Note in group A"},
    )
    client.post(
        f"/people/{person_id}/progress-notes",
        headers=actor.headers,
        json={"group_id": group_b, "note": "Note in group B"},
    )

    all_notes = client.get(f"/people/{person_id}/progress-notes", headers=actor.headers).json()
    assert len(all_notes) == 2

    scoped = client.get(
        f"/people/{person_id}/progress-notes",
        headers=actor.headers,
        params={"group_id": group_a},
    ).json()
    assert len(scoped) == 1
    assert scoped[0]["group_id"] == group_a


def test_note_requires_active_group_membership(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    _group_id, person_id = _group_with_member(client, actor)
    other_group_id = client.post(
        "/groups", headers=actor.headers, json={"name": "Other"}
    ).json()["id"]

    resp = client.post(
        f"/people/{person_id}/progress-notes",
        headers=actor.headers,
        json={"group_id": other_group_id, "note": "Shouldn't be allowed"},
    )
    assert resp.status_code == 400


def test_trainer_can_write_parent_cannot(client: TestClient, db: Session) -> None:
    manager = bootstrap_actor(db, org_name="Klub")
    group_id, person_id = _group_with_member(client, manager)

    trainer = make_person(db, given="Trener")
    add_membership(db, person=trainer, school=manager.school)
    trainer_assign = assign_role(
        db, person=trainer, school=manager.school, role=RoleCode.TRAINER
    )
    from app.security.auth import DEV_PERSON_HEADER
    from app.security.deps import CONTEXT_HEADER

    trainer_headers = {DEV_PERSON_HEADER: trainer.id, CONTEXT_HEADER: trainer_assign.id}
    ok = client.post(
        f"/people/{person_id}/progress-notes",
        headers=trainer_headers,
        json={"group_id": group_id, "note": "Trainer note"},
    )
    assert ok.status_code == 201
    assert ok.json()["author_person_id"] == trainer.id

    parent = bootstrap_actor(db, org_name="Klub2", role=RoleCode.PARENT, given="Roditelj")
    denied = client.post(
        f"/people/{person_id}/progress-notes",
        headers=parent.headers,
        json={"group_id": group_id, "note": "nope"},
    )
    assert denied.status_code == 403


def test_tenant_isolation(client: TestClient, db: Session) -> None:
    org1 = bootstrap_actor(db, org_name="Org1")
    group_id, person_id = _group_with_member(client, org1)

    org2 = bootstrap_actor(db, org_name="Org2")
    # org2 staff cannot see or write notes about org1's person/group: the
    # person isn't visible in org2's tenant at all.
    resp = client.get(f"/people/{person_id}/progress-notes", headers=org2.headers)
    assert resp.status_code == 404

    resp2 = client.post(
        f"/people/{person_id}/progress-notes",
        headers=org2.headers,
        json={"group_id": group_id, "note": "cross-tenant"},
    )
    assert resp2.status_code == 404


def test_attendance_save_can_include_progress_note(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id, person_id = _group_with_member(client, actor)
    session_id = client.post(
        "/schedule/sessions", headers=actor.headers, json={"group_id": group_id, **SLOT}
    ).json()["id"]

    saved = client.put(
        f"/schedule/sessions/{session_id}/attendance",
        headers=actor.headers,
        json={
            "attendance_version": 0,
            "exceptions": [],
            "progress_notes": [
                {"person_id": person_id, "note": "Worked hard today.", "level": "PROFICIENT"}
            ],
        },
    )
    assert saved.status_code == 200
    assert saved.json()["progress_notes_saved"] == 1

    notes = client.get(f"/people/{person_id}/progress-notes", headers=actor.headers).json()
    assert len(notes) == 1
    assert notes[0]["session_id"] == session_id
    assert notes[0]["group_id"] == group_id
    assert notes[0]["level"] == "PROFICIENT"


def test_attendance_save_rejects_note_for_non_roster_person(
    client: TestClient, db: Session
) -> None:
    actor = bootstrap_actor(db)
    group_id, _person_id = _group_with_member(client, actor)
    session_id = client.post(
        "/schedule/sessions", headers=actor.headers, json={"group_id": group_id, **SLOT}
    ).json()["id"]
    outsider_id = client.post(
        "/people", headers=actor.headers, json={"given_name": "Van", "family_name": "Spiska"}
    ).json()["id"]

    resp = client.put(
        f"/schedule/sessions/{session_id}/attendance",
        headers=actor.headers,
        json={
            "attendance_version": 0,
            "exceptions": [],
            "progress_notes": [{"person_id": outsider_id, "note": "nope"}],
        },
    )
    assert resp.status_code == 400
