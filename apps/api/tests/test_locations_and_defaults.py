"""Locations are the general concept, and a group is the default source for
who leads a session and where it happens."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import Actor, bootstrap_actor


def _location(client: TestClient, actor: Actor, name: str, kind: str = "OTHER") -> str:
    response = client.post(
        "/locations", headers=actor.headers, json={"name": name, "kind": kind}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _staff_person(client: TestClient, actor: Actor, given: str) -> str:
    return client.post(
        "/people",
        headers=actor.headers,
        json={"given_name": given, "family_name": "T", "member_type": "STAFF"},
    ).json()["id"]


def test_location_carries_a_kind_and_defaults_to_other(
    client: TestClient, db: Session
) -> None:
    actor = bootstrap_actor(db)
    theatre = _location(client, actor, "Pozorište", "THEATRE")
    plain = _location(client, actor, "Bez vrste")

    listed = {item["id"]: item["kind"] for item in
              client.get("/locations", headers=actor.headers).json()["items"]}
    assert listed[theatre] == "THEATRE"
    # Never guessed as a hall: the old model had no kind to infer one from.
    assert listed[plain] == "OTHER"

    updated = client.patch(
        f"/locations/{theatre}", headers=actor.headers, json={"kind": "ONLINE"}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["kind"] == "ONLINE"


def test_new_session_inherits_the_group_defaults(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    coach = _staff_person(client, actor, "Trener")
    hall = _location(client, actor, "Sala 1", "SPORTS_HALL")
    group_id = client.post(
        "/groups",
        headers=actor.headers,
        json={
            "name": "G",
            "default_trainer_person_id": coach,
            "default_location_id": hall,
        },
    ).json()["id"]

    created = client.post(
        "/schedule/sessions",
        headers=actor.headers,
        json={
            "group_id": group_id,
            "starts_at": "2026-09-01T15:00:00Z",
            "ends_at": "2026-09-01T16:00:00Z",
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["trainer_person_id"] == coach
    assert created.json()["location_id"] == hall


def test_a_single_session_may_override_the_group_defaults(
    client: TestClient, db: Session
) -> None:
    actor = bootstrap_actor(db)
    coach = _staff_person(client, actor, "Trener")
    stand_in = _staff_person(client, actor, "Zamena")
    hall = _location(client, actor, "Sala 1", "SPORTS_HALL")
    pitch = _location(client, actor, "Teren", "FIELD")
    group_id = client.post(
        "/groups",
        headers=actor.headers,
        json={
            "name": "G",
            "default_trainer_person_id": coach,
            "default_location_id": hall,
        },
    ).json()["id"]

    created = client.post(
        "/schedule/sessions",
        headers=actor.headers,
        json={
            "group_id": group_id,
            "starts_at": "2026-09-02T15:00:00Z",
            "ends_at": "2026-09-02T16:00:00Z",
            "trainer_person_id": stand_in,
            "location_id": pitch,
        },
    ).json()
    assert created["trainer_person_id"] == stand_in
    assert created["location_id"] == pitch

    # The group's own defaults are untouched by that one-off override.
    group = next(
        g for g in client.get("/groups", headers=actor.headers).json()["items"]
        if g["id"] == group_id
    )
    assert group["default_trainer_person_id"] == coach
    assert group["default_location_id"] == hall


def test_explicit_null_means_deliberately_unassigned(
    client: TestClient, db: Session
) -> None:
    actor = bootstrap_actor(db)
    coach = _staff_person(client, actor, "Trener")
    group_id = client.post(
        "/groups",
        headers=actor.headers,
        json={"name": "G", "default_trainer_person_id": coach},
    ).json()["id"]

    created = client.post(
        "/schedule/sessions",
        headers=actor.headers,
        json={
            "group_id": group_id,
            "starts_at": "2026-09-03T15:00:00Z",
            "ends_at": "2026-09-03T16:00:00Z",
            "trainer_person_id": None,
        },
    ).json()
    assert created["trainer_person_id"] is None


def test_a_foreign_location_is_never_accepted(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    other = bootstrap_actor(db, org_name="Druga škola", given="Druga")
    foreign_location = _location(client, other, "Tuđa sala", "SPORTS_HALL")
    group_id = client.post("/groups", headers=actor.headers, json={"name": "G"}).json()["id"]

    refused = client.post(
        "/schedule/sessions",
        headers=actor.headers,
        json={
            "group_id": group_id,
            "starts_at": "2026-09-04T15:00:00Z",
            "ends_at": "2026-09-04T16:00:00Z",
            "location_id": foreign_location,
        },
    )
    assert refused.status_code == 404


def test_series_occurrences_inherit_the_series_location(
    client: TestClient, db: Session
) -> None:
    actor = bootstrap_actor(db)
    hall = _location(client, actor, "Sala 1", "SPORTS_HALL")
    group_id = client.post(
        "/groups", headers=actor.headers, json={"name": "G", "default_location_id": hall}
    ).json()["id"]

    series = client.post(
        "/schedule/series",
        headers=actor.headers,
        json={
            "group_id": group_id,
            "title": "Sreda 18:00",
            "weekdays": [2],
            "start_date": "2026-09-02",
            "local_time": "18:00:00",
            "duration_minutes": 60,
        },
    )
    assert series.status_code == 201, series.text
    assert series.json()["location_id"] == hall

    generated = client.post(
        f"/schedule/series/{series.json()['id']}/generate",
        headers=actor.headers,
        json={"from_date": "2026-09-01", "weeks": 3},
    )
    assert generated.status_code == 200, generated.text
    assert generated.json()["created_count"] >= 1

    sessions = client.get(
        "/schedule/sessions",
        headers=actor.headers,
        params={"date_from": "2026-09-01T00:00:00Z", "date_to": "2026-10-01T00:00:00Z"},
    ).json()
    assert sessions
    assert all(s["location_id"] == hall for s in sessions)
