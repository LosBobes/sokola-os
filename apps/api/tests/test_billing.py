from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import Actor, bootstrap_actor

PRICE = "3000.00"


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
        "amount": "3000.00",
        "description": "Članarina septembar",
        "period_label": "2026-09",
    }


def test_post_billing_run_journey5(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group_with_members(client, actor, 2)
    body = _run_body(group_id)

    preview = client.post("/billing/runs/preview", headers=actor.headers, json=body).json()
    assert len(preview["items"]) == 2
    assert preview["total"] == "6000.00"

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


# ---------------------------------------------------------------------------
# M1, pricing source: charge amounts derived from Group.base_monthly_price
# minus GroupMembership.discount when amount is omitted.
# ---------------------------------------------------------------------------


def test_pricing_derived_amount_matches_group_price_minus_discount(
    client: TestClient, db: Session
) -> None:
    actor = bootstrap_actor(db)
    group_id = client.post(
        "/groups",
        headers=actor.headers,
        json={"name": "Cenovnik", "base_monthly_price": PRICE},
    ).json()["id"]
    pid = client.post(
        "/people", headers=actor.headers, json={"given_name": "Popust", "family_name": "L"}
    ).json()["id"]
    member = client.post(
        f"/groups/{group_id}/members", headers=actor.headers, json={"person_id": pid}
    ).json()
    client.patch(
        f"/groups/{group_id}/members/{member['membership_id']}/discount",
        headers=actor.headers,
        json={"discount": "500.00"},
    )

    body = {"group_id": group_id, "description": "Članarina", "period_label": "2026-09"}
    preview = client.post("/billing/runs/preview", headers=actor.headers, json=body).json()
    assert preview["items"] == [
        {"person_id": pid, "display_name": "Popust L", "amount": "2500.00"}
    ]
    assert preview["total"] == "2500.00"

    posted = client.post(
        "/billing/runs",
        headers=actor.headers,
        json={**body, "preview_hash": preview["preview_hash"]},
    )
    assert posted.status_code == 201
    charges = client.get(
        "/charges", headers=actor.headers, params={"person_id": pid}
    ).json()["items"]
    assert charges[0]["amount_due"] == "2500.00"


def test_pricing_discount_floors_at_zero(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = client.post(
        "/groups",
        headers=actor.headers,
        json={"name": "Besplatno", "base_monthly_price": "100.00"},
    ).json()["id"]
    pid = client.post(
        "/people", headers=actor.headers, json={"given_name": "Stipendija", "family_name": "K"}
    ).json()["id"]
    member = client.post(
        f"/groups/{group_id}/members", headers=actor.headers, json={"person_id": pid}
    ).json()
    client.patch(
        f"/groups/{group_id}/members/{member['membership_id']}/discount",
        headers=actor.headers,
        json={"discount": "500.00"},
    )

    body = {"group_id": group_id, "description": "Članarina", "period_label": "2026-09"}
    preview = client.post("/billing/runs/preview", headers=actor.headers, json=body).json()
    assert preview["items"][0]["amount"] == "0.00"


def test_pricing_requires_group_price_when_amount_omitted(
    client: TestClient, db: Session
) -> None:
    actor = bootstrap_actor(db)
    group_id = _group_with_members(client, actor, 1)
    body = {"group_id": group_id, "description": "Članarina", "period_label": "2026-09"}
    resp = client.post("/billing/runs/preview", headers=actor.headers, json=body)
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["code"] == "GROUP_PRICE_NOT_SET"


def test_explicit_amount_override_still_works(client: TestClient, db: Session) -> None:
    """Backward compatibility: an explicit amount is still honoured
    verbatim, even when the group has its own list price configured."""
    actor = bootstrap_actor(db)
    group_id = client.post(
        "/groups",
        headers=actor.headers,
        json={"name": "Cenovnik", "base_monthly_price": PRICE},
    ).json()["id"]
    pid = client.post(
        "/people", headers=actor.headers, json={"given_name": "Č", "family_name": "L"}
    ).json()["id"]
    client.post(f"/groups/{group_id}/members", headers=actor.headers, json={"person_id": pid})

    body = {
        "group_id": group_id,
        "amount": "123.45",
        "description": "Vanredna uplata",
        "period_label": "2026-09",
    }
    preview = client.post("/billing/runs/preview", headers=actor.headers, json=body).json()
    assert preview["items"][0]["amount"] == "123.45"


# ---------------------------------------------------------------------------
# M2, debts / dugovanja aggregated view.
# ---------------------------------------------------------------------------


def test_debts_view_aggregates_per_person_and_org(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group_with_members(client, actor, 2)
    body = _run_body(group_id)
    preview = client.post("/billing/runs/preview", headers=actor.headers, json=body).json()
    client.post(
        "/billing/runs",
        headers=actor.headers,
        json={**body, "preview_hash": preview["preview_hash"]},
    )
    charges = client.get("/charges", headers=actor.headers).json()["items"]
    assert len(charges) == 2

    # Fully pay one charge, partially pay the other.
    client.post(
        f"/charges/{charges[0]['id']}/payments",
        headers=actor.headers,
        json={"amount": "3000.00", "method": "CASH"},
    )
    client.post(
        f"/charges/{charges[1]['id']}/payments",
        headers=actor.headers,
        json={"amount": "1000.00", "method": "CASH"},
    )

    debts = client.get("/billing/debts", headers=actor.headers).json()
    assert debts["total"] == 1
    assert debts["items"][0]["person_id"] == charges[1]["person_id"]
    assert debts["items"][0]["outstanding"] == "2000.00"
    assert debts["items"][0]["open_charge_count"] == 1

    summary = client.get("/billing/debts/summary", headers=actor.headers).json()
    assert summary["total_outstanding"] == "2000.00"
    assert summary["people_with_debt"] == 1


def test_debts_view_respects_tenant_isolation(client: TestClient, db: Session) -> None:
    org_a = bootstrap_actor(db, org_name="Klub A")
    org_b = bootstrap_actor(db, org_name="Klub B")

    group_b = _group_with_members(client, org_b, 1)
    body_b = _run_body(group_b)
    preview_b = client.post(
        "/billing/runs/preview", headers=org_b.headers, json=body_b
    ).json()
    client.post(
        "/billing/runs",
        headers=org_b.headers,
        json={**body_b, "preview_hash": preview_b["preview_hash"]},
    )

    # Org B has an open debt; org A sees nothing.
    assert client.get("/billing/debts", headers=org_a.headers).json()["total"] == 0
    assert (
        client.get("/billing/debts/summary", headers=org_a.headers).json()[
            "total_outstanding"
        ]
        == "0.00"
    )
    assert (
        client.get("/billing/debts/summary", headers=org_b.headers).json()[
            "total_outstanding"
        ]
        == "3000.00"
    )


# ---------------------------------------------------------------------------
# P1, charge cancellation.
# ---------------------------------------------------------------------------


def test_charge_cancellation_journey(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group_with_members(client, actor, 1)
    body = _run_body(group_id)
    preview = client.post("/billing/runs/preview", headers=actor.headers, json=body).json()
    client.post(
        "/billing/runs",
        headers=actor.headers,
        json={**body, "preview_hash": preview["preview_hash"]},
    )
    charge_id = client.get("/charges", headers=actor.headers).json()["items"][0]["id"]

    cancelled = client.post(
        f"/charges/{charge_id}/cancel",
        headers=actor.headers,
        json={"reason": "WAIVED", "note": "Socijalni slučaj"},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"
    assert cancelled.json()["cancellation_reason"] == "WAIVED"

    # Cancelling an already-cancelled charge is refused.
    again = client.post(
        f"/charges/{charge_id}/cancel", headers=actor.headers, json={"reason": "OTHER"}
    )
    assert again.status_code == 409
    assert again.json()["error"]["details"]["code"] == "CHARGE_NOT_CANCELLABLE"


def test_paid_charge_cannot_be_cancelled(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group_with_members(client, actor, 1)
    body = _run_body(group_id)
    preview = client.post("/billing/runs/preview", headers=actor.headers, json=body).json()
    client.post(
        "/billing/runs",
        headers=actor.headers,
        json={**body, "preview_hash": preview["preview_hash"]},
    )
    charge_id = client.get("/charges", headers=actor.headers).json()["items"][0]["id"]
    client.post(
        f"/charges/{charge_id}/payments",
        headers=actor.headers,
        json={"amount": PRICE, "method": "CASH"},
    )

    resp = client.post(
        f"/charges/{charge_id}/cancel", headers=actor.headers, json={"reason": "ERROR"}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["code"] == "CHARGE_NOT_CANCELLABLE"


def test_charge_cancellation_is_idempotent(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_id = _group_with_members(client, actor, 1)
    body = _run_body(group_id)
    preview = client.post("/billing/runs/preview", headers=actor.headers, json=body).json()
    client.post(
        "/billing/runs",
        headers=actor.headers,
        json={**body, "preview_hash": preview["preview_hash"]},
    )
    charge_id = client.get("/charges", headers=actor.headers).json()["items"][0]["id"]
    headers = {**actor.headers, "Idempotency-Key": "cancel-key-1"}

    first = client.post(
        f"/charges/{charge_id}/cancel", headers=headers, json={"reason": "DUPLICATE"}
    )
    second = client.post(
        f"/charges/{charge_id}/cancel", headers=headers, json={"reason": "DUPLICATE"}
    )
    assert first.status_code == 200
    assert second.json() == first.json()
