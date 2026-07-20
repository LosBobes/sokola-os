"""Per-area permission layer.

Authorization follows GRANTED AREAS, not the role *name* (PRD 01 §19.2/§25.5).
A role has a default set of areas it may touch; an individual ``RoleAssignment``
may be *restricted* to a subset of those (``granted_areas``) — for example an
ADMIN invited "for finances only". A restriction can only ever *narrow* a role's
defaults, never escalate them.

``ROLE_DEFAULT_AREAS`` is derived by auditing every ``require_roles(...)`` guard
that existed on the product routers, so the default (unrestricted) behaviour is
preserved exactly:

    Area            | roles that could reach it (require_roles audit)
    ----------------|------------------------------------------------
    PEOPLE          | OWNER, MANAGER, ADMIN            (people router _staff)
    GROUPS          | OWNER, MANAGER, ADMIN            (groups router _staff)
    SCHEDULING      | OWNER, MANAGER, ADMIN            (scheduling router _staff)
    ATTENDANCE      | OWNER, MANAGER, ADMIN, TRAINER   (attendance _recorders)
    BILLING         | OWNER, MANAGER, ADMIN            (billing router _finance)
    PAYMENTS        | OWNER, MANAGER, ADMIN            (payments router _finance)
    EVENTS          | OWNER, MANAGER, ADMIN            (events _staff)
    COMMUNICATIONS  | OWNER, MANAGER, ADMIN            (communications _staff)
    PARENTS         | PARENT                           (parent router + events _parent)
    DOCUMENTS       | OWNER, MANAGER, ADMIN            (documents _staff — new area, no
                    |                                    require_roles precedent to audit)

ORGANIZATION and ROLES have no ``require_roles`` guard today (the organization
and identity routers gate on context alone), so including them in the
administrative roles' defaults is behaviour-neutral: no route consults them yet.
They are granted to OWNER/MANAGER/ADMIN so that a future area guard and the
"restrict this assignment" UI have a coherent, non-empty administrative set.

IMPORT (PRD 11, added with the CSV bulk-import feature) has no legacy
``require_roles`` guard to audit — it is granted to OWNER/MANAGER/ADMIN
directly, matching PEOPLE/GROUPS since importing people/groups is exactly the
same administrative surface those areas already gate.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Iterable

from app.common.errors import ForbiddenError
from app.domains.identity.enums import RoleCode
from app.security.context import RequestContext
from app.security.deps import ContextDep


class PermissionArea(enum.StrEnum):
    """A cohesive product surface that access is granted over, one per product
    domain (plus ROLES for role/invite administration)."""

    PEOPLE = "PEOPLE"
    PARENTS = "PARENTS"
    GROUPS = "GROUPS"
    SCHEDULING = "SCHEDULING"
    ATTENDANCE = "ATTENDANCE"
    BILLING = "BILLING"
    PAYMENTS = "PAYMENTS"
    EVENTS = "EVENTS"
    COMMUNICATIONS = "COMMUNICATIONS"
    ORGANIZATION = "ORGANIZATION"
    ROLES = "ROLES"  # role / invitation administration
    PRIVACY = "PRIVACY"  # consent, DSAR, and retention-period administration
    DOCUMENTS = "DOCUMENTS"
    IMPORT = "IMPORT"  # bulk CSV import of people/groups (PRD 11)


# Everything a staff role administers by default. ORGANIZATION/ROLES/PRIVACY are
# behaviour-neutral today except where their own domain's routes now guard on
# them (PRIVACY does) — see module docstring.
_STAFF_AREAS: frozenset[PermissionArea] = frozenset(
    {
        PermissionArea.PEOPLE,
        PermissionArea.GROUPS,
        PermissionArea.SCHEDULING,
        PermissionArea.ATTENDANCE,
        PermissionArea.BILLING,
        PermissionArea.PAYMENTS,
        PermissionArea.EVENTS,
        PermissionArea.COMMUNICATIONS,
        PermissionArea.ORGANIZATION,
        PermissionArea.ROLES,
        PermissionArea.PRIVACY,
        PermissionArea.DOCUMENTS,
        PermissionArea.IMPORT,
    }
)

ROLE_DEFAULT_AREAS: dict[RoleCode, frozenset[PermissionArea]] = {
    RoleCode.OWNER: _STAFF_AREAS,
    RoleCode.MANAGER: _STAFF_AREAS,
    RoleCode.ADMIN: _STAFF_AREAS,
    # TRAINER only ever passed the attendance recorder guard.
    RoleCode.TRAINER: frozenset({PermissionArea.ATTENDANCE}),
    # PARENT reaches only the parent surface — including the parent-facing event
    # routes, which are guarded on PARENTS (not EVENTS, which is staff-only).
    RoleCode.PARENT: frozenset({PermissionArea.PARENTS}),
    # STUDENT held no require_roles guard on any product route.
    RoleCode.STUDENT: frozenset(),
}


def effective_areas(
    role_code: RoleCode, granted_areas: frozenset[PermissionArea] | None
) -> frozenset[PermissionArea]:
    """The areas an assignment may actually touch.

    ``granted_areas is None`` -> the role's full default. Otherwise the
    intersection of the default with the granted set: a restriction, never an
    escalation (a granted area outside the role's default confers nothing).
    """
    default = ROLE_DEFAULT_AREAS.get(role_code, frozenset())
    if granted_areas is None:
        return default
    return default & granted_areas


def parse_granted_areas(raw: Iterable[str] | None) -> frozenset[PermissionArea] | None:
    """Turn the assignment's stored area strings into a validated area set.

    ``None`` (unrestricted) is preserved as ``None``. Unknown/stale strings are
    dropped rather than raising, so a bad row degrades to a tighter grant, never
    a 500 and never an escalation.
    """
    if raw is None:
        return None
    areas: set[PermissionArea] = set()
    for value in raw:
        try:
            areas.add(PermissionArea(value))
        except ValueError:
            continue
    return frozenset(areas)


def require_permission(
    *areas: PermissionArea,
) -> Callable[[RequestContext], RequestContext]:
    """Dependency factory: the active context's effective areas must intersect
    ``areas`` (OR semantics, mirroring :func:`require_roles`).

    Feature flags remain separate — this is only the permission half.
    """
    required = frozenset(areas)

    def _guard(context: ContextDep) -> RequestContext:
        granted = parse_granted_areas(context.granted_areas)
        if effective_areas(context.role_code, granted).isdisjoint(required):
            raise ForbiddenError("Nemate ovlašćenje za ovu radnju.")
        return context

    return _guard


__all__ = [
    "ROLE_DEFAULT_AREAS",
    "PermissionArea",
    "effective_areas",
    "parse_granted_areas",
    "require_permission",
]
