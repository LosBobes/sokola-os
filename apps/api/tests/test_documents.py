from __future__ import annotations

from typing import Any

from app.domains.identity.enums import RoleCode
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import Actor, add_actor, bootstrap_actor, make_child_with_guardian

PDF_BYTES = b"%PDF-1.4 minimal pdf content"


def _upload(
    client: TestClient,
    actor: Actor,
    *,
    filename: str = "ugovor.pdf",
    content: bytes = PDF_BYTES,
    content_type: str = "application/pdf",
    **form: Any,
) -> Any:
    return client.post(
        "/documents",
        headers=actor.headers,
        files={"file": (filename, content, content_type)},
        data=form,
    )


def test_upload_accepts_allowed_formats(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    formats = [
        ("a.pdf", "application/pdf"),
        ("a.jpg", "image/jpeg"),
        ("a.png", "image/png"),
        (
            "a.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    ]
    for filename, content_type in formats:
        resp = _upload(client, staff, filename=filename, content_type=content_type)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["filename"] == filename
        assert body["content_type"] == content_type
        assert body["visibility"] == "STAFF_ONLY"
        assert body["document_type"] == "GENERAL"


def test_upload_rejects_unsupported_format(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    resp = _upload(client, staff, filename="a.txt", content=b"hello", content_type="text/plain")
    assert resp.status_code == 400
    assert resp.json()["error"]["details"]["code"] == "UNSUPPORTED_FORMAT"


def test_upload_rejects_oversized_file(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    oversized = b"0" * (10 * 1024 * 1024 + 1)
    resp = _upload(client, staff, content=oversized)
    assert resp.status_code == 400
    assert resp.json()["error"]["details"]["code"] == "FILE_TOO_LARGE"


def test_upload_requires_permission(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    student = add_actor(db, school=staff.school, role=RoleCode.STUDENT)
    resp = _upload(client, student)
    assert resp.status_code == 403


def test_download_staff_only_document_forbidden_for_non_staff(
    client: TestClient, db: Session
) -> None:
    staff = bootstrap_actor(db)
    outsider = add_actor(db, school=staff.school, role=RoleCode.STUDENT)
    doc_id = _upload(client, staff).json()["id"]

    forbidden = client.get(f"/documents/{doc_id}/content", headers=outsider.headers)
    assert forbidden.status_code == 403

    ok = client.get(f"/documents/{doc_id}/content", headers=staff.headers)
    assert ok.status_code == 200
    assert ok.content == PDF_BYTES
    assert ok.headers["content-type"] == "application/pdf"


def test_download_subject_visibility_allows_subject_and_guardian(
    client: TestClient, db: Session
) -> None:
    staff = bootstrap_actor(db)
    guardian = add_actor(db, school=staff.school, role=RoleCode.PARENT)
    child = make_child_with_guardian(db, school=staff.school, guardian=guardian.person)
    other_guardian = add_actor(
        db, school=staff.school, role=RoleCode.PARENT, given="Nepovezan"
    )

    doc_id = _upload(
        client,
        staff,
        document_type="GENERAL",
        visibility="SUBJECT",
        subject_person_id=child.id,
    ).json()["id"]

    # Unrelated guardian cannot see it.
    denied = client.get(f"/documents/{doc_id}/content", headers=other_guardian.headers)
    assert denied.status_code == 403

    # The child's guardian can.
    allowed = client.get(f"/documents/{doc_id}/content", headers=guardian.headers)
    assert allowed.status_code == 200
    assert allowed.content == PDF_BYTES

    # Staff can always reach it too.
    staff_ok = client.get(f"/documents/{doc_id}/content", headers=staff.headers)
    assert staff_ok.status_code == 200


def test_subject_visibility_requires_school_member_subject(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    resp = _upload(
        client, staff, visibility="SUBJECT", subject_person_id="per_does_not_exist"
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["details"]["code"] == "SUBJECT_NOT_A_MEMBER"


def test_cross_school_access_is_not_found(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    other_school_staff = bootstrap_actor(db, org_name="Druga škola")
    doc_id = _upload(client, staff).json()["id"]

    metadata = client.get(f"/documents/{doc_id}", headers=other_school_staff.headers)
    assert metadata.status_code == 404

    content = client.get(f"/documents/{doc_id}/content", headers=other_school_staff.headers)
    assert content.status_code == 404


def test_list_documents_is_school_scoped_and_paginated(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    other_school_staff = bootstrap_actor(db, org_name="Druga škola")
    _upload(client, staff, filename="jedan.pdf")
    _upload(client, staff, filename="dva.pdf")
    _upload(client, other_school_staff, filename="tudje.pdf")

    resp = client.get("/documents", headers=staff.headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert {item["filename"] for item in body["items"]} == {"jedan.pdf", "dva.pdf"}

    limited = client.get("/documents?limit=1", headers=staff.headers)
    assert limited.json()["limit"] == 1
    assert len(limited.json()["items"]) == 1


def test_non_staff_list_only_sees_own_visible_documents(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    guardian = add_actor(db, school=staff.school, role=RoleCode.PARENT)
    child = make_child_with_guardian(db, school=staff.school, guardian=guardian.person)

    _upload(client, staff, filename="interno.pdf")  # STAFF_ONLY
    _upload(
        client,
        staff,
        filename="dete.pdf",
        visibility="SUBJECT",
        subject_person_id=child.id,
    )

    resp = client.get("/documents", headers=guardian.headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["filename"] == "dete.pdf"


def test_contract_acknowledgement_by_subject_and_guardian(
    client: TestClient, db: Session
) -> None:
    staff = bootstrap_actor(db)
    guardian = add_actor(db, school=staff.school, role=RoleCode.PARENT)
    child = make_child_with_guardian(db, school=staff.school, guardian=guardian.person)
    unrelated = add_actor(
        db, school=staff.school, role=RoleCode.PARENT, given="Nepovezan"
    )

    doc_id = _upload(
        client,
        staff,
        document_type="CONTRACT",
        visibility="SUBJECT",
        subject_person_id=child.id,
    ).json()["id"]

    # An unrelated person may not acknowledge (they can't even see it).
    denied = client.post(f"/documents/{doc_id}/acknowledge", headers=unrelated.headers)
    assert denied.status_code == 403

    ack = client.post(f"/documents/{doc_id}/acknowledge", headers=guardian.headers)
    assert ack.status_code == 200
    body = ack.json()
    assert body["acknowledged_at"] is not None
    assert body["acknowledged_by_person_id"] == guardian.person.id

    # Idempotent: acknowledging again doesn't move the timestamp/actor.
    ack_again = client.post(f"/documents/{doc_id}/acknowledge", headers=guardian.headers)
    assert ack_again.json()["acknowledged_at"] == body["acknowledged_at"]


def test_acknowledge_rejects_non_contract_document(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db)
    doc_id = _upload(client, staff, document_type="GENERAL").json()["id"]
    resp = client.post(f"/documents/{doc_id}/acknowledge", headers=staff.headers)
    assert resp.status_code == 400
    assert resp.json()["error"]["details"]["code"] == "NOT_A_CONTRACT"


def test_staff_cannot_acknowledge_on_behalf_of_subject(client: TestClient, db: Session) -> None:
    """Staff can administer (see) a SUBJECT contract but acknowledging is the
    subject's/guardian's act, not staff's."""
    staff = bootstrap_actor(db)
    guardian = add_actor(db, school=staff.school, role=RoleCode.PARENT)
    child = make_child_with_guardian(db, school=staff.school, guardian=guardian.person)
    doc_id = _upload(
        client,
        staff,
        document_type="CONTRACT",
        visibility="SUBJECT",
        subject_person_id=child.id,
    ).json()["id"]

    resp = client.post(f"/documents/{doc_id}/acknowledge", headers=staff.headers)
    assert resp.status_code == 403
