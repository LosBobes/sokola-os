from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import Actor, bootstrap_actor


def _group_with_members(client: TestClient, actor: Actor, count: int) -> str:
    group_id = client.post("/groups", headers=actor.headers, json={"name": "G"}).json()["id"]
    for i in range(count):
        pid = client.post(
            "/people", headers=actor.headers, json={"given_name": f"Č{i}", "family_name": "L"}
        ).json()["id"]
        client.post(
            f"/groups/{group_id}/members", headers=actor.headers, json={"person_id": pid}
        )
    return group_id


def _run_body(group_id: str) -> dict:
    return {
        "group_id": group_id,
        "amount_minor": 300000,
        "description": "Članarina septembar",
        "period_label": "2026-09",
    }


def test_post_billing_run_journey5(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group_with_members(client, actor, 2)
    body = _run_body(group_id)

    preview = client.post("/billing/runs/preview", headers=actor.headers, json=body).json()
    assert len(preview["items"]) == 2
    assert preview["total_minor"] == 600000

    posted = client.post(
        "/billing/runs",
        headers=actor.headers,
        json={**body, "preview_hash": preview["preview_hash"]},
    )
    assert posted.status_code == 201
    assert posted.json()["charge_count"] == 2

    charges = client.get("/charges", headers=actor.headers).json()
    assert charges["total"] == 2
    assert all(c["status"] == "OPEN" for c in charges["items"])


def test_billing_run_is_idempotent(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group_with_members(client, actor, 2)
    body = _run_body(group_id)
    preview = client.post("/billing/runs/preview", headers=actor.headers, json=body).json()
    post_body = {**body, "preview_hash": preview["preview_hash"]}
    headers = {**actor.headers, "Idempotency-Key": "run-key-1"}

    first = client.post("/billing/runs", headers=headers, json=post_body)
    second = client.post("/billing/runs", headers=headers, json=post_body)
    assert second.json()["id"] == first.json()["id"]
    # Replay did not double-charge.
    assert client.get("/charges", headers=actor.headers).json()["total"] == 2


def test_stale_preview_is_refused(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group_with_members(client, actor, 2)
    body = _run_body(group_id)
    preview = client.post("/billing/runs/preview", headers=actor.headers, json=body).json()

    # Roster changes after the preview was taken.
    _group_with_members  # noqa: B018
    new_pid = client.post(
        "/people", headers=actor.headers, json={"given_name": "Novi", "family_name": "Č"}
    ).json()["id"]
    client.post(f"/groups/{group_id}/members", headers=actor.headers, json={"person_id": new_pid})

    stale = client.post(
        "/billing/runs",
        headers=actor.headers,
        json={**body, "preview_hash": preview["preview_hash"]},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["details"]["code"] == "PREVIEW_STALE"
