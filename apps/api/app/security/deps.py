"""FastAPI dependencies that turn a request into a verified context.

Flow (Part 6): authenticate -> resolve Person -> the client names a chosen
RoleAssignment -> the server re-derives school/role/scope from the DB and
confirms the assignment belongs to this person and is active. Downstream code
receives an immutable :class:`RequestContext` and re-checks every resource
against ``school_id``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.common.enums import RecordStatus
from app.common.errors import ForbiddenError, UnauthorizedError
from app.config import Settings, get_settings
from app.db import get_db
from app.domains.identity.auth_models import AuthSession, UserAccount
from app.domains.identity.enums import RoleAssignmentStatus, RoleCode
from app.domains.identity.models import RoleAssignment
from app.domains.school.enums import SchoolStatus
from app.domains.school.models import School
from app.domains.tenancy import context as tenant_context
from app.domains.tenancy.enums import (
    WORKSPACE_ADMIN,
    WORKSPACE_GUARDIAN,
    WORKSPACE_INSTRUCTOR,
)
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

    school = _resolve_tenant(db, principal, assignment.school_id)

    return RequestContext(
        person_id=principal.person_id,
        role_assignment_id=assignment.id,
        school_id=school.id,
        role_code=assignment.role_code,
        scope_type=assignment.scope_type,
        scope_ref_id=assignment.scope_ref_id,
        granted_areas=(
            tuple(assignment.granted_areas)
            if assignment.granted_areas is not None
            else None
        ),
    )


def _resolve_tenant(db: Session, principal: Principal, school_id: str) -> School:
    """M03 §8 steps 2–5 for this request.

    The *selection* still comes from the role-assignment header — changing that
    is F-24's job and waits for M05, since narrowing a person to one of their
    roles can only stop being an authorization decision once M05 can compute
    the union of all of them. What changes here is everything after the
    selection.

    Two things this adds that were missing:

    * a **server-side context row** with version snapshots, so §8 step 3 has
      something to compare. Without a stored moment of selection there is no
      such thing as a stale context — only a context, forever;
    * a **membership re-proof** (§6.1 point 4). An active role assignment was
      treated as sufficient, and §6.1 requires current M06 `ACTIVE` membership
      evidence *as well*: `DRAFT`, `SUSPENDED` and `TERMINATED` membership give
      no regular access however the role reads.

    A request with no server session — the local dev-header adapter — gets the
    school checks and the membership proof but no context row, because there is
    no session to hang one on. That is the honest shape: the dev adapter has
    never had a session, and inventing one for it would make the tests prove
    something production does not do.
    """
    school = db.get(School, school_id)
    if school is None or school.status is SchoolStatus.DEACTIVATED:
        raise ForbiddenError("Škola nije dostupna.")

    if not tenant_context.has_active_membership(
        db, school_id=school.id, person_id=principal.person_id
    ):
        # §13 keeps this generic: it does not say whether the membership never
        # existed, was suspended or was revoked.
        raise ForbiddenError("Nemate aktivan pristup ovoj školi.")

    if principal.session_id is None or principal.user_account_id is None:
        return school

    session = db.get(AuthSession, principal.session_id)
    account = db.get(UserAccount, principal.user_account_id)
    if session is None or account is None:
        raise ForbiddenError("Kontekst više nije aktivan.")

    existing = tenant_context.current(db, session.id)
    if (
        existing is None
        or not existing.is_active
        or existing.school_id != school.id
    ):
        # First selection, a revived context, or a switch. §9 treats all three
        # as one transition: the row is reused and its version moves, so a
        # response still in flight for the previous school cannot land here.
        tenant_context.select_context(
            db,
            session=session,
            account=account,
            school=school,
            workspace_key=_workspace_for(db, principal, school.id),
        )
        db.commit()
        return school

    resolved = tenant_context.resolve(
        db, context=existing, account=account, person_id=principal.person_id
    )
    db.commit()
    return resolved


def _workspace_for(db: Session, principal: Principal, school_id: str) -> str:
    """The display focus to record for a newly selected context.

    Derived from the person's roles in this school *for now*, and recorded
    rather than enforced — §3 is explicit that `workspace_key` "ne sužava i ne
    proširuje efektivna prava". Nothing reads it back to make a decision, which
    is what keeps this interim derivation from becoming the authorization path
    F-24 warns about. M05 replaces it with a real chooser over allowed options.
    """
    roles = set(
        db.execute(
            select(RoleAssignment.role_code).where(
                RoleAssignment.school_id == school_id,
                RoleAssignment.person_id == principal.person_id,
                RoleAssignment.status == RoleAssignmentStatus.ACTIVE,
                RoleAssignment.record_status != RecordStatus.ARCHIVED,
            )
        ).scalars().all()
    )
    if roles & {RoleCode.OWNER, RoleCode.MANAGER, RoleCode.ADMIN}:
        return WORKSPACE_ADMIN
    if RoleCode.TRAINER in roles:
        return WORKSPACE_INSTRUCTOR
    if RoleCode.PARENT in roles:
        return WORKSPACE_GUARDIAN
    return WORKSPACE_ADMIN


ContextDep = Annotated[RequestContext, Depends(get_context)]


def require_roles(*roles: RoleCode) -> Callable[[RequestContext], RequestContext]:
    """Dependency factory: the active context must hold one of ``roles``.

    Feature flags are checked separately, a user must pass *both* the flag and
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
