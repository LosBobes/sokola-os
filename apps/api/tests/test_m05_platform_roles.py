"""M05 §2–§3: platform role assignment, effectiveness and the guard.

The increment's shape was decided by the product owner: build the platform
role and guard, keep owner de/reactivation working alongside it (so F-41 stays
open rather than closing), and proceed without step-up authentication
(recorded as F-45).

What these tests are most concerned with is the **read**. §3 makes the
request-time check the authority, not a job, and this repo has no job at all —
so `SCHEDULED` and an elapsed `valid_until` must both read as ineffective
without anything having stamped the row. A guard that trusted the status
column would hand out platform access on the strength of a row nobody had got
around to expiring.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.common.errors import ConflictError, ForbiddenError
from app.domains.authorization.enums import DOMAIN_PLATFORM
from app.domains.authorization.platform_enums import (
    OPEN_PLATFORM_ROLE_STATUSES,
    PlatformRoleKey,
    PlatformRoleRevokeReason,
    PlatformRoleStatus,
    PlatformRoleSuspendReason,
)
from app.domains.authorization.platform_models import PlatformRoleAssignment
from app.domains.authorization.platform_roles import (
    MANAGE_PLATFORM_ROLES,
    effective_roles,
    grant_platform_role,
    has_platform_permission,
    is_effective,
    platform_permissions,
    require_platform_permission,
    resume_platform_role,
    revoke_platform_role,
    suspend_platform_role,
)
from app.domains.identity.accounts import create_account_with_identity
from app.domains.identity.auth_enums import GOOGLE_ISSUER, GOOGLE_PROVIDER
from app.domains.identity.auth_models import AuthIdentity, UserAccount
from app.domains.identity.enums import RoleCode
from app.domains.school.enums import SchoolStatus
from app.domains.school.models import School
from app.domains.tenancy import security as tenant_security
from app.platform import clock
from app.security.csrf import CSRF_COOKIE, CSRF_HEADER
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.factories import bootstrap_actor, make_person, make_school


def _account(db: Session, subject: str) -> UserAccount:
    person = make_person(db, given="P", family=subject[-6:])
    account, _ = create_account_with_identity(
        db,
        person_id=person.id,
        provider_key=GOOGLE_PROVIDER,
        issuer=GOOGLE_ISSUER,
        subject=subject,
        login_email=f"{subject}@example.invalid",
        email_verified=True,
    )
    db.commit()
    return account


def _seed_assignment(
    db: Session,
    account: UserAccount,
    role_key: PlatformRoleKey = PlatformRoleKey.PLATFORM_SECURITY_ADMIN,
    *,
    status: PlatformRoleStatus = PlatformRoleStatus.ACTIVE,
    valid_from: dt.datetime | None = None,
    valid_until: dt.datetime | None = None,
) -> PlatformRoleAssignment:
    """Insert an assignment directly, the way the operator script does.

    Used instead of `grant_platform_role` wherever a test needs the *first*
    holder, because the command refuses a caller who holds nothing — which is
    the property that keeps it from being a way to create platform access out
    of nothing.
    """
    now = clock.now()
    assignment = PlatformRoleAssignment(
        user_account_id=account.id,
        role_key=role_key,
        status=status,
        valid_from=valid_from or now,
        valid_until=valid_until,
        source_ticket_ref="OPS-SEED",
        created_by_account_id=account.id,
        suspended_at=now if status is PlatformRoleStatus.SUSPENDED else None,
        suspended_by_account_id=(
            account.id if status is PlatformRoleStatus.SUSPENDED else None
        ),
        suspend_reason_code=(
            PlatformRoleSuspendReason.OPERATIONAL_PAUSE
            if status is PlatformRoleStatus.SUSPENDED
            else None
        ),
        revoked_at=now if status is PlatformRoleStatus.REVOKED else None,
        revoked_by_account_id=(
            account.id if status is PlatformRoleStatus.REVOKED else None
        ),
        revoke_reason_code=(
            PlatformRoleRevokeReason.DUTIES_CHANGED
            if status is PlatformRoleStatus.REVOKED
            else None
        ),
    )
    db.add(assignment)
    db.commit()
    return assignment


# ---------------------------------------------------------------------------
# The enum and the registry must agree
# ---------------------------------------------------------------------------


def test_the_platform_role_enum_matches_the_registry(db: Session) -> None:
    """The five keys exist twice — as a column enum and as `RoleDefinition`
    rows — and the duplication must not drift.

    A column needs a closed set the database can check; the registry needs
    rows a published revision can bind permissions to. Neither can be derived
    from the other at import time without a database, so this asserts the
    agreement instead.
    """
    from app.domains.authorization.models import RoleDefinition

    registry_keys = set(
        db.execute(
            select(RoleDefinition.role_key).where(
                RoleDefinition.authorization_domain_key == DOMAIN_PLATFORM
            )
        ).scalars()
    )
    assert registry_keys == {r.value for r in PlatformRoleKey}


def test_the_open_statuses_constant_matches_the_partial_index(db: Session) -> None:
    """`OPEN_PLATFORM_ROLE_STATUSES` and the index predicate describe the same
    set, asserted against the live index definition rather than the source.

    If they ever disagree, the service would consider a row open that the
    database would happily duplicate — the kind of divergence that produces
    two active platform admins where the code believes there is one.
    """
    predicate = db.execute(
        text(
            "SELECT pg_get_expr(indpred, indrelid) FROM pg_index i "
            "JOIN pg_class c ON c.oid = i.indexrelid "
            "WHERE c.relname = 'uq_platform_role_assignment_open'"
        )
    ).scalar_one()
    for status in OPEN_PLATFORM_ROLE_STATUSES:
        assert status.value in predicate
    for terminal in (PlatformRoleStatus.REVOKED, PlatformRoleStatus.EXPIRED):
        assert terminal.value not in predicate


# ---------------------------------------------------------------------------
# The read (§3)
# ---------------------------------------------------------------------------


def test_a_scheduled_assignment_grants_nothing(db: Session) -> None:
    """§3: the request-time check is the authority, and nothing materializes
    SCHEDULED in this repo.

    Treating it as effective would grant access the moment a future-dated row
    was written, which is the opposite of what scheduling it meant.
    """
    account = _account(db, "sub-scheduled")
    assignment = _seed_assignment(
        db, account, status=PlatformRoleStatus.SCHEDULED
    )
    assert not is_effective(assignment)
    assert effective_roles(db, user_account_id=account.id) == frozenset()
    assert platform_permissions(db, user_account_id=account.id) == frozenset()


def test_a_suspended_assignment_grants_nothing(db: Session) -> None:
    account = _account(db, "sub-suspended")
    _seed_assignment(db, account, status=PlatformRoleStatus.SUSPENDED)
    assert effective_roles(db, user_account_id=account.id) == frozenset()


def test_the_instant_a_window_closes_is_already_outside_it(db: Session) -> None:
    """An elapsed `valid_until` is ineffective even though the row still says
    ACTIVE — there is no expiry job, and the reader does not wait for one.

    The same boundary rule M04's entitlements use: `now == valid_until` is
    already outside the window.
    """
    account = _account(db, "sub-window")
    closes_at = clock.now() + dt.timedelta(hours=1)
    assignment = _seed_assignment(
        db,
        account,
        role_key=PlatformRoleKey.PLATFORM_OPERATIONS_ADMIN,
        valid_until=closes_at,
    )

    assert is_effective(assignment, at=closes_at - dt.timedelta(seconds=1))
    assert not is_effective(assignment, at=closes_at)
    assert not is_effective(assignment, at=closes_at + dt.timedelta(days=7))
    assert assignment.status is PlatformRoleStatus.ACTIVE, "no job has run"
    assert effective_roles(db, user_account_id=account.id, at=closes_at) == frozenset()


def test_a_future_valid_from_grants_nothing_yet(db: Session) -> None:
    account = _account(db, "sub-future")
    starts_at = clock.now() + dt.timedelta(days=1)
    assignment = _seed_assignment(
        db,
        account,
        role_key=PlatformRoleKey.PLATFORM_SUPPORT_AGENT,
        valid_from=starts_at,
    )
    assert not is_effective(assignment)
    assert is_effective(assignment, at=starts_at)


def test_an_account_less_caller_holds_no_platform_role(db: Session) -> None:
    """The dev-header adapter has no account, so it can never hold a platform
    role — and the guard says so without the caller having to remember.

    Worth asserting rather than assuming: `Principal.user_account_id` is
    `None` on that path, and a guard that indexed a dict by it would have
    raised instead of refusing, which is a 500 where a 403 belongs.
    """
    assert effective_roles(db, user_account_id=None) == frozenset()
    assert platform_permissions(db, user_account_id=None) == frozenset()
    assert not has_platform_permission(
        db, user_account_id=None, permission_key=MANAGE_PLATFORM_ROLES
    )
    with pytest.raises(ForbiddenError):
        require_platform_permission(
            db, user_account_id=None, permission_key=MANAGE_PLATFORM_ROLES
        )


def test_an_effective_security_admin_holds_the_registry_bindings(db: Session) -> None:
    """The union comes from the published revision, not from a list here."""
    from app.domains.authorization.bindings import permissions_for_role_keys

    account = _account(db, "sub-sec")
    _seed_assignment(db, account)

    expected = permissions_for_role_keys(
        db,
        role_keys=frozenset({PlatformRoleKey.PLATFORM_SECURITY_ADMIN.value}),
        domain=DOMAIN_PLATFORM,
    )
    assert expected, "revision 1.3 must bind the security admin, or this proves nothing"
    assert platform_permissions(db, user_account_id=account.id) == expected
    assert MANAGE_PLATFORM_ROLES in expected


def test_roles_do_not_inherit_one_anothers_permissions(db: Session) -> None:
    """§3.2 point 2: administrative rank inherits nothing.

    A security admin does not get the operations admin's school-lifecycle
    permission by being senior; the only way to hold a permission is for a
    role you hold to be bound to it.
    """
    account = _account(db, "sub-norank")
    _seed_assignment(db, account)
    perms = platform_permissions(db, user_account_id=account.id)
    assert "platform.schools.lifecycle.manage" not in perms


# ---------------------------------------------------------------------------
# Mutations (§2)
# ---------------------------------------------------------------------------


def test_only_a_holder_of_manage_may_grant(db: Session) -> None:
    """The command cannot create platform access from nothing.

    This is the property that makes the missing step-up (F-45) less sharp: an
    attacker with a session, however privileged, reaches a refusal here. The
    first assignment needs the operator script and a database connection.
    """
    outsider = _account(db, "sub-outsider")
    target = _account(db, "sub-target")

    with pytest.raises(ForbiddenError):
        grant_platform_role(
            db,
            actor_account_id=outsider.id,
            user_account_id=target.id,
            role_key=PlatformRoleKey.PLATFORM_SUPPORT_AGENT,
            source_ticket_ref="OPS-1",
        )
    db.rollback()
    assert (
        db.execute(select(func.count()).select_from(PlatformRoleAssignment)).scalar_one()
        == 0
    )


def test_a_security_admin_may_grant_and_the_grant_is_audited(db: Session) -> None:
    admin = _account(db, "sub-admin")
    _seed_assignment(db, admin)
    target = _account(db, "sub-grantee")

    assignment = grant_platform_role(
        db,
        actor_account_id=admin.id,
        user_account_id=target.id,
        role_key=PlatformRoleKey.PLATFORM_OPERATIONS_ADMIN,
        source_ticket_ref="OPS-7",
    )
    db.commit()

    assert assignment.status is PlatformRoleStatus.ACTIVE
    assert effective_roles(db, user_account_id=target.id) == {
        PlatformRoleKey.PLATFORM_OPERATIONS_ADMIN.value
    }
    trail = db.execute(
        text("SELECT action, entity_id, context FROM audit_log WHERE entity_type = :t"),
        {"t": "platform_role_assignment"},
    ).all()
    assert any(row[0] == "m05.platform_role.granted" for row in trail)
    # The summary and context name the role and the ticket, never the account.
    joined = " ".join(str(r) for r in trail)
    assert "OPS-7" in joined
    assert target.id not in joined.replace(assignment.id, "")


def test_one_open_assignment_per_account_and_role(db: Session) -> None:
    """§2, and the index is partial so history does not block a re-grant.

    Both halves: a second *open* row is refused by the database even when the
    service is bypassed, and a terminal row leaves the slot free.
    """
    account = _account(db, "sub-oneopen")
    _seed_assignment(db, account, role_key=PlatformRoleKey.PLATFORM_BILLING_ADMIN)

    db.add(
        PlatformRoleAssignment(
            user_account_id=account.id,
            role_key=PlatformRoleKey.PLATFORM_BILLING_ADMIN,
            status=PlatformRoleStatus.ACTIVE,
            valid_from=clock.now(),
            source_ticket_ref="OPS-DUP",
            created_by_account_id=account.id,
        )
    )
    with pytest.raises(IntegrityError) as raised:
        db.commit()
    assert "uq_platform_role_assignment_open" in str(raised.value)
    db.rollback()

    # A revoked row is history: the same role may be granted again.
    db.execute(
        text(
            "UPDATE platform_role_assignment SET status = 'REVOKED', "
            "revoked_at = now(), revoked_by_account_id = :a, "
            "revoke_reason_code = 'DUTIES_CHANGED' WHERE user_account_id = :a"
        ),
        {"a": account.id},
    )
    db.commit()
    again = _seed_assignment(
        db, account, role_key=PlatformRoleKey.PLATFORM_BILLING_ADMIN
    )
    assert again.status is PlatformRoleStatus.ACTIVE


def test_the_last_security_admin_cannot_be_removed(db: Session) -> None:
    """§2. Without this, one command leaves the platform with nobody able to
    grant platform roles, and the only recovery is the operator script — which
    exists to be used once."""
    admin = _account(db, "sub-last")
    assignment = _seed_assignment(db, admin)

    with pytest.raises(ConflictError):
        revoke_platform_role(
            db,
            actor_account_id=admin.id,
            assignment=assignment,
            reason=PlatformRoleRevokeReason.DUTIES_CHANGED,
        )
    db.rollback()
    with pytest.raises(ConflictError):
        suspend_platform_role(
            db,
            actor_account_id=admin.id,
            assignment=assignment,
            reason=PlatformRoleSuspendReason.SECURITY_INCIDENT,
        )
    db.rollback()
    assert effective_roles(db, user_account_id=admin.id) == {
        PlatformRoleKey.PLATFORM_SECURITY_ADMIN.value
    }


def test_the_second_security_admin_may_be_removed(db: Session) -> None:
    """The protection is about the *last* one, not about the role."""
    first = _account(db, "sub-first")
    _seed_assignment(db, first)
    second = _account(db, "sub-second")
    other = grant_platform_role(
        db,
        actor_account_id=first.id,
        user_account_id=second.id,
        role_key=PlatformRoleKey.PLATFORM_SECURITY_ADMIN,
        source_ticket_ref="OPS-2",
    )
    db.commit()

    revoke_platform_role(
        db,
        actor_account_id=first.id,
        assignment=other,
        reason=PlatformRoleRevokeReason.EMPLOYMENT_ENDED,
    )
    db.commit()
    assert other.status is PlatformRoleStatus.REVOKED
    assert effective_roles(db, user_account_id=second.id) == frozenset()


def test_a_future_dated_admin_does_not_stand_in_for_the_last_one(db: Session) -> None:
    """The subtle one: the last-admin protection counts *effective* holders.

    A second security admin dated to start tomorrow has status ACTIVE — there
    is no job to hold it at SCHEDULED — and grants nothing today. Counting the
    status column alone would let the last *real* admin be removed while that
    row stood in for them, leaving the platform with no effective security
    admin at all until tomorrow.

    This is the one constructible stand-in for that role. The first version of
    this test used an elapsed `valid_until`, and the database refused the row:
    `ck_platform_role_security_admin_not_temporal` makes a time-boxed security
    admin impossible even through raw SQL. That is a stronger guarantee than
    the test assumed, and worth recording — the window-based stand-in cannot
    happen, while the future-dated one can.
    """
    real = _account(db, "sub-real")
    real_assignment = _seed_assignment(db, real)
    future = _account(db, "sub-future-admin")
    tomorrow = clock.now() + dt.timedelta(days=1)
    future_assignment = _seed_assignment(db, future, valid_from=tomorrow)

    # Status says ACTIVE; the read says otherwise, and the read is authority.
    assert future_assignment.status is PlatformRoleStatus.ACTIVE
    assert not is_effective(future_assignment)
    assert effective_roles(db, user_account_id=future.id) == frozenset()

    with pytest.raises(ConflictError):
        revoke_platform_role(
            db,
            actor_account_id=real.id,
            assignment=real_assignment,
            reason=PlatformRoleRevokeReason.DUTIES_CHANGED,
        )
    db.rollback()

    # The same row becomes a real holder once its window opens — same row,
    # different answer, which is what deciding at read time means.
    assert is_effective(future_assignment, at=tomorrow)


def test_suspend_then_resume_restores_access_and_clears_the_stamp(
    db: Session,
) -> None:
    admin = _account(db, "sub-sadmin")
    _seed_assignment(db, admin)
    agent = _account(db, "sub-agent")
    assignment = grant_platform_role(
        db,
        actor_account_id=admin.id,
        user_account_id=agent.id,
        role_key=PlatformRoleKey.PLATFORM_SUPPORT_AGENT,
        source_ticket_ref="OPS-3",
    )
    db.commit()

    suspend_platform_role(
        db,
        actor_account_id=admin.id,
        assignment=assignment,
        reason=PlatformRoleSuspendReason.UNDER_INVESTIGATION,
    )
    db.commit()
    assert effective_roles(db, user_account_id=agent.id) == frozenset()
    assert assignment.suspend_reason_code is PlatformRoleSuspendReason.UNDER_INVESTIGATION

    resume_platform_role(db, actor_account_id=admin.id, assignment=assignment)
    db.commit()
    assert effective_roles(db, user_account_id=agent.id) == {
        PlatformRoleKey.PLATFORM_SUPPORT_AGENT.value
    }
    # The stamp is cleared because the CHECK ties it to the status; the history
    # of the suspension lives in the append-only audit trail instead.
    assert assignment.suspended_at is None
    assert assignment.suspend_reason_code is None


def test_a_revoke_cannot_claim_to_be_an_expiry(db: Session) -> None:
    """`ROLE_EXPIRED` is a system code. A revoke claiming to be one, with no
    expiry, is a lie the audit trail would carry forever."""
    admin = _account(db, "sub-radmin")
    _seed_assignment(db, admin)
    agent = _account(db, "sub-ragent")
    assignment = grant_platform_role(
        db,
        actor_account_id=admin.id,
        user_account_id=agent.id,
        role_key=PlatformRoleKey.PLATFORM_INCIDENT_COMMANDER,
        source_ticket_ref="OPS-4",
    )
    db.commit()

    with pytest.raises(ConflictError):
        revoke_platform_role(
            db,
            actor_account_id=admin.id,
            assignment=assignment,
            reason=PlatformRoleRevokeReason.ROLE_EXPIRED,
        )
    db.rollback()
    assert assignment.status is PlatformRoleStatus.ACTIVE


def test_a_security_admin_cannot_be_time_boxed(db: Session) -> None:
    """§2 makes it non-temporal, enforced in the database as well as the
    service — otherwise an import could create one that quietly expires."""
    admin = _account(db, "sub-nontemporal")
    _seed_assignment(db, admin)
    target = _account(db, "sub-boxed")

    with pytest.raises(ConflictError):
        grant_platform_role(
            db,
            actor_account_id=admin.id,
            user_account_id=target.id,
            role_key=PlatformRoleKey.PLATFORM_SECURITY_ADMIN,
            source_ticket_ref="OPS-5",
            valid_until=clock.now() + dt.timedelta(days=30),
        )
    db.rollback()

    db.add(
        PlatformRoleAssignment(
            user_account_id=target.id,
            role_key=PlatformRoleKey.PLATFORM_SECURITY_ADMIN,
            status=PlatformRoleStatus.ACTIVE,
            valid_from=clock.now(),
            valid_until=clock.now() + dt.timedelta(days=30),
            source_ticket_ref="OPS-BYPASS",
            created_by_account_id=target.id,
        )
    )
    with pytest.raises(IntegrityError) as raised:
        db.commit()
    assert "ck_platform_role_security_admin_not_temporal" in str(raised.value)
    db.rollback()


# ---------------------------------------------------------------------------
# The de/reactivation move, over HTTP (M04 §3.6, both paths)
# ---------------------------------------------------------------------------


def _signed_in_account(client: TestClient, db: Session, email: str) -> UserAccount:
    """Register through the real password path so the client holds a real
    session cookie, then return the account it created.

    A real session is required rather than the dev header, because a platform
    assignment hangs off a `UserAccount` and the dev-header adapter has none.
    That is the property `test_an_account_less_caller_holds_no_platform_role`
    asserts from the other side.
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
        select(AuthIdentity.user_account_id).where(
            AuthIdentity.login_email.ilike(email)
        )
    ).scalar_one()
    account = db.get(UserAccount, account_id)
    assert account is not None
    return account


def _csrf(client: TestClient) -> dict[str, str]:
    """The header a cookie-authenticated mutation needs.

    Without it every POST below returns 403 `CSRF_FAILED` — which looks
    exactly like the permission refusal these tests are trying to prove, and
    two of them did pass on it before this was added. So each refusal below
    asserts the error *code*, not just the status.
    """
    token = client.cookies.get(CSRF_COOKIE)
    assert token, "the register call should have set a CSRF cookie"
    return {CSRF_HEADER: token}


def test_a_platform_operations_admin_can_deactivate_and_reactivate(
    db: Session, client: TestClient
) -> None:
    """SCH-05 and SCH-06 by the platform, which is what §3.6 asks for.

    The round trip matters: reactivation bumps the tenant access version too,
    so contexts built while the school was off do not simply resume.
    """
    account = _signed_in_account(client, db, "ops@example.invalid")
    _seed_assignment(
        db, account, role_key=PlatformRoleKey.PLATFORM_OPERATIONS_ADMIN
    )
    school = make_school(db, name="Platformska skola")
    before = tenant_security.current_version(db, school.id)

    off = client.post(
        f"/platform/schools/{school.id}/deactivate",
        json={"reason_code": "OPERATIONAL_PAUSE", "case_reference": "OPS-9"},
        headers=_csrf(client),
    )
    assert off.status_code == 200, off.text
    assert off.json()["status"] == "DEACTIVATED"
    mid = tenant_security.current_version(db, school.id)
    assert mid > before

    on = client.post(
        f"/platform/schools/{school.id}/reactivate",
        json={"reason_code": "OPERATIONAL_RESUME", "case_reference": "OPS-9"},
        headers=_csrf(client),
    )
    assert on.status_code == 200, on.text
    assert on.json()["status"] == "ACTIVE"
    assert tenant_security.current_version(db, school.id) > mid


def test_a_signed_in_caller_without_the_platform_role_is_refused(
    db: Session, client: TestClient
) -> None:
    """Holding a session is not holding platform access, and the refusal
    happens before the school is touched."""
    _signed_in_account(client, db, "nobody@example.invalid")
    school = make_school(db, name="Netaknuta skola")

    resp = client.post(
        f"/platform/schools/{school.id}/deactivate",
        json={"reason_code": "OPERATIONAL_PAUSE", "case_reference": "OPS-10"},
        headers=_csrf(client),
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN", (
        "must fail on the permission guard, not on CSRF"
    )
    db.expire_all()
    assert db.get(School, school.id).status is SchoolStatus.ACTIVE


def test_a_security_admin_cannot_deactivate_a_school(
    db: Session, client: TestClient
) -> None:
    """§3.2 point 2 again, where it bites hardest: a security admin is senior
    and still holds no school-lifecycle permission, because no role they hold
    is bound to it."""
    account = _signed_in_account(client, db, "sec@example.invalid")
    _seed_assignment(db, account, role_key=PlatformRoleKey.PLATFORM_SECURITY_ADMIN)
    school = make_school(db, name="Nije za bezbednjaka")

    resp = client.post(
        f"/platform/schools/{school.id}/deactivate",
        json={"reason_code": "OPERATIONAL_PAUSE", "case_reference": "OPS-11"},
        headers=_csrf(client),
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN", (
        "must fail on the permission guard, not on CSRF"
    )
    db.expire_all()
    assert db.get(School, school.id).status is SchoolStatus.ACTIVE


def test_a_reason_outside_the_registry_is_refused(
    db: Session, client: TestClient
) -> None:
    """§8.1.2: the reason comes from the SCH-05 registry.

    `INITIAL_ACTIVATION` is a system code written by the provisioning path. A
    platform actor claiming it would put a false account of what happened into
    an append-only history, so it is refused rather than accepted and ignored.
    """
    account = _signed_in_account(client, db, "ops2@example.invalid")
    _seed_assignment(
        db, account, role_key=PlatformRoleKey.PLATFORM_OPERATIONS_ADMIN
    )
    school = make_school(db, name="Pogresan razlog")

    resp = client.post(
        f"/platform/schools/{school.id}/deactivate",
        json={"reason_code": "INITIAL_ACTIVATION", "case_reference": "OPS-12"},
        headers=_csrf(client),
    )
    assert resp.status_code == 409
    db.expire_all()
    assert db.get(School, school.id).status is SchoolStatus.ACTIVE


def test_the_owner_path_still_works_alongside_the_platform_one(
    db: Session, client: TestClient
) -> None:
    """**Both paths**, which is the decision this increment implements.

    §3.6 makes de/reactivation platform-only, and this repo has always let an
    active owner do it. Taking that away before anyone holds a platform role
    would have meant nobody could deactivate a school at all — no assignment
    exists anywhere until the operator script is run. So the owner route is
    untouched and asserted here, and F-41 stays open rather than closing.
    """
    actor = bootstrap_actor(db, org_name="Vlasnikova skola", given="Ana", role=RoleCode.OWNER)
    resp = client.post("/schools/current/deactivate", headers=actor.headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "DEACTIVATED"
