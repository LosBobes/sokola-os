"""Role assignment + permission-change endpoints (§25/§26), protected last
owner (§14), ownership add/transfer (§14), and school deactivate/reactivate
(§31). Integration tests against real Postgres."""

from __future__ import annotations

from app.domains.identity.enums import RoleCode
from app.security.auth import DEV_PERSON_HEADER
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import add_actor, bootstrap_actor, make_person

# ---------------------------------------------------------------------------
# M3, assign / list / permission-change / suspend / revoke
# ---------------------------------------------------------------------------


def test_assign_role_to_existing_member(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    member = add_actor(db, organization=staff.organization, role=RoleCode.STUDENT, given="Ana")

    resp = client.post(
        "/roles",
        headers=staff.headers,
        json={"person_id": member.person.id, "role_code": "TRAINER"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["role_code"] == "TRAINER"
    assert body["status"] == "ACTIVE"
    assert body["granted_areas"] is None

    # Assigning the exact same role/scope again is refused.
    dup = client.post(
        "/roles",
        headers=staff.headers,
        json={"person_id": member.person.id, "role_code": "TRAINER"},
    )
    assert dup.status_code == 409


def test_assign_role_rejects_owner_use_transfer_instead(
    client: TestClient, db: Session
) -> None:
    staff = bootstrap_actor(db)
    member = add_actor(db, organization=staff.organization, role=RoleCode.STUDENT, given="X")
    resp = client.post(
        "/roles",
        headers=staff.headers,
        json={"person_id": member.person.id, "role_code": "OWNER"},
    )
    assert resp.status_code == 400


def test_assign_role_requires_org_membership(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    stranger = make_person(db, given="Stranac")
    resp = client.post(
        "/roles", headers=staff.headers, json={"person_id": stranger.id, "role_code": "MANAGER"}
    )
    assert resp.status_code == 404


def test_update_granted_areas_restricts_and_clears(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    admin = add_actor(db, organization=staff.organization, role=RoleCode.ADMIN, given="Admin")

    restrict = client.patch(
        f"/roles/{admin.assignment.id}/granted-areas",
        headers=staff.headers,
        json={"granted_areas": ["BILLING"]},
    )
    assert restrict.status_code == 200
    assert restrict.json()["granted_areas"] == ["BILLING"]

    # An area outside the role's default is rejected, a restriction can only
    # narrow, never escalate (§19.2/§25.5).
    escalate = client.patch(
        f"/roles/{admin.assignment.id}/granted-areas",
        headers=staff.headers,
        json={"granted_areas": ["NOT_A_REAL_AREA"]},
    )
    assert escalate.status_code == 400

    clear = client.patch(
        f"/roles/{admin.assignment.id}/granted-areas",
        headers=staff.headers,
        json={"granted_areas": None},
    )
    assert clear.status_code == 200
    assert clear.json()["granted_areas"] is None


def test_restricted_admin_cannot_grant_areas_beyond_their_own(
    client: TestClient, db: Session
) -> None:
    # An ADMIN restricted to just ROLES+BILLING must not be able to launder
    # that into broader access, for anyone including themselves, by
    # granting a wider set than they themselves effectively hold (§19.2/§25.5).
    staff = bootstrap_actor(db)
    restricted_admin = add_actor(
        db,
        organization=staff.organization,
        role=RoleCode.ADMIN,
        given="Ograničen",
        granted_areas=["ROLES", "BILLING"],
    )
    target = add_actor(
        db, organization=staff.organization, role=RoleCode.ADMIN, given="Meta"
    )

    # Cannot grant a third party more than the restricted admin itself holds.
    escalate_other = client.patch(
        f"/roles/{target.assignment.id}/granted-areas",
        headers=restricted_admin.headers,
        json={"granted_areas": ["PEOPLE"]},
    )
    assert escalate_other.status_code == 400

    # Cannot self-escalate by clearing their own restriction to the full
    # (unrestricted) ADMIN default either.
    self_escalate = client.patch(
        f"/roles/{restricted_admin.assignment.id}/granted-areas",
        headers=restricted_admin.headers,
        json={"granted_areas": None},
    )
    assert self_escalate.status_code == 400

    # Narrowing to a set they still hold (ROLES stays, BILLING stays) is fine.
    narrow = client.patch(
        f"/roles/{restricted_admin.assignment.id}/granted-areas",
        headers=restricted_admin.headers,
        json={"granted_areas": ["ROLES", "BILLING"]},
    )
    assert narrow.status_code == 200

    # Same bound applies to inviting a new staff member, an unrestricted
    # ADMIN invite (granted_areas omitted) would exceed what this restricted
    # actor itself holds.
    invite_escalate = client.post(
        "/invitations",
        headers=restricted_admin.headers,
        json={
            "type": "STAFF",
            "role_code": "ADMIN",
            "target_email": "novi@example.com",
            "scope_type": "ORGANIZATION",
        },
    )
    assert invite_escalate.status_code == 400

    # But inviting within the areas they actually hold succeeds.
    invite_within_bounds = client.post(
        "/invitations",
        headers=restricted_admin.headers,
        json={
            "type": "STAFF",
            "role_code": "ADMIN",
            "target_email": "u-granicama@example.com",
            "scope_type": "ORGANIZATION",
            "granted_areas": ["BILLING"],
        },
    )
    assert invite_within_bounds.status_code == 201


def test_suspend_and_revoke_assignment(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    trainer = add_actor(db, organization=staff.organization, role=RoleCode.TRAINER, given="T")

    suspended = client.post(
        f"/roles/{trainer.assignment.id}/suspend", headers=staff.headers, json={}
    )
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "SUSPENDED"

    # Suspending again is refused (not active).
    assert (
        client.post(
            f"/roles/{trainer.assignment.id}/suspend", headers=staff.headers, json={}
        ).status_code
        == 409
    )

    revoked = client.post(
        f"/roles/{trainer.assignment.id}/revoke",
        headers=staff.headers,
        json={"reason": "Napustio klub"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "REVOKED"

    assert (
        client.post(
            f"/roles/{trainer.assignment.id}/revoke", headers=staff.headers, json={}
        ).status_code
        == 409
    )


def test_list_role_assignments(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    add_actor(db, organization=staff.organization, role=RoleCode.TRAINER, given="Trener")

    body = client.get("/roles", headers=staff.headers).json()
    role_codes = {item["role_code"] for item in body["items"]}
    assert {"MANAGER", "TRAINER"} <= role_codes


# ---------------------------------------------------------------------------
# M8, trainer scoped to a group, direct assignment path
# ---------------------------------------------------------------------------


def test_assign_role_scoped_to_group(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    group_id = client.post("/groups", headers=staff.headers, json={"name": "G1"}).json()["id"]
    trainer = add_actor(db, organization=staff.organization, role=RoleCode.STUDENT, given="X")

    resp = client.post(
        "/roles",
        headers=staff.headers,
        json={
            "person_id": trainer.person.id,
            "role_code": "TRAINER",
            "scope_type": "GROUP",
            "scope_ref_id": group_id,
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["scope_type"] == "GROUP"
    assert resp.json()["scope_ref_id"] == group_id


def test_assign_role_scope_must_reference_a_real_group_in_this_org(
    client: TestClient, db: Session
) -> None:
    staff = bootstrap_actor(db)
    member = add_actor(db, organization=staff.organization, role=RoleCode.STUDENT, given="X")
    resp = client.post(
        "/roles",
        headers=staff.headers,
        json={
            "person_id": member.person.id,
            "role_code": "TRAINER",
            "scope_type": "GROUP",
            "scope_ref_id": "grp_ne_postoji",
        },
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# M4, protected last owner
# ---------------------------------------------------------------------------


def test_last_owner_cannot_be_revoked(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db, role=RoleCode.OWNER)
    resp = client.post(
        f"/roles/{staff.assignment.id}/revoke", headers=staff.headers, json={}
    )
    assert resp.status_code == 409


def test_last_owner_cannot_be_suspended(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db, role=RoleCode.OWNER)
    resp = client.post(
        f"/roles/{staff.assignment.id}/suspend", headers=staff.headers, json={}
    )
    assert resp.status_code == 409


def test_second_owner_can_be_revoked_but_not_the_last(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db, role=RoleCode.OWNER)
    second_owner = add_actor(
        db, organization=staff.organization, role=RoleCode.OWNER, given="Drugi"
    )

    first = client.post(
        f"/roles/{second_owner.assignment.id}/revoke", headers=staff.headers, json={}
    )
    assert first.status_code == 200

    # Now only one active owner remains, it is protected.
    second = client.post(f"/roles/{staff.assignment.id}/revoke", headers=staff.headers, json={})
    assert second.status_code == 409


# ---------------------------------------------------------------------------
# M5, ownership add/transfer
# ---------------------------------------------------------------------------


def test_transfer_ownership_adds_and_revokes_previous(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db, role=RoleCode.OWNER)
    successor = add_actor(
        db, organization=staff.organization, role=RoleCode.MANAGER, given="Naslednik"
    )

    resp = client.post(
        "/roles/ownership/transfer",
        headers=staff.headers,
        json={
            "new_owner_person_id": successor.person.id,
            "revoke_from_person_id": staff.person.id,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["new_owner"]["role_code"] == "OWNER"
    assert body["new_owner"]["status"] == "ACTIVE"
    assert body["revoked_owner"]["status"] == "REVOKED"

    # The school never had zero owners, this never trips the last-owner guard,
    # because the new owner was granted before the old one was revoked.
    remaining = client.get("/roles", headers=successor.headers).json()["items"]
    owners = [r for r in remaining if r["role_code"] == "OWNER" and r["status"] == "ACTIVE"]
    assert len(owners) == 1
    assert owners[0]["person_id"] == successor.person.id


def test_transfer_ownership_add_only_keeps_both_owners(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db, role=RoleCode.OWNER)
    co_owner = add_actor(
        db, organization=staff.organization, role=RoleCode.MANAGER, given="Suvlasnik"
    )

    resp = client.post(
        "/roles/ownership/transfer",
        headers=staff.headers,
        json={"new_owner_person_id": co_owner.person.id},
    )
    assert resp.status_code == 200
    assert resp.json()["revoked_owner"] is None

    # Both are now active owners, neither is the sole one, so both are
    # individually revocable.
    ok = client.post(f"/roles/{staff.assignment.id}/revoke", headers=staff.headers, json={})
    assert ok.status_code == 200


def test_transfer_ownership_rejects_already_an_owner(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db, role=RoleCode.OWNER)
    other_owner = add_actor(
        db, organization=staff.organization, role=RoleCode.OWNER, given="Već"
    )
    resp = client.post(
        "/roles/ownership/transfer",
        headers=staff.headers,
        json={"new_owner_person_id": other_owner.person.id},
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Permission gate + tenant isolation
# ---------------------------------------------------------------------------


def test_only_roles_area_can_administer_roles(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    trainer = add_actor(db, organization=staff.organization, role=RoleCode.TRAINER, given="T")
    resp = client.post(
        "/roles",
        headers=trainer.headers,
        json={"person_id": trainer.person.id, "role_code": "MANAGER"},
    )
    assert resp.status_code == 403


def test_role_admin_does_not_cross_tenants(client: TestClient, db: Session) -> None:
    org_a = bootstrap_actor(db, org_name="Klub A")
    member_a = add_actor(db, organization=org_a.organization, role=RoleCode.STUDENT, given="A")

    org_b = bootstrap_actor(db, org_name="Klub B")
    resp = client.post(
        "/roles",
        headers=org_b.headers,
        json={"person_id": member_a.person.id, "role_code": "MANAGER"},
    )
    assert resp.status_code == 404  # member_a not visible from org B

    suspend_resp = client.post(
        f"/roles/{member_a.assignment.id}/suspend", headers=org_b.headers, json={}
    )
    assert suspend_resp.status_code == 404


# ---------------------------------------------------------------------------
# P1, deactivate/reactivate school
# ---------------------------------------------------------------------------


def test_deactivate_locks_out_context_then_owner_reactivates(
    client: TestClient, db: Session
) -> None:
    staff = bootstrap_actor(db, role=RoleCode.OWNER)

    deactivated = client.post("/organizations/current/deactivate", headers=staff.headers)
    assert deactivated.status_code == 200
    assert deactivated.json()["id"] == staff.organization.id

    # The context is now unreachable, even for the same owner.
    blocked = client.get("/organizations/current", headers=staff.headers)
    assert blocked.status_code == 403

    reactivated = client.post(
        f"/organizations/{staff.organization.id}/reactivate",
        headers={DEV_PERSON_HEADER: staff.person.id},
    )
    assert reactivated.status_code == 200

    # Context resolution works again.
    restored = client.get("/organizations/current", headers=staff.headers)
    assert restored.status_code == 200


def test_reactivate_requires_active_owner(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db, role=RoleCode.OWNER)
    manager = add_actor(
        db, organization=staff.organization, role=RoleCode.MANAGER, given="Menadžer"
    )
    client.post("/organizations/current/deactivate", headers=staff.headers)

    denied = client.post(
        f"/organizations/{staff.organization.id}/reactivate",
        headers={DEV_PERSON_HEADER: manager.person.id},
    )
    assert denied.status_code == 403


def test_reactivate_unknown_organization_is_not_found(client: TestClient, db: Session) -> None:
    person = make_person(db, given="Niko")
    resp = client.post(
        "/organizations/org_ne_postoji/reactivate",
        headers={DEV_PERSON_HEADER: person.id},
    )
    assert resp.status_code == 404
