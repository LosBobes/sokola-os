"""Participants and staff are different things, everywhere they meet.

The rules under test:
  * only a group member with role MEMBER is rostered for attendance,
  * only a MEMBER is billed by a membership run,
  * staff never consume a limited group's places,
  * the school's "aktivni članovi" figure counts PARTICIPANT memberships only.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import Actor, bootstrap_actor


def _person(client: TestClient, actor: Actor, given: str, member_type: str) -> str:
    response = client.post(
        "/people",
        headers=actor.headers,
        json={"given_name": given, "family_name": "T", "member_type": member_type},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _session_for(client: TestClient, actor: Actor, group_id: str) -> str:
    response = client.post(
        "/schedule/sessions",
        headers=actor.headers,
        json={
            "group_id": group_id,
            "starts_at": "2026-09-01T15:00:00Z",
            "ends_at": "2026-09-01T16:00:00Z",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_attendance_roster_excludes_group_staff(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = client.post("/groups", headers=actor.headers, json={"name": "G"}).json()["id"]

    child = _person(client, actor, "Polaznik", "PARTICIPANT")
    coach = _person(client, actor, "Trener", "STAFF")
    client.post(
        f"/groups/{group_id}/members", headers=actor.headers, json={"person_id": child}
    )
    client.post(
        f"/groups/{group_id}/members",
        headers=actor.headers,
        json={"person_id": coach, "role": "TRAINER"},
    )

    session_id = _session_for(client, actor, group_id)
    sheet = client.get(
        f"/schedule/sessions/{session_id}/attendance", headers=actor.headers
    ).json()

    assert [entry["person_id"] for entry in sheet["entries"]] == [child]


def test_billing_run_charges_participants_only(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = client.post("/groups", headers=actor.headers, json={"name": "G"}).json()["id"]

    child = _person(client, actor, "Polaznik", "PARTICIPANT")
    coach = _person(client, actor, "Trener", "STAFF")
    client.post(
        f"/groups/{group_id}/members", headers=actor.headers, json={"person_id": child}
    )
    client.post(
        f"/groups/{group_id}/members",
        headers=actor.headers,
        json={"person_id": coach, "role": "TRAINER"},
    )

    preview = client.post(
        "/billing/runs/preview",
        headers=actor.headers,
        json={
            "group_id": group_id,
            "amount": "3000.00",
            "description": "Članarina",
            "period_label": "2026-09",
        },
    ).json()

    assert [item["person_id"] for item in preview["items"]] == [child]
    assert preview["total"] == "3000.00"


def test_staff_do_not_fill_a_limited_group(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = client.post(
        "/groups",
        headers=actor.headers,
        json={"name": "G", "capacity_mode": "LIMITED", "capacity": 1},
    ).json()["id"]

    child = _person(client, actor, "Polaznik", "PARTICIPANT")
    coach = _person(client, actor, "Trener", "STAFF")
    assistant = _person(client, actor, "Asistent", "STAFF")
    second_child = _person(client, actor, "Drugi", "PARTICIPANT")

    assert (
        client.post(
            f"/groups/{group_id}/members", headers=actor.headers, json={"person_id": child}
        ).status_code
        == 201
    )
    # The single place is taken, but staff are not participants.
    for person_id, role in ((coach, "TRAINER"), (assistant, "ASSISTANT")):
        assert (
            client.post(
                f"/groups/{group_id}/members",
                headers=actor.headers,
                json={"person_id": person_id, "role": role},
            ).status_code
            == 201
        )
    # A second participant, however, does not fit.
    assert (
        client.post(
            f"/groups/{group_id}/members",
            headers=actor.headers,
            json={"person_id": second_child},
        ).status_code
        == 409
    )


def test_member_role_can_be_corrected_and_moves_the_roster(
    client: TestClient, db: Session
) -> None:
    actor = bootstrap_actor(db)
    group_id = client.post("/groups", headers=actor.headers, json={"name": "G"}).json()["id"]
    person_id = _person(client, actor, "Neko", "PARTICIPANT")
    membership_id = client.post(
        f"/groups/{group_id}/members", headers=actor.headers, json={"person_id": person_id}
    ).json()["membership_id"]
    session_id = _session_for(client, actor, group_id)

    before = client.get(
        f"/schedule/sessions/{session_id}/attendance", headers=actor.headers
    ).json()
    assert len(before["entries"]) == 1

    changed = client.patch(
        f"/groups/{group_id}/members/{membership_id}/role",
        headers=actor.headers,
        json={"role": "ASSISTANT"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["role"] == "ASSISTANT"

    after = client.get(
        f"/schedule/sessions/{session_id}/attendance", headers=actor.headers
    ).json()
    assert after["entries"] == []


def test_active_member_count_ignores_staff_and_guardians(
    client: TestClient, db: Session
) -> None:
    actor = bootstrap_actor(db)
    _person(client, actor, "Polaznik", "PARTICIPANT")
    _person(client, actor, "Trener", "STAFF")
    _person(client, actor, "Roditelj", "GUARDIAN")
    _person(client, actor, "Kontakt", "CONTACT")

    overview = client.get("/reports/overview", headers=actor.headers)
    assert overview.status_code == 200, overview.text
    # The bootstrapped actor's own membership is seeded PARTICIPANT by the test
    # factory, so the school has exactly two participants: them and the child.
    assert overview.json()["active_member_count"] == 2


def test_people_can_be_listed_by_member_type(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    _person(client, actor, "Polaznik", "PARTICIPANT")
    coach = _person(client, actor, "Trener", "STAFF")

    staff = client.get("/people?member_type=STAFF", headers=actor.headers).json()
    assert [item["id"] for item in staff["items"]] == [coach]
    assert staff["total"] == 1
