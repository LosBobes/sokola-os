from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import Actor, bootstrap_actor


def _group_with_members(client: TestClient, actor: Actor, count: int) -> str:
    group_id = client.post("/groups", headers=actor.headers, json={"name": "G"}).json()["id"]
    for i in range(count):
        pid = client.post(
            "/people", headers=actor.headers, json={"given_name": f"P{i}", "family_name": "L"}
        ).json()["id"]
        client.post(
            f"/groups/{group_id}/members", headers=actor.headers, json={"person_id": pid}
        )
    return group_id


def test_publish_announcement_journey7(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group_with_members(client, actor, 2)
    draft = {
        "title": "Trening otkazan",
        "body": "Sutrašnji trening je otkazan.",
        "target_type": "GROUP",
        "target_group_id": group_id,
    }

    preview = client.post(
        "/communications/announcements/preview", headers=actor.headers, json=draft
    ).json()
    assert preview["recipient_count"] == 2

    published = client.post(
        "/communications/announcements",
        headers=actor.headers,
        json={**draft, "snapshot_hash": preview["snapshot_hash"]},
    )
    assert published.status_code == 201
    assert published.json()["recipient_count"] == 2


def test_stale_snapshot_is_refused(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group_with_members(client, actor, 2)
    draft = {
        "title": "Obaveštenje",
        "body": "Tekst.",
        "target_type": "GROUP",
        "target_group_id": group_id,
    }
    preview = client.post(
        "/communications/announcements/preview", headers=actor.headers, json=draft
    ).json()

    # Recipient set changes after preview.
    new_pid = client.post(
        "/people", headers=actor.headers, json={"given_name": "Novi", "family_name": "L"}
    ).json()["id"]
    client.post(f"/groups/{group_id}/members", headers=actor.headers, json={"person_id": new_pid})

    stale = client.post(
        "/communications/announcements",
        headers=actor.headers,
        json={**draft, "snapshot_hash": preview["snapshot_hash"]},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["details"]["code"] == "SNAPSHOT_STALE"
