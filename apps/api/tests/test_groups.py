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


def _make_program(client: TestClient, actor, name: str = "Karate") -> str:
    resp = client.post("/programs", headers=actor.headers, json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


def _make_location(client: TestClient, actor, name: str = "Centrala") -> str:
    resp = client.post("/locations", headers=actor.headers, json={"name": name})
    assert resp.status_code == 201
    return resp.json()["id"]


def _add_member(client: TestClient, actor, group_id: str, person_id: str) -> dict:
    resp = client.post(
        f"/groups/{group_id}/members", headers=actor.headers, json={"person_id": person_id}
    )
    assert resp.status_code == 201
    return resp.json()


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


# ---------------------------------------------------------------------------
# M1, pricing (group list price + per-member discount)
# ---------------------------------------------------------------------------


def test_group_pricing_set_at_creation_and_read(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    created = client.post(
        "/groups",
        headers=actor.headers,
        json={"name": "Balet", "base_monthly_price": "2500.00"},
    )
    assert created.status_code == 201
    group = created.json()
    assert group["base_monthly_price"] == "2500.00"

    listed = client.get("/groups", headers=actor.headers).json()
    assert listed["items"][0]["base_monthly_price"] == "2500.00"


def test_group_pricing_set_and_cleared_via_patch(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group = client.post("/groups", headers=actor.headers, json={"name": "Balet"}).json()
    assert group["base_monthly_price"] is None

    updated = client.patch(
        f"/groups/{group['id']}",
        headers=actor.headers,
        json={"base_monthly_price": "3000.00"},
    )
    assert updated.status_code == 200
    assert updated.json()["base_monthly_price"] == "3000.00"

    cleared = client.patch(
        f"/groups/{group['id']}",
        headers=actor.headers,
        json={"base_monthly_price": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["base_monthly_price"] is None


def test_group_pricing_rejects_negative_price(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    resp = client.post(
        "/groups", headers=actor.headers, json={"name": "Balet", "base_monthly_price": "-1.00"}
    )
    assert resp.status_code == 422


def test_membership_discount_set_and_read(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group = client.post("/groups", headers=actor.headers, json={"name": "Balet"}).json()
    person_id = _make_person_in_org(client, actor, "Mina")
    member = _add_member(client, actor, group["id"], person_id)
    assert member["discount"] == "0.00"

    discounted = client.patch(
        f"/groups/{group['id']}/members/{member['membership_id']}/discount",
        headers=actor.headers,
        json={"discount": "50.00"},
    )
    assert discounted.status_code == 200
    assert discounted.json()["discount"] == "50.00"

    members = client.get(f"/groups/{group['id']}/members", headers=actor.headers).json()
    assert members[0]["discount"] == "50.00"


def test_membership_discount_rejects_negative(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group = client.post("/groups", headers=actor.headers, json={"name": "Balet"}).json()
    person_id = _make_person_in_org(client, actor, "Mina")
    member = _add_member(client, actor, group["id"], person_id)

    resp = client.patch(
        f"/groups/{group['id']}/members/{member['membership_id']}/discount",
        headers=actor.headers,
        json={"discount": -100},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# M2, enrollment lifecycle (suspend / resume / end)
# ---------------------------------------------------------------------------


def test_membership_suspend_and_resume(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group = client.post("/groups", headers=actor.headers, json={"name": "Balet"}).json()
    person_id = _make_person_in_org(client, actor, "Mina")
    member = _add_member(client, actor, group["id"], person_id)
    membership_url = f"/groups/{group['id']}/members/{member['membership_id']}"

    suspended = client.post(
        f"{membership_url}/suspend", headers=actor.headers, json={"reason": "Bolest"}
    )
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "SUSPENDED"

    # Suspending an already-suspended membership is a conflict.
    resuspend = client.post(f"{membership_url}/suspend", headers=actor.headers, json={})
    assert resuspend.status_code == 409

    resumed = client.post(f"{membership_url}/resume", headers=actor.headers, json={})
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "ACTIVE"

    # Resuming an already-active membership is a conflict.
    reresume = client.post(f"{membership_url}/resume", headers=actor.headers, json={})
    assert reresume.status_code == 409


def test_membership_end_is_terminal(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group = client.post("/groups", headers=actor.headers, json={"name": "Balet"}).json()
    person_id = _make_person_in_org(client, actor, "Mina")
    member = _add_member(client, actor, group["id"], person_id)
    membership_url = f"/groups/{group['id']}/members/{member['membership_id']}"

    ended = client.post(
        f"{membership_url}/end",
        headers=actor.headers,
        json={"end_reason": "LEFT", "reason": "Preselila se"},
    )
    assert ended.status_code == 200
    body = ended.json()
    assert body["status"] == "ENDED"
    assert body["end_reason"] == "LEFT"
    assert body["ended_at"] is not None

    # Ended is terminal: cannot end/suspend/resume again.
    reend = client.post(
        f"{membership_url}/end", headers=actor.headers, json={"end_reason": "LEFT"}
    )
    assert reend.status_code == 409
    late_suspend = client.post(f"{membership_url}/suspend", headers=actor.headers, json={})
    assert late_suspend.status_code == 409
    late_resume = client.post(f"{membership_url}/resume", headers=actor.headers, json={})
    assert late_resume.status_code == 409

    # Ended memberships drop out of the roster.
    members = client.get(f"/groups/{group['id']}/members", headers=actor.headers).json()
    assert members == []


def test_ended_member_can_rejoin_the_same_group(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group = client.post("/groups", headers=actor.headers, json={"name": "Balet"}).json()
    person_id = _make_person_in_org(client, actor, "Mina")
    member = _add_member(client, actor, group["id"], person_id)

    client.post(
        f"/groups/{group['id']}/members/{member['membership_id']}/end",
        headers=actor.headers,
        json={"end_reason": "SEASON_END"},
    )

    rejoined = client.post(
        f"/groups/{group['id']}/members", headers=actor.headers, json={"person_id": person_id}
    )
    assert rejoined.status_code == 201
    assert rejoined.json()["membership_id"] != member["membership_id"]


def test_membership_lifecycle_rejects_foreign_group_or_membership(
    client: TestClient, db: Session
) -> None:
    org_a = bootstrap_actor(db, org_name="Klub A")
    org_b = bootstrap_actor(db, org_name="Klub B")

    group_a = client.post("/groups", headers=org_a.headers, json={"name": "Grupa A"}).json()
    person_a = _make_person_in_org(client, org_a, "Ana")
    member_a = _add_member(client, org_a, group_a["id"], person_a)

    # org_b cannot act on org_a's group at all.
    resp = client.post(
        f"/groups/{group_a['id']}/members/{member_a['membership_id']}/suspend",
        headers=org_b.headers,
        json={},
    )
    assert resp.status_code == 404

    # org_b has its own group; org_a's membership id inside it is still foreign.
    group_b = client.post("/groups", headers=org_b.headers, json={"name": "Grupa B"}).json()
    resp2 = client.post(
        f"/groups/{group_b['id']}/members/{member_a['membership_id']}/suspend",
        headers=org_b.headers,
        json={},
    )
    assert resp2.status_code == 404


# ---------------------------------------------------------------------------
# M4, program/location link
# ---------------------------------------------------------------------------


def test_group_program_and_location_link_set_and_cleared(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    program_id = _make_program(client, actor)
    location_id = _make_location(client, actor)

    created = client.post(
        "/groups",
        headers=actor.headers,
        json={"name": "Karate junior", "program_id": program_id, "location_id": location_id},
    )
    assert created.status_code == 201
    group = created.json()
    assert group["program_id"] == program_id
    assert group["location_id"] == location_id

    cleared = client.patch(
        f"/groups/{group['id']}",
        headers=actor.headers,
        json={"program_id": None, "location_id": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["program_id"] is None
    assert cleared.json()["location_id"] is None


def test_group_program_link_rejects_foreign_program(client: TestClient, db: Session) -> None:
    org_a = bootstrap_actor(db, org_name="Klub A")
    org_b = bootstrap_actor(db, org_name="Klub B")

    foreign_program_id = _make_program(client, org_b, "Tuđi program")

    resp = client.post(
        "/groups",
        headers=org_a.headers,
        json={"name": "Grupa A", "program_id": foreign_program_id},
    )
    assert resp.status_code == 404


def test_group_location_link_rejects_foreign_location_on_update(
    client: TestClient, db: Session
) -> None:
    org_a = bootstrap_actor(db, org_name="Klub A")
    org_b = bootstrap_actor(db, org_name="Klub B")

    group = client.post("/groups", headers=org_a.headers, json={"name": "Grupa A"}).json()
    foreign_location_id = _make_location(client, org_b, "Tuđi ogranak")

    resp = client.patch(
        f"/groups/{group['id']}",
        headers=org_a.headers,
        json={"location_id": foreign_location_id},
    )
    assert resp.status_code == 404
