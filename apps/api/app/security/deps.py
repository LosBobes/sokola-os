"""FastAPI dependencies that turn a request into a verified context.

Flow (Part 6): authenticate -> resolve Person -> the client names a chosen
RoleAssignment -> the server re-derives organization/role/scope from the DB and
confirms the assignment belongs to this person and is active. Downstream code
receives an immutable :class:`RequestContext` and re-checks every resource
against ``organization_id``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.common.enums import RecordStatus
from app.common.errors import ForbiddenError, UnauthorizedError
from app.config import Settings, get_settings
from app.db import get_db
from app.domains.identity.enums import RoleAssignmentStatus, RoleCode
from app.domains.identity.models import RoleAssignment
from app.domains.organization.models import Organization
from app.security.auth import Principal, resolve_principal
from app.security.context import RequestContext

CONTEXT_HEADER = "x-sokola-role-assignment-id"

SettingsDep = Annotated[Settings, Depends(get_settings)]
DbDep = Annotated[Session, Depends(get_db)]


def get_principal(request: Request, db: DbDep, settings: SettingsDep) -> Principal:
    return resolve_principal(request, db, settings)


PrincipalDep = Annotated[Principal, Depends(get_principal)]


def get_context(request: Request, db: DbDep, principal: PrincipalDep) -> RequestContext:
    assignment_id = request.headers.get(CONTEXT_HEADER)
    if not assignment_id:
        raise ForbiddenError("Nije izabran kontekst (škola/uloga).")

    assignment = db.get(RoleAssignment, assignment_id)
    if assignment is None or assignment.person_id != principal.person_id:
        # Never confirm existence of a context the caller doesn't own.
        raise ForbiddenError("Nedostupan kontekst.")
    if (
        assignment.status is not RoleAssignmentStatus.ACTIVE
        or assignment.record_status is RecordStatus.ARCHIVED
    ):
        raise ForbiddenError("Kontekst više nije aktivan.")

    organization = db.get(Organization, assignment.organization_id)
    if organization is None or organization.record_status is RecordStatus.ARCHIVED:
        raise ForbiddenError("Škola nije dostupna.")

    return RequestContext(
        person_id=principal.person_id,
        role_assignment_id=assignment.id,
        organization_id=organization.id,
        role_code=assignment.role_code,
        scope_type=assignment.scope_type,
        scope_ref_id=assignment.scope_ref_id,
        granted_areas=(
            tuple(assignment.granted_areas)
            if assignment.granted_areas is not None
            else None
        ),
    )


ContextDep = Annotated[RequestContext, Depends(get_context)]


def require_roles(*roles: RoleCode) -> Callable[[RequestContext], RequestContext]:
    """Dependency factory: the active context must hold one of ``roles``.

    Feature flags are checked separately — a user must pass *both* the flag and
    the permission. This guard is only the permission half.
    """
    allowed = set(roles)

    def _guard(context: ContextDep) -> RequestContext:
        if context.role_code not in allowed:
            raise ForbiddenError("Nemate ovlašćenje za ovu radnju.")
        return context

    return _guard


__all__ = [
    "ContextDep",
    "DbDep",
    "PrincipalDep",
    "SettingsDep",
    "UnauthorizedError",
    "get_context",
    "get_principal",
    "require_roles",
]
