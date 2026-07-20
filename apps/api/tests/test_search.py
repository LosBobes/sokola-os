from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import Actor, bootstrap_actor

SESSION_TIMES = {
    "starts_at": "2026-09-01T17:00:00+00:00",
    "ends_at": "2026-09-01T18:00:00+00:00",
}
EVENT_TIME = {"starts_at": "2026-12-20T09:00:00+00:00"}


def _person(client: TestClient, actor: Actor, given: str, family: str = "Test") -> str:
    resp = client.post(
        "/people", headers=actor.headers, json={"given_name": given, "family_name": family}
    )
    assert resp.status_code == 201
    return str(resp.json()["id"])


def _group(client: TestClient, actor: Actor, name: str) -> str:
    resp = client.post("/groups", headers=actor.headers, json={"name": name})
    assert resp.status_code == 201
    return str(resp.json()["id"])


def _add_member(client: TestClient, actor: Actor, group_id: str, person_id: str) -> None:
    resp = client.post(
        f"/groups/{group_id}/members", headers=actor.headers, json={"person_id": person_id}
    )
    assert resp.status_code == 201


def _session(client: TestClient, actor: Actor, group_id: str, title: str) -> str:
    resp = client.post(
        "/schedule/sessions",
        headers=actor.headers,
        json={"group_id": group_id, "title": title, **SESSION_TIMES},
    )
    assert resp.status_code == 201
    return str(resp.json()["id"])


def _event(client: TestClient, actor: Actor, title: str) -> str:
    resp = client.post(
        "/events", headers=actor.headers, json={"title": title, **EVENT_TIME}
    )
    assert resp.status_code == 201
    return str(resp.json()["id"])


def _charge_via_run(
    client: TestClient, actor: Actor, group_id: str, description: str, period: str = "2026-09"
) -> None:
    body = {
        "group_id": group_id,
        "amount_minor": 100000,
        "description": description,
        "period_label": period,
    }
    preview = client.post("/billing/runs/preview", headers=actor.headers, json=body).json()
    posted = client.post(
        "/billing/runs",
        headers=actor.headers,
        json={**body, "preview_hash": preview["preview_hash"]},
    )
    assert posted.status_code == 201


def _search(client: TestClient, actor: Actor, q: str) -> dict:
    resp = client.get("/search", headers=actor.headers, params={"q": q})
    assert resp.status_code == 200
    return dict(resp.json())


def test_search_returns_matches_across_entity_types(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)

    person_id = _person(client, actor, "Zmajko", "Testić")
    group_id = _group(client, actor, "Zmajevi Klub")
    _add_member(client, actor, group_id, person_id)
    session_id = _session(client, actor, group_id, "Zmajevi Trening")
    event_id = _event(client, actor, "Zmajevi Turnir")
    _charge_via_run(client, actor, group_id, "Zmajevi članarina")

    body = _search(client, actor, "Zmaj")
    results = body["results"]
    assert body["query"] == "Zmaj"

    by_type = {r["type"]: r for r in results}
    assert set(by_type) == {"PERSON", "GROUP", "SESSION", "EVENT", "CHARGE"}
    assert by_type["PERSON"]["id"] == person_id
    assert by_type["GROUP"]["id"] == group_id
    assert by_type["SESSION"]["id"] == session_id
    assert by_type["EVENT"]["id"] == event_id
    # The charge belongs to the group's only member (the created person).
    assert by_type["CHARGE"]["subtitle"].startswith("Zmajko Testić")


def test_org_b_data_never_appears_in_org_a_results(client: TestClient, db: Session) -> None:
    """The critical invariant: every sub-query is scoped to the caller's
    organization, never leaking a same-named row from a different tenant."""
    org_a = bootstrap_actor(db, org_name="Klub A")
    org_b = bootstrap_actor(db, org_name="Klub B")

    person_a = _person(client, org_a, "Deljivi", "Termin")
    group_a = _group(client, org_a, "Deljivi Termin Klub")
    _add_member(client, org_a, group_a, person_a)
    session_a = _session(client, org_a, group_a, "Deljivi Termin Trening")
    event_a = _event(client, org_a, "Deljivi Termin Turnir")
    _charge_via_run(client, org_a, group_a, "Deljivi Termin članarina")

    person_b = _person(client, org_b, "Deljivi", "Termin")
    group_b = _group(client, org_b, "Deljivi Termin Klub")
    _add_member(client, org_b, group_b, person_b)
    session_b = _session(client, org_b, group_b, "Deljivi Termin Trening")
    event_b = _event(client, org_b, "Deljivi Termin Turnir")
    _charge_via_run(client, org_b, group_b, "Deljivi Termin članarina")

    results_a = _search(client, org_a, "Deljivi Termin")["results"]
    ids_a = {r["id"] for r in results_a}
    assert person_a in ids_a and group_a in ids_a and session_a in ids_a and event_a in ids_a
    assert person_b not in ids_a
    assert group_b not in ids_a
    assert session_b not in ids_a
    assert event_b not in ids_a
    # Charges aren't easily correlated by id across orgs from this test alone,
    # but there must be exactly one (org A's) — never two.
    charge_results_a = [r for r in results_a if r["type"] == "CHARGE"]
    assert len(charge_results_a) == 1

    results_b = _search(client, org_b, "Deljivi Termin")["results"]
    ids_b = {r["id"] for r in results_b}
    assert person_b in ids_b and group_b in ids_b and session_b in ids_b and event_b in ids_b
    assert person_a not in ids_b
    assert group_a not in ids_b
    assert session_a not in ids_b
    assert event_a not in ids_b
    charge_results_b = [r for r in results_b if r["type"] == "CHARGE"]
    assert len(charge_results_b) == 1


def test_empty_query_returns_empty(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    _person(client, actor, "Neko", "Neko")

    assert _search(client, actor, "")["results"] == []
    assert _search(client, actor, "   ")["results"] == []


def test_no_match_returns_empty(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    _person(client, actor, "Postojeći", "Član")

    assert _search(client, actor, "Nepostojeći Pojam Xyz123")["results"] == []


def test_prefix_match_ranks_before_substring_match(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    group_prefix = _group(client, actor, "Rank Prvi")
    group_substr = _group(client, actor, "Grupa Rank Drugi")

    results = _search(client, actor, "Rank")["results"]
    group_results = [r for r in results if r["type"] == "GROUP"]
    ids_in_order = [r["id"] for r in group_results]
    assert ids_in_order.index(group_prefix) < ids_in_order.index(group_substr)
