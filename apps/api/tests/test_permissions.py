"""Per-area permission layer (issues #1/#2).

Access must follow GRANTED AREAS, not the role *name*: an ADMIN restricted to
finances must not reach roster/other ADMIN-gated surfaces, while an unrestricted
assignment keeps exactly the access its role had before this layer existed.
"""

from __future__ import annotations

import pytest
from app.common.errors import ForbiddenError
from app.domains.identity.enums import RoleCode, RoleScopeType
from app.security.context import RequestContext
from app.security.permissions import (
    ROLE_DEFAULT_AREAS,
    PermissionArea,
    effective_areas,
    require_permission,
)
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from tests.factories import (
    Actor,
    add_actor,
    bootstrap_actor,
    make_child_with_guardian,
)


def _ctx(
    role: RoleCode, granted_areas: tuple[str, ...] | None = None
) -> RequestContext:
    return RequestContext(
        person_id="per_1",
        role_assignment_id="rol_1",
        organization_id="org_1",
        role_code=role,
        scope_type=RoleScopeType.ORGANIZATION,
        granted_areas=granted_areas,
    )


# --- effective_areas ------------------------------------------------------


def test_effective_areas_none_is_full_role_default() -> None:
    assert effective_areas(RoleCode.MANAGER, None) == ROLE_DEFAULT_AREAS[RoleCode.MANAGER]
    assert effective_areas(RoleCode.TRAINER, None) == frozenset({PermissionArea.ATTENDANCE})


def test_effective_areas_restriction_narrows() -> None:
    granted = frozenset({PermissionArea.BILLING})
    assert effective_areas(RoleCode.ADMIN, granted) == frozenset({PermissionArea.BILLING})


def test_effective_areas_cannot_escalate_beyond_role_default() -> None:
    # TRAINER only defaults to ATTENDANCE; granting BILLING confers nothing.
    granted = frozenset({PermissionArea.BILLING, PermissionArea.ATTENDANCE})
    assert effective_areas(RoleCode.TRAINER, granted) == frozenset({PermissionArea.ATTENDANCE})


# --- require_permission guard ---------------------------------------------


def test_require_permission_allows_and_blocks() -> None:
    ctx = _ctx(RoleCode.ADMIN, granted_areas=("BILLING",))
    require_permission(PermissionArea.BILLING)(ctx)  # allowed → no raise
    with pytest.raises(ForbiddenError):
        require_permission(PermissionArea.PEOPLE)(ctx)


def test_require_permission_role_name_alone_is_not_enough() -> None:
    # An ADMIN by name, but restricted to BILLING, is blocked on PEOPLE.
    ctx = _ctx(RoleCode.ADMIN, granted_areas=("BILLING",))
    with pytest.raises(ForbiddenError):
        require_permission(PermissionArea.PEOPLE)(ctx)


# --- HTTP: role name alone does not grant area access ---------------------


def _create_person(client: TestClient, actor: Actor) -> Response:
    """POST /people (createPerson) is the PEOPLE-area-guarded roster write."""
    return client.post(
        "/people", headers=actor.headers, json={"given_name": "Novi", "family_name": "Č"}
    )


def _group_with_members(client: TestClient, actor: Actor, count: int) -> str:
    group_id = client.post("/groups", headers=actor.headers, json={"name": "G"}).json()["id"]
    for i in range(count):
        pid = client.post(
            "/people", headers=actor.headers, json={"given_name": f"Č{i}", "family_name": "L"}
        ).json()["id"]
        client.post(
            f"/groups/{group_id}/members", headers=actor.headers, json={"person_id": pid}
        )
    return group_id


def test_finance_only_admin_denied_on_people_allowed_on_billing(
    client: TestClient, db: Session
) -> None:
    # Full-access staff seed the data the finance-only admin will bill.
    owner = bootstrap_actor(db, role=RoleCode.MANAGER)
    group_id = _group_with_members(client, owner, 2)

    # An ADMIN in the SAME org, invited "for finances only".
    finance_admin = add_actor(
        db,
        organization=owner.organization,
        role=RoleCode.ADMIN,
        given="Finansije",
        granted_areas=[PermissionArea.BILLING.value],
    )

    # Denied on a PEOPLE route despite being an ADMIN by name.
    denied = _create_person(client, finance_admin)
    assert denied.status_code == 403

    # Allowed on a BILLING route.
    allowed = client.post(
        "/billing/runs/preview",
        headers=finance_admin.headers,
        json={
            "group_id": group_id,
            "amount_minor": 300000,
            "description": "Članarina",
            "period_label": "2026-09",
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["total_minor"] == 600000


# --- HTTP: default (granted_areas=None) preserves prior access ------------


def test_default_grant_preserves_manager_roster_access(
    client: TestClient, db: Session
) -> None:
    manager = bootstrap_actor(db, role=RoleCode.MANAGER)
    assert manager.assignment.granted_areas is None
    assert _create_person(client, manager).status_code == 201


def test_default_grant_preserves_admin_finance_access(
    client: TestClient, db: Session
) -> None:
    owner = bootstrap_actor(db, role=RoleCode.MANAGER)
    group_id = _group_with_members(client, owner, 1)
    admin = add_actor(db, organization=owner.organization, role=RoleCode.ADMIN, given="Admin")
    preview = client.post(
        "/billing/runs/preview",
        headers=admin.headers,
        json={
            "group_id": group_id,
            "amount_minor": 100000,
            "description": "Č",
            "period_label": "2026-09",
        },
    )
    assert preview.status_code == 200


def test_default_grant_preserves_trainer_attendance_but_not_roster(
    client: TestClient, db: Session
) -> None:
    trainer = bootstrap_actor(db, role=RoleCode.TRAINER, given="Trener")
    # TRAINER keeps ATTENDANCE: the guard passes, only the (missing) session 404s.
    sheet = client.get(
        "/schedule/sessions/ses_missing/attendance", headers=trainer.headers
    )
    assert sheet.status_code == 404
    # TRAINER never had roster (PEOPLE) write access.
    assert _create_person(client, trainer).status_code == 403


def test_default_grant_preserves_parent_access(client: TestClient, db: Session) -> None:
    staff = bootstrap_actor(db, role=RoleCode.MANAGER)
    parent = add_actor(
        db, organization=staff.organization, role=RoleCode.PARENT, given="Roditelj"
    )
    make_child_with_guardian(db, organization=staff.organization, guardian=parent.person)
    children = client.get("/parent/children", headers=parent.headers)
    assert children.status_code == 200
    assert len(children.json()) == 1
    # A parent is not staff.
    assert _create_person(client, parent).status_code == 403


def test_student_has_no_area_access(client: TestClient, db: Session) -> None:
    student = bootstrap_actor(db, role=RoleCode.STUDENT, given="Đak")
    assert _create_person(client, student).status_code == 403


# --- tenant isolation still holds -----------------------------------------


def test_area_grant_does_not_cross_tenants(client: TestClient, db: Session) -> None:
    # Staff in org A create a person; an admin in org B (same area access, other
    # tenant) must not see it — the org re-check is independent of the area layer.
    org_a = bootstrap_actor(db, org_name="Klub A", role=RoleCode.MANAGER)
    person_id = client.post(
        "/people", headers=org_a.headers, json={"given_name": "Tajna", "family_name": "A"}
    ).json()["id"]

    org_b = bootstrap_actor(db, org_name="Klub B", role=RoleCode.ADMIN, given="Drugi")
    leaked = client.get(f"/people/{person_id}", headers=org_b.headers)
    assert leaked.status_code == 404
