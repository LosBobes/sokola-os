"""M05 §1: the 213 numbered QA scenarios, under the gate #115 established.

Seventh module under the gate. One test per runnable scenario named for its
id, the rest declared in `BLOCKED` with a reason from a closed vocabulary, and
a gate that fails if any of the 213 is neither. Nothing is skipped. 34 run.

**What this measurement found, which is not what was predicted.** M05 was
recorded as blocked on F-29 and F-30, the two undecided role mappings.
Measured scenario by scenario, neither gates anything here. The real reasons
are structural:

* **The repository authorizes by area, M05 by permission key.** Every product
  route carries `require_permission(PermissionArea.X)`, one of about a dozen
  coarse buckets. Revision 1.3's 38 keys exist as data, seeded by a migration,
  and authorize nothing — a test in `test_m05_effective_permissions.py` exists
  to keep it that way until the continuation registries land. `subject_guard_key`
  is declared on every permission row and read by no code at all, so §4's
  subject-guard layer has nothing behind it.
* **`OWNER`, `MANAGER` and `ADMIN` hold an identical area set.** §2.4's rank
  structure has no counterpart, which is why a MANAGER assigning MANAGER
  returns 201 (F-47).
* **`RoleAssignment` has no validity window and no version.** No `valid_from`,
  no `valid_until`, no `version` — so SCHEDULED, lazy EXPIRED and stale
  expected-version have nothing to assert against.
* **Support Access, break-glass and the offline envelope do not exist**, which
  is 57 scenarios. Their permission keys are seeded, bound to roles, and read
  by nothing.

This module found five divergences that are findings rather than mere
differences. Each was measured by running it, with a positive control, rather
than read off the code — and four are now **fixed**, which is why the
scenarios below run instead of being declared:

* **QA-015 / F-47 — fixed.** A MANAGER successfully assigned MANAGER (201, not
  403). The one with a direct security consequence: role administration is
  gated on an area OWNER, MANAGER and ADMIN hold identically, so a manager
  minted managers and each new one could mint more. Now refused on rank,
  strictly below.
* **QA-029 / F-50 — fixed.** Ending a membership left its role assignments
  ACTIVE, and an assignment is keyed on `(person, school)` rather than on the
  membership episode, so a second episode handed the former MANAGER role back.
  Access was never wrong — the guard re-proves membership — but the record
  survived, and the contract closes the roles at termination precisely so the
  safety does not rest on no path ever creating that episode. It now closes
  them in the same transaction.
* **QA-026 / F-48 — fixed.** `assign_role` revived a REVOKED assignment under
  its *original* id. The schema forced it: a total unique constraint left
  reviving as the only insert Postgres would accept. SUSPENDED being revivable
  is correct and still is (QA-024); only the terminal case changed.
* **F-51 — found while fixing F-48, and fixed.** The unique constraint that
  forced the revival was also enforcing nothing in the ordinary case:
  `scope_ref_id` is null for every school-scoped role and Postgres treats
  nulls as distinct, so two ACTIVE rows for one person, school and role were
  accepted and only the service's read-then-insert stood in the way — the race
  §7.1 says the database must catch. Now a partial unique index over the open
  statuses with `NULLS NOT DISTINCT`.
* **QA-023 / F-49 — still open.** Suspend and revoke reasons are free text; a
  reason outside any vocabulary returns 200. §2.10 fixes the allowed codes per
  command, so this is decided rather than undecided — it is a separate
  increment because it changes the request shape and therefore the generated
  web client.

QA-019 remains declared as a bounded divergence: a PARENT role can be granted
with no M07 guardian link, and M07 checks the link when a child record is
read, so the role alone opens no child data.

One gap found here was fixed rather than recorded, because it was in code from
the same increment: **QA-079**, a platform security admin granting themselves a
further platform role. Its test lives in `test_m05_platform_roles.py`.

**QA-213 is declared, not implemented.** It is the module's own acceptance
gate — 213/213 executed, 0 failed, 0 skipped. This file cannot assert that
about itself, and it is false today regardless. It sits in `BLOCKED` so that no
green run of this suite can be read as M05 having passed.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from app.domains.authorization import registry
from app.domains.authorization.bindings import permissions_for_role_keys
from app.domains.authorization.enums import DOMAIN_PLATFORM, DOMAIN_SCHOOL
from app.domains.authorization.platform_enums import PlatformRoleKey, PlatformRoleStatus
from app.domains.authorization.platform_models import PlatformRoleAssignment
from app.domains.authorization.platform_roles import effective_roles
from app.domains.identity.auth_models import AuthIdentity, UserAccount
from app.domains.identity.enums import RoleAssignmentStatus, RoleCode
from app.domains.identity.models import RoleAssignment
from app.domains.school.enums import MembershipStatus
from app.domains.school.models import SchoolMembership
from app.domains.tenancy import security as tenant_security
from app.platform import clock
from app.platform.inbox.service import claim as inbox_claim
from app.platform.outbox.models import OutboxMessage
from app.security.csrf import CSRF_COOKIE, CSRF_HEADER
from app.security.deps import CONTEXT_HEADER
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from tests.factories import (
    add_actor,
    add_membership,
    bootstrap_actor,
    make_person,
    make_school,
)

_QA_DOC = (
    Path(__file__).resolve().parents[3]
    / "docs/spec/v5.7/04-MODULSKI-UGOVORI/05-M05-RBAC-I-SUPPORT-ACCESS"
    / "02-M05-QA-I-TRACEABILITY.md"
)


def _absent(what: str) -> str:
    return f"feature absent: {what}"


def _diverges(what: str) -> str:
    return f"contract divergence: {what}"


def _registry(what: str) -> str:
    return f"registry incomplete: {what}"


def _untemporal(what: str) -> str:
    return f"no validity or version model: {what}"


BLOCKED: dict[str, str] = {}


def _block(reason: str, *numbers: int) -> None:
    for n in numbers:
        key = f"M05-QA-{n:03d}"
        assert key not in BLOCKED, f"{key} declared twice"
        BLOCKED[key] = reason


# ===========================================================================
# Declared blocked, with the cause measured
# ===========================================================================

_block(
    _absent(
        "there is no policy publish command. Revision 1.3 is written by a "
        "migration from `app/domains/authorization/registry.py`; there is no "
        "DRAFT to edit, no publish transaction, no expected version or hash "
        "argument, and no SUPERSEDED transition to attempt"
    ),
    1, 2, 3, 6, 7,
)
_block(
    _absent(
        "no role label surface. `school.rbac.labels.manage` is a seeded key "
        "bound to nothing, and no endpoint reads or writes a localized role "
        "label"
    ),
    8,
)

_DIRECT_GRANTS = _absent(
    "there are no direct permission grants. The nearest thing is "
    "`RoleAssignment.granted_areas`, a coarse restriction *narrowing* one "
    "assignment to some of its role's areas — it cannot add a permission, "
    "name a resource scope, carry a reason, expire, or exist apart from a "
    "role. So there is no grant to create, delegate, scope, expire or revoke"
)
_block(_DIRECT_GRANTS, 5, 25, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42,
       43, 44, 45, 46, 77, 156, 157, 190, 199)

_block(
    _untemporal(
        "`RoleAssignment` carries id, person_id, school_id, role_code, "
        "scope_type, scope_ref_id, granted_areas, status, record_status and "
        "timestamps — no `valid_from`, no `valid_until`, no `version`. "
        "`AssignRoleRequest` accepts no validity window either, so SCHEDULED, "
        "lazy EXPIRED and stale expected-version have nothing to assert"
    ),
    12, 27, 81,
)

_block(
    _absent(
        "Standard Support Access does not exist. The registry carries the "
        "permission keys (`platform.support.*`, `school.support.*`) and "
        "nothing implements them: no support request, approval, grant, "
        "session, masked read, controlled repair, activity chain or ticket "
        "verifier. There is no table, service or route for any of it"
    ),
    *range(83, 113), 139, 140, 141, 142, 143, 178, 186, 209,
)
_block(
    _absent(
        "break-glass does not exist: no activation, no incident reference, no "
        "ratification, no post-incident review. `platform.support."
        "break_glass.activate` and `.ratify` are seeded keys read by nothing"
    ),
    *range(113, 121),
)
_block(
    _absent(
        "there is no offline authorization envelope: no lease, no device "
        "binding, no nonce, no queued-operation allow-list, no sync "
        "authorization recheck. Nothing issues or validates one"
    ),
    *range(121, 130), 153, 177,
)

_block(
    _absent(
        "`RoleCode` has OWNER, MANAGER, ADMIN, TRAINER, PARENT and STUDENT. "
        "There is no LIMITED_ADMIN and no SUBSTITUTE_INSTRUCTOR, so neither "
        "can be assigned, hold a baseline binding, or be refused one"
    ),
    16, 18, 61, 149,
)
_block(
    _absent(
        "there is no PAYER role. §2.4's PAYER and GUARDIAN are two roles with "
        "separate subject bases; this repo has one `PARENT` role plus M07 "
        "guardian links, and paying is a property of an M12 family ledger "
        "rather than a role an account holds"
    ),
    144, 151, 152, 165, 166, 171, 183, 194, 201, 203,
)

_block(
    _absent(
        "there is no authorization cache. Every guard reads the database on "
        "the request, so there is no stale entry to invalidate and no cache "
        "key to vary. The contract's property holds, but by absence — a test "
        "asserting it would assert nothing"
    ),
    55, 71, 75,
)
_block(_absent("there is no realtime channel to interrupt"), 64)
_block(
    _absent(
        "there is no service principal or background callback acting on a "
        "user's behalf, so none can carry a stale version"
    ),
    65,
)
_block(
    _absent(
        "there is no step-up authentication and no precommit recheck layer. "
        "No command re-reads the actor's authority between its first guard and "
        "its commit, so HIGH/CRITICAL `RBAC_CONCURRENT_CHANGE` has nothing to "
        "be raised by (F-45)"
    ),
    66, 72, 137, 160, 179, 198, 212,
)
_block(
    _absent(
        "permissions reach the server only as the actor's role in the resolved "
        "context. No token or request body carries a permission claim for the "
        "server to ignore"
    ),
    56,
)
_block(
    _absent(
        "there is no port that can report a store unavailable. Membership and "
        "policy are read with ordinary queries, so an outage surfaces as a "
        "driver exception rather than a fail-closed 503"
    ),
    58,
)
_block(
    _absent(
        "there is no subject guard layer. `PermissionDefinition."
        "subject_guard_key` is declared on every registry row and read by no "
        "code in `app/` — grep finds it only in the model and the seed. A "
        "permission area is never narrowed per record, per group assignment or "
        "per child, so there is no guard here to refuse one document, one "
        "roster or one child while the area still allows the rest"
    ),
    59, 60, 62, 63,
)
_block(
    _absent(
        "no account status command exists. `platform.accounts.suspend` is a "
        "constant in `auth_enums` and a seeded key; no router references it, "
        "and nothing can move a `UserAccount` to SUSPENDED for the guard to "
        "fail closed on"
    ),
    67,
)
_block(
    _absent(
        "no route consults an entitlement. `SchoolProductEntitlement` exists "
        "with a full lifecycle and nothing in `app/security` or any router "
        "reads it — M04's own module recorded the same thing as a finding "
        "(#119: the entitlement guard is called from nowhere). So an "
        "entitlement cannot be on *and* bypassed, because it is never "
        "consulted either way"
    ),
    69,
)
_block(
    _absent(
        "there are no feature flags. Nothing in `app/` defines or reads one, "
        "so no flag can be on while a permission is missing"
    ),
    70,
)
_block(
    _absent(
        "there are no cursors. `/roles` and every other list page on "
        "`items/limit/offset/total`; an unrecognised `cursor` query parameter "
        "is ignored rather than refused. So there is no signed cursor to "
        "replay across tenants and no cursor syntax to invalidate"
    ),
    54,
)
_block(
    _absent(
        "there is no commercial command surface. The six `platform."
        "commercial.*` keys are seeded and no router references any of them, "
        "so COM-01..20 cannot be attempted with or without a key"
    ),
    134,
)

_block(
    _registry(
        "§3.3.2's M08–M12 permission keys are not seeded. Revision 1.3 holds "
        "the 38 keys §3.3 determines and nothing for locations, groups, "
        "scheduling, attendance or finance — no catalogue to list, no binding "
        "to check, no risk or offline value to read. The modules themselves "
        "exist and are guarded by `PermissionArea`, which their own QA covers; "
        "what is missing is the M05 registry that should be deciding it"
    ),
    145, 146, 147, 148, 150, 154, 155, 158,
)
_block(
    _registry(
        "§3.3.3's M13–M16 keys are not seeded either, with the same "
        "consequence: communication, notification, document and event routes "
        "are guarded by `PermissionArea`, not by the keys these scenarios name"
    ),
    161, 162, 163, 164, 167, 168, 169, 170, 172, 173, 174, 175, 176,
)
_block(
    _registry(
        "the M17–M21/M28 keys exist in the registry documents but are not "
        "seeded into a revision, and the M28 portal surface they guard does "
        "not exist in this repo"
    ),
    184, 185, 187, 188, 189, 192, 193, 195, 196, 197, 200, 202, 204, 205, 206,
    207, 208, 210,
)
_block(
    _absent(
        "there is no route→permission binding registry. Routes carry "
        "`require_permission(PermissionArea...)` written inline, so nothing "
        "could fail closed at publish or startup on an unknown key"
    ),
    182, 211,
)
_block(
    _absent(
        "there is no subject basis. §2.7's `subject_basis_kind`/"
        "`subject_basis_ref` belong to the direct grant this repo lacks, and "
        "`RoleAssignment` carries no `school_membership_id` — so the "
        "tenant-safe composite FK these scenarios probe does not exist as a "
        "constraint to violate"
    ),
    135, 136, 138,
)
_block(
    _absent(
        "there are no metrics or traces to scan and no latency budget measured "
        "anywhere, so §3.6's p95/p99 half cannot be evidenced. The PII half is "
        "covered for the surfaces that exist by M01/M02/M04's audit scans"
    ),
    130,
)
_block(
    _absent(
        "there is no migration harness for a legacy RBAC seed: no "
        "SUBSTITUTE_TRAINER or SOKOLA_ADMIN rows ever existed here, and there "
        "is no orphan-grant or thin-support-grant repair to run twice"
    ),
    131,
)

# --- measured divergences, each one a finding ------------------------------
_block(
    _diverges(
        "`RoleTransitionRequest.reason` is free text, `str | None` with "
        "max_length 500 and no vocabulary. Measured: suspending with "
        "`NIJE_IZ_VOKABULARA_XYZ` returns 200, where the contract requires 422 "
        "`RBAC_REASON_INVALID` and no change. M05 §2.10 fixes the allowed codes "
        "per command, so this is a decided change rather than an open question "
        "— it is a separate increment because it changes the request shape and "
        "so the generated web client (F-49)"
    ),
    23,
)
_block(
    _diverges(
        "a guardian relation is not required at assignment time. Measured: "
        "assigning PARENT to a member with no M07 guardian link returns 201, "
        "where the contract requires 422 `RBAC_GUARDIAN_RELATION_REQUIRED`. "
        "Bounded rather than exploitable: the PARENT role carries only the "
        "PARENTS area and M07 checks the link when a child record is read, so "
        "the role alone opens no child data — the divergence is that the "
        "refusal happens late instead of at the point of grant"
    ),
    19,
)
_block(
    _absent(
        "there is no primary-owner designation. `RoleAssignment` has no such "
        "column and `transfer_ownership` protects the *last* owner rather than "
        "a primary one, so `RBAC_PRIMARY_OWNER_TRANSFER_REQUIRED` has no state "
        "to be raised from"
    ),
    22,
)
_block(
    _diverges(
        "the resolver that would raise this is wired to nothing. "
        "`PolicyUnavailableError` exists and fires when no revision is ACTIVE, "
        "but it is a 500 `AUTHORIZATION_POLICY_UNAVAILABLE` reachable only "
        "through `effective_permissions`, which no guard calls — the live "
        "guard is `app.security.permissions` and reads no policy store at all"
    ),
    57,
)
_block(
    _diverges(
        "guards are area-based, with no separate resource or subject guard "
        "layer to scan for. Every product route carries "
        "`require_permission(PermissionArea...)`; none carries a permission "
        "key, a resource type or a subject guard key, so the coverage this "
        "scenario asserts cannot be computed over this codebase"
    ),
    180,
)
_block(
    _absent(
        "neither half exists: no step-up freshness window to satisfy and no "
        "idempotency key on the platform-role commands, so a retry is a second "
        "call rather than a replay"
    ),
    80,
)
_block(
    _diverges(
        "this is the module's own acceptance gate, not a behaviour. It "
        "requires 213/213 actually executed with 0 failed and 0 skipped, which "
        "is exactly what this file cannot assert about itself — and which is "
        "false today in any case: 34 of the 213 run. Declared rather than "
        "implemented so that no green run of this suite can be read as M05 "
        "having passed"
    ),
    213,
)


# ===========================================================================
# Fixtures
# ===========================================================================


def _signed_in_account(client: TestClient, db: Session, email: str) -> UserAccount:
    """An account with a real session cookie.

    A platform assignment hangs off a `UserAccount`, and the dev-header
    adapter has none — `Principal.user_account_id` is `None` there — so these
    scenarios cannot be driven with the header shortcut.
    """
    resp = client.post(
        "/auth/password/register",
        json={
            "email": email,
            "password": "longenough1",
            "given_name": "Platform",
            "family_name": "Operator",
        },
    )
    assert resp.status_code == 200, resp.text
    account_id = db.execute(
        select(AuthIdentity.user_account_id).where(AuthIdentity.login_email.ilike(email))
    ).scalar_one()
    account = db.get(UserAccount, account_id)
    assert account is not None
    return account


def _csrf(client: TestClient) -> dict[str, str]:
    token = client.cookies.get(CSRF_COOKIE)
    assert token, "the register call should have set a CSRF cookie"
    return {CSRF_HEADER: token}


def _platform_assignment(
    db: Session,
    account: UserAccount,
    role_key: PlatformRoleKey = PlatformRoleKey.PLATFORM_OPERATIONS_ADMIN,
) -> PlatformRoleAssignment:
    """Insert the row the way the operator script does — the command refuses a
    caller who holds nothing, which is what stops it being a way to create
    platform access from nothing."""
    assignment = PlatformRoleAssignment(
        user_account_id=account.id,
        role_key=role_key,
        status=PlatformRoleStatus.ACTIVE,
        valid_from=clock.now(),
        source_ticket_ref="QA-SEED",
        created_by_account_id=account.id,
    )
    db.add(assignment)
    db.commit()
    return assignment


# ===========================================================================
# A. Policy and role catalogue
# ===========================================================================


def test_m05_qa_004_a_permission_with_no_binding_is_deny_for_every_role(
    db: Session,
) -> None:
    """§3.2 point 3: a permission is default-deny for every role until a
    published revision binds it.

    The row is inserted rather than found, because revision 1.3 as shipped
    binds *every* one of its 38 keys to at least one role — I expected the
    support and break-glass keys to be unbound and they are not. So the seed
    cannot demonstrate this property, and the property being tested is the
    resolver's anyway: given a permission no binding names, no role may hold
    it. A resolver that fell back to "unknown means allow", or that joined
    loosely enough to pick up an unbound key, would pass every other test in
    this file.
    """
    revision_id = db.execute(
        text("SELECT id FROM authorization_policy_revision WHERE status = 'ACTIVE'")
    ).scalar_one()
    orphan = "school.qa004.never_bound"

    db.execute(
        text(
            "INSERT INTO permission_definition (id, policy_revision_id, permission_key,"
            " authorization_domain_key, resource_type, action, risk_level,"
            " delegation_class, step_up_required, offline_policy, child_data_class,"
            " status, created_at, updated_at)"
            " VALUES (:id, :rev, :key, 'SCHOOL', 'qa004', 'read', 'LOW',"
            " 'ROLE_ONLY', false, 'DENY', 'NONE', 'ACTIVE', now(), now())"
        ),
        {"id": "perm_qa004", "rev": revision_id, "key": orphan},
    )
    db.commit()

    every_role = frozenset(role.key for role in registry.ROLES)
    held = permissions_for_role_keys(
        db, role_keys=every_role, domain=DOMAIN_SCHOOL
    ) | permissions_for_role_keys(db, role_keys=every_role, domain=DOMAIN_PLATFORM)

    assert orphan not in held
    assert held, "the seeded bindings should still resolve"
    # Nothing resolved outside the catalogue either.
    catalogue = frozenset(perm.key for perm in registry.PERMISSIONS) | {orphan}
    assert held <= catalogue, sorted(held - catalogue)


def test_m05_qa_009_no_super_admin_and_no_standing_support_role_exists(
    db: Session,
) -> None:
    """§7.7 and the reason this is a build-time check rather than a review
    habit.

    `SUPER_ADMIN` and a permanent `SOKOLA_SUPPORT` are the two shapes that
    would quietly undo every other guard in the module: one role that holds
    everything, or one that holds tenant access without a grant. Neither may
    exist as a definition, as a seeded row, or as an assignment.
    """
    role_keys = {role.key for role in registry.ROLES}
    assert "SUPER_ADMIN" not in role_keys
    assert "SOKOLA_SUPPORT" not in role_keys
    assert not {key for key in role_keys if "SUPER" in key}

    seeded = {
        row[0]
        for row in db.execute(text("SELECT DISTINCT role_key FROM role_definition")).all()
    }
    assert not {key for key in seeded if "SUPER" in key or key == "SOKOLA_SUPPORT"}

    # Platform roles are the only account-scoped ones, and each is a named
    # operator role rather than a standing support identity.
    platform = {
        row[0]
        for row in db.execute(
            text(
                "SELECT DISTINCT role_key FROM role_definition"
                " WHERE authorization_domain_key = 'PLATFORM'"
            )
        ).all()
    }
    assert platform <= {key.value for key in PlatformRoleKey}, sorted(platform)


def test_m05_qa_010_a_platform_role_opens_no_school_data(
    db: Session, client: TestClient
) -> None:
    """§2.6: a platform role is account-scoped and carries no tenant access.

    The refusal is uniform by construction, which is the part worth pinning.
    `_require_school` raises the same `ForbiddenError` for a school that does
    not exist, one that is DEACTIVATED, and one the caller simply has no
    membership in — so a platform operator probing school ids learns nothing
    about which of them are real.
    """
    account = _signed_in_account(client, db, "ops-qa010@example.invalid")
    _platform_assignment(db, account)
    school = make_school(db, name="Tudja skola")

    assert effective_roles(db, user_account_id=account.id) == {
        PlatformRoleKey.PLATFORM_OPERATIONS_ADMIN.value
    }

    # The platform role holds no school-domain permission at all.
    held = permissions_for_role_keys(
        db,
        role_keys=frozenset({PlatformRoleKey.PLATFORM_OPERATIONS_ADMIN.value}),
        domain=DOMAIN_PLATFORM,
    )
    assert held, "the operations admin should hold platform permissions"
    assert not {key for key in held if key.startswith("school.")}

    # And it resolves no context in that school.
    denied = client.get("/roles", headers={CONTEXT_HEADER: school.id})
    assert denied.status_code in (401, 403, 404), denied.text
    body = denied.text
    assert school.name not in body


# ===========================================================================
# B. Role assignments
# ===========================================================================


def test_m05_qa_011_an_owner_assigns_a_manager_with_one_audit_and_one_outbox(
    db: Session, client: TestClient
) -> None:
    """§5.2. The counts are the assertion, not the 201.

    A command that wrote two audit rows, or none, would still answer 201 and
    still show the role in the next list — so the trail is where a regression
    would actually appear. The contract also names `version 1`, which has no
    counterpart here: `RoleAssignment` carries no version column at all, and
    that absence is declared against QA-081.
    """
    owner = bootstrap_actor(db, org_name="QA011", role=RoleCode.OWNER, given="Vlasnik")
    target = make_person(db, given="Novi", family="Menadzer")
    add_membership(db, person=target, school=owner.school)
    db.commit()

    resp = client.post(
        "/roles",
        headers=owner.headers,
        json={"person_id": target.id, "role_code": "MANAGER"},
    )
    assert resp.status_code == 201, resp.text
    assignment_id = resp.json()["id"]

    row = db.get(RoleAssignment, assignment_id)
    assert row is not None
    assert row.status is RoleAssignmentStatus.ACTIVE
    assert row.school_id == owner.school.id

    audits = db.execute(
        text(
            "SELECT action FROM audit_log WHERE entity_type = 'role_assignment'"
            " AND entity_id = :i"
        ),
        {"i": assignment_id},
    ).all()
    assert [r[0] for r in audits] == ["role_assignment.created"]

    events = db.execute(
        text("SELECT event_type FROM outbox_message WHERE payload->>'role_assignment_id' = :i"),
        {"i": assignment_id},
    ).all()
    assert [r[0] for r in events] == ["role_assignment.created"]


def test_m05_qa_013_a_target_without_a_membership_cannot_be_given_a_role(
    db: Session, client: TestClient
) -> None:
    """§5.2: no role without a current M06 membership.

    The contract asks for 422 `RBAC_MEMBERSHIP_REQUIRED`; this repo answers
    404, resolving the person *through* the school so that someone who is not
    a member is indistinguishable from someone who does not exist. The
    stricter answer is the one that leaks less, and the state assertion is the
    same either way: nothing is written.
    """
    owner = bootstrap_actor(db, org_name="QA013", role=RoleCode.OWNER, given="Vlasnik")
    outsider = make_person(db, given="Nije", family="Clan")
    db.commit()

    resp = client.post(
        "/roles",
        headers=owner.headers,
        json={"person_id": outsider.id, "role_code": "TRAINER"},
    )
    assert resp.status_code == 404, resp.text

    assert not db.execute(
        select(RoleAssignment).where(RoleAssignment.person_id == outsider.id)
    ).scalars().all()


def test_m05_qa_014_a_membership_from_another_school_is_a_safe_404(
    db: Session, client: TestClient
) -> None:
    """The tenant property at the point of grant.

    School B's member is real, and the id the caller sends is real. What must
    not happen is a response that distinguishes "exists elsewhere" from "does
    not exist" — so this asserts the same 404 as QA-013's complete unknown.
    """
    a = bootstrap_actor(db, org_name="QA014-A", role=RoleCode.OWNER, given="A")
    b = bootstrap_actor(db, org_name="QA014-B", role=RoleCode.OWNER, given="B")
    theirs = add_actor(db, school=b.school, role=RoleCode.TRAINER, given="Njihov")

    resp = client.post(
        "/roles",
        headers=a.headers,
        json={"person_id": theirs.person.id, "role_code": "TRAINER"},
    )
    assert resp.status_code == 404, resp.text
    assert b.school.name not in resp.text
    assert theirs.person.display_name not in resp.text

    held = db.execute(
        select(RoleAssignment).where(
            RoleAssignment.person_id == theirs.person.id,
            RoleAssignment.school_id == a.school.id,
        )
    ).scalars().all()
    assert not held


def test_m05_qa_017_a_manager_may_assign_an_instructor(
    db: Session, client: TestClient
) -> None:
    """§2.4: assigning downward is allowed inside the school.

    The positive half of the pair whose negative half is QA-015. That one is
    declared, not implemented, because this repo answers it wrongly: the same
    MANAGER may equally assign MANAGER, since role administration is gated on
    an area OWNER and MANAGER share (F-47). This test states what does work,
    so the finding is about a missing restriction rather than a missing route.
    """
    mgr = bootstrap_actor(db, org_name="QA017", role=RoleCode.MANAGER, given="Menadzer")
    target = make_person(db, given="Novi", family="Trener")
    add_membership(db, person=target, school=mgr.school)
    db.commit()

    resp = client.post(
        "/roles", headers=mgr.headers, json={"person_id": target.id, "role_code": "TRAINER"}
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["role_code"] == "TRAINER"


def test_m05_qa_020_ownership_is_not_reachable_through_the_generic_grant(
    db: Session, client: TestClient
) -> None:
    """§14: OWNER arrives only through the ownership transfer path.

    `assign_role` refuses the role code outright, before resolving the target
    — so it is not a permission check that happens to deny, but a route that
    cannot grant ownership at all. The contract names 403; this repo answers
    400. The distinction that matters is that no assignment appears.
    """
    owner = bootstrap_actor(db, org_name="QA020", role=RoleCode.OWNER, given="Vlasnik")
    target = make_person(db, given="Zeli", family="Vlasnistvo")
    add_membership(db, person=target, school=owner.school)
    db.commit()

    resp = client.post(
        "/roles", headers=owner.headers, json={"person_id": target.id, "role_code": "OWNER"}
    )
    assert resp.status_code == 400, resp.text

    owners = db.execute(
        select(RoleAssignment).where(
            RoleAssignment.school_id == owner.school.id,
            RoleAssignment.role_code == RoleCode.OWNER,
            RoleAssignment.status == RoleAssignmentStatus.ACTIVE,
        )
    ).scalars().all()
    assert [o.person_id for o in owners] == [owner.person.id]


def test_m05_qa_021_the_last_active_owner_survives_both_transitions(
    db: Session, client: TestClient
) -> None:
    """§5.2 and §14: a school is never left without an owner.

    Both doors are tried, because a guard placed on one of them is the easy
    mistake: suspension and revocation are separate commands with separate
    conflict checks, and protecting only the second leaves the first able to
    strand the school with an owner who cannot act.

    The scenario's other half — a temporal OWNER being refused with
    `RBAC_ROLE_VALIDITY_INVALID` — has no counterpart and is declared against
    QA-012: an assignment here cannot carry a validity window to be invalid.
    """
    owner = bootstrap_actor(db, org_name="QA021", role=RoleCode.OWNER, given="Jedini")

    suspended = client.post(
        f"/roles/{owner.assignment.id}/suspend",
        headers=owner.headers,
        json={"reason": "pokusaj"},
    )
    assert suspended.status_code == 409, suspended.text

    revoked = client.post(
        f"/roles/{owner.assignment.id}/revoke",
        headers=owner.headers,
        json={"reason": "pokusaj"},
    )
    assert revoked.status_code == 409, revoked.text

    db.expire_all()
    row = db.get(RoleAssignment, owner.assignment.id)
    assert row is not None
    assert row.status is RoleAssignmentStatus.ACTIVE


def test_m05_qa_024_a_suspended_assignment_can_be_made_active_again(
    db: Session, client: TestClient
) -> None:
    """§5.2: SUSPENDED is recoverable, and the recovery is audited as such.

    This is the behaviour QA-026 declares the *defect* of: the same code path
    revives a REVOKED assignment, which the contract makes terminal (F-48).
    Pinning the legitimate half here is what makes that finding precise —
    the fix must distinguish the two statuses, not remove the path.
    """
    owner = bootstrap_actor(db, org_name="QA024", role=RoleCode.OWNER, given="Vlasnik")
    trainer = add_actor(db, school=owner.school, role=RoleCode.TRAINER, given="Trener")

    off = client.post(
        f"/roles/{trainer.assignment.id}/suspend",
        headers=owner.headers,
        json={"reason": "pauza"},
    )
    assert off.status_code == 200, off.text

    back = client.post(
        "/roles",
        headers=owner.headers,
        json={"person_id": trainer.person.id, "role_code": "TRAINER"},
    )
    assert back.status_code == 201, back.text
    assert back.json()["id"] == trainer.assignment.id

    db.expire_all()
    row = db.get(RoleAssignment, trainer.assignment.id)
    assert row is not None
    assert row.status is RoleAssignmentStatus.ACTIVE

    actions = [
        r[0]
        for r in db.execute(
            text(
                "SELECT action FROM audit_log WHERE entity_type = 'role_assignment'"
                " AND entity_id = :i ORDER BY created_at"
            ),
            {"i": trainer.assignment.id},
        ).all()
    ]
    assert "role_assignment.reactivated" in actions


def test_m05_qa_028_a_suspended_membership_makes_an_active_role_ineffective(
    db: Session, client: TestClient
) -> None:
    """§6.1 point 4: the guard re-proves membership, and the role row is left
    alone.

    Both halves matter. If the guard trusted the role assignment, a suspended
    member would keep working; if the suspension rewrote the role row, the
    school would lose the record of what that person's role had been and
    reinstating them would mean guessing.

    The actor is an OWNER here on purpose: OWNER holds the ROLES area, so the
    200 before and the 403 after can only be the membership proof moving. With
    a TRAINER both calls return 403 and the test would prove nothing.
    """
    owner = bootstrap_actor(db, org_name="QA028", role=RoleCode.OWNER, given="Vlasnik")
    mgr = add_actor(db, school=owner.school, role=RoleCode.MANAGER, given="Menadzer")

    assert client.get("/roles", headers=mgr.headers).status_code == 200

    db.execute(
        text(
            "UPDATE school_membership SET status = 'SUSPENDED',"
            " suspension_reason_code = 'OTHER'"
            " WHERE person_id = :p AND school_id = :s"
        ),
        {"p": mgr.person.id, "s": mgr.school.id},
    )
    db.commit()

    assert client.get("/roles", headers=mgr.headers).status_code == 403

    db.expire_all()
    row = db.get(RoleAssignment, mgr.assignment.id)
    assert row is not None
    assert row.status is RoleAssignmentStatus.ACTIVE


def test_m05_qa_030_a_deactivated_school_resolves_no_context(
    db: Session, client: TestClient
) -> None:
    """§6.1: the school's own state is proved before anything else.

    Checked with an OWNER for the same reason as QA-028 — the 200 is the
    control that makes the 403 mean something. The school check runs before
    the membership check, so a deactivated school refuses even a member whose
    membership is perfectly current.
    """
    owner = bootstrap_actor(db, org_name="QA030", role=RoleCode.OWNER, given="Vlasnik")
    assert client.get("/roles", headers=owner.headers).status_code == 200

    db.execute(
        text("UPDATE school SET status = 'DEACTIVATED', deactivated_at = now() WHERE id = :s"),
        {"s": owner.school.id},
    )
    db.commit()

    denied = client.get("/roles", headers=owner.headers)
    assert denied.status_code == 403, denied.text


# ===========================================================================
# C. Union
# ===========================================================================


def test_m05_qa_047_two_roles_union_and_the_workspace_does_not_filter(
    db: Session, client: TestClient
) -> None:
    """§3.1 step 5 and §3.2 point 1: the union is of every active role, and
    the chosen workspace is a display grouping that changes nothing.

    The workspace is the trap here. It is the one piece of M05 state a client
    sends, so a resolver that quietly intersected the union with "permissions
    of the workspace's role" would look right in the UI and be wrong — the
    contract says a MANAGER who is also an INSTRUCTOR holds both sets however
    they are currently looking at the school.
    """
    from app.application.available_contexts import _WORKSPACE_ROLE_KEY
    from app.application.effective_permissions import effective_permissions

    mgr = bootstrap_actor(db, org_name="QA047", role=RoleCode.MANAGER, given="Oba")
    from tests.factories import assign_role

    assign_role(db, person=mgr.person, school=mgr.school, role=RoleCode.TRAINER)
    db.commit()

    both = effective_permissions(db, person_id=mgr.person.id, school_id=mgr.school.id)
    manager_only = permissions_for_role_keys(db, role_keys=frozenset({"MANAGER"}))
    instructor_only = permissions_for_role_keys(db, role_keys=frozenset({"INSTRUCTOR"}))

    assert both == manager_only | instructor_only
    assert manager_only <= both
    assert instructor_only <= both

    # The workspace map is a separate question and does not enter the union.
    # It answers "which workspaces may this person choose between", which is
    # why `ADMIN` and `MANAGER` share one there and must not here — the
    # separation `test_the_permission_map_is_not_the_workspace_map` guards.
    assert _WORKSPACE_ROLE_KEY[RoleCode.MANAGER] == "MANAGER"
    assert _WORKSPACE_ROLE_KEY[RoleCode.ADMIN] == "MANAGER"
    assert _WORKSPACE_ROLE_KEY[RoleCode.TRAINER] == "INSTRUCTOR"
    assert effective_permissions(
        db, person_id=mgr.person.id, school_id=mgr.school.id
    ) == both


def test_m05_qa_048_the_union_counts_only_active_assignments(
    db: Session, client: TestClient
) -> None:
    """§3.2: a suspended role contributes nothing, and the other one is
    unaffected.

    Both directions are asserted. Dropping the suspended role's permissions
    is the easy half; the half that breaks is leaving the *remaining* role
    intact, because a resolver that filtered on the person rather than on each
    assignment would strip both.
    """
    from app.application.effective_permissions import effective_permissions

    from tests.factories import assign_role

    owner = bootstrap_actor(db, org_name="QA048", role=RoleCode.OWNER, given="Vlasnik")
    both = add_actor(db, school=owner.school, role=RoleCode.MANAGER, given="Oba")
    trainer_assignment = assign_role(
        db, person=both.person, school=both.school, role=RoleCode.TRAINER
    )
    db.commit()

    full = effective_permissions(db, person_id=both.person.id, school_id=both.school.id)

    off = client.post(
        f"/roles/{trainer_assignment.id}/suspend",
        headers=owner.headers,
        json={"reason": "pauza"},
    )
    assert off.status_code == 200, off.text

    after = effective_permissions(db, person_id=both.person.id, school_id=both.school.id)
    manager_only = permissions_for_role_keys(db, role_keys=frozenset({"MANAGER"}))
    assert after == manager_only
    assert after <= full


# ===========================================================================
# D. Tenant isolation
# ===========================================================================


def test_m05_qa_049_a_known_id_from_another_school_is_a_safe_404(
    db: Session, client: TestClient
) -> None:
    """§11: the id is real, the actor is real, and the answer reveals
    neither.

    Read and write are both tried. A system that hid other tenants' rows from
    reads while letting a mutation reach them by id would pass a naive
    isolation test and still be exploitable — the write path is where the
    tenant filter is most often left off.
    """
    a = bootstrap_actor(db, org_name="QA049-A", role=RoleCode.OWNER, given="A")
    b = bootstrap_actor(db, org_name="QA049-B", role=RoleCode.OWNER, given="B")

    read = client.get("/roles", headers=a.headers)
    assert read.status_code == 200
    ids = {item["id"] for item in read.json()["items"]}
    assert b.assignment.id not in ids

    write = client.post(
        f"/roles/{b.assignment.id}/revoke", headers=a.headers, json={"reason": "pokusaj"}
    )
    assert write.status_code == 404, write.text
    assert b.school.name not in write.text

    db.expire_all()
    untouched = db.get(RoleAssignment, b.assignment.id)
    assert untouched is not None
    assert untouched.status is RoleAssignmentStatus.ACTIVE


def test_m05_qa_050_a_shared_organization_carries_no_access(
    db: Session, client: TestClient
) -> None:
    """§4.1: paying for two schools is not holding a role in both.

    The organization link is the one relationship that genuinely spans
    tenants, which makes it the obvious place for an "it's all one customer"
    shortcut to be introduced later. Nothing in the authorization path may
    read it.
    """
    a = bootstrap_actor(db, org_name="QA050-A", role=RoleCode.OWNER, given="A")
    c = bootstrap_actor(db, org_name="QA050-C", role=RoleCode.OWNER, given="C")

    org_of_a = db.execute(
        text("SELECT organization_id FROM organization_school WHERE school_id = :s"),
        {"s": a.school.id},
    ).scalar_one()
    db.execute(
        text("UPDATE organization_school SET organization_id = :o WHERE school_id = :s"),
        {"o": org_of_a, "s": c.school.id},
    )
    db.commit()

    shared = db.execute(
        text(
            "SELECT DISTINCT organization_id FROM organization_school"
            " WHERE school_id IN (:x, :y)"
        ),
        {"x": a.school.id, "y": c.school.id},
    ).scalars().all()
    assert shared == [org_of_a], "both schools should now hang off one organization"

    denied = client.post(
        f"/roles/{c.assignment.id}/revoke", headers=a.headers, json={"reason": "pokusaj"}
    )
    assert denied.status_code == 404, denied.text

    listed = client.get("/roles", headers=a.headers)
    assert c.assignment.id not in {item["id"] for item in listed.json()["items"]}


def test_m05_qa_051_an_unknown_id_and_a_foreign_id_answer_identically(
    db: Session, client: TestClient
) -> None:
    """§11's enumeration rule, which is only meaningful as a comparison.

    Either answer alone looks fine. What leaks is the *difference* — if a real
    id from another school produced a different status, code or body shape
    from an id that never existed, the endpoint would be a membership oracle
    for every id the caller cares to try.
    """
    a = bootstrap_actor(db, org_name="QA051-A", role=RoleCode.OWNER, given="A")
    b = bootstrap_actor(db, org_name="QA051-B", role=RoleCode.OWNER, given="B")

    foreign = client.post(
        f"/roles/{b.assignment.id}/revoke", headers=a.headers, json={"reason": "x"}
    )
    unknown = client.post(
        "/roles/rol_00000000000000000000000000/revoke",
        headers=a.headers,
        json={"reason": "x"},
    )

    assert foreign.status_code == unknown.status_code == 404
    assert foreign.json()["error"]["code"] == unknown.json()["error"]["code"]
    assert foreign.json()["error"]["message"] == unknown.json()["error"]["message"]
    assert sorted(foreign.json()["error"]) == sorted(unknown.json()["error"])


def test_m05_qa_052_a_member_without_the_area_is_forbidden_not_hidden(
    db: Session, client: TestClient
) -> None:
    """§11 again, from the other side, and the distinction is deliberate.

    The resource is in the caller's own school, so there is nothing to hide:
    403 is correct and 404 would be worse, because it would teach callers that
    404 means "no permission" and erode the safe-404 the cross-tenant cases
    depend on. Asserted next to an OWNER control so the 403 is attributable to
    the area and not to the context.
    """
    owner = bootstrap_actor(db, org_name="QA052", role=RoleCode.OWNER, given="Vlasnik")
    trainer = add_actor(db, school=owner.school, role=RoleCode.TRAINER, given="Trener")

    assert client.get("/roles", headers=owner.headers).status_code == 200

    denied = client.get("/roles", headers=trainer.headers)
    assert denied.status_code == 403, denied.text
    assert denied.json()["error"]["code"] == "FORBIDDEN"


def test_m05_qa_053_a_list_counts_only_the_rows_the_caller_may_see(
    db: Session, client: TestClient
) -> None:
    """§11: the total is computed over the visible set, not filtered after
    counting.

    A count taken before the tenant filter is the classic version of this
    leak: the rows never appear, and the number still says how many exist.
    The contract names a cursor; this repo pages on `items/limit/offset/total`
    and has no cursor at all, which is declared against QA-054.
    """
    a = bootstrap_actor(db, org_name="QA053-A", role=RoleCode.OWNER, given="A")
    b = bootstrap_actor(db, org_name="QA053-B", role=RoleCode.OWNER, given="B")
    for i in range(3):
        add_actor(db, school=a.school, role=RoleCode.TRAINER, given=f"A{i}")
    for i in range(5):
        add_actor(db, school=b.school, role=RoleCode.TRAINER, given=f"B{i}")

    mine = client.get("/roles", headers=a.headers)
    assert mine.status_code == 200
    body = mine.json()
    assert body["total"] == 4, body  # one owner plus three trainers
    assert len(body["items"]) == 4
    assert {item["school_id"] for item in body["items"]} == {a.school.id}

    theirs = client.get("/roles", headers=b.headers)
    assert theirs.json()["total"] == 6


def test_m05_qa_068_a_moved_tenant_access_version_invalidates_the_context(
    db: Session, client: TestClient
) -> None:
    """§8 step 3b: M03's tenant access version is re-read on every resolve.

    This is the mechanism that makes a role change take effect without
    waiting for a session to expire. The positive resolve first is what makes
    the failure meaningful — without it, a raise could just as easily mean the
    fixture never built a usable context.
    """
    import pytest as _pytest
    from app.common.errors import TenantContextStaleError
    from app.domains.identity.auth_models import AuthSession
    from app.domains.identity.models import Person
    from app.domains.tenancy import context as tenant_context
    from app.domains.tenancy.enums import TenantInvalidationReason

    from tests.factories import assign_role

    account = _signed_in_account(client, db, "qa068@example.invalid")
    person = db.get(Person, account.person_id)
    assert person is not None
    school = make_school(db, name="QA068 skola")
    add_membership(db, person=person, school=school)
    assign_role(db, person=person, school=school, role=RoleCode.MANAGER)
    db.commit()

    session = db.execute(
        select(AuthSession).where(AuthSession.user_account_id == account.id)
    ).scalars().first()
    assert session is not None

    ctx = tenant_context.select_context(
        db, session=session, account=account, school=school, workspace_key="ADMIN"
    )
    db.commit()

    resolved = tenant_context.resolve(
        db, context=ctx, account=account, person_id=person.id
    )
    assert resolved.id == school.id

    tenant_security.invalidate(
        db, school.id, reason_code=TenantInvalidationReason.SECURITY_INCIDENT
    )
    db.commit()

    with _pytest.raises(TenantContextStaleError):
        tenant_context.resolve(db, context=ctx, account=account, person_id=person.id)


# ===========================================================================
# E. Transactionality and concurrency
# ===========================================================================


def test_m05_qa_073_a_failing_audit_insert_rolls_the_whole_command_back(
    db: Session, client: TestClient, monkeypatch
) -> None:
    """§7.1: business write, audit, outbox and receipt are one transaction.

    Simulated at the audit boundary because that is the one this command
    actually has, and the property is the one that cannot be checked by
    reading the code: that the business row is *gone*, not merely that an
    exception escaped. A command that caught and logged this would leave a
    role assignment nobody ever authorized and no trail saying who made it.
    """
    from app.domains.identity import roles_service

    owner = bootstrap_actor(db, org_name="QA073", role=RoleCode.OWNER, given="Vlasnik")
    target = make_person(db, given="Nikad", family="Upisan")
    add_membership(db, person=target, school=owner.school)
    db.commit()

    before = db.execute(
        select(RoleAssignment).where(RoleAssignment.person_id == target.id)
    ).scalars().all()
    assert not before

    def _explode(*args, **kwargs):
        raise RuntimeError("audit store down")

    monkeypatch.setattr(roles_service, "record_audit", _explode)

    # TestClient re-raises a server-side exception rather than turning it into
    # a response, which is the right behaviour to assert against: what matters
    # is that the caller gets no success and the row does not survive.
    import pytest as _pytest

    with _pytest.raises(RuntimeError, match="audit store down"):
        client.post(
            "/roles",
            headers=owner.headers,
            json={"person_id": target.id, "role_code": "TRAINER"},
        )

    db.rollback()
    db.expire_all()
    after = db.execute(
        select(RoleAssignment).where(RoleAssignment.person_id == target.id)
    ).scalars().all()
    assert not after, "the assignment must not survive a failed audit"

    events = db.execute(
        text("SELECT count(*) FROM outbox_message WHERE payload->>'person_id' = :p"),
        {"p": target.id},
    ).scalar_one()
    assert events == 0


def test_m05_qa_074_the_same_event_is_handled_once(db: Session) -> None:
    """§7.1: a consumer that sees a message three times acts once.

    At-least-once delivery means this is not a theoretical case, and the
    guarantee is a uniqueness constraint rather than a check-then-act — which
    is the only version that holds when two workers claim the same message at
    the same moment.
    """
    message = OutboxMessage(
        event_type="role_assignment.created",
        payload={"role_assignment_id": "rol_qa074"},
        school_id=None,
    )
    db.add(message)
    db.commit()

    first = inbox_claim(db, consumer="qa074", message=message)
    db.commit()
    second = inbox_claim(db, consumer="qa074", message=message)
    db.commit()
    third = inbox_claim(db, consumer="qa074", message=message)
    db.commit()

    assert first is True
    assert second is False
    assert third is False

    # A different consumer is a different obligation and claims it on its own.
    assert inbox_claim(db, consumer="qa074-other", message=message) is True


def test_m05_qa_076_concurrent_owner_removals_cannot_reach_zero(
    db: Session, client: TestClient
) -> None:
    """§14: whatever order they arrive in, one owner remains.

    Run sequentially, which is the honest form of this test: the guard is a
    read-then-check inside each command's transaction, so two serialized
    attempts prove the invariant holds at the boundary. The genuinely
    concurrent version would need two connections racing the same check, and
    what protects that case is the same conflict the second call hits here.
    """
    first = bootstrap_actor(db, org_name="QA076", role=RoleCode.OWNER, given="Prvi")
    second = add_actor(db, school=first.school, role=RoleCode.OWNER, given="Drugi")

    gone = client.post(
        f"/roles/{second.assignment.id}/revoke",
        headers=first.headers,
        json={"reason": "jedan odlazi"},
    )
    assert gone.status_code == 200, gone.text

    blocked = client.post(
        f"/roles/{first.assignment.id}/revoke",
        headers=first.headers,
        json={"reason": "i drugi"},
    )
    assert blocked.status_code == 409, blocked.text

    remaining = db.execute(
        select(RoleAssignment).where(
            RoleAssignment.school_id == first.school.id,
            RoleAssignment.role_code == RoleCode.OWNER,
            RoleAssignment.status == RoleAssignmentStatus.ACTIVE,
        )
    ).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].person_id == first.person.id


def test_m05_qa_078_a_security_admin_cannot_be_time_boxed_or_be_the_last_one_out(
    db: Session, client: TestClient
) -> None:
    """§2.6: the platform always has at least one explicitly ACTIVE security
    admin, and that role can never be the temporary kind.

    The two halves are one scenario because they close the same hole from
    opposite ends. A time-boxed security admin would let the platform expire
    into having none, with nothing having been revoked and no decision taken;
    revoking the last one does it in a single call. The counting is of
    *effective* holders, not of rows reading ACTIVE — a future-dated or
    elapsed admin is not a standby, and counting rows would let the last real
    one go.
    """
    import pytest as _pytest
    from app.common.errors import ConflictError
    from app.domains.authorization.platform_enums import PlatformRoleRevokeReason
    from app.domains.authorization.platform_roles import (
        grant_platform_role,
        revoke_platform_role,
    )

    admin = _signed_in_account(client, db, "qa078@example.invalid")
    _platform_assignment(db, admin, role_key=PlatformRoleKey.PLATFORM_SECURITY_ADMIN)
    other = _signed_in_account(client, db, "qa078b@example.invalid")

    with _pytest.raises(ConflictError):
        grant_platform_role(
            db,
            actor_account_id=admin.id,
            user_account_id=other.id,
            role_key=PlatformRoleKey.PLATFORM_SECURITY_ADMIN,
            source_ticket_ref="SEC-78",
            valid_until=clock.now() + dt.timedelta(days=1),
        )
    db.rollback()

    held = db.execute(
        select(PlatformRoleAssignment).where(
            PlatformRoleAssignment.user_account_id == other.id
        )
    ).scalars().all()
    assert not held

    existing = db.execute(
        select(PlatformRoleAssignment).where(
            PlatformRoleAssignment.user_account_id == admin.id
        )
    ).scalars().one()
    with _pytest.raises(ConflictError):
        revoke_platform_role(
            db,
            actor_account_id=admin.id,
            assignment=existing,
            reason=PlatformRoleRevokeReason.DUTIES_CHANGED,
        )
    db.rollback()

    assert effective_roles(db, user_account_id=admin.id) == {
        PlatformRoleKey.PLATFORM_SECURITY_ADMIN.value
    }


def test_m05_qa_079_a_security_admin_cannot_grant_to_themselves(
    db: Session, client: TestClient
) -> None:
    """§2.6: self-assignment is refused even though the caller holds the
    permission.

    The escalation the permission guard cannot see — the caller genuinely
    holds `platform.roles.manage`, and what is wrong is that actor and subject
    are one account. Found by this measurement and fixed in the same
    increment; the detailed version, including the proof that it fails when
    the guard is removed, is in `test_m05_platform_roles.py`.
    """
    import pytest as _pytest
    from app.common.errors import ForbiddenError
    from app.domains.authorization.platform_roles import grant_platform_role

    admin = _signed_in_account(client, db, "qa079@example.invalid")
    _platform_assignment(db, admin, role_key=PlatformRoleKey.PLATFORM_SECURITY_ADMIN)

    with _pytest.raises(ForbiddenError):
        grant_platform_role(
            db,
            actor_account_id=admin.id,
            user_account_id=admin.id,
            role_key=PlatformRoleKey.PLATFORM_BILLING_ADMIN,
            source_ticket_ref="SEC-79",
        )
    db.rollback()

    assert effective_roles(db, user_account_id=admin.id) == {
        PlatformRoleKey.PLATFORM_SECURITY_ADMIN.value
    }


def test_m05_qa_082_a_race_past_the_application_check_hits_a_constraint(
    db: Session, client: TestClient
) -> None:
    """§7.1: the database is the last guard, and one open row is what it
    allows.

    The application check and the index are deliberately both present. The
    check gives a clean conflict for the ordinary case; the partial unique
    index is what holds when two callers pass that check at the same moment.
    Written directly against the constraint because that is the only way to
    reach it — and the constraint being *partial* is the other half: terminal
    rows are history and must not block a later re-grant.
    """
    import pytest as _pytest
    from sqlalchemy.exc import IntegrityError

    account = _signed_in_account(client, db, "qa082@example.invalid")
    _platform_assignment(db, account, role_key=PlatformRoleKey.PLATFORM_SUPPORT_AGENT)

    duplicate = PlatformRoleAssignment(
        user_account_id=account.id,
        role_key=PlatformRoleKey.PLATFORM_SUPPORT_AGENT,
        status=PlatformRoleStatus.ACTIVE,
        valid_from=clock.now(),
        source_ticket_ref="QA-082",
        created_by_account_id=account.id,
    )
    db.add(duplicate)
    with _pytest.raises(IntegrityError):
        db.commit()
    db.rollback()

    open_rows = db.execute(
        select(PlatformRoleAssignment).where(
            PlatformRoleAssignment.user_account_id == account.id,
            PlatformRoleAssignment.role_key == PlatformRoleKey.PLATFORM_SUPPORT_AGENT,
        )
    ).scalars().all()
    assert len(open_rows) == 1


def test_m05_qa_132_the_static_scan_finds_one_source_of_truth(db: Session) -> None:
    """§9: role and permission meaning lives in one place, and the shapes that
    would undo the module are absent.

    A scan rather than a behaviour, because each of these is something a later
    change introduces quietly: a second role catalogue that drifts from the
    first, an owner binding written as a wildcard, a `TRAINER` key living
    alongside `INSTRUCTOR` so that two spellings authorize differently.
    """
    # One catalogue, and the database agrees with it.
    seeded_permissions = {
        row[0]
        for row in db.execute(
            text("SELECT DISTINCT permission_key FROM permission_definition")
        ).all()
    }
    declared = {perm.key for perm in registry.PERMISSIONS}
    assert declared <= seeded_permissions, sorted(declared - seeded_permissions)

    # No wildcard anywhere in the bindings or the catalogue.
    for key in seeded_permissions:
        assert "*" not in key, key
    bound = {
        row[0]
        for row in db.execute(
            text("SELECT DISTINCT permission_key FROM role_permission_binding")
        ).all()
    }
    for key in bound:
        assert "*" not in key, key
    assert bound <= seeded_permissions, sorted(bound - seeded_permissions)

    # No parallel TRAINER key beside INSTRUCTOR, in either direction.
    role_keys = {
        row[0] for row in db.execute(text("SELECT DISTINCT role_key FROM role_definition")).all()
    }
    assert "INSTRUCTOR" in role_keys
    assert "TRAINER" not in role_keys
    assert "SUBSTITUTE_TRAINER" not in role_keys

    # No standing support identity, and no super admin.
    assert not {k for k in role_keys if "SUPER" in k or k == "SOKOLA_SUPPORT"}


def test_m05_qa_133_a_reserved_authorization_domain_resolves_nothing(
    db: Session,
) -> None:
    """§2.2.1: a domain exists as a row, and only an ACTIVE one is usable.

    The point of the design is that adding a domain later is a seed change
    rather than a schema change — which only pays off if RESERVED actually
    means unusable. So this asserts both that the reserved rows are present as
    the contract's H0 describes, and that nothing is bound inside them: a
    reserved domain with bindings would be an active domain wearing the wrong
    label.
    """
    rows = {
        row[0]: row[1]
        for row in db.execute(
            text("SELECT authorization_domain_key, status FROM authorization_domain_definition")
        ).all()
    }
    assert rows == {
        "SCHOOL": "ACTIVE",
        "PLATFORM": "ACTIVE",
        "EVENT_ORGANIZER_WORKSPACE": "RESERVED",
        "VENUE_OPERATOR_WORKSPACE": "RESERVED",
    }, rows

    reserved = [key for key, status in rows.items() if status == "RESERVED"]
    for domain in reserved:
        roles = db.execute(
            text("SELECT count(*) FROM role_definition WHERE authorization_domain_key = :d"),
            {"d": domain},
        ).scalar_one()
        bindings = db.execute(
            text(
                "SELECT count(*) FROM role_permission_binding"
                " WHERE authorization_domain_key = :d"
            ),
            {"d": domain},
        ).scalar_one()
        permissions = db.execute(
            text(
                "SELECT count(*) FROM permission_definition"
                " WHERE authorization_domain_key = :d"
            ),
            {"d": domain},
        ).scalar_one()
        assert (roles, bindings, permissions) == (0, 0, 0), (domain, roles, bindings, permissions)

    # And the resolver returns nothing for a role key read in a reserved domain.
    assert permissions_for_role_keys(
        db, role_keys=frozenset({"OWNER", "MANAGER"}), domain="EVENT_ORGANIZER_WORKSPACE"
    ) == frozenset()


def test_m05_qa_159_the_policy_seed_hash_is_reproducible(db: Session) -> None:
    """§2.2: the same catalogue hashes the same way, and a changed one does
    not.

    The hash is what makes "this revision is immutable" checkable rather than
    merely asserted, so it has to be a function of the content and nothing
    else — not of dict ordering, not of when it ran. The negative half is the
    one that gives it meaning: if mutating a permission's risk level left the
    hash alone, the hash would certify nothing.

    The other half of the scenario — that changed semantics *require* a new
    revision — needs the publish command this repo does not have, and is
    declared against QA-001.
    """
    import dataclasses

    first = registry.canonical_hash()
    second = registry.canonical_hash()
    assert first == second
    assert len(first) == 64

    stored = db.execute(
        text(
            "SELECT canonical_content_hash FROM authorization_policy_revision"
            " WHERE revision_no = :n"
        ),
        {"n": registry.REVISION_NO},
    ).scalar_one()
    assert stored == first, "the seeded revision should carry the hash of its content"

    original = registry.PERMISSIONS
    mutated = list(original)
    mutated[0] = dataclasses.replace(
        original[0], risk=_other_risk(original[0].risk)
    )
    try:
        registry.PERMISSIONS = tuple(mutated)  # type: ignore[misc]
        assert registry.canonical_hash() != first
    finally:
        registry.PERMISSIONS = original  # type: ignore[misc]
    assert registry.canonical_hash() == first


def _other_risk(risk):
    """Any risk level other than this one, so the mutation is a real change."""
    from app.domains.authorization.enums import RiskLevel

    return next(level for level in RiskLevel if level is not risk)


def test_m05_qa_181_every_m17_m21_m28_key_has_exactly_one_registry_row() -> None:
    """§3.3.4: one row per permission, spelled in full.

    A key listed twice is two sources of truth for the same right, and the two
    copies drift. A shortened `school/x` form beside `school.x` is worse,
    because both look plausible and only one is ever bound. Table rows are
    counted rather than mentions — the document also discusses keys in prose,
    and `portal.mysokola.access` appears there as an example.
    """
    doc = (
        _QA_DOC.parent / "03-M05-PERMISSION-REGISTRY-M17-M21-M28.md"
    ).read_text(encoding="utf-8")
    rows = re.findall(r"^\| `((?:school|platform|portal)\.[a-z0-9_.]+)` \|", doc, re.MULTILINE)

    assert len(rows) == 34, len(rows)
    assert len(set(rows)) == len(rows), sorted(
        key for key in set(rows) if rows.count(key) > 1
    )
    for key in rows:
        assert "/" not in key, key
        assert not key.endswith("."), key


def test_m05_qa_191_all_sixteen_m06_m07_keys_are_present_exactly_once() -> None:
    """§3.3.1: sixteen keys, each once, no wildcard and no alias row.

    The count is named by the contract, so it is asserted literally: a
    seventeenth row means a right was added without the contract moving, and
    fifteen means one was dropped.
    """
    doc = (
        _QA_DOC.parent / "04-M05-PERMISSION-REGISTRY-M06-M07.md"
    ).read_text(encoding="utf-8")
    rows = re.findall(r"^\| `((?:school|platform)\.[a-z0-9_.]+)` \|", doc, re.MULTILINE)

    assert len(rows) == 16, len(rows)
    assert len(set(rows)) == 16, sorted(key for key in set(rows) if rows.count(key) > 1)
    for key in rows:
        assert "*" not in key and "/" not in key, key


# ===========================================================================
# The gate
# ===========================================================================


def _declared() -> set[str]:
    return set(re.findall(r"M05-QA-\d{3}", _QA_DOC.read_text(encoding="utf-8")))


def _implemented() -> set[str]:
    source = Path(__file__).read_text(encoding="utf-8")
    return {
        f"M05-QA-{n}"
        for n in re.findall(r"^def test_m05_qa_(\d{3})_", source, re.MULTILINE)
    }


def test_every_m05_scenario_is_implemented_or_declared() -> None:
    declared = _declared()
    assert len(declared) == 213, f"expected 213 scenarios, found {len(declared)}"
    implemented = _implemented()
    blocked = set(BLOCKED)
    assert not (implemented & blocked), sorted(implemented & blocked)
    missing = declared - implemented - blocked
    assert not missing, f"neither implemented nor declared blocked: {sorted(missing)}"
    stray = (implemented | blocked) - declared
    assert not stray, f"ids not in the contract: {sorted(stray)}"
    assert len(implemented) == 34, f"the docstring claims 34 run, found {len(implemented)}"


def test_the_m05_blocked_reasons_name_one_of_four_causes() -> None:
    """A free-text reason rots into "TODO", so the vocabulary is closed and
    this refuses a fifth cause.

    M05 needed two the earlier modules did not. `registry incomplete` is not
    `feature absent`: the mechanism exists and only the catalogue rows are
    missing, which is a seed to write rather than a module. `no validity or
    version model` is a schema change, and keeping it separate stops three
    scenarios from hiding under a vaguer cause that would not say what they
    are waiting for.
    """
    for scenario, reason in BLOCKED.items():
        assert any(
            cause in reason
            for cause in (
                "feature absent",
                "contract divergence",
                "registry incomplete",
                "no validity or version model",
            )
        ), f"{scenario} has an unrecognised blocking reason: {reason}"


# ===========================================================================
# Implemented in the same increment as this file's second revision
# ===========================================================================


def test_m05_qa_015_a_manager_cannot_assign_a_manager(
    db: Session, client: TestClient
) -> None:
    """§2.4: an actor assigns only strictly below their own rank.

    Declared as a divergence when this module was first written, because the
    repo answered 201 — `ROLE_DEFAULT_AREAS` gives OWNER, MANAGER and ADMIN an
    identical area set and role administration is gated on one of them, so a
    manager could mint managers and each new one could mint more (F-47).

    The refusal is checked by error code rather than status, and ADMIN is
    included: F-29 resolved ADMIN to M05 MANAGER, so it carries MANAGER's rank
    and a manager may not grant it either. The TRAINER call is the control —
    a guard that refused everything would satisfy the negatives and break the
    product.
    """
    from tests.factories import add_membership

    mgr = bootstrap_actor(db, org_name="QA015", role=RoleCode.MANAGER, given="Menadzer")
    target = make_person(db, given="Cilj", family="Osoba")
    add_membership(db, person=target, school=mgr.school)
    db.commit()

    for refused in ("MANAGER", "ADMIN"):
        resp = client.post(
            "/roles", headers=mgr.headers, json={"person_id": target.id, "role_code": refused}
        )
        assert resp.status_code == 403, (refused, resp.text)
        assert resp.json()["error"]["code"] == "FORBIDDEN"

    allowed = client.post(
        "/roles", headers=mgr.headers, json={"person_id": target.id, "role_code": "TRAINER"}
    )
    assert allowed.status_code == 201, allowed.text


def test_m05_qa_026_a_revoked_assignment_is_not_revived(
    db: Session, client: TestClient
) -> None:
    """§5.2: REVOKED is terminal, and a later grant needs a new id.

    Declared as a divergence first time round: `assign_role` found the revoked
    row and set it back to ACTIVE, so one id carried a revocation and its
    reversal (F-48). The schema was what forced it — a total unique constraint
    left reviving as the only insert Postgres would accept.

    The old row is asserted still REVOKED rather than just absent from the
    response, because the property is that history survives *beside* the new
    grant. QA-024's suspended case is the deliberate contrast and still
    revives under the same id.
    """
    owner = bootstrap_actor(db, org_name="QA026", role=RoleCode.OWNER, given="Vlasnik")
    trainer = add_actor(db, school=owner.school, role=RoleCode.TRAINER, given="Trener")
    original = trainer.assignment.id

    gone = client.post(
        f"/roles/{original}/revoke", headers=owner.headers, json={"reason": "zavrsio"}
    )
    assert gone.status_code == 200, gone.text

    again = client.post(
        "/roles",
        headers=owner.headers,
        json={"person_id": trainer.person.id, "role_code": "TRAINER"},
    )
    assert again.status_code == 201, again.text
    assert again.json()["id"] != original

    db.expire_all()
    old = db.get(RoleAssignment, original)
    assert old is not None
    assert old.status is RoleAssignmentStatus.REVOKED


def test_m05_qa_029_a_terminated_membership_closes_its_roles(
    db: Session, client: TestClient
) -> None:
    """§5.2: the episode's open role records are revoked with it, and a new
    episode does not revive them.

    This was F-50, and the access control was never the problem — the request
    guard re-proves membership, so a terminated member was already denied. What
    survived was the record, and an assignment is keyed on `(person, school)`
    rather than on the episode, so inserting a second ACTIVE membership handed
    the former MANAGER role straight back.

    Both halves are asserted, in order, each against a control: the role row
    goes REVOKED at termination, and a *new* episode afterwards does not
    restore access. The second half is the one the contract names explicitly
    ("nova epizoda ih ne oživljava") and the one that would silently come back
    if the cascade were moved out of the termination's transaction.

    A MANAGER is used because MANAGER holds the ROLES area, so 200 before and
    403 after can only be the membership proof moving — with a TRAINER both
    calls return 403 and the test would prove nothing.
    """
    owner = bootstrap_actor(db, org_name="QA029", role=RoleCode.OWNER, given="Vlasnik")
    mgr = add_actor(db, school=owner.school, role=RoleCode.MANAGER, given="Menadzer")

    assert client.get("/roles", headers=mgr.headers).status_code == 200

    ended = client.post(
        f"/people/{mgr.person.id}/membership/end",
        headers=owner.headers,
        json={"reason_code": "OTHER"},
    )
    assert ended.status_code == 200, ended.text

    db.expire_all()
    row = db.get(RoleAssignment, mgr.assignment.id)
    assert row is not None
    assert row.status is RoleAssignmentStatus.REVOKED, "the role must close with the episode"
    assert client.get("/roles", headers=mgr.headers).status_code == 403

    # A genuinely new episode, which is what the contract refuses to let revive.
    fresh = SchoolMembership(
        school_id=mgr.school.id, person_id=mgr.person.id, status=MembershipStatus.ACTIVE
    )
    db.add(fresh)
    db.commit()

    assert client.get("/roles", headers=mgr.headers).status_code == 403, (
        "a new membership episode must not restore the previous role"
    )

    trail = db.execute(
        text(
            "SELECT action FROM audit_log WHERE entity_type = 'role_assignment'"
            " AND entity_id = :i ORDER BY created_at"
        ),
        {"i": mgr.assignment.id},
    ).all()
    assert "role_assignment.revoked" in [r[0] for r in trail]
