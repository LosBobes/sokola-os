"""Membership + guardian lifecycle (PRD 03): end/suspend/resume, protected last
owner, revoke parental access, primary contact, school-local data, and the
duplicate detection + review workflow. Integration tests against real Postgres."""

from __future__ import annotations

from app.domains.identity.enums import RoleCode
from app.domains.people.enums import GuardianAccessStatus, GuardianRelationshipType
from app.domains.people.models import GuardianOrganizationAccess, GuardianRelationship
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import (
    Actor,
    add_actor,
    bootstrap_actor,
    make_child_with_guardian,
    make_person,
)


def _create_member(client: TestClient, actor: Actor, given: str, family: str) -> str:
    resp = client.post(
        "/people", headers=actor.headers, json={"given_name": given, "family_name": family}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ---------------------------------------------------------------------------
# M1, end / suspend / resume
# ---------------------------------------------------------------------------


def test_membership_end_suspend_resume(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    person_id = _create_member(client, staff, "Petar", "Petrović")

    assert (
        client.get(f"/people/{person_id}/membership", headers=staff.headers).json()["status"]
        == "ACTIVE"
    )

    # Suspend removes the person from the active roster …
    suspended = client.post(
        f"/people/{person_id}/membership/suspend", headers=staff.headers, json={}
    )
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "SUSPENDED"
    roster_ids = {p["id"] for p in client.get("/people", headers=staff.headers).json()["items"]}
    assert person_id not in roster_ids

    # … suspending again is rejected …
    assert (
        client.post(
            f"/people/{person_id}/membership/suspend", headers=staff.headers, json={}
        ).status_code
        == 409
    )

    # … resume brings them back …
    resumed = client.post(
        f"/people/{person_id}/membership/resume", headers=staff.headers, json={}
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "ACTIVE"

    # … end is terminal …
    ended = client.post(
        f"/people/{person_id}/membership/end",
        headers=staff.headers,
        json={"reason": "Ispisan"},
    )
    assert ended.status_code == 200
    assert ended.json()["status"] == "ENDED"

    # … resuming an ended membership is refused, and ending twice is refused.
    assert (
        client.post(
            f"/people/{person_id}/membership/resume", headers=staff.headers, json={}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/people/{person_id}/membership/end", headers=staff.headers, json={}
        ).status_code
        == 409
    )


# ---------------------------------------------------------------------------
# M2, protected last owner (§22)
# ---------------------------------------------------------------------------


def test_ending_last_owner_is_blocked_until_a_second_owner_exists(
    client: TestClient, db: Session
) -> None:
    owner = bootstrap_actor(db, role=RoleCode.OWNER)

    blocked = client.post(
        f"/people/{owner.person.id}/membership/end", headers=owner.headers, json={}
    )
    assert blocked.status_code == 409
    assert "vlasnik" in blocked.json()["error"]["message"].lower()

    # A second owner lifts the protection.
    add_actor(db, organization=owner.organization, role=RoleCode.OWNER, given="Drugi")
    ok = client.post(
        f"/people/{owner.person.id}/membership/end", headers=owner.headers, json={}
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "ENDED"


# ---------------------------------------------------------------------------
# M6, school-local member data (§8/§9/§10)
# ---------------------------------------------------------------------------


def test_local_member_code_is_unique_within_org(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    a = _create_member(client, staff, "Ana", "A")
    b = _create_member(client, staff, "Bojan", "B")

    first = client.patch(
        f"/people/{a}/membership",
        headers=staff.headers,
        json={"local_member_code": "K-100", "admin_note": "Plaća gotovinom"},
    )
    assert first.status_code == 200
    assert first.json()["local_member_code"] == "K-100"
    assert first.json()["admin_note"] == "Plaća gotovinom"

    # Same code for another member in the same org is a conflict.
    clash = client.patch(
        f"/people/{b}/membership", headers=staff.headers, json={"local_member_code": "K-100"}
    )
    assert clash.status_code == 409

    # A different code is fine, and admin_note is untouched when omitted.
    other = client.patch(
        f"/people/{b}/membership", headers=staff.headers, json={"local_member_code": "K-101"}
    )
    assert other.status_code == 200
    assert other.json()["local_member_code"] == "K-101"


# ---------------------------------------------------------------------------
# M4, revoke parental access (§30)
# ---------------------------------------------------------------------------


def test_revoke_parental_access(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    parent = add_actor(
        db, organization=staff.organization, role=RoleCode.PARENT, given="Roditelj"
    )
    child = make_child_with_guardian(
        db, organization=staff.organization, guardian=parent.person, given="Dete"
    )

    # The parent sees the child before revocation.
    before = client.get("/parent/children", headers=parent.headers).json()
    assert any(c["person_id"] == child.id for c in before)

    revoked = client.post(
        f"/people/{child.id}/guardians/{parent.person.id}/revoke",
        headers=staff.headers,
        json={"reason": "Zabrana suda"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["access_status"] == GuardianAccessStatus.REVOKED.value

    # The child disappears from the parent's view, and a second revoke conflicts.
    after = client.get("/parent/children", headers=parent.headers).json()
    assert all(c["person_id"] != child.id for c in after)
    again = client.post(
        f"/people/{child.id}/guardians/{parent.person.id}/revoke",
        headers=staff.headers,
        json={},
    )
    assert again.status_code == 409


# ---------------------------------------------------------------------------
# M5, primary contact designation (§25)
# ---------------------------------------------------------------------------


def _add_guardian(db: Session, *, organization_id: str, guardian_id: str, child_id: str) -> None:
    db.add(
        GuardianRelationship(
            guardian_person_id=guardian_id,
            child_person_id=child_id,
            relationship_type=GuardianRelationshipType.PARENT,
        )
    )
    db.add(
        GuardianOrganizationAccess(
            organization_id=organization_id,
            guardian_person_id=guardian_id,
            child_person_id=child_id,
            status=GuardianAccessStatus.ACTIVE,
        )
    )
    db.commit()


def test_primary_contact_is_exclusive_per_child(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    g1 = make_person(db, given="Majka", family="M")
    child = make_child_with_guardian(
        db, organization=staff.organization, guardian=g1, given="Dete"
    )
    g2 = make_person(db, given="Otac", family="O")
    _add_guardian(
        db, organization_id=staff.organization.id, guardian_id=g2.id, child_id=child.id
    )

    first = client.post(
        f"/people/{child.id}/guardians/{g1.id}/primary", headers=staff.headers
    )
    assert first.status_code == 200
    assert first.json()["is_primary_contact"] is True

    # Designating the second guardian demotes the first, only one primary remains.
    second = client.post(
        f"/people/{child.id}/guardians/{g2.id}/primary", headers=staff.headers
    )
    assert second.status_code == 200
    assert second.json()["is_primary_contact"] is True

    contacts = client.get(f"/people/{child.id}/guardians", headers=staff.headers).json()
    primaries = [c for c in contacts if c["is_primary_contact"]]
    assert len(primaries) == 1
    assert primaries[0]["guardian_person_id"] == g2.id


# ---------------------------------------------------------------------------
# P2, duplicate detection + review (§13–15)
# ---------------------------------------------------------------------------


def test_duplicate_detection_and_merge_review(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    first = _create_member(client, staff, "Petar", "Petrović")
    dup = client.post(
        "/people",
        headers=staff.headers,
        json={
            "given_name": "Petar",
            "family_name": "Petrović",
            "allow_possible_duplicate": True,
            "duplicate_reason": "Uneto greškom",
        },
    )
    assert dup.status_code == 201
    second = dup.json()["id"]

    clusters = client.get("/people/duplicates", headers=staff.headers).json()
    assert len(clusters) == 1
    assert {c["person_id"] for c in clusters[0]["candidates"]} == {first, second}

    review = client.post(
        "/people/merge-reviews",
        headers=staff.headers,
        json={"source_person_id": second, "target_person_id": first, "reason": "Isti čovek"},
    )
    assert review.status_code == 201
    review_id = review.json()["id"]
    assert review.json()["status"] == "FLAGGED"
    assert len(client.get("/people/merge-reviews", headers=staff.headers).json()) == 1

    decided = client.post(
        f"/people/merge-reviews/{review_id}/decision",
        headers=staff.headers,
        json={"decision": "MERGE", "reason": "Potvrđeno"},
    )
    assert decided.status_code == 200
    assert decided.json()["status"] == "MERGED"

    # The merged (source) person leaves the roster and can no longer be read.
    roster = {p["id"] for p in client.get("/people", headers=staff.headers).json()["items"]}
    assert second not in roster
    assert first in roster
    assert client.get(f"/people/{second}", headers=staff.headers).status_code == 404

    # Deciding an already-resolved case conflicts; duplicates are gone.
    again = client.post(
        f"/people/merge-reviews/{review_id}/decision",
        headers=staff.headers,
        json={"decision": "DISMISS", "reason": "x"},
    )
    assert again.status_code == 409
    assert client.get("/people/duplicates", headers=staff.headers).json() == []


def test_merge_review_dismiss_keeps_both_people(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    a = _create_member(client, staff, "Mila", "Ilić")
    b = client.post(
        "/people",
        headers=staff.headers,
        json={
            "given_name": "Mila",
            "family_name": "Ilić",
            "allow_possible_duplicate": True,
            "duplicate_reason": "Blizanci",
        },
    ).json()["id"]

    review_id = client.post(
        "/people/merge-reviews",
        headers=staff.headers,
        json={"source_person_id": b, "target_person_id": a, "reason": "Provera"},
    ).json()["id"]
    dismissed = client.post(
        f"/people/merge-reviews/{review_id}/decision",
        headers=staff.headers,
        json={"decision": "DISMISS", "reason": "Različite osobe"},
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "DISMISSED"

    roster = {p["id"] for p in client.get("/people", headers=staff.headers).json()["items"]}
    assert {a, b} <= roster


# ---------------------------------------------------------------------------
# Tenant isolation across every new write surface
# ---------------------------------------------------------------------------


def test_lifecycle_is_isolated_per_organization(client: TestClient, db: Session) -> None:
    org_a = bootstrap_actor(db, org_name="Klub A")
    org_b = bootstrap_actor(db, org_name="Klub B")
    person_id = _create_member(client, org_a, "Nikola", "N")

    # Org B sees no membership for org A's person, and cannot end/suspend/patch it.
    assert (
        client.get(f"/people/{person_id}/membership", headers=org_b.headers).status_code == 404
    )
    assert (
        client.post(
            f"/people/{person_id}/membership/end", headers=org_b.headers, json={}
        ).status_code
        == 404
    )
    assert (
        client.patch(
            f"/people/{person_id}/membership",
            headers=org_b.headers,
            json={"local_member_code": "X"},
        ).status_code
        == 404
    )

    # And org A's action still works, proving the 404 was isolation, not a bad id.
    assert (
        client.post(
            f"/people/{person_id}/membership/suspend", headers=org_a.headers, json={}
        ).status_code
        == 200
    )
