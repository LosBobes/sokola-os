"""M03 tenancy enums.

`School` is the only operational security tenant (§1), so everything here is
about one school's access as a whole — never about one person's place in it,
which is M06's, nor about what they may do, which is M05's.
"""

from __future__ import annotations

import enum


class TenantInvalidationReason(enum.StrEnum):
    """§5.2 `last_invalidation_reason_code`, a closed `Code64` registry.

    Closed because this is what a security reviewer reads months later to answer
    "why did an entire school lose access on the 14th". Free text answers that
    with whatever the caller happened to be thinking.
    """

    SCHOOL_DEACTIVATED = "SCHOOL_DEACTIVATED"
    SCHOOL_REACTIVATED = "SCHOOL_REACTIVATED"
    SECURITY_INCIDENT = "SECURITY_INCIDENT"
    OWNERSHIP_TRANSFERRED = "OWNERSHIP_TRANSFERRED"
    SUPPORT_ACCESS_REVOKED = "SUPPORT_ACCESS_REVOKED"
    PLATFORM_POLICY = "PLATFORM_POLICY"
    LEGAL_HOLD = "LEGAL_HOLD"


#: §15's outbox event for a tenant-wide invalidation. Tenant-scoped, so unlike
#: M01's account event it carries `school_id` — §11: "svaki tenant događaj ima
#: `tenant_id=school_id`; platform događaj koristi eksplicitni platform scope,
#: ne `null` po navici".
SCHOOL_ACCESS_INVALIDATED_EVENT = "tenancy.school_access_invalidated"


class TenantContextStatus(enum.StrEnum):
    """§5.3. `ABSENT` is the absence of a row before the first selection, so it
    is not a value here — only the two states a stored row can be in."""

    ACTIVE = "ACTIVE"
    INVALIDATED = "INVALIDATED"


class ContextInvalidationReason(enum.StrEnum):
    """§9's reasons for a context leaving `ACTIVE`, as a closed `Code64` set.

    A context ends for very different reasons — the person asked, their access
    was taken away, the school went away, the session went away — and a
    security review that cannot tell them apart cannot answer the only question
    worth asking afterwards.
    """

    USER_CLEARED = "USER_CLEARED"
    #: The version snapshot no longer matches the authority it was taken from
    #: (§8 step 3). Not a decision anyone made; a decision made elsewhere that
    #: this context is now too old to act on.
    CONTEXT_STALE = "CONTEXT_STALE"
    SESSION_ENDED = "SESSION_ENDED"
    MEMBERSHIP_REVOKED = "MEMBERSHIP_REVOKED"
    SCHOOL_UNAVAILABLE = "SCHOOL_UNAVAILABLE"
    TENANT_ACCESS_INVALIDATED = "TENANT_ACCESS_INVALIDATED"
    SWITCHED_AWAY = "SWITCHED_AWAY"


#: §3: the closed display registry `workspace_key` is drawn from. These decide
#: navigation and the landing screen and nothing else — §3 again: "Nije role
#: assignment, permission filter niti authorization dokaz."
WORKSPACE_ADMIN = "ADMIN"
WORKSPACE_INSTRUCTOR = "INSTRUCTOR"
WORKSPACE_GUARDIAN = "GUARDIAN"
WORKSPACE_PAYER = "PAYER"

WORKSPACE_KEYS = frozenset(
    {WORKSPACE_ADMIN, WORKSPACE_INSTRUCTOR, WORKSPACE_GUARDIAN, WORKSPACE_PAYER}
)


class SchoolMode(enum.StrEnum):
    """§6.1 vs §6.2: what a context is allowed to be used *for*.

    Not the school's status — the status is M04's and lives on `School`. This
    is what the status plus the actor means for this one session: a school
    that is `ACTIVE` gives `REGULAR` work, a school that is `IN_PREPARATION`
    gives only setup, and `DEACTIVATED` gives no context at all (§6.3), so it
    has no mode here.
    """

    REGULAR = "REGULAR"
    #: §6.2. Opens only O01–O07 and the explicit M20/M04 setup commands — never
    #: regular Finance, Attendance, Documents, Reporting or a guardian
    #: workspace.
    SETUP_ONLY = "SETUP_ONLY"


#: Where a client may start once a context resolves.
#:
#: For regular work this is the role home, which already dispatches by role in
#: the web app; naming a per-workspace route here would put the same decision
#: in two places and let them drift.
START_ROUTE_REGULAR = "/"
#: The setup surface a `SETUP_ONLY` context may open. §14's UI for this does
#: not exist yet (recorded as F-28); the contract still says what the route is
#: rather than sending a setup-only actor to the regular home, which §6.2
#: forbids.
START_ROUTE_SETUP = "/skola/priprema"
