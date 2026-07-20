"""Recurring session series: create, 12-week generation + idempotent top-up,
conflict-aware skipping, scoped edits, cancel/reactivate, and tenant isolation."""

from __future__ import annotations

import datetime as dt

from app.domains.identity.enums import RoleCode
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import Actor, add_actor, bootstrap_actor

START_DATE = "2026-09-01"  # a Tuesday -> weekday() == 1
WEEKDAY = dt.date.fromisoformat(START_DATE).weekday()
RANGE = {"date_from": "2026-08-01T00:00:00+00:00", "date_to": "2027-01-01T00:00:00+00:00"}


def _group(client: TestClient, actor: Actor, name: str = "Grupa A") -> str:
    return client.post("/groups", headers=actor.headers, json={"name": name}).json()["id"]


def _series_body(group_id: str, **overrides: object) -> dict:
    body = {
        "group_id": group_id,
        "title": "Redovni trening",
        "frequency": "WEEKLY",
        "weekdays": [WEEKDAY],
        "start_date": START_DATE,
        "local_time": "17:00:00",
        "duration_minutes": 60,
    }
    body.update(overrides)
    return body


def _create_series(client: TestClient, actor: Actor, group_id: str, **overrides: object) -> dict:
    resp = client.post(
        "/schedule/series", headers=actor.headers, json=_series_body(group_id, **overrides)
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _generate(client: TestClient, actor: Actor, series_id: str, weeks: int = 12) -> dict:
    resp = client.post(
        f"/schedule/series/{series_id}/generate",
        headers=actor.headers,
        json={"from_date": START_DATE, "weeks": weeks},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _list_sessions(client: TestClient, actor: Actor) -> list[dict]:
    resp = client.get("/schedule/sessions", headers=actor.headers, params=RANGE)
    return sorted(resp.json(), key=lambda s: s["starts_at"])


def test_create_weekly_series(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group(client, actor)
    trainer = add_actor(db, organization=actor.organization, role=RoleCode.TRAINER, given="Trener")

    series = _create_series(client, actor, group_id, trainer_person_id=trainer.person.id)
    assert series["frequency"] == "WEEKLY"
    assert series["weekdays"] == [WEEKDAY]
    assert series["trainer_person_id"] == trainer.person.id

    listing = client.get("/schedule/series", headers=actor.headers).json()
    assert [s["id"] for s in listing] == [series["id"]]


def test_series_create_rejects_foreign_trainer(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group(client, actor)
    other = bootstrap_actor(db, org_name="Drugi klub")
    foreign_trainer = add_actor(
        db, organization=other.organization, role=RoleCode.TRAINER, given="Stranac"
    )
    resp = client.post(
        "/schedule/series",
        headers=actor.headers,
        json=_series_body(group_id, trainer_person_id=foreign_trainer.person.id),
    )
    assert resp.status_code == 404


def test_generate_twelve_weeks_and_idempotent_topup(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group(client, actor)
    series = _create_series(client, actor, group_id)

    first = _generate(client, actor, series["id"])
    assert first["created_count"] == 12
    assert first["skipped_existing"] == 0
    assert first["skipped_conflicts"] == []
    assert len(_list_sessions(client, actor)) == 12

    # Re-running is a no-op: same key (series, starts_at) -> nothing duplicated.
    second = _generate(client, actor, series["id"])
    assert second["created_count"] == 0
    assert second["skipped_existing"] == 12
    assert len(_list_sessions(client, actor)) == 12


def test_generation_skips_conflicts(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group(client, actor)

    first = _create_series(client, actor, group_id)
    assert _generate(client, actor, first["id"])["created_count"] == 12

    # A second series on the same group at the same slot fully conflicts.
    second = _create_series(client, actor, group_id, title="Duplikat")
    result = _generate(client, actor, second["id"])
    assert result["created_count"] == 0
    assert len(result["skipped_conflicts"]) == 12
    assert result["skipped_conflicts"][0]["reason"] == "SESSION_CONFLICT"
    assert len(_list_sessions(client, actor)) == 12  # no extra sessions materialized


def test_edit_scope_single(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group(client, actor)
    series = _create_series(client, actor, group_id)
    _generate(client, actor, series["id"])
    sessions = _list_sessions(client, actor)
    pivot = sessions[5]

    resp = client.patch(
        f"/schedule/sessions/{pivot['id']}",
        headers=actor.headers,
        json={"scope": "SINGLE", "reason": "OTHER", "title": "Poseban trening"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    after = {s["id"]: s for s in _list_sessions(client, actor)}
    assert after[pivot["id"]]["title"] == "Poseban trening"
    assert after[sessions[4]["id"]]["title"] == "Redovni trening"
    assert after[sessions[6]["id"]]["title"] == "Redovni trening"


def test_edit_scope_single_time_change_shifts_instant(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group(client, actor)
    series = _create_series(client, actor, group_id)
    _generate(client, actor, series["id"])
    pivot = _list_sessions(client, actor)[0]

    resp = client.patch(
        f"/schedule/sessions/{pivot['id']}",
        headers=actor.headers,
        json={"scope": "SINGLE", "reason": "TIME_CHANGE", "local_time": "19:30:00"},
    )
    assert resp.status_code == 200
    changed = resp.json()[0]
    assert changed["starts_at"] != pivot["starts_at"]
    # 60-minute duration preserved across the move.
    starts = dt.datetime.fromisoformat(changed["starts_at"])
    ends = dt.datetime.fromisoformat(changed["ends_at"])
    assert (ends - starts) == dt.timedelta(minutes=60)


def test_edit_scope_this_and_future(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group(client, actor)
    series = _create_series(client, actor, group_id)
    _generate(client, actor, series["id"])
    sessions = _list_sessions(client, actor)
    pivot = sessions[5]

    resp = client.patch(
        f"/schedule/sessions/{pivot['id']}",
        headers=actor.headers,
        json={"scope": "THIS_AND_FUTURE", "reason": "OTHER", "title": "Novi naziv"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 7  # pivot + 6 later occurrences

    after = _list_sessions(client, actor)
    assert all(s["title"] == "Redovni trening" for s in after[:5])
    assert all(s["title"] == "Novi naziv" for s in after[5:])

    # The series template inherited the change (future top-ups follow it).
    series_now = client.get("/schedule/series", headers=actor.headers).json()[0]
    assert series_now["title"] == "Novi naziv"


def test_edit_scope_all_future(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group(client, actor)
    trainer = add_actor(db, organization=actor.organization, role=RoleCode.TRAINER, given="Trener")
    series = _create_series(client, actor, group_id)
    _generate(client, actor, series["id"])
    pivot = _list_sessions(client, actor)[8]

    resp = client.patch(
        f"/schedule/sessions/{pivot['id']}",
        headers=actor.headers,
        json={
            "scope": "ALL_FUTURE",
            "reason": "TRAINER_CHANGE",
            "trainer_person_id": trainer.person.id,
        },
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 12  # every upcoming occurrence

    after = _list_sessions(client, actor)
    assert all(s["trainer_person_id"] == trainer.person.id for s in after)


def test_cancel_and_reactivate(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group(client, actor)
    draft = {
        "group_id": group_id,
        "starts_at": "2026-09-01T17:00:00+00:00",
        "ends_at": "2026-09-01T18:00:00+00:00",
    }
    session_id = client.post("/schedule/sessions", headers=actor.headers, json=draft).json()["id"]

    cancelled = client.post(
        f"/schedule/sessions/{session_id}/cancel",
        headers=actor.headers,
        json={"reason": "WEATHER", "note": "Padavine"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert cancelled.json()["cancellation_reason"] == "WEATHER"

    # Double cancel is refused.
    assert (
        client.post(
            f"/schedule/sessions/{session_id}/cancel",
            headers=actor.headers,
            json={"reason": "OTHER"},
        ).status_code
        == 409
    )

    reactivated = client.post(
        f"/schedule/sessions/{session_id}/reactivate", headers=actor.headers
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["status"] == "SCHEDULED"
    assert reactivated.json()["cancellation_reason"] is None


def test_reactivate_blocked_by_conflict(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group(client, actor)
    slot = {
        "group_id": group_id,
        "starts_at": "2026-09-01T17:00:00+00:00",
        "ends_at": "2026-09-01T18:00:00+00:00",
    }
    a_id = client.post("/schedule/sessions", headers=actor.headers, json=slot).json()["id"]
    client.post(
        f"/schedule/sessions/{a_id}/cancel", headers=actor.headers, json={"reason": "OTHER"}
    )

    # A new session now occupies the freed slot.
    assert client.post("/schedule/sessions", headers=actor.headers, json=slot).status_code == 201

    blocked = client.post(f"/schedule/sessions/{a_id}/reactivate", headers=actor.headers)
    assert blocked.status_code == 409
    assert blocked.json()["error"]["details"]["code"] == "SESSION_CONFLICT"


def test_tenant_isolation(client: TestClient, db: Session) -> None:
    owner = bootstrap_actor(db, org_name="Vlasnik klub")
    group_id = _group(client, owner)
    series = _create_series(client, owner, group_id)
    _generate(client, owner, series["id"])
    session_id = _list_sessions(client, owner)[0]["id"]

    intruder = bootstrap_actor(db, org_name="Uljez klub")
    # Foreign series is invisible: generate and edit both 404.
    assert (
        client.post(
            f"/schedule/series/{series['id']}/generate",
            headers=intruder.headers,
            json={"weeks": 12},
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/schedule/sessions/{session_id}",
            headers=intruder.headers,
            json={"scope": "SINGLE", "title": "hack"},
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/schedule/sessions/{session_id}/cancel",
            headers=intruder.headers,
            json={"reason": "OTHER"},
        ).status_code
        == 404
    )
    assert client.get("/schedule/series", headers=intruder.headers).json() == []
