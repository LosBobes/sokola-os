from __future__ import annotations

from app.domains.identity.enums import RoleCode
from app.security.auth import DEV_PERSON_HEADER
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.factories import assign_role, make_organization, make_person


def test_me_requires_authentication(client: TestClient) -> None:
    resp = client.get("/me")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_me_lists_only_own_contexts(client: TestClient, db: Session) -> None:
    ana = make_person(db, given="Ana")
    marko = make_person(db, given="Marko")
    club = make_organization(db, name="Klub Soko")
    school = make_organization(db, name="Škola Ritam")

    assign_role(db, person=ana, organization=club, role=RoleCode.MANAGER)
    assign_role(db, person=ana, organization=school, role=RoleCode.TRAINER)
    assign_role(db, person=marko, organization=club, role=RoleCode.PARENT)

    resp = client.get("/me", headers={DEV_PERSON_HEADER: ana.id})
    assert resp.status_code == 200
    body = resp.json()
    assert body["person_id"] == ana.id
    orgs = {c["organization_name"]: c["role_code"] for c in body["contexts"]}
    # Ana sees exactly her two contexts, never Marko's, never orgs she has no role in.
    assert orgs == {"Klub Soko": "MANAGER", "Škola Ritam": "TRAINER"}


def test_contexts_endpoint_matches_me(client: TestClient, db: Session) -> None:
    ana = make_person(db, given="Ana")
    club = make_organization(db)
    assign_role(db, person=ana, organization=club, role=RoleCode.OWNER)

    resp = client.get("/me/contexts", headers={DEV_PERSON_HEADER: ana.id})
    assert resp.status_code == 200
    contexts = resp.json()
    assert len(contexts) == 1
    assert contexts[0]["role_code"] == "OWNER"
