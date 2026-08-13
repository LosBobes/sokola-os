"""Privacy domain (PRD 12): consent records, DSAR lifecycle, retention
periods, and the `has_active_consent` gating hook. Integration tests against
real Postgres."""

from __future__ import annotations

from app.domains.identity.enums import RoleCode
from app.domains.privacy.consent_gate import has_active_consent
from app.domains.privacy.enums import ConsentScope
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import add_actor, add_membership, bootstrap_actor, make_person

# ---------------------------------------------------------------------------
# Consent, record / list / withdraw
# ---------------------------------------------------------------------------


def test_record_and_list_consent(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    subject = make_person(db, given="Milica", family="Petrović")
    add_membership(db, person=subject, organization=staff.organization)

    created = client.post(
        "/consents",
        headers=staff.headers,
        json={"person_id": subject.id, "scope": "PHOTO_VIDEO", "note": "Usmena saglasnost"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["person_id"] == subject.id
    assert body["scope"] == "PHOTO_VIDEO"
    assert body["revoked_at"] is None
    assert body["granted_at"]

    listed = client.get("/consents", headers=staff.headers, params={"person_id": subject.id})
    assert listed.status_code == 200
    page = listed.json()
    assert page["total"] == 1
    assert page["items"][0]["id"] == body["id"]


def test_record_consent_requires_person_in_this_org(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    resp = client.post(
        "/consents",
        headers=staff.headers,
        json={"person_id": "per_ne_postoji", "scope": "DATA_PROCESSING"},
    )
    assert resp.status_code == 404


def test_withdraw_consent(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    subject = make_person(db, given="Nikola", family="Jovanović")
    add_membership(db, person=subject, organization=staff.organization)

    created = client.post(
        "/consents",
        headers=staff.headers,
        json={"person_id": subject.id, "scope": "MARKETING_COMMUNICATIONS"},
    ).json()

    withdrawn = client.post(
        f"/consents/{created['id']}/withdraw", headers=staff.headers, json={"note": "Na zahtev"}
    )
    assert withdrawn.status_code == 200
    assert withdrawn.json()["revoked_at"] is not None

    # Withdrawing an already-withdrawn consent is refused.
    again = client.post(f"/consents/{created['id']}/withdraw", headers=staff.headers, json={})
    assert again.status_code == 409


def test_consent_tenant_isolation(client: TestClient, db: Session) -> None:
    org_a = bootstrap_actor(db, org_name="Klub A")
    org_b = bootstrap_actor(db, org_name="Klub B")
    subject_a = make_person(db, given="A", family="Osoba")
    add_membership(db, person=subject_a, organization=org_a.organization)

    created = client.post(
        "/consents",
        headers=org_a.headers,
        json={"person_id": subject_a.id, "scope": "DATA_PROCESSING"},
    ).json()

    # Org B cannot list org A's subject consents (subject isn't visible to it)…
    assert (
        client.get(
            "/consents", headers=org_b.headers, params={"person_id": subject_a.id}
        ).status_code
        == 404
    )
    # …nor withdraw a consent that belongs to org A.
    withdraw_resp = client.post(
        f"/consents/{created['id']}/withdraw", headers=org_b.headers, json={}
    )
    assert withdraw_resp.status_code == 404


def test_only_privacy_area_can_record_consent(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    trainer = add_actor(db, organization=staff.organization, role=RoleCode.TRAINER, given="Trener")
    finance_only = add_actor(
        db,
        organization=staff.organization,
        role=RoleCode.ADMIN,
        given="Finansije",
        granted_areas=["BILLING"],
    )
    subject = make_person(db, given="Subjekat", family="Test")
    add_membership(db, person=subject, organization=staff.organization)

    for actor in (trainer, finance_only):
        resp = client.post(
            "/consents",
            headers=actor.headers,
            json={"person_id": subject.id, "scope": "DATA_PROCESSING"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# has_active_consent gating hook
# ---------------------------------------------------------------------------


def test_has_active_consent_true_then_false_after_withdrawal(
    client: TestClient, db: Session
) -> None:
    staff = bootstrap_actor(db)
    subject = make_person(db, given="Jelena", family="Ilić")
    add_membership(db, person=subject, organization=staff.organization)

    # No consent recorded yet.
    assert (
        has_active_consent(
            db, staff.organization.id, subject.id, ConsentScope.PHOTO_VIDEO
        )
        is False
    )

    created = client.post(
        "/consents",
        headers=staff.headers,
        json={"person_id": subject.id, "scope": "PHOTO_VIDEO"},
    ).json()

    db.expire_all()
    assert (
        has_active_consent(db, staff.organization.id, subject.id, ConsentScope.PHOTO_VIDEO)
        is True
    )
    # A different scope for the same person is unaffected.
    assert (
        has_active_consent(
            db, staff.organization.id, subject.id, ConsentScope.MARKETING_COMMUNICATIONS
        )
        is False
    )

    client.post(f"/consents/{created['id']}/withdraw", headers=staff.headers, json={})
    db.expire_all()
    assert (
        has_active_consent(db, staff.organization.id, subject.id, ConsentScope.PHOTO_VIDEO)
        is False
    )


# ---------------------------------------------------------------------------
# DSAR lifecycle
# ---------------------------------------------------------------------------


def test_dsar_lifecycle_pending_to_fulfilled(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    subject = make_person(db, given="Marko", family="Kovačević")
    add_membership(db, person=subject, organization=staff.organization)

    created = client.post(
        "/dsar-requests",
        headers=staff.headers,
        json={"person_id": subject.id, "request_type": "EXPORT", "note": "Traži izvoz podataka"},
    )
    assert created.status_code == 201, created.text
    req = created.json()
    assert req["status"] == "PENDING"

    started = client.post(f"/dsar-requests/{req['id']}/start", headers=staff.headers)
    assert started.status_code == 200
    assert started.json()["status"] == "IN_PROGRESS"

    # Cannot be started twice.
    restart = client.post(f"/dsar-requests/{req['id']}/start", headers=staff.headers)
    assert restart.status_code == 409

    fulfilled = client.post(
        f"/dsar-requests/{req['id']}/fulfill",
        headers=staff.headers,
        json={"note": "Podaci izvezeni i poslati e-poštom."},
    )
    assert fulfilled.status_code == 200
    body = fulfilled.json()
    assert body["status"] == "FULFILLED"
    assert body["decision_note"] == "Podaci izvezeni i poslati e-poštom."
    assert body["decided_at"] is not None

    # Already-decided requests cannot be decided again.
    again = client.post(
        f"/dsar-requests/{req['id']}/fulfill", headers=staff.headers, json={"note": "opet"}
    )
    assert again.status_code == 409


def test_dsar_rejection_directly_from_pending(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    subject = make_person(db, given="Ana", family="Simić")
    add_membership(db, person=subject, organization=staff.organization)

    req = client.post(
        "/dsar-requests",
        headers=staff.headers,
        json={"person_id": subject.id, "request_type": "ERASURE"},
    ).json()

    # A request may be rejected directly from PENDING (no forced "start" step).
    rejected = client.post(
        f"/dsar-requests/{req['id']}/reject",
        headers=staff.headers,
        json={"note": "Nema pravnog osnova za brisanje: aktivan ugovor."},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"


def test_dsar_list_and_get(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    subject = make_person(db, given="Petar", family="Nikolić")
    add_membership(db, person=subject, organization=staff.organization)

    created = client.post(
        "/dsar-requests",
        headers=staff.headers,
        json={"person_id": subject.id, "request_type": "ACCESS"},
    ).json()

    fetched = client.get(f"/dsar-requests/{created['id']}", headers=staff.headers)
    assert fetched.status_code == 200
    assert fetched.json()["id"] == created["id"]

    listed = client.get(
        "/dsar-requests", headers=staff.headers, params={"person_id": subject.id}
    ).json()
    assert listed["total"] == 1


def test_dsar_tenant_isolation(client: TestClient, db: Session) -> None:
    org_a = bootstrap_actor(db, org_name="Klub A")
    org_b = bootstrap_actor(db, org_name="Klub B")
    subject_a = make_person(db, given="A", family="Osoba")
    add_membership(db, person=subject_a, organization=org_a.organization)

    created = client.post(
        "/dsar-requests",
        headers=org_a.headers,
        json={"person_id": subject_a.id, "request_type": "ACCESS"},
    ).json()

    assert client.get(f"/dsar-requests/{created['id']}", headers=org_b.headers).status_code == 404
    assert (
        client.post(f"/dsar-requests/{created['id']}/start", headers=org_b.headers).status_code
        == 404
    )


# ---------------------------------------------------------------------------
# Retention periods
# ---------------------------------------------------------------------------


def test_retention_period_crud_and_deactivation(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)

    created = client.post(
        "/retention-periods",
        headers=staff.headers,
        json={"data_category": "DOCUMENTS", "retention_period_days": 1825, "note": "5 godina"},
    )
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["retention_period_days"] == 1825
    assert row["status"] == "ACTIVE"

    fetched = client.get(f"/retention-periods/{row['id']}", headers=staff.headers)
    assert fetched.status_code == 200

    updated = client.patch(
        f"/retention-periods/{row['id']}",
        headers=staff.headers,
        json={"retention_period_days": 2190},
    )
    assert updated.status_code == 200
    assert updated.json()["retention_period_days"] == 2190

    listed = client.get("/retention-periods", headers=staff.headers).json()
    assert listed["total"] == 1

    deactivated = client.post(
        f"/retention-periods/{row['id']}/deactivate", headers=staff.headers
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["status"] == "ARCHIVED"
    assert client.get("/retention-periods", headers=staff.headers).json()["total"] == 0


def test_retention_period_category_conflict_then_reuse_after_deactivation(
    client: TestClient, db: Session
) -> None:
    staff = bootstrap_actor(db)
    first = client.post(
        "/retention-periods",
        headers=staff.headers,
        json={"data_category": "ATTENDANCE_RECORDS", "retention_period_days": 365},
    )
    assert first.status_code == 201

    clash = client.post(
        "/retention-periods",
        headers=staff.headers,
        json={"data_category": "ATTENDANCE_RECORDS", "retention_period_days": 730},
    )
    assert clash.status_code == 409

    client.post(f"/retention-periods/{first.json()['id']}/deactivate", headers=staff.headers)
    reuse = client.post(
        "/retention-periods",
        headers=staff.headers,
        json={"data_category": "ATTENDANCE_RECORDS", "retention_period_days": 730},
    )
    assert reuse.status_code == 201


def test_retention_period_tenant_isolation(client: TestClient, db: Session) -> None:
    org_a = bootstrap_actor(db, org_name="Klub A")
    org_b = bootstrap_actor(db, org_name="Klub B")

    created = client.post(
        "/retention-periods",
        headers=org_a.headers,
        json={"data_category": "BILLING_RECORDS", "retention_period_days": 3650},
    ).json()

    assert (
        client.get(f"/retention-periods/{created['id']}", headers=org_b.headers).status_code
        == 404
    )
    # Org B may still create its own retention period for the same category.
    own = client.post(
        "/retention-periods",
        headers=org_b.headers,
        json={"data_category": "BILLING_RECORDS", "retention_period_days": 1000},
    )
    assert own.status_code == 201
