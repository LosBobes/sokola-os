"""Invitation lifecycle (PRD 01, §16-24): send / accept-existing / accept-new /
revoke / reissue / 7-day expiry / wrong-account rejection, plus the
parent-invite-to-specific-child and trainer-group-assignment paths.
Integration tests against real Postgres."""

from __future__ import annotations

import datetime as dt
from typing import Any

from app.domains.identity.enums import InvitationStatus, RoleCode
from app.domains.identity.models import Invitation
from app.security.auth import DEV_PERSON_HEADER
from app.security.deps import CONTEXT_HEADER
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import (
    Actor,
    add_actor,
    bootstrap_actor,
    link_login_email,
    make_child_with_guardian,
    make_person,
)


def _send(
    client: TestClient,
    staff: Actor,
    *,
    type: str = "STAFF",
    target_email: str = "novi@primer.rs",
    role_code: str | None = "MANAGER",
    scope_type: str = "ORGANIZATION",
    scope_ref_id: str | None = None,
    granted_areas: list[str] | None = None,
    target_child_person_id: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": type,
        "target_email": target_email,
        "scope_type": scope_type,
        "scope_ref_id": scope_ref_id,
        "granted_areas": granted_areas,
        "target_child_person_id": target_child_person_id,
    }
    if role_code is not None:
        body["role_code"] = role_code
    resp = client.post("/invitations", headers=staff.headers, json=body)
    assert resp.status_code == 201, resp.text
    result: dict[str, Any] = resp.json()
    return result


def _accept_headers(db: Session, *, email: str, given: str = "Novi") -> tuple[dict[str, str], str]:
    """A brand-new person, with a verified login email, ready to accept."""
    person = make_person(db, given=given, family="Član")
    link_login_email(db, person=person, email=email)
    return {DEV_PERSON_HEADER: person.id}, person.id


# ---------------------------------------------------------------------------
# M1, send / accept-new / accept-existing
# ---------------------------------------------------------------------------


def test_send_invitation_returns_token_once(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    created = _send(client, staff, target_email="menadzer@primer.rs", role_code="MANAGER")

    assert created["token"]
    inv = created["invitation"]
    assert inv["status"] == "PENDING"
    assert inv["role_code"] == "MANAGER"
    assert inv["target_email"] == "menadzer@primer.rs"
    assert inv["person_id"] is None
    assert inv["invited_by_person_id"] == staff.person.id

    # expires ~7 days out
    expires_at = dt.datetime.fromisoformat(inv["expires_at"])
    delta = expires_at - dt.datetime.now(tz=dt.UTC)
    assert dt.timedelta(days=6, hours=23) < delta <= dt.timedelta(days=7, minutes=5)


def test_accept_invitation_as_new_person_grants_context(
    client: TestClient, db: Session
) -> None:
    staff = bootstrap_actor(db, org_name="Klub Soko")
    created = _send(client, staff, target_email="trener@primer.rs", role_code="TRAINER")

    headers, person_id = _accept_headers(db, email="trener@primer.rs")
    resp = client.post("/invitations/accept", headers=headers, json={"token": created["token"]})
    assert resp.status_code == 200, resp.text
    ctx = resp.json()["context"]
    assert ctx["organization_id"] == staff.organization.id
    assert ctx["role_code"] == "TRAINER"

    # /me/contexts now lists it, and the new context actually works.
    contexts = client.get("/me/contexts", headers=headers).json()
    assert any(c["role_assignment_id"] == ctx["role_assignment_id"] for c in contexts)

    invitation = db.get(Invitation, created["invitation"]["id"])
    assert invitation is not None
    assert invitation.status is InvitationStatus.ACCEPTED
    assert invitation.person_id == person_id


def test_accept_invitation_as_existing_person_adds_second_context(
    client: TestClient, db: Session
) -> None:
    """The same accept path also serves a person who already has a context
    elsewhere (§21), acceptance only ever adds, never replaces."""
    other_org = bootstrap_actor(db, org_name="Prva škola")
    headers = other_org.headers
    link_login_email(db, person=other_org.person, email="postojeci@primer.rs")

    new_org = bootstrap_actor(db, org_name="Druga škola")
    created = _send(client, new_org, target_email="postojeci@primer.rs", role_code="ADMIN")

    resp = client.post("/invitations/accept", headers=headers, json={"token": created["token"]})
    assert resp.status_code == 200, resp.text

    contexts = client.get("/me/contexts", headers=headers).json()
    org_ids = {c["organization_id"] for c in contexts}
    assert {other_org.organization.id, new_org.organization.id} <= org_ids


# ---------------------------------------------------------------------------
# M2, wrong-account rejection (§23)
# ---------------------------------------------------------------------------


def test_accept_invitation_wrong_account_is_rejected(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    created = _send(client, staff, target_email="ispravan@primer.rs", role_code="MANAGER")

    headers, _ = _accept_headers(db, email="pogresan@primer.rs")
    resp = client.post("/invitations/accept", headers=headers, json={"token": created["token"]})
    assert resp.status_code == 403

    invitation = db.get(Invitation, created["invitation"]["id"])
    assert invitation is not None
    assert invitation.status is InvitationStatus.PENDING  # untouched


# ---------------------------------------------------------------------------
# M1, revoke / reissue / expiry
# ---------------------------------------------------------------------------


def test_revoke_invitation_blocks_acceptance(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    created = _send(client, staff, target_email="opozvan@primer.rs", role_code="MANAGER")
    invitation_id = created["invitation"]["id"]

    revoked = client.post(
        f"/invitations/{invitation_id}/revoke", headers=staff.headers, json={"reason": "Greška"}
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "REVOKED"

    # Revoking twice is refused.
    assert (
        client.post(
            f"/invitations/{invitation_id}/revoke", headers=staff.headers, json={}
        ).status_code
        == 409
    )

    headers, _ = _accept_headers(db, email="opozvan@primer.rs")
    resp = client.post("/invitations/accept", headers=headers, json={"token": created["token"]})
    assert resp.status_code == 409


def test_reissue_invitation_voids_old_token(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    created = _send(client, staff, target_email="ponovo@primer.rs", role_code="MANAGER")
    invitation_id = created["invitation"]["id"]

    reissued = client.post(f"/invitations/{invitation_id}/reissue", headers=staff.headers)
    assert reissued.status_code == 201
    new = reissued.json()
    assert new["invitation"]["id"] != invitation_id
    assert new["invitation"]["reissued_from_invitation_id"] == invitation_id
    assert new["token"] != created["token"]

    old_invitation = db.get(Invitation, invitation_id)
    assert old_invitation is not None
    assert old_invitation.status is InvitationStatus.REISSUED

    headers, _ = _accept_headers(db, email="ponovo@primer.rs")
    # Old token is dead …
    assert (
        client.post(
            "/invitations/accept", headers=headers, json={"token": created["token"]}
        ).status_code
        == 409
    )
    # … the new one works.
    ok = client.post("/invitations/accept", headers=headers, json={"token": new["token"]})
    assert ok.status_code == 200


def test_invitation_expires_after_seven_days(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    created = _send(client, staff, target_email="istekao@primer.rs", role_code="MANAGER")
    invitation_id = created["invitation"]["id"]

    invitation = db.get(Invitation, invitation_id)
    assert invitation is not None
    invitation.expires_at = dt.datetime.now(tz=dt.UTC) - dt.timedelta(seconds=1)
    db.commit()

    headers, _ = _accept_headers(db, email="istekao@primer.rs")
    resp = client.post("/invitations/accept", headers=headers, json={"token": created["token"]})
    assert resp.status_code == 409

    db.expire_all()
    refreshed = db.get(Invitation, invitation_id)
    assert refreshed is not None
    assert refreshed.status is InvitationStatus.EXPIRED

    # An expired invitation may still be reissued.
    assert (
        client.post(f"/invitations/{invitation_id}/reissue", headers=staff.headers).status_code
        == 201
    )


# ---------------------------------------------------------------------------
# M7, parent-invite-to-specific-child + additional guardian (§19.4/19.5)
# ---------------------------------------------------------------------------


def test_parent_invitation_links_guardian_to_specific_child(
    client: TestClient, db: Session
) -> None:
    staff = bootstrap_actor(db)
    existing_guardian = add_actor(
        db, organization=staff.organization, role=RoleCode.PARENT, given="Prvi"
    )
    child = make_child_with_guardian(
        db, organization=staff.organization, guardian=existing_guardian.person, given="Dete"
    )

    created = _send(
        client,
        staff,
        type="PARENT",
        target_email="drugi.roditelj@primer.rs",
        role_code=None,
        target_child_person_id=child.id,
    )
    assert created["invitation"]["role_code"] == "PARENT"
    assert created["invitation"]["target_child_person_id"] == child.id

    headers, _ = _accept_headers(db, email="drugi.roditelj@primer.rs", given="Drugi")
    accepted = client.post(
        "/invitations/accept", headers=headers, json={"token": created["token"]}
    )
    assert accepted.status_code == 200, accepted.text
    ctx = accepted.json()["context"]
    assert ctx["role_code"] == "PARENT"

    parent_headers = {**headers, CONTEXT_HEADER: ctx["role_assignment_id"]}
    children = client.get("/parent/children", headers=parent_headers).json()
    assert [c["person_id"] for c in children] == [child.id]

    # The original guardian keeps their own access too, this was additive.
    original_headers = existing_guardian.headers
    original_children = client.get("/parent/children", headers=original_headers).json()
    assert [c["person_id"] for c in original_children] == [child.id]


def test_parent_invitation_requires_a_child_in_this_school(
    client: TestClient, db: Session
) -> None:
    staff = bootstrap_actor(db)
    resp = client.post(
        "/invitations",
        headers=staff.headers,
        json={
            "type": "PARENT",
            "target_email": "roditelj@primer.rs",
            "scope_type": "ORGANIZATION",
            "target_child_person_id": "per_ne_postoji",
        },
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# M8, trainer group-assignment path (§19.3)
# ---------------------------------------------------------------------------


def test_staff_invitation_can_scope_trainer_to_a_group(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    group_id = client.post("/groups", headers=staff.headers, json={"name": "Grupa A"}).json()["id"]

    created = _send(
        client,
        staff,
        target_email="trener.grupa@primer.rs",
        role_code="TRAINER",
        scope_type="GROUP",
        scope_ref_id=group_id,
    )
    assert created["invitation"]["scope_type"] == "GROUP"
    assert created["invitation"]["scope_ref_id"] == group_id

    headers, _ = _accept_headers(db, email="trener.grupa@primer.rs")
    accepted = client.post(
        "/invitations/accept", headers=headers, json={"token": created["token"]}
    )
    assert accepted.status_code == 200
    ctx = accepted.json()["context"]
    assert ctx["scope_type"] == "GROUP"
    assert ctx["scope_ref_id"] == group_id


def test_owner_role_cannot_be_scoped_to_a_group(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    group_id = client.post("/groups", headers=staff.headers, json={"name": "Grupa B"}).json()["id"]
    resp = client.post(
        "/invitations",
        headers=staff.headers,
        json={
            "type": "STAFF",
            "target_email": "x@primer.rs",
            "role_code": "OWNER",
            "scope_type": "GROUP",
            "scope_ref_id": group_id,
        },
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Permission gate + tenant isolation
# ---------------------------------------------------------------------------


def test_only_roles_area_can_send_invitations(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    trainer = add_actor(db, organization=staff.organization, role=RoleCode.TRAINER, given="Trener")
    finance_only = add_actor(
        db, organization=staff.organization, role=RoleCode.ADMIN, given="Finansije",
        granted_areas=["BILLING"],
    )

    for actor in (trainer, finance_only):
        resp = client.post(
            "/invitations",
            headers=actor.headers,
            json={
                "type": "STAFF",
                "target_email": "x@primer.rs",
                "role_code": "MANAGER",
                "scope_type": "ORGANIZATION",
            },
        )
        assert resp.status_code == 403


def test_invitation_admin_does_not_cross_tenants(client: TestClient, db: Session) -> None:
    org_a = bootstrap_actor(db, org_name="Klub A")
    created = _send(client, org_a, target_email="a@primer.rs", role_code="MANAGER")

    org_b = bootstrap_actor(db, org_name="Klub B")
    invitation_id = created["invitation"]["id"]
    assert client.get(f"/invitations/{invitation_id}", headers=org_b.headers).status_code == 404
    revoke_resp = client.post(
        f"/invitations/{invitation_id}/revoke", headers=org_b.headers, json={}
    )
    assert revoke_resp.status_code == 404
