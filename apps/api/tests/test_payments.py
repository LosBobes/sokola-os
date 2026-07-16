from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import Actor, bootstrap_actor


def _one_charge(client: TestClient, actor: Actor) -> str:
    group_id = client.post("/groups", headers=actor.headers, json={"name": "G"}).json()["id"]
    pid = client.post(
        "/people", headers=actor.headers, json={"given_name": "Platiša", "family_name": "L"}
    ).json()["id"]
    client.post(f"/groups/{group_id}/members", headers=actor.headers, json={"person_id": pid})
    body = {
        "group_id": group_id,
        "amount_minor": 300000,
        "description": "Članarina",
        "period_label": "2026-09",
    }
    preview = client.post("/billing/runs/preview", headers=actor.headers, json=body).json()
    client.post(
        "/billing/runs",
        headers=actor.headers,
        json={**body, "preview_hash": preview["preview_hash"]},
    )
    return client.get("/charges", headers=actor.headers).json()["items"][0]["id"]


def test_record_payment_journey6(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    charge_id = _one_charge(client, actor)

    partial = client.post(
        f"/charges/{charge_id}/payments",
        headers=actor.headers,
        json={"amount_minor": 100000, "method": "CASH"},
    )
    assert partial.status_code == 201
    assert partial.json()["charge_status"] == "PARTIALLY_PAID"

    rest = client.post(
        f"/charges/{charge_id}/payments",
        headers=actor.headers,
        json={"amount_minor": 200000, "method": "BANK_TRANSFER"},
    )
    assert rest.json()["charge_status"] == "PAID"
    assert rest.json()["charge_amount_paid_minor"] == 300000


def test_overpayment_and_double_settlement_are_refused(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    charge_id = _one_charge(client, actor)

    over = client.post(
        f"/charges/{charge_id}/payments",
        headers=actor.headers,
        json={"amount_minor": 400000, "method": "CASH"},
    )
    assert over.status_code == 409
    assert over.json()["error"]["details"]["code"] == "OVERPAYMENT"

    client.post(
        f"/charges/{charge_id}/payments",
        headers=actor.headers,
        json={"amount_minor": 300000, "method": "CASH"},
    )
    already = client.post(
        f"/charges/{charge_id}/payments",
        headers=actor.headers,
        json={"amount_minor": 1, "method": "CASH"},
    )
    assert already.status_code == 409


def test_payment_is_idempotent(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    charge_id = _one_charge(client, actor)
    headers = {**actor.headers, "Idempotency-Key": "pay-key-1"}
    payload = {"amount_minor": 100000, "method": "CASH"}

    first = client.post(f"/charges/{charge_id}/payments", headers=headers, json=payload)
    second = client.post(f"/charges/{charge_id}/payments", headers=headers, json=payload)
    assert second.json()["id"] == first.json()["id"]
    # Applied once, not twice.
    items = client.get("/charges", headers=actor.headers).json()["items"]
    charge = next(c for c in items if c["id"] == charge_id)
    assert charge["amount_paid_minor"] == 100000
