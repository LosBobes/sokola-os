"""Events carry enough detail to sit on the shared Raspored calendar, and the
staff feed shows the ones a planner needs to see, not only published ones."""

from __future__ import annotations

from app.domains.identity.enums import RoleCode
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import Actor, add_actor, bootstrap_actor

WINDOW = {"date_from": "2026-07-01T00:00:00Z", "date_to": "2026-08-01T00:00:00Z"}


def _location(client: TestClient, actor: Actor, name: str, kind: str) -> str:
    return client.post(
        "/locations", headers=actor.headers, json={"name": name, "kind": kind}
    ).json()["id"]


def test_an_event_carries_where_who_and_what(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    resort = _location(client, actor, "Zlatibor", "OUTDOOR")
    lead = client.post(
        "/people",
        headers=actor.headers,
        json={"given_name": "Vođa", "family_name": "Puta", "member_type": "STAFF"},
    ).json()["id"]

    created = client.post(
        "/events",
        headers=actor.headers,
        json={
            "title": "Letnji fudbalski kamp 2026",
            "type": "TRAINING_CAMP",
            "starts_at": "2026-07-10T08:00:00Z",
            "ends_at": "2026-07-17T18:00:00Z",
            "location_id": resort,
            "location_note": "Zlatibor — hotel „X“, teren „Y“",
            "responsible_person_id": lead,
            "description": "Sedmodnevni kamp za sve uzraste.",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["type"] == "TRAINING_CAMP"
    assert body["location_id"] == resort
    # One structured place plus the detail a single row cannot hold.
    assert body["location_note"] == "Zlatibor — hotel „X“, teren „Y“"
    assert body["responsible_person_id"] == lead
    assert body["ends_at"] is not None


def test_preparation_is_a_first_class_event_type(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    kopaonik = _location(client, actor, "Sportski centar Kopaonik", "SPORTS_HALL")
    created = client.post(
        "/events",
        headers=actor.headers,
        json={
            "title": "Zimske pripreme prve grupe",
            "type": "PREPARATION",
            "starts_at": "2026-07-20T08:00:00Z",
            "location_id": kopaonik,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["type"] == "PREPARATION"


def test_the_calendar_feed_shows_drafts_the_parent_list_does_not(
    client: TestClient, db: Session
) -> None:
    actor = bootstrap_actor(db)
    published = client.post(
        "/events",
        headers=actor.headers,
        json={"title": "Objavljen", "starts_at": "2026-07-11T08:00:00Z"},
    ).json()["id"]
    draft_id = client.post(
        "/events",
        headers=actor.headers,
        json={"title": "Nacrt", "starts_at": "2026-07-12T08:00:00Z"},
    ).json()["id"]
    # Drop the second one out of the published set the way a cancellation does.
    client.post(f"/events/{draft_id}/cancel", headers=actor.headers)

    calendar = client.get("/events/calendar", headers=actor.headers, params=WINDOW).json()
    assert {e["id"] for e in calendar} == {published, draft_id}

    parent_visible = client.get("/events", headers=actor.headers).json()
    assert {e["id"] for e in parent_visible} == {published}


def test_the_calendar_window_is_honoured(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    client.post(
        "/events",
        headers=actor.headers,
        json={"title": "Van prozora", "starts_at": "2026-09-01T08:00:00Z"},
    )
    assert client.get("/events/calendar", headers=actor.headers, params=WINDOW).json() == []


def test_a_trainer_may_read_the_calendar_but_not_create_events(
    client: TestClient, db: Session
) -> None:
    actor = bootstrap_actor(db)
    trainer = add_actor(
        db, school=actor.school, role=RoleCode.TRAINER, given="Trener"
    )
    client.post(
        "/events",
        headers=actor.headers,
        json={"title": "Turnir", "starts_at": "2026-07-15T08:00:00Z"},
    )

    readable = client.get("/events/calendar", headers=trainer.headers, params=WINDOW)
    assert readable.status_code == 200
    assert len(readable.json()) == 1

    refused = client.post(
        "/events",
        headers=trainer.headers,
        json={"title": "Ne mogu", "starts_at": "2026-07-16T08:00:00Z"},
    )
    assert refused.status_code == 403


def test_a_foreign_location_or_person_is_never_accepted_on_an_event(
    client: TestClient, db: Session
) -> None:
    actor = bootstrap_actor(db)
    other = bootstrap_actor(db, org_name="Druga", given="Druga")
    foreign_location = _location(client, other, "Tuđa", "SPORTS_HALL")

    refused = client.post(
        "/events",
        headers=actor.headers,
        json={
            "title": "Kamp",
            "starts_at": "2026-07-10T08:00:00Z",
            "location_id": foreign_location,
        },
    )
    assert refused.status_code == 404

    refused_person = client.post(
        "/events",
        headers=actor.headers,
        json={
            "title": "Kamp",
            "starts_at": "2026-07-10T08:00:00Z",
            "responsible_person_id": other.person.id,
        },
    )
    assert refused_person.status_code == 404


def test_an_event_may_not_end_before_it_starts(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    refused = client.post(
        "/events",
        headers=actor.headers,
        json={
            "title": "Naopako",
            "starts_at": "2026-07-10T08:00:00Z",
            "ends_at": "2026-07-09T08:00:00Z",
        },
    )
    assert refused.status_code == 422


def test_calendar_never_leaks_another_schools_events(
    client: TestClient, db: Session
) -> None:
    actor = bootstrap_actor(db)
    other = bootstrap_actor(db, org_name="Druga", given="Druga")
    client.post(
        "/events",
        headers=other.headers,
        json={"title": "Tuđ događaj", "starts_at": "2026-07-11T08:00:00Z"},
    )
    assert client.get("/events/calendar", headers=actor.headers, params=WINDOW).json() == []


def test_a_parent_cannot_reach_the_staff_calendar(client: TestClient, db: Session) -> None:
    """Parents keep seeing published events only. The calendar feed carries
    drafts and cancellations, which are the school's internal planning."""
    actor = bootstrap_actor(db)
    parent = add_actor(
        db, school=actor.school, role=RoleCode.PARENT, given="Roditelj"
    )
    client.post(
        "/events",
        headers=actor.headers,
        json={"title": "Nacrt", "starts_at": "2026-07-11T08:00:00Z"},
    )

    assert (
        client.get("/events/calendar", headers=parent.headers, params=WINDOW).status_code
        == 403
    )
