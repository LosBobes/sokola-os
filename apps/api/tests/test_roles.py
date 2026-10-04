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
    member = add_actor(db, school=staff.school, role=RoleCode.STUDENT, given="Ana")

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
    member = add_actor(db, school=staff.school, role=RoleCode.STUDENT, given="X")
    resp = client.post(
        "/roles",
        headers=staff.headers,
        json={"person_id": member.person.id, "role_code": "OWNER"},
    )
    assert resp.status_code == 400


def test_assign_role_requires_school_membership(client: TestClient, db: Session) -> None:
    """The actor is an OWNER so that the 404 is attributable to the membership.

    It used to be the default MANAGER, which worked only while a MANAGER could
    assign MANAGER. Since F-47 that is refused on rank, before the target is
    resolved — so the same call would now return 403 and prove nothing about
    membership. Rank has its own tests below.
    """
    staff = bootstrap_actor(db, role=RoleCode.OWNER)
    stranger = make_person(db, given="Stranac")
    resp = client.post(
        "/roles", headers=staff.headers, json={"person_id": stranger.id, "role_code": "MANAGER"}
    )
    assert resp.status_code == 404


def test_update_granted_areas_restricts_and_clears(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    admin = add_actor(db, school=staff.school, role=RoleCode.ADMIN, given="Admin")

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
        school=staff.school,
        role=RoleCode.ADMIN,
        given="Ograničen",
        granted_areas=["ROLES", "BILLING"],
    )
    target = add_actor(
        db, school=staff.school, role=RoleCode.ADMIN, given="Meta"
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
            "scope_type": "SCHOOL",
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
            "scope_type": "SCHOOL",
            "granted_areas": ["BILLING"],
        },
    )
    assert invite_within_bounds.status_code == 201


def test_suspend_and_revoke_assignment(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    trainer = add_actor(db, school=staff.school, role=RoleCode.TRAINER, given="T")

    suspended = client.post(
        f"/roles/{trainer.assignment.id}/suspend",
        headers=staff.headers,
        json={"reason_code": "TEMPORARY_LEAVE"},
    )
    assert suspended.status_code == 200
    assert suspended.json()["status"] == "SUSPENDED"

    # Suspending again is refused (not active).
    assert (
        client.post(
            f"/roles/{trainer.assignment.id}/suspend",
            headers=staff.headers,
            json={"reason_code": "TEMPORARY_LEAVE"},
        ).status_code
        == 409
    )

    revoked = client.post(
        f"/roles/{trainer.assignment.id}/revoke",
        headers=staff.headers,
        json={"reason_code": "RESPONSIBILITY_ENDED"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "REVOKED"

    assert (
        client.post(
            f"/roles/{trainer.assignment.id}/revoke",
            headers=staff.headers,
            json={"reason_code": "RESPONSIBILITY_ENDED"},
        ).status_code
        == 409
    )


def test_list_role_assignments(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    add_actor(db, school=staff.school, role=RoleCode.TRAINER, given="Trener")

    body = client.get("/roles", headers=staff.headers).json()
    role_codes = {item["role_code"] for item in body["items"]}
    assert {"MANAGER", "TRAINER"} <= role_codes


# ---------------------------------------------------------------------------
# M8, trainer scoped to a group, direct assignment path
# ---------------------------------------------------------------------------


def test_assign_role_scoped_to_group(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    group_id = client.post("/groups", headers=staff.headers, json={"name": "G1"}).json()["id"]
    trainer = add_actor(db, school=staff.school, role=RoleCode.STUDENT, given="X")

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


def test_assign_role_scope_must_reference_a_real_group_in_this_school(
    client: TestClient, db: Session
) -> None:
    staff = bootstrap_actor(db)
    member = add_actor(db, school=staff.school, role=RoleCode.STUDENT, given="X")
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
        f"/roles/{staff.assignment.id}/revoke",
        headers=staff.headers,
        json={"reason_code": "RESPONSIBILITY_ENDED"},
    )
    assert resp.status_code == 409


def test_last_owner_cannot_be_suspended(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db, role=RoleCode.OWNER)
    resp = client.post(
        f"/roles/{staff.assignment.id}/suspend",
        headers=staff.headers,
        json={"reason_code": "TEMPORARY_LEAVE"},
    )
    assert resp.status_code == 409


def test_second_owner_can_be_revoked_but_not_the_last(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db, role=RoleCode.OWNER)
    second_owner = add_actor(
        db, school=staff.school, role=RoleCode.OWNER, given="Drugi"
    )

    first = client.post(
        f"/roles/{second_owner.assignment.id}/revoke",
        headers=staff.headers,
        json={"reason_code": "RESPONSIBILITY_ENDED"},
    )
    assert first.status_code == 200

    # Now only one active owner remains, it is protected.
    second = client.post(
        f"/roles/{staff.assignment.id}/revoke",
        headers=staff.headers,
        json={"reason_code": "RESPONSIBILITY_ENDED"},
    )
    assert second.status_code == 409


# ---------------------------------------------------------------------------
# M5, ownership add/transfer
# ---------------------------------------------------------------------------


def test_transfer_ownership_adds_and_revokes_previous(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db, role=RoleCode.OWNER)
    successor = add_actor(
        db, school=staff.school, role=RoleCode.MANAGER, given="Naslednik"
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
        db, school=staff.school, role=RoleCode.MANAGER, given="Suvlasnik"
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
    ok = client.post(
        f"/roles/{staff.assignment.id}/revoke",
        headers=staff.headers,
        json={"reason_code": "RESPONSIBILITY_ENDED"},
    )
    assert ok.status_code == 200


def test_transfer_ownership_rejects_already_an_owner(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db, role=RoleCode.OWNER)
    other_owner = add_actor(
        db, school=staff.school, role=RoleCode.OWNER, given="Već"
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
    trainer = add_actor(db, school=staff.school, role=RoleCode.TRAINER, given="T")
    resp = client.post(
        "/roles",
        headers=trainer.headers,
        json={"person_id": trainer.person.id, "role_code": "MANAGER"},
    )
    assert resp.status_code == 403


def test_role_admin_does_not_cross_tenants(client: TestClient, db: Session) -> None:
    """Org B's *owner* is used, for the same reason as the test above.

    A MANAGER would now be refused on rank before the tenant check ran, which
    would leave this asserting the wrong thing entirely. With an OWNER the
    refusal is the tenant boundary again, which is what the test is for.
    """
    org_a = bootstrap_actor(db, org_name="Klub A")
    member_a = add_actor(db, school=org_a.school, role=RoleCode.STUDENT, given="A")

    org_b = bootstrap_actor(db, org_name="Klub B", role=RoleCode.OWNER)
    resp = client.post(
        "/roles",
        headers=org_b.headers,
        json={"person_id": member_a.person.id, "role_code": "MANAGER"},
    )
    assert resp.status_code == 404  # member_a not visible from org B

    suspend_resp = client.post(
        f"/roles/{member_a.assignment.id}/suspend",
        headers=org_b.headers,
        json={"reason_code": "TEMPORARY_LEAVE"},
    )
    assert suspend_resp.status_code == 404


# ---------------------------------------------------------------------------
# P1, deactivate/reactivate school
# ---------------------------------------------------------------------------


def test_deactivate_locks_out_context_then_owner_reactivates(
    client: TestClient, db: Session
) -> None:
    staff = bootstrap_actor(db, role=RoleCode.OWNER)

    deactivated = client.post("/schools/current/deactivate", headers=staff.headers)
    assert deactivated.status_code == 200
    assert deactivated.json()["id"] == staff.school.id

    # The context is now unreachable, even for the same owner.
    blocked = client.get("/schools/current", headers=staff.headers)
    assert blocked.status_code == 403

    reactivated = client.post(
        f"/schools/{staff.school.id}/reactivate",
        headers={DEV_PERSON_HEADER: staff.person.id},
    )
    assert reactivated.status_code == 200

    # Context resolution works again.
    restored = client.get("/schools/current", headers=staff.headers)
    assert restored.status_code == 200


def test_reactivate_requires_active_owner(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db, role=RoleCode.OWNER)
    manager = add_actor(
        db, school=staff.school, role=RoleCode.MANAGER, given="Menadžer"
    )
    client.post("/schools/current/deactivate", headers=staff.headers)

    denied = client.post(
        f"/schools/{staff.school.id}/reactivate",
        headers={DEV_PERSON_HEADER: manager.person.id},
    )
    assert denied.status_code == 403


def test_reactivate_unknown_school_is_not_found(client: TestClient, db: Session) -> None:
    person = make_person(db, given="Niko")
    resp = client.post(
        "/schools/org_ne_postoji/reactivate",
        headers={DEV_PERSON_HEADER: person.id},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# F-47 — §2.4 rank: an actor assigns only strictly below themselves
# ---------------------------------------------------------------------------


def test_a_manager_cannot_assign_a_manager_or_an_admin(
    client: TestClient, db: Session
) -> None:
    """F-47, and the positive control is the point.

    `ROLE_DEFAULT_AREAS` gives OWNER, MANAGER and ADMIN the same areas, and
    role administration is gated on one of them — so before this a MANAGER
    assigning MANAGER returned 201, and each manager it created could create
    more. ADMIN is refused for the same reason: F-29 resolved it to M05
    MANAGER, so it carries MANAGER's rank.

    The TRAINER case runs in the same test rather than separately, because a
    rank guard that refused *everything* would satisfy the two negatives and
    break the product. Both halves have to hold together.
    """
    mgr = bootstrap_actor(db, org_name="Rang", role=RoleCode.MANAGER, given="Menadzer")
    target = make_person(db, given="Cilj", family="Osoba")
    from tests.factories import add_membership

    add_membership(db, person=target, school=mgr.school)
    db.commit()

    for refused in ("MANAGER", "ADMIN"):
        resp = client.post(
            "/roles",
            headers=mgr.headers,
            json={"person_id": target.id, "role_code": refused},
        )
        assert resp.status_code == 403, (refused, resp.text)
        assert resp.json()["error"]["code"] == "FORBIDDEN"

    allowed = client.post(
        "/roles", headers=mgr.headers, json={"person_id": target.id, "role_code": "TRAINER"}
    )
    assert allowed.status_code == 201, allowed.text


def test_an_owner_may_still_assign_a_manager(client: TestClient, db: Session) -> None:
    """The rank rule is "strictly below", so OWNER keeps what it had.

    Worth its own test: the cheap way to implement F-47 is to forbid granting
    MANAGER at all, which would pass the test above and quietly take the
    ability away from owners too.
    """
    owner = bootstrap_actor(db, org_name="RangO", role=RoleCode.OWNER, given="Vlasnik")
    target = make_person(db, given="Novi", family="Menadzer")
    from tests.factories import add_membership

    add_membership(db, person=target, school=owner.school)
    db.commit()

    resp = client.post(
        "/roles", headers=owner.headers, json={"person_id": target.id, "role_code": "MANAGER"}
    )
    assert resp.status_code == 201, resp.text


def test_the_local_ranks_match_the_registry() -> None:
    """The copy in `identity/policy.py` must not drift from M05 §2.4.

    The ranks are duplicated on purpose — the architecture gate forbids a
    domain's `policy` module importing another domain, so `policy.py` cannot
    read the authorization registry. A duplicated constant with nothing
    watching it is how the two quietly disagree, and the disagreement would
    show up as the wrong people being allowed to grant roles.

    The mapping from this repo's `RoleCode` to M05's role keys is F-29 and
    F-30's; `STUDENT` has no counterpart and is excluded, which is why it
    carries a rank below every assignable role rather than a mirrored one.
    """
    from app.application.effective_permissions import canonical_role_key
    from app.domains.authorization import registry
    from app.domains.identity.policy import _ADMINISTRATIVE_RANK

    registry_rank = {role.key: role.administrative_rank for role in registry.ROLES}

    checked = 0
    for role_code, local_rank in _ADMINISTRATIVE_RANK.items():
        if role_code is RoleCode.STUDENT:
            continue
        key = canonical_role_key(role_code)
        assert key in registry_rank, key
        assert local_rank == registry_rank[key], (role_code, key, local_rank)
        checked += 1
    assert checked >= 5, checked
    assert _ADMINISTRATIVE_RANK[RoleCode.STUDENT] < min(
        rank for code, rank in _ADMINISTRATIVE_RANK.items() if code is not RoleCode.STUDENT
    )


# ---------------------------------------------------------------------------
# F-48 / F-51 — REVOKED is history, and the database says so
# ---------------------------------------------------------------------------


def test_a_revoked_role_is_regranted_as_a_new_assignment(
    client: TestClient, db: Session
) -> None:
    """F-48: the revoked row stays, and the new grant is a different id.

    Previously the only thing the schema allowed was reviving the revoked row,
    so one id ended up carrying a revocation and its reversal. The old row is
    asserted still REVOKED, not merely absent from the response — the point is
    that the history survives beside the new grant.
    """
    owner = bootstrap_actor(db, org_name="Ponovo", role=RoleCode.OWNER, given="Vlasnik")
    trainer = add_actor(db, school=owner.school, role=RoleCode.TRAINER, given="Trener")
    original_id = trainer.assignment.id

    revoked = client.post(
        f"/roles/{original_id}/revoke",
        headers=owner.headers,
        json={"reason_code": "RESPONSIBILITY_ENDED"},
    )
    assert revoked.status_code == 200, revoked.text

    again = client.post(
        "/roles",
        headers=owner.headers,
        json={"person_id": trainer.person.id, "role_code": "TRAINER"},
    )
    assert again.status_code == 201, again.text
    assert again.json()["id"] != original_id

    db.expire_all()
    from app.domains.identity.enums import RoleAssignmentStatus
    from app.domains.identity.models import RoleAssignment

    old = db.get(RoleAssignment, original_id)
    assert old is not None
    assert old.status is RoleAssignmentStatus.REVOKED
    fresh = db.get(RoleAssignment, again.json()["id"])
    assert fresh is not None
    assert fresh.status is RoleAssignmentStatus.ACTIVE


def test_the_database_refuses_a_second_open_assignment(db: Session) -> None:
    """F-51: the index binds even though `scope_ref_id` is null.

    This is the case the old constraint missed. Nulls are distinct inside a
    normal unique index, and `scope_ref_id` is null for every school-scoped
    role, so two ACTIVE rows for one person, school and role were accepted and
    only the service's read-then-insert stood in the way. Written against the
    constraint directly because that is the only way to reach it — the point of
    a last-resort guard is that it holds when the application check loses a
    race.
    """
    import pytest
    from app.domains.identity.models import RoleAssignment
    from sqlalchemy.exc import IntegrityError

    owner = bootstrap_actor(db, org_name="Duplikat", role=RoleCode.OWNER, given="Vlasnik")
    duplicate = RoleAssignment(
        person_id=owner.person.id,
        school_id=owner.school.id,
        role_code=RoleCode.OWNER,
        scope_type=owner.assignment.scope_type,
        scope_ref_id=None,
    )
    assert owner.assignment.scope_ref_id is None, "the null case is the one that regressed"
    db.add(duplicate)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# ---------------------------------------------------------------------------
# F-49 — the reason vocabulary, the mandatory note, and the stamped triple
# ---------------------------------------------------------------------------


def test_a_note_is_required_for_the_codes_the_contract_marks(
    client: TestClient, db: Session
) -> None:
    """§2.10 marks some codes with `*`: those need a note, the rest do not.

    Both directions matter. Demanding a note everywhere would be the easy
    over-correction and would make the common cases tedious; demanding it
    nowhere is the state this replaces. `SECURITY_REVIEW` describes a decision
    somebody took, and without the note the record says a decision happened
    and not why.
    """
    owner = bootstrap_actor(db, org_name="Beleska", role=RoleCode.OWNER, given="Vlasnik")
    trainer = add_actor(db, school=owner.school, role=RoleCode.TRAINER, given="Trener")

    missing = client.post(
        f"/roles/{trainer.assignment.id}/suspend",
        headers=owner.headers,
        json={"reason_code": "SECURITY_REVIEW"},
    )
    assert missing.status_code == 422, missing.text

    with_note = client.post(
        f"/roles/{trainer.assignment.id}/suspend",
        headers=owner.headers,
        json={"reason_code": "SECURITY_REVIEW", "reason_note": "Prijava sa terena."},
    )
    assert with_note.status_code == 200, with_note.text

    db.expire_all()
    from app.domains.identity.models import RoleAssignment

    row = db.get(RoleAssignment, trainer.assignment.id)
    assert row is not None
    assert row.suspend_reason_note == "Prijava sa terena."


def test_an_unmarked_code_needs_no_note(client: TestClient, db: Session) -> None:
    """The other half of the pair above, as its own test so a regression that
    made every code require a note could not hide behind it."""
    owner = bootstrap_actor(db, org_name="BezBeleske", role=RoleCode.OWNER, given="Vlasnik")
    trainer = add_actor(db, school=owner.school, role=RoleCode.TRAINER, given="Trener")

    resp = client.post(
        f"/roles/{trainer.assignment.id}/revoke",
        headers=owner.headers,
        json={"reason_code": "RESPONSIBILITY_ENDED"},
    )
    assert resp.status_code == 200, resp.text

    db.expire_all()
    from app.domains.identity.models import RoleAssignment

    row = db.get(RoleAssignment, trainer.assignment.id)
    assert row is not None
    assert row.revoke_reason_note is None
    assert row.revoke_reason_code is not None
    assert row.revoked_at is not None
    assert row.revoked_by_person_id == owner.person.id


def test_the_audit_summary_names_the_code_and_not_the_note(
    client: TestClient, db: Session
) -> None:
    """The note stays on the row; the audit log gets the code.

    The predecessor interpolated the free-text reason into the summary, so
    client-supplied text landed in a trail that is read far more widely than
    the assignment it describes — the same shape as F-42's leak in a different
    column. What an audit reader needs is a value they can filter on.
    """
    from sqlalchemy import text as sql_text

    owner = bootstrap_actor(db, org_name="Trag49", role=RoleCode.OWNER, given="Vlasnik")
    trainer = add_actor(db, school=owner.school, role=RoleCode.TRAINER, given="Trener")
    secret = "Poverljiv detalj iz prijave"

    resp = client.post(
        f"/roles/{trainer.assignment.id}/revoke",
        headers=owner.headers,
        json={"reason_code": "SECURITY_REVOKE", "reason_note": secret},
    )
    assert resp.status_code == 200, resp.text

    summaries = [
        r[0]
        for r in db.execute(
            sql_text(
                "SELECT summary FROM audit_log WHERE entity_type = 'role_assignment'"
                " AND entity_id = :i"
            ),
            {"i": trainer.assignment.id},
        ).all()
    ]
    assert summaries, "the revocation should be audited"
    joined = " ".join(summaries)
    assert "SECURITY_REVOKE" in joined
    assert secret not in joined


def test_the_database_refuses_a_half_written_revocation(db: Session) -> None:
    """§2.5: all three of the triple, or none.

    Written against the constraint because the service always writes all
    three — which is exactly why the constraint matters. A future code path
    that set the status and forgot the stamp would leave a revoked assignment
    that cannot say who revoked it or why, and the audit trail outlives the
    person who could have told you.
    """
    import pytest
    from app.domains.identity.enums import RoleAssignmentStatus
    from sqlalchemy.exc import IntegrityError

    owner = bootstrap_actor(db, org_name="PolaTrojke", role=RoleCode.OWNER, given="Vlasnik")
    trainer = add_actor(db, school=owner.school, role=RoleCode.TRAINER, given="Trener")

    trainer.assignment.status = RoleAssignmentStatus.REVOKED
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
