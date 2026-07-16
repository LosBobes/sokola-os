from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import bootstrap_actor


def _make_person_in_org(client: TestClient, actor, given: str) -> str:
    resp = client.post(
        "/people", headers=actor.headers, json={"given_name": given, "family_name": "Test"}
    )
    assert resp.status_code == 201
    return resp.json()["id"]


def test_create_group_and_add_members(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group = client.post(
        "/groups", headers=actor.headers, json={"name": "Mlađi pioniri"}
    ).json()

    person_id = _make_person_in_org(client, actor, "Luka")
    added = client.post(
        f"/groups/{group['id']}/members", headers=actor.headers, json={"person_id": person_id}
    )
    assert added.status_code == 201
    assert added.json()["person_id"] == person_id

    members = client.get(f"/groups/{group['id']}/members", headers=actor.headers).json()
    assert [m["person_id"] for m in members] == [person_id]


def test_capacity_is_enforced(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group = client.post(
        "/groups",
        headers=actor.headers,
        json={"name": "Mala grupa", "capacity_mode": "LIMITED", "capacity": 1},
    ).json()

    p1 = _make_person_in_org(client, actor, "Prvi")
    p2 = _make_person_in_org(client, actor, "Drugi")

    assert (
        client.post(
            f"/groups/{group['id']}/members", headers=actor.headers, json={"person_id": p1}
        ).status_code
        == 201
    )
    full = client.post(
        f"/groups/{group['id']}/members", headers=actor.headers, json={"person_id": p2}
    )
    assert full.status_code == 409


def test_cannot_add_person_from_another_org(client: TestClient, db: Session) -> None:
    org_a = bootstrap_actor(db, org_name="Klub A")
    org_b = bootstrap_actor(db, org_name="Klub B")

    outsider_id = _make_person_in_org(client, org_b, "Stranac")
    group = client.post("/groups", headers=org_a.headers, json={"name": "Grupa A"}).json()

    resp = client.post(
        f"/groups/{group['id']}/members",
        headers=org_a.headers,
        json={"person_id": outsider_id},
    )
    assert resp.status_code == 404
