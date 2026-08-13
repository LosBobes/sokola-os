from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import Actor, bootstrap_actor

T1 = "2026-09-01T17:00:00+00:00"
T1_END = "2026-09-01T18:00:00+00:00"
T1_OVERLAP = "2026-09-01T17:30:00+00:00"
T1_OVERLAP_END = "2026-09-01T18:30:00+00:00"
T2 = "2026-09-01T19:00:00+00:00"
T2_END = "2026-09-01T20:00:00+00:00"


def _group(client: TestClient, actor: Actor, name: str = "Grupa A") -> str:
    return client.post("/groups", headers=actor.headers, json={"name": name}).json()["id"]


def test_create_one_off_session_journey1(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group(client, actor)

    draft = {"group_id": group_id, "starts_at": T1, "ends_at": T1_END, "title": "Trening"}

    # Adapter previews conflicts first, none yet.
    preview = client.post("/schedule/conflict-check", headers=actor.headers, json=draft).json()
    assert preview["has_conflict"] is False

    created = client.post("/schedule/sessions", headers=actor.headers, json=draft)
    assert created.status_code == 201
    assert created.json()["status"] == "SCHEDULED"


def test_overlapping_session_is_refused(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group(client, actor)
    base = {"group_id": group_id, "starts_at": T1, "ends_at": T1_END}
    assert client.post("/schedule/sessions", headers=actor.headers, json=base).status_code == 201

    overlap = {"group_id": group_id, "starts_at": T1_OVERLAP, "ends_at": T1_OVERLAP_END}
    conflict = client.post("/schedule/sessions", headers=actor.headers, json=overlap)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["details"]["code"] == "SESSION_CONFLICT"

    # A non-overlapping slot for the same group is fine.
    later = {"group_id": group_id, "starts_at": T2, "ends_at": T2_END}
    assert client.post("/schedule/sessions", headers=actor.headers, json=later).status_code == 201


def test_create_session_is_idempotent(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group(client, actor)
    draft = {"group_id": group_id, "starts_at": T1, "ends_at": T1_END}
    headers = {**actor.headers, "Idempotency-Key": "sess-key-1"}

    first = client.post("/schedule/sessions", headers=headers, json=draft)
    second = client.post("/schedule/sessions", headers=headers, json=draft)
    assert first.status_code == 201
    assert second.json()["id"] == first.json()["id"]

    listing = client.get(
        "/schedule/sessions",
        headers=actor.headers,
        params={"date_from": "2026-09-01T00:00:00+00:00", "date_to": "2026-09-02T00:00:00+00:00"},
    ).json()
    assert len(listing) == 1  # replay did not create a duplicate


def test_implausible_date_is_rejected(client: TestClient, db: Session) -> None:
    """A malformed datetime-local value (e.g. an incomplete year picker producing
    "1111-11-11") must be refused, not silently create a session no view will
    ever show."""
    actor = bootstrap_actor(db)
    group_id = _group(client, actor)
    draft = {
        "group_id": group_id,
        "starts_at": "1111-11-11T09:49:00+00:00",
        "ends_at": "1111-11-11T10:49:00+00:00",
    }
    resp = client.post("/schedule/sessions", headers=actor.headers, json=draft)
    assert resp.status_code == 422
