from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.domains.school import service
from app.domains.school.schemas import (
    CreateSchoolRequest,
    SchoolResponse,
    TenantPublic,
)
from app.security.deps import ContextDep, DbDep, PrincipalDep
from app.security.permissions import PermissionArea, require_permission

router = APIRouter(tags=["schools"])

_roles_admin = require_permission(PermissionArea.ROLES)
RolesContext = Annotated[ContextDep, Depends(_roles_admin)]


@router.get("/tenants/{slug}", response_model=TenantPublic, operation_id="lookupTenant")
def lookup_tenant(slug: str, db: DbDep) -> TenantPublic:
    """Public tenant discovery: map a school code to the tenant to log in to."""
    return service.lookup_tenant(db, slug)


@router.post(
    "/schools",
    response_model=SchoolResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createSchool",
)
def create_school(
    body: CreateSchoolRequest, db: DbDep, principal: PrincipalDep
) -> SchoolResponse:
    """Create a new school. The caller becomes its owner. Requires
    authentication but no prior context (this is how a tenant is bootstrapped)."""
    return service.create_school(db, principal, body)


@router.get(
    "/schools/current",
    response_model=SchoolResponse,
    operation_id="getCurrentSchool",
)
def get_current_school(db: DbDep, context: ContextDep) -> SchoolResponse:
    return service.get_school(db, context.school_id)


@router.post(
    "/schools/current/deactivate",
    response_model=SchoolResponse,
    operation_id="deactivateSchool",
    responses={409: {"description": "Already deactivated."}},
)
def deactivate_school(db: DbDep, context: RolesContext) -> SchoolResponse:
    """§31, deactivate the caller's active school. Locks out every future
    context resolution against it; see ``reactivateSchool``."""
    return service.deactivate_school(db, context)


@router.post(
    "/schools/{school_id}/reactivate",
    response_model=SchoolResponse,
    operation_id="reactivateSchool",
    responses={
        403: {"description": "Caller is not an active owner of this school."},
        404: {"description": "School not found."},
        409: {"description": "Already active."},
    },
)
def reactivate_school(
    school_id: str, db: DbDep, principal: PrincipalDep
) -> SchoolResponse:
    """§31, a deactivated school cannot be reached through the normal
    context-selection path (a deactivated org is rejected at context
    resolution), so this authenticates on the principal alone and checks
    ownership of the named school directly."""
    return service.reactivate_school(db, principal, school_id)
