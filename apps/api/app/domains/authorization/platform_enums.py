"""M05 §2 platform-role enums.

A platform role is not a school role with a wider reach. It is a different
kind of thing: it attaches to a **`UserAccount`**, never to a `Person` in a
school, and it carries no `school_id`, no `SchoolMembership` and no workspace.
§3 is explicit that a platform permission "ne otvara podatke dece, attendance,
dokumente ili school finance" — holding one is not a way into a tenant.

That is why these live in their own module rather than beside the school role
enums: the two must not acquire a shared base class that tempts a caller to
treat one as a variant of the other.
"""

from __future__ import annotations

import enum


class PlatformRoleKey(enum.StrEnum):
    """§2's canonical platform role keys.

    These five strings also exist in the policy registry as `RoleDefinition`
    rows under the `PLATFORM` domain. Duplicating them as an enum is
    deliberate — a column needs a closed set the database can check — and
    `test_the_platform_role_enum_matches_the_registry` asserts the two agree,
    so the duplication cannot drift into disagreement.
    """

    PLATFORM_SECURITY_ADMIN = "PLATFORM_SECURITY_ADMIN"
    PLATFORM_OPERATIONS_ADMIN = "PLATFORM_OPERATIONS_ADMIN"
    PLATFORM_SUPPORT_AGENT = "PLATFORM_SUPPORT_AGENT"
    PLATFORM_INCIDENT_COMMANDER = "PLATFORM_INCIDENT_COMMANDER"
    PLATFORM_BILLING_ADMIN = "PLATFORM_BILLING_ADMIN"


class PlatformRoleStatus(enum.StrEnum):
    """§2's assignment lifecycle.

    `SCHEDULED` exists because §2 allows an assignment to be created before it
    takes effect. Nothing in this increment materializes it — there is no job
    — and that is safe in only one direction: the read-time guard treats
    `SCHEDULED` as **not effective**, so an assignment that has not been
    materialized grants nothing rather than granting early.

    `REVOKED` and `EXPIRED` are terminal. Coming back is a new assignment with
    a new id, so "this person held platform access twice" stays two rows.
    """

    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


#: The statuses an assignment can still come back from, and therefore the ones
#: that occupy the "one open assignment per (account, role)" slot §2 requires.
#: A terminal row must not block a fresh grant to the same person.
OPEN_PLATFORM_ROLE_STATUSES = (
    PlatformRoleStatus.SCHEDULED,
    PlatformRoleStatus.ACTIVE,
    PlatformRoleStatus.SUSPENDED,
)


class PlatformRoleSuspendReason(enum.StrEnum):
    """Closed registry, because this is what a security reviewer reads months
    later to answer "why did this person lose platform access on the 14th".
    Free text answers that with whatever the caller happened to be thinking."""

    SECURITY_INCIDENT = "SECURITY_INCIDENT"
    UNDER_INVESTIGATION = "UNDER_INVESTIGATION"
    LEAVE_OF_ABSENCE = "LEAVE_OF_ABSENCE"
    OPERATIONAL_PAUSE = "OPERATIONAL_PAUSE"


class PlatformRoleRevokeReason(enum.StrEnum):
    """As above, for the terminal transition.

    `ROLE_EXPIRED` is a system code: the read-time guard, not an operator,
    decides that a window has closed, and a human revoke claiming to be an
    expiry would be a lie the audit trail carries forever.
    """

    EMPLOYMENT_ENDED = "EMPLOYMENT_ENDED"
    DUTIES_CHANGED = "DUTIES_CHANGED"
    SECURITY_DECISION = "SECURITY_DECISION"
    GRANTED_IN_ERROR = "GRANTED_IN_ERROR"
    #: System code, never operator-selectable.
    ROLE_EXPIRED = "ROLE_EXPIRED"


#: The reasons an operator may choose. `ROLE_EXPIRED` is excluded on purpose.
OPERATOR_REVOKE_REASONS = frozenset(
    r for r in PlatformRoleRevokeReason if r is not PlatformRoleRevokeReason.ROLE_EXPIRED
)

#: §2: `PLATFORM_SECURITY_ADMIN` is non-temporal — it has no `valid_until` and
#: is removed only by an explicit command that keeps at least one other active
#: holder. Every other platform role may be time-boxed.
NON_TEMPORAL_PLATFORM_ROLES = frozenset({PlatformRoleKey.PLATFORM_SECURITY_ADMIN})

#: §8.1's audit actions for this aggregate.
PLATFORM_ROLE_GRANTED_ACTION = "m05.platform_role.granted"
PLATFORM_ROLE_SUSPENDED_ACTION = "m05.platform_role.suspended"
PLATFORM_ROLE_RESUMED_ACTION = "m05.platform_role.resumed"
PLATFORM_ROLE_REVOKED_ACTION = "m05.platform_role.revoked"
