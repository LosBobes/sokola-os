"""M05 §3: what a platform actor may do, decided per request.

Named `platform_roles` rather than `service` for the same reason M03's
`security` module is: the architecture gate stops one domain importing
another's `service`, and the school lifecycle commands have to be able to ask
this question. A port that has to be reachable is not a layering violation
dressed up.

Three things live here, in order of how much care they need:

* **the read** — is this account's hold on this role effective *now*;
* **the guard** — a command boundary that refuses when it is not;
* **the mutations** — grant, suspend, resume, revoke.

The read is the one that matters. §3 requires the request-time check to be the
authority, not a job: `SCHEDULED` reads as not effective and an elapsed
`valid_until` reads as not effective, whether or not anything has got around
to stamping the row. A guard that waited for a sweep would give every expired
platform grant a window of extra life whose length was set by how backed up
the worker was.

**What this module deliberately does not do: step-up authentication.** §2
requires it for platform-role mutation, which is CRITICAL risk, and this
repository has no re-authentication mechanism at all. The product owner chose
to proceed without it rather than build M01 step-up first. Recorded as F-45.
The mitigations that *are* available are applied: only an existing holder of
`platform.roles.manage` may mutate, the last security admin cannot be removed,
every change is audited, and the first assignment cannot be created through
this module at all — see `scripts/grant_platform_role.py`.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass
from app.common.errors import ConflictError, ForbiddenError
from app.domains.authorization.bindings import permissions_for_role_keys
from app.domains.authorization.enums import DOMAIN_PLATFORM
from app.domains.authorization.platform_enums import (
    NON_TEMPORAL_PLATFORM_ROLES,
    OPEN_PLATFORM_ROLE_STATUSES,
    OPERATOR_REVOKE_REASONS,
    PLATFORM_ROLE_GRANTED_ACTION,
    PLATFORM_ROLE_RESUMED_ACTION,
    PLATFORM_ROLE_REVOKED_ACTION,
    PLATFORM_ROLE_SUSPENDED_ACTION,
    PlatformRoleKey,
    PlatformRoleRevokeReason,
    PlatformRoleStatus,
    PlatformRoleSuspendReason,
)
from app.domains.authorization.platform_models import PlatformRoleAssignment
from app.platform import clock
from app.platform.audit.service import record_audit

#: The permission that gates every mutation below (§2, CRITICAL risk). Bound
#: in the registry to `PLATFORM_SECURITY_ADMIN` alone.
MANAGE_PLATFORM_ROLES = "platform.roles.manage"


# ---------------------------------------------------------------------------
# The read (§3)
# ---------------------------------------------------------------------------


def is_effective(
    assignment: PlatformRoleAssignment, *, at: dt.datetime | None = None
) -> bool:
    """Every clause evaluated now, rather than trusted from the status column.

    `SCHEDULED` is false here even once `valid_from` has passed. Nothing in
    this increment materializes it, so treating it as effective would grant
    access the moment a future-dated row was written — which is the opposite
    of what scheduling it meant.
    """
    now = at or clock.now()
    if assignment.status is not PlatformRoleStatus.ACTIVE:
        return False
    if assignment.valid_from > now:
        return False
    # Strictly less than: the instant a window closes is already outside it,
    # the same rule M04's entitlements use.
    return assignment.valid_until is None or now < assignment.valid_until


def effective_roles(
    db: Session, *, user_account_id: str | None, at: dt.datetime | None = None
) -> frozenset[str]:
    """The platform role keys this account holds right now.

    `None` is accepted and answers "none". The dev-header adapter has no
    account (`Principal.user_account_id` is `None`), so a local development
    caller can never hold a platform role — which is correct, and worth
    letting the type system say rather than making every caller remember.
    """
    if user_account_id is None:
        return frozenset()
    rows = db.execute(
        select(PlatformRoleAssignment).where(
            PlatformRoleAssignment.user_account_id == user_account_id,
            PlatformRoleAssignment.status == PlatformRoleStatus.ACTIVE,
        )
    ).scalars()
    return frozenset(row.role_key.value for row in rows if is_effective(row, at=at))


def platform_permissions(
    db: Session, *, user_account_id: str | None, at: dt.datetime | None = None
) -> frozenset[str]:
    """The union of the bindings those roles hold, in the PLATFORM domain.

    A union, never a rank lookup: §3.2 says effective permissions are the
    union of a person's active roles, and administrative rank inherits
    nothing — holding a senior role does not imply a junior one's bindings.
    """
    keys = effective_roles(db, user_account_id=user_account_id, at=at)
    if not keys:
        return frozenset()
    return permissions_for_role_keys(db, role_keys=keys, domain=DOMAIN_PLATFORM)


def has_platform_permission(
    db: Session,
    *,
    user_account_id: str | None,
    permission_key: str,
    at: dt.datetime | None = None,
) -> bool:
    return permission_key in platform_permissions(
        db, user_account_id=user_account_id, at=at
    )


def require_platform_permission(
    db: Session,
    *,
    user_account_id: str | None,
    permission_key: str,
    at: dt.datetime | None = None,
) -> None:
    """Guard for a command boundary. Fail-closed by construction.

    An absent assignment, a suspended one, a scheduled one, an elapsed window
    and a caller with no account at all all reach the same refusal, and the
    refusal says nothing about which — §11's enumeration rule applies to
    platform access too, and "you are not a platform admin" and "your platform
    admin role expired" are not a distinction worth handing out.
    """
    if not has_platform_permission(
        db, user_account_id=user_account_id, permission_key=permission_key, at=at
    ):
        raise ForbiddenError("Nemate ovlašćenje za ovu radnju.")


# ---------------------------------------------------------------------------
# Mutations (§2, §8.1)
# ---------------------------------------------------------------------------


def _open_assignment(
    db: Session, *, user_account_id: str, role_key: PlatformRoleKey
) -> PlatformRoleAssignment | None:
    return db.execute(
        select(PlatformRoleAssignment).where(
            PlatformRoleAssignment.user_account_id == user_account_id,
            PlatformRoleAssignment.role_key == role_key,
            PlatformRoleAssignment.status.in_(OPEN_PLATFORM_ROLE_STATUSES),
        )
    ).scalar_one_or_none()


def _other_active_security_admins(db: Session, *, excluding_id: str) -> int:
    """How many *other* accounts hold an effective security admin role.

    Counted over ACTIVE rows and then filtered through `is_effective`, because
    a row whose window has closed is not a holder even though its status still
    says ACTIVE — exactly the case the read-time rule exists for. Counting the
    column alone would let the last real security admin be removed while an
    expired row stood in for them.
    """
    rows = db.execute(
        select(PlatformRoleAssignment).where(
            PlatformRoleAssignment.role_key == PlatformRoleKey.PLATFORM_SECURITY_ADMIN,
            PlatformRoleAssignment.status == PlatformRoleStatus.ACTIVE,
            PlatformRoleAssignment.id != excluding_id,
        )
    ).scalars()
    return sum(1 for row in rows if is_effective(row))


def grant_platform_role(
    db: Session,
    *,
    actor_account_id: str | None,
    user_account_id: str,
    role_key: PlatformRoleKey,
    source_ticket_ref: str,
    valid_until: dt.datetime | None = None,
    now: dt.datetime | None = None,
) -> PlatformRoleAssignment:
    """Give an account a platform role.

    The caller must already hold `platform.roles.manage`, which the registry
    binds to `PLATFORM_SECURITY_ADMIN` alone. That is what keeps this command
    from being a way to create platform access from nothing: the *first*
    security admin cannot be granted here, only by the operator script, which
    needs database access rather than a session.
    """
    require_platform_permission(
        db, user_account_id=actor_account_id, permission_key=MANAGE_PLATFORM_ROLES
    )
    assert actor_account_id is not None  # the guard above refuses None

    # M05-QA-079: a security admin may not grant themselves a further platform
    # role. Holding `platform.roles.manage` is otherwise enough to reach every
    # other platform role one call at a time — billing, operations, incident
    # command — with no second person involved anywhere in the chain. The
    # permission guard above cannot catch it, because the caller genuinely has
    # the permission; what is wrong is that actor and subject are the same
    # account.
    #
    # The operator bootstrap is unaffected: it writes the row directly, having
    # no session to act in, which is also why the first security admin cannot
    # come from here.
    if user_account_id == actor_account_id:
        raise ForbiddenError("Platformsku ulogu ne možete dodeliti sami sebi.")

    if role_key in NON_TEMPORAL_PLATFORM_ROLES and valid_until is not None:
        raise ConflictError("Ova platformska uloga ne može imati rok važenja.")

    moment = now or clock.now()
    if valid_until is not None and valid_until <= moment:
        raise ConflictError("Rok važenja mora biti u budućnosti.")
    if _open_assignment(db, user_account_id=user_account_id, role_key=role_key):
        raise ConflictError("Nalog već ima otvorenu dodelu ove platformske uloge.")

    assignment = PlatformRoleAssignment(
        user_account_id=user_account_id,
        role_key=role_key,
        status=PlatformRoleStatus.ACTIVE,
        valid_from=moment,
        valid_until=valid_until,
        source_ticket_ref=source_ticket_ref,
        created_by_account_id=actor_account_id,
    )
    db.add(assignment)
    db.flush()
    _audit(
        db,
        action=PLATFORM_ROLE_GRANTED_ACTION,
        assignment=assignment,
        summary=f"Dodeljena platformska uloga {role_key.value}.",
    )
    return assignment


def suspend_platform_role(
    db: Session,
    *,
    actor_account_id: str | None,
    assignment: PlatformRoleAssignment,
    reason: PlatformRoleSuspendReason,
    expected_version: int | None = None,
    now: dt.datetime | None = None,
) -> PlatformRoleAssignment:
    require_platform_permission(
        db, user_account_id=actor_account_id, permission_key=MANAGE_PLATFORM_ROLES
    )
    assert actor_account_id is not None
    if assignment.status is not PlatformRoleStatus.ACTIVE:
        raise ConflictError("Dodela nije aktivna.")
    _check_version(assignment, expected_version)
    _protect_last_security_admin(db, assignment)

    assignment.status = PlatformRoleStatus.SUSPENDED
    assignment.suspended_at = now or clock.now()
    assignment.suspended_by_account_id = actor_account_id
    assignment.suspend_reason_code = reason
    assignment.version += 1
    db.flush()
    _audit(
        db,
        action=PLATFORM_ROLE_SUSPENDED_ACTION,
        assignment=assignment,
        summary=f"Suspendovana platformska uloga {assignment.role_key.value}.",
    )
    return assignment


def resume_platform_role(
    db: Session,
    *,
    actor_account_id: str | None,
    assignment: PlatformRoleAssignment,
    expected_version: int | None = None,
) -> PlatformRoleAssignment:
    """Bring a suspended assignment back, clearing its suspension stamp.

    The stamp is cleared rather than kept because the CHECK ties it to the
    status: a row that is ACTIVE while still carrying a suspension reason
    reads, later, as suspended. The history of *this* suspension lives in the
    audit entry, which is append-only and cannot be cleared.
    """
    require_platform_permission(
        db, user_account_id=actor_account_id, permission_key=MANAGE_PLATFORM_ROLES
    )
    if assignment.status is not PlatformRoleStatus.SUSPENDED:
        raise ConflictError("Dodela nije suspendovana.")
    _check_version(assignment, expected_version)

    assignment.status = PlatformRoleStatus.ACTIVE
    assignment.suspended_at = None
    assignment.suspended_by_account_id = None
    assignment.suspend_reason_code = None
    assignment.version += 1
    db.flush()
    _audit(
        db,
        action=PLATFORM_ROLE_RESUMED_ACTION,
        assignment=assignment,
        summary=f"Vraćena platformska uloga {assignment.role_key.value}.",
    )
    return assignment


def revoke_platform_role(
    db: Session,
    *,
    actor_account_id: str | None,
    assignment: PlatformRoleAssignment,
    reason: PlatformRoleRevokeReason,
    expected_version: int | None = None,
    now: dt.datetime | None = None,
) -> PlatformRoleAssignment:
    require_platform_permission(
        db, user_account_id=actor_account_id, permission_key=MANAGE_PLATFORM_ROLES
    )
    assert actor_account_id is not None
    if reason not in OPERATOR_REVOKE_REASONS:
        # ROLE_EXPIRED is a system code. A revoke claiming to be an expiry,
        # with no expiry, is a lie the audit trail would carry forever.
        raise ConflictError("Razlog opoziva nije iz dozvoljenog registra.")
    if assignment.status not in OPEN_PLATFORM_ROLE_STATUSES:
        raise ConflictError("Dodela je već zatvorena.")
    _check_version(assignment, expected_version)
    _protect_last_security_admin(db, assignment)

    assignment.status = PlatformRoleStatus.REVOKED
    assignment.revoked_at = now or clock.now()
    assignment.revoked_by_account_id = actor_account_id
    assignment.revoke_reason_code = reason
    # A revoke supersedes any suspension; the CHECK ties the stamp to status.
    assignment.suspended_at = None
    assignment.suspended_by_account_id = None
    assignment.suspend_reason_code = None
    assignment.version += 1
    db.flush()
    _audit(
        db,
        action=PLATFORM_ROLE_REVOKED_ACTION,
        assignment=assignment,
        summary=f"Opozvana platformska uloga {assignment.role_key.value}.",
    )
    return assignment


def _protect_last_security_admin(
    db: Session, assignment: PlatformRoleAssignment
) -> None:
    """§2: removing a security admin must keep at least one other active one.

    Without this, one command can leave the platform with nobody able to grant
    platform roles — and the recovery path would be the operator script and a
    database connection, which is exactly the situation the script exists to
    be used *once*.
    """
    if assignment.role_key is not PlatformRoleKey.PLATFORM_SECURITY_ADMIN:
        return
    if _other_active_security_admins(db, excluding_id=assignment.id) == 0:
        raise ConflictError(
            "Platforma ne može ostati bez aktivnog bezbednosnog administratora."
        )


def _check_version(
    assignment: PlatformRoleAssignment, expected_version: int | None
) -> None:
    if expected_version is not None and expected_version != assignment.version:
        raise ConflictError("Dodela je u međuvremenu izmenjena.")


def _audit(
    db: Session,
    *,
    action: str,
    assignment: PlatformRoleAssignment,
    summary: str,
) -> None:
    """One audit entry per transition, with no `school_id`.

    §11: a platform event uses an explicit platform scope rather than `null`
    out of habit — here the absence is the scope, because a platform role
    belongs to no school, and `record_audit` chains platform entries on their
    own key. The summary names the role and never the account: who it was is
    `entity_id` and the context, read under a purpose-limited view.
    """
    record_audit(
        db,
        data_class=AuditDataClass.ROLE,
        action=action,
        entity_type="platform_role_assignment",
        entity_id=assignment.id,
        summary=summary,
        school_id=None,
        context={
            "role_key": assignment.role_key.value,
            "status": assignment.status.value,
            "source_ticket_ref": assignment.source_ticket_ref,
        },
    )
