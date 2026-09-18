"""The server-derived request context.

The client may *request* a context (which role/school it is acting in) but
never *grants* one. The security layer resolves this object from the database on
every request; domains receive it and re-check every resource against
``school_id``. There is no global ``isAdmin`` flag and no client-supplied
role or tenant id anywhere in the system.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domains.identity.enums import RoleCode, RoleScopeType


@dataclass(frozen=True, slots=True)
class RequestContext:
    person_id: str
    role_assignment_id: str
    school_id: str
    role_code: RoleCode
    scope_type: RoleScopeType
    # Branch/group scoping, when the role is narrower than the whole org.
    scope_ref_id: str | None = None
    # Per-assignment area restriction. ``None`` means the role's full default
    # areas; a tuple restricts this assignment to those area codes (a narrowing,
    # never an escalation). Interpreted by ``app.security.permissions``.
    granted_areas: tuple[str, ...] | None = None
