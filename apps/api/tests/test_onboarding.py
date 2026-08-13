"""Guided school onboarding (PRD 02 §24/§25, PRD 01 §13), the Wave 1 capstone.

Per-step progress, the "u pripremi" invite gate (only a co-owner invite is
allowed until the school activates), and the activation transition itself.
Integration tests against real Postgres."""

from __future__ import annotations

from typing import Any

from app.domains.identity.enums import RoleCode
from app.domains.organization.enums import OrganizationLifecycleStatus
from app.domains.organization.models import Organization
from app.security.auth import DEV_PERSON_HEADER
from app.security.deps import CONTEXT_HEADER
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import add_actor, make_person


def _bootstrap_owner(
    client: TestClient, db: Session, *, org_name: str = "Nova Škola"
) -> tuple[dict[str, str], dict[str, Any]]:
    """Create a school through the real signup path (``POST /organizations``),
    which, unlike ``tests.factories.bootstrap_actor``, starts it
    IN_PREPARATION. Returns ready owner headers plus the created organization."""
    person = make_person(db, given="Osnivač")
    bare_headers = {DEV_PERSON_HEADER: person.id}
    org = client.post(
        "/organizations", headers=bare_headers, json={"name": org_name, "type": "SCHOOL"}
    ).json()
    contexts = client.get("/me/contexts", headers=bare_headers).json()
    assignment_id = contexts[0]["role_assignment_id"]
    headers = {**bare_headers, CONTEXT_HEADER: assignment_id}
    return headers, org


def _step(progress: dict[str, Any], name: str) -> dict[str, Any]:
    match = [s for s in progress["steps"] if s["step"] == name]
    assert len(match) == 1, f"step {name} missing from {progress['steps']}"
    return match[0]


# ---------------------------------------------------------------------------
# M1, per-step progress, "what's left"
# ---------------------------------------------------------------------------


def test_new_school_starts_in_preparation_with_only_profile_done(
    client: TestClient, db: Session
) -> None:
    headers, org = _bootstrap_owner(client, db)
    assert org["lifecycle_status"] == "IN_PREPARATION"

    progress = client.get("/onboarding/progress", headers=headers).json()
    assert progress["organization_id"] == org["id"]
    assert progress["lifecycle_status"] == "IN_PREPARATION"
    assert progress["activated_at"] is None
    assert progress["can_activate"] is False

    assert _step(progress, "SCHOOL_PROFILE")["completed"] is True
    for name in ("LOCATIONS", "ROOMS", "PROGRAMS", "FIRST_INVITE", "ACTIVATE"):
        assert _step(progress, name)["completed"] is False
    assert set(progress["remaining_steps"]) == {
        "LOCATIONS",
        "ROOMS",
        "PROGRAMS",
        "FIRST_INVITE",
        "ACTIVATE",
    }


def test_progress_tracks_structure_setup_and_first_invite(
    client: TestClient, db: Session
) -> None:
    headers, _org = _bootstrap_owner(client, db)

    loc = client.post(
        "/locations", headers=headers, json={"name": "Centrala"}
    )
    assert loc.status_code == 201, loc.text
    progress = client.get("/onboarding/progress", headers=headers).json()
    assert _step(progress, "LOCATIONS")["completed"] is True
    assert _step(progress, "LOCATIONS")["completed_at"] is not None
    assert progress["can_activate"] is True  # minimum bar (a location) is met
    assert _step(progress, "ROOMS")["completed"] is False

    room = client.post(
        "/rooms",
        headers=headers,
        json={"location_id": loc.json()["id"], "name": "Sala 1"},
    )
    assert room.status_code == 201, room.text
    program = client.post("/programs", headers=headers, json={"name": "Klasičan balet"})
    assert program.status_code == 201, program.text

    progress = client.get("/onboarding/progress", headers=headers).json()
    assert _step(progress, "ROOMS")["completed"] is True
    assert _step(progress, "PROGRAMS")["completed"] is True
    assert _step(progress, "FIRST_INVITE")["completed"] is False

    invited = client.post(
        "/invitations",
        headers=headers,
        json={
            "type": "STAFF",
            "target_email": "suvlasnik@primer.rs",
            "role_code": "OWNER",
            "scope_type": "ORGANIZATION",
        },
    )
    assert invited.status_code == 201, invited.text

    progress = client.get("/onboarding/progress", headers=headers).json()
    assert _step(progress, "FIRST_INVITE")["completed"] is True
    assert set(progress["remaining_steps"]) == {"ACTIVATE"}


# ---------------------------------------------------------------------------
# M2/M3, "u pripremi" blocks normal staff invites, not the first-owner path
# ---------------------------------------------------------------------------


def test_in_preparation_blocks_normal_staff_invite(client: TestClient, db: Session) -> None:
    headers, _org = _bootstrap_owner(client, db)

    resp = client.post(
        "/invitations",
        headers=headers,
        json={
            "type": "STAFF",
            "target_email": "menadzer@primer.rs",
            "role_code": "MANAGER",
            "scope_type": "ORGANIZATION",
        },
    )
    assert resp.status_code == 403


def test_in_preparation_blocks_parent_invite(client: TestClient, db: Session) -> None:
    headers, _org = _bootstrap_owner(client, db)

    # Blocked by the onboarding gate before the (nonexistent) child is even
    # looked up, a PARENT invite isn't the first-owner path either.
    resp = client.post(
        "/invitations",
        headers=headers,
        json={
            "type": "PARENT",
            "target_email": "roditelj@primer.rs",
            "scope_type": "ORGANIZATION",
            "target_child_person_id": "per_ne_postoji",
        },
    )
    assert resp.status_code == 403


def test_in_preparation_allows_first_owner_invite(client: TestClient, db: Session) -> None:
    headers, _org = _bootstrap_owner(client, db)

    resp = client.post(
        "/invitations",
        headers=headers,
        json={
            "type": "STAFF",
            "target_email": "suvlasnik@primer.rs",
            "role_code": "OWNER",
            "scope_type": "ORGANIZATION",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["invitation"]["role_code"] == "OWNER"


def test_activation_lifts_the_invite_gate(client: TestClient, db: Session) -> None:
    headers, _org = _bootstrap_owner(client, db)
    client.post("/locations", headers=headers, json={"name": "Centrala"})

    activated = client.post("/onboarding/activate", headers=headers)
    assert activated.status_code == 200, activated.text
    assert activated.json()["lifecycle_status"] == "ACTIVE"

    resp = client.post(
        "/invitations",
        headers=headers,
        json={
            "type": "STAFF",
            "target_email": "menadzer@primer.rs",
            "role_code": "MANAGER",
            "scope_type": "ORGANIZATION",
        },
    )
    assert resp.status_code == 201, resp.text


# ---------------------------------------------------------------------------
# Activation requires the minimum setup (at least one location)
# ---------------------------------------------------------------------------


def test_activation_requires_a_location(client: TestClient, db: Session) -> None:
    headers, org = _bootstrap_owner(client, db)

    blocked = client.post("/onboarding/activate", headers=headers)
    assert blocked.status_code == 409

    client.post("/locations", headers=headers, json={"name": "Centrala"})
    ok = client.post("/onboarding/activate", headers=headers)
    assert ok.status_code == 200, ok.text
    progress = ok.json()
    assert progress["lifecycle_status"] == "ACTIVE"
    assert progress["activated_at"] is not None
    assert progress["can_activate"] is False
    assert _step(progress, "ACTIVATE")["completed"] is True

    org_row = db.get(Organization, org["id"])
    assert org_row is not None
    assert org_row.lifecycle_status is OrganizationLifecycleStatus.ACTIVE

    # Already active, a second activation is refused.
    again = client.post("/onboarding/activate", headers=headers)
    assert again.status_code == 409


def test_activate_requires_organization_permission(client: TestClient, db: Session) -> None:
    headers, org = _bootstrap_owner(client, db)
    client.post("/locations", headers=headers, json={"name": "Centrala"})

    org_row = db.get(Organization, org["id"])
    assert org_row is not None
    trainer = add_actor(db, organization=org_row, role=RoleCode.TRAINER, given="Trener")

    resp = client.post("/onboarding/activate", headers=trainer.headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_onboarding_progress_is_isolated_per_school(client: TestClient, db: Session) -> None:
    headers_a, _org_a = _bootstrap_owner(client, db, org_name="Škola A")
    headers_b, _org_b = _bootstrap_owner(client, db, org_name="Škola B")

    client.post("/locations", headers=headers_a, json={"name": "Centrala A"})

    progress_a = client.get("/onboarding/progress", headers=headers_a).json()
    progress_b = client.get("/onboarding/progress", headers=headers_b).json()
    assert progress_a["can_activate"] is True
    assert progress_b["can_activate"] is False

    activated_a = client.post("/onboarding/activate", headers=headers_a)
    assert activated_a.status_code == 200

    # B is untouched by A's activation and still needs its own location.
    still_blocked_b = client.post("/onboarding/activate", headers=headers_b)
    assert still_blocked_b.status_code == 409
