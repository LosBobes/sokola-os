"""CSV import for people/groups (PRD 11, issue #13). Integration tests against
real Postgres: upload -> preview (dry-run) -> commit, plus tenant isolation."""

from __future__ import annotations

from app.domains.identity.enums import RoleCode
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import Actor, add_actor, bootstrap_actor

CSV_HEADER = "given_name,family_name,group_name,local_member_code"


def _csv(rows: list[str]) -> str:
    return "\n".join([CSV_HEADER, *rows]) + "\n"


def _upload(client: TestClient, actor: Actor, content: str, filename: str = "clanovi.csv") -> dict:
    resp = client.post(
        "/import/uploads",
        headers=actor.headers,
        files={"file": (filename, content.encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _preview(client: TestClient, actor: Actor, batch_id: str) -> dict:
    resp = client.post(f"/import/uploads/{batch_id}/preview", headers=actor.headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _commit(client: TestClient, actor: Actor, batch_id: str) -> dict:
    resp = client.post(f"/import/uploads/{batch_id}/commit", headers=actor.headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _make_group(client: TestClient, actor: Actor, name: str) -> dict:
    resp = client.post("/groups", headers=actor.headers, json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Upload + preview happy path
# ---------------------------------------------------------------------------


def test_upload_and_preview_happy_path(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    _make_group(client, actor, "Mlađi pioniri")

    content = _csv(
        [
            "Ana,Marković,Mlađi pioniri,C-001",
            "Marko,Marković,,",
        ]
    )
    batch = _upload(client, actor, content)
    assert batch["status"] == "PENDING"
    assert batch["total_rows"] == 2
    assert batch["source_filename"] == "clanovi.csv"

    preview = _preview(client, actor, batch["id"])
    assert preview["batch"]["status"] == "PREVIEWED"
    assert preview["batch"]["valid_rows"] == 2
    assert preview["batch"]["invalid_rows"] == 0
    rows = preview["rows"]
    assert len(rows) == 2
    assert all(r["valid"] for r in rows)
    assert rows[0]["group_name"] == "Mlađi pioniri"
    assert rows[0]["duplicate_person_ids"] == []


def test_upload_rejects_missing_required_column(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    content = "given_name,group_name\nAna,Neka grupa\n"
    resp = client.post(
        "/import/uploads",
        headers=actor.headers,
        files={"file": ("bad.csv", content.encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 400
    assert "family_name" in resp.json()["error"]["details"]["required_columns"]


# ---------------------------------------------------------------------------
# Invalid rows: missing field, group not found
# ---------------------------------------------------------------------------


def test_preview_flags_missing_field_and_missing_group(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    content = _csv(
        [
            ",Bezimeni,,",  # missing given_name
            "Iva,Ivić,Nepostojeća grupa,",  # group doesn't exist
        ]
    )
    batch = _upload(client, actor, content)
    preview = _preview(client, actor, batch["id"])

    assert preview["batch"]["valid_rows"] == 0
    assert preview["batch"]["invalid_rows"] == 2

    missing_field_row, missing_group_row = preview["rows"]
    assert missing_field_row["valid"] is False
    assert "Ime i prezime" in missing_field_row["reason"]

    assert missing_group_row["valid"] is False
    assert "Nepostojeća grupa" in missing_group_row["reason"]


# ---------------------------------------------------------------------------
# Duplicate detection (mirrors GET /people/duplicates from #6)
# ---------------------------------------------------------------------------


def test_preview_flags_possible_duplicate_without_invalidating_row(
    client: TestClient, db: Session
) -> None:
    actor = bootstrap_actor(db)
    existing = client.post(
        "/people", headers=actor.headers, json={"given_name": "Petar", "family_name": "Petrović"}
    )
    assert existing.status_code == 201
    existing_id = existing.json()["id"]

    content = _csv(["Petar,Petrović,,"])
    batch = _upload(client, actor, content)
    preview = _preview(client, actor, batch["id"])

    row = preview["rows"][0]
    assert row["valid"] is True
    assert row["duplicate_person_ids"] == [existing_id]


# ---------------------------------------------------------------------------
# Commit: creates valid rows, skips invalid ones, partial-result counts
# ---------------------------------------------------------------------------


def test_commit_creates_valid_rows_and_skips_invalid_with_correct_counts(
    client: TestClient, db: Session
) -> None:
    actor = bootstrap_actor(db)
    group = _make_group(client, actor, "Balet")

    content = _csv(
        [
            "Mila,Ilić,Balet,B-100",
            ",Bezimeni,,",  # invalid: missing given_name
        ]
    )
    batch = _upload(client, actor, content)
    _preview(client, actor, batch["id"])
    committed = _commit(client, actor, batch["id"])

    assert committed["batch"]["status"] == "COMMITTED"
    assert committed["batch"]["created_rows"] == 1
    assert committed["batch"]["skipped_rows"] == 1

    outcomes = {r["row_number"]: r for r in committed["rows"]}
    assert outcomes[1]["outcome"] == "CREATED"
    assert outcomes[1]["person_id"] is not None
    assert outcomes[2]["outcome"] == "SKIPPED"
    assert outcomes[2]["person_id"] is None

    created_person_id = outcomes[1]["person_id"]
    person = client.get(f"/people/{created_person_id}", headers=actor.headers)
    assert person.status_code == 200
    assert person.json()["display_name"] == "Mila Ilić"

    members = client.get(f"/groups/{group['id']}/members", headers=actor.headers).json()
    assert [m["person_id"] for m in members] == [created_person_id]

    # Only one real person was created from the import, the invalid row never
    # touched Person. Total is 2: the imported person plus the staff actor
    # themselves (bootstrap_actor is also a Person with org membership).
    people = client.get("/people", headers=actor.headers).json()
    assert people["total"] == 2


def test_commit_requires_preview_first(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    batch = _upload(client, actor, _csv(["Ana,Anić,,"]))

    resp = client.post(f"/import/uploads/{batch['id']}/commit", headers=actor.headers)
    assert resp.status_code == 409


def test_commit_twice_conflicts(client: TestClient, db: Session) -> None:
    actor = bootstrap_actor(db)
    batch = _upload(client, actor, _csv(["Ana,Anić,,"]))
    _preview(client, actor, batch["id"])
    _commit(client, actor, batch["id"])

    resp = client.post(f"/import/uploads/{batch['id']}/commit", headers=actor.headers)
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_import_batch_invisible_to_other_org(client: TestClient, db: Session) -> None:
    org_a = bootstrap_actor(db, org_name="Klub A")
    org_b = bootstrap_actor(db, org_name="Klub B")

    batch = _upload(client, org_a, _csv(["Ana,Anić,,"]))

    assert (
        client.get(f"/import/uploads/{batch['id']}", headers=org_b.headers).status_code == 404
    )
    assert (
        client.post(f"/import/uploads/{batch['id']}/preview", headers=org_b.headers).status_code
        == 404
    )
    assert (
        client.post(f"/import/uploads/{batch['id']}/commit", headers=org_b.headers).status_code
        == 404
    )


def test_import_group_name_only_resolves_within_same_org(client: TestClient, db: Session) -> None:
    org_a = bootstrap_actor(db, org_name="Klub A")
    org_b = bootstrap_actor(db, org_name="Klub B")
    _make_group(client, org_b, "Deljena grupa")

    batch = _upload(client, org_a, _csv(["Ana,Anić,Deljena grupa,"]))
    preview = _preview(client, org_a, batch["id"])

    row = preview["rows"][0]
    assert row["valid"] is False
    assert "Deljena grupa" in row["reason"]


# ---------------------------------------------------------------------------
# Permission gate
# ---------------------------------------------------------------------------


def test_trainer_cannot_import(client: TestClient, db: Session) -> None:
    org = bootstrap_actor(db)
    trainer = add_actor(db, organization=org.organization, role=RoleCode.TRAINER, given="Trener")

    resp = client.post(
        "/import/uploads",
        headers=trainer.headers,
        files={"file": ("x.csv", _csv(["Ana,Anić,,"]).encode("utf-8"), "text/csv")},
    )
    assert resp.status_code == 403
