"""Seed a realistic demo school into the local dev database.

Drives creation through the real HTTP endpoints (FastAPI TestClient, in-process
,  writes land in the same database the dev server uses) so every business
rule, validation, and side effect runs exactly as it would from the UI. Uses
the dev-header auth adapter to act as each seeded person; only works locally
(refused if ``allow_insecure_dev_auth`` is off).

Run: python -m scripts.seed_demo
"""

from __future__ import annotations

import datetime as dt
import sys

from app.config import get_settings
from app.db import SessionLocal
from app.domains.identity.accounts import create_account_with_identity
from app.domains.identity.auth_enums import (
    LOCAL_PASSWORD_ISSUER,
    LOCAL_PASSWORD_PROVIDER,
)
from app.domains.identity.auth_models import LocalPasswordCredential
from app.main import create_app
from app.security.identity_lookup import normalize_email
from app.security.password import hash_password
from fastapi.testclient import TestClient

DEV_PERSON_HEADER = "x-sokola-person-id"
CONTEXT_HEADER = "x-sokola-role-assignment-id"

ORG_NAME = "Sokolski Klub Demo"

# (given, family, login email, password), after creation each of these gets an
# email+password credential plus the email as a lookup identifier, so they can
# sign in for real afterward.
OWNER = ("Vladimir", "Batočanin", "vlasnik@sokola-demo.local", "vlasnik-demo-123")
MANAGER = ("Jovana", "Nikolić", "menadzer@sokola-demo.local", "menadzer-demo-123")
TRAINER = ("Marko", "Đorđević", "trener@sokola-demo.local", "trener-demo-123")
STUDENT_WITH_LOGIN = ("Mila", "Jovanović", "ucenik@sokola-demo.local", "ucenik-demo-123")

ROSTER_ONLY = [
    ("Petar", "Petrović"),
    ("Ana", "Anić"),
    ("Nikola", "Stanković"),
    ("Teodora", "Ilić"),
    ("Luka", "Pavlović"),
    ("Sara", "Kostić"),
    ("Filip", "Ristić"),
    ("Ivana", "Simić"),
]


def die(msg: str) -> None:
    print(f"✗ {msg}", file=sys.stderr)
    sys.exit(1)


def create_identity(client: TestClient, given: str, family: str) -> str:
    resp = client.post(
        "/internal/dev/identities", json={"given_name": given, "family_name": family}
    )
    if resp.status_code != 201:
        die(f"create identity {given} {family}: {resp.status_code} {resp.text}")
    return str(resp.json()["person_id"])


def link_login_identity(person_id: str, email: str, password: str) -> None:
    """Give the seeded person a real login: an email+password credential plus
    the email as a lookup identifier. The dev header this script uses only
    builds data, this is what lets each seeded user actually sign in
    afterward."""
    with SessionLocal() as db:
        _, identity = create_account_with_identity(
            db,
            person_id=person_id,
            provider_key=LOCAL_PASSWORD_PROVIDER,
            issuer=LOCAL_PASSWORD_ISSUER,
            subject=f"local:seed-{person_id}",
            login_email=normalize_email(email),
        )
        db.add(
            LocalPasswordCredential(
                auth_identity_id=identity.id, password_hash=hash_password(password)
            )
        )
        db.commit()


def main() -> None:
    settings = get_settings()
    if not settings.allow_insecure_dev_auth:
        die("SOKOLA_ALLOW_INSECURE_DEV_AUTH must be true, this script is local-dev only.")

    client = TestClient(create_app())

    print(f"Creating owner: {OWNER[0]} {OWNER[1]}")
    owner_id = create_identity(client, OWNER[0], OWNER[1])
    owner_headers = {DEV_PERSON_HEADER: owner_id}

    print(f"Creating school: {ORG_NAME}")
    org_resp = client.post(
        "/schools", headers=owner_headers, json={"name": ORG_NAME, "type": "SPORTS_CLUB"}
    )
    if org_resp.status_code != 201:
        die(f"create school: {org_resp.status_code} {org_resp.text}")
    org = org_resp.json()
    org_id = org["id"]

    me = client.get("/me", headers=owner_headers).json()
    owner_ctx = next(c for c in me["contexts"] if c["school_id"] == org_id)
    owner_headers = {**owner_headers, CONTEXT_HEADER: owner_ctx["role_assignment_id"]}
    link_login_identity(owner_id, OWNER[2], OWNER[3])

    def add_roster_person(given: str, family: str) -> str:
        resp = client.post(
            "/people", headers=owner_headers, json={"given_name": given, "family_name": family}
        )
        if resp.status_code != 201:
            die(f"add person {given} {family}: {resp.status_code} {resp.text}")
        return str(resp.json()["id"])

    def grant_role(person_id: str, role_code: str) -> None:
        resp = client.post(
            "/roles", headers=owner_headers, json={"person_id": person_id, "role_code": role_code}
        )
        if resp.status_code != 201:
            die(f"grant {role_code} to {person_id}: {resp.status_code} {resp.text}")

    print(f"Adding manager: {MANAGER[0]} {MANAGER[1]}")
    manager_id = add_roster_person(MANAGER[0], MANAGER[1])
    grant_role(manager_id, "MANAGER")
    link_login_identity(manager_id, MANAGER[2], MANAGER[3])

    print(f"Adding trainer: {TRAINER[0]} {TRAINER[1]}")
    trainer_id = add_roster_person(TRAINER[0], TRAINER[1])
    grant_role(trainer_id, "TRAINER")
    link_login_identity(trainer_id, TRAINER[2], TRAINER[3])

    print(f"Adding student with login: {STUDENT_WITH_LOGIN[0]} {STUDENT_WITH_LOGIN[1]}")
    student_login_id = add_roster_person(STUDENT_WITH_LOGIN[0], STUDENT_WITH_LOGIN[1])
    grant_role(student_login_id, "STUDENT")
    link_login_identity(student_login_id, STUDENT_WITH_LOGIN[2], STUDENT_WITH_LOGIN[3])

    print(f"Adding {len(ROSTER_ONLY)} roster-only members")
    roster_ids = [student_login_id] + [add_roster_person(g, f) for g, f in ROSTER_ONLY]

    print("Creating groups")
    groups = {}
    for name, capacity in [("Početnici", 12), ("Napredni", 10)]:
        resp = client.post(
            "/groups",
            headers=owner_headers,
            json={"name": name, "capacity_mode": "LIMITED", "capacity": capacity},
        )
        if resp.status_code != 201:
            die(f"create group {name}: {resp.status_code} {resp.text}")
        groups[name] = resp.json()["id"]

    print("Enrolling members into groups")
    for i, person_id in enumerate(roster_ids):
        group_id = groups["Početnici"] if i % 2 == 0 else groups["Napredni"]
        resp = client.post(
            f"/groups/{group_id}/members", headers=owner_headers, json={"person_id": person_id}
        )
        if resp.status_code != 201:
            die(f"enroll {person_id} in {group_id}: {resp.status_code} {resp.text}")

    print("Scheduling sessions (past + upcoming)")
    now = dt.datetime.now(dt.UTC).replace(minute=0, second=0, microsecond=0)
    session_offsets_days = [-14, -7, -3, 2, 9, 16]
    created_sessions = []
    for group_name, group_id in groups.items():
        for offset in session_offsets_days:
            starts = now + dt.timedelta(days=offset, hours=18)
            ends = starts + dt.timedelta(hours=1)
            draft = {
                "group_id": group_id,
                "starts_at": starts.isoformat(),
                "ends_at": ends.isoformat(),
                "title": f"Trening · {group_name}",
            }
            resp = client.post("/schedule/sessions", headers=owner_headers, json=draft)
            if resp.status_code != 201:
                die(f"create session for {group_name} @ {offset}d: {resp.status_code} {resp.text}")
            body = resp.json()
            created_sessions.append({**body, "offset": offset, "group_id": group_id})

    print("Recording attendance for past sessions")
    for s in created_sessions:
        if s["offset"] >= 0:
            continue
        att = client.get(f"/schedule/sessions/{s['id']}/attendance", headers=owner_headers).json()
        members_resp = client.get(f"/groups/{s['group_id']}/members", headers=owner_headers).json()
        member_ids = [m["person_id"] for m in members_resp]
        exceptions = []
        for i, pid in enumerate(member_ids):
            if i % 5 == 0:
                exceptions.append({"person_id": pid, "status": "ABSENT"})
            elif i % 5 == 1:
                exceptions.append({"person_id": pid, "status": "LATE"})
        resp = client.put(
            f"/schedule/sessions/{s['id']}/attendance",
            headers=owner_headers,
            json={"attendance_version": att["attendance_version"], "exceptions": exceptions},
        )
        if resp.status_code != 200:
            die(f"save attendance for {s['id']}: {resp.status_code} {resp.text}")

    print("Posting a billing run")
    for group_name, group_id in groups.items():
        preview = client.post(
            "/billing/runs/preview",
            headers=owner_headers,
            json={
                "group_id": group_id,
                "amount": 300000,
                "description": f"Članarina · {group_name}",
                "period_label": "Jul 2026",
            },
        )
        if preview.status_code != 200:
            die(f"preview billing for {group_name}: {preview.status_code} {preview.text}")
        pv = preview.json()
        posted = client.post(
            "/billing/runs",
            headers=owner_headers,
            json={
                "group_id": group_id,
                "amount": 300000,
                "description": f"Članarina · {group_name}",
                "period_label": "Jul 2026",
                "preview_hash": pv["preview_hash"],
            },
        )
        if posted.status_code != 201:
            die(f"post billing for {group_name}: {posted.status_code} {posted.text}")

    print("Recording a partial payment")
    charges = client.get("/charges?limit=5", headers=owner_headers).json()["items"]
    if charges:
        first = charges[0]
        resp = client.post(
            f"/charges/{first['id']}/payments",
            headers=owner_headers,
            json={"amount": 100000, "method": "CASH"},
        )
        if resp.status_code != 201:
            die(f"record payment: {resp.status_code} {resp.text}")

    print("Publishing an announcement")
    draft = {
        "title": "Dobrodošli u novu sezonu!",
        "body": "Treninzi počinju ovog meseca. Vidimo se na terenu!",
        "target_type": "SCHOOL",
        "target_group_id": None,
    }
    preview = client.post(
        "/communications/announcements/preview", headers=owner_headers, json=draft
    )
    if preview.status_code != 200:
        die(f"preview announcement: {preview.status_code} {preview.text}")
    pv = preview.json()
    published = client.post(
        "/communications/announcements",
        headers=owner_headers,
        json={**draft, "snapshot_hash": pv["snapshot_hash"]},
    )
    if published.status_code != 201:
        die(f"publish announcement: {published.status_code} {published.text}")

    print()
    print("=" * 60)
    print(f"Seeded '{ORG_NAME}', log in at http://localhost:5173 with email + password:")
    for label, who in [
        ("Owner (full access)", OWNER),
        ("Manager", MANAGER),
        ("Trainer", TRAINER),
        ("Student (own portal)", STUDENT_WITH_LOGIN),
    ]:
        print(f"  {label:<22} {who[2]}  /  {who[3]}")
    n_groups, n_roster, n_sessions = len(groups), len(roster_ids), len(created_sessions)
    print(f"  {n_groups} groups, {n_roster} roster members, {n_sessions} sessions")
    print("=" * 60)


if __name__ == "__main__":
    main()
