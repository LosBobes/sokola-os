from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.domains.organization import service
from app.domains.organization.schemas import (
    CreateOrganizationRequest,
    OrganizationResponse,
    TenantPublic,
)
from app.security.deps import ContextDep, DbDep, PrincipalDep
from app.security.permissions import PermissionArea, require_permission

router = APIRouter(tags=["organizations"])

_roles_admin = require_permission(PermissionArea.ROLES)
RolesContext = Annotated[ContextDep, Depends(_roles_admin)]


@router.get("/tenants/{slug}", response_model=TenantPublic, operation_id="lookupTenant")
def lookup_tenant(slug: str, db: DbDep) -> TenantPublic:
    """Public tenant discovery: map a school code to the tenant to log in to."""
    return service.lookup_tenant(db, slug)


@router.post(
    "/organizations",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createOrganization",
)
def create_organization(
    body: CreateOrganizationRequest, db: DbDep, principal: PrincipalDep
) -> OrganizationResponse:
    """Create a new organization. The caller becomes its owner. Requires
    authentication but no prior context (this is how a tenant is bootstrapped)."""
    return service.create_organization(db, principal, body)


@router.get(
    "/organizations/current",
    response_model=OrganizationResponse,
    operation_id="getCurrentOrganization",
)
def get_current_organization(db: DbDep, context: ContextDep) -> OrganizationResponse:
    return service.get_organization(db, context.organization_id)


@router.post(
    "/organizations/current/deactivate",
    response_model=OrganizationResponse,
    operation_id="deactivateOrganization",
    responses={409: {"description": "Already deactivated."}},
)
def deactivate_organization(db: DbDep, context: RolesContext) -> OrganizationResponse:
    """§31, deactivate the caller's active school. Locks out every future
    context resolution against it; see ``reactivateOrganization``."""
    return service.deactivate_organization(db, context)


@router.post(
    "/organizations/{organization_id}/reactivate",
    response_model=OrganizationResponse,
    operation_id="reactivateOrganization",
    responses={
        403: {"description": "Caller is not an active owner of this school."},
        404: {"description": "School not found."},
        409: {"description": "Already active."},
    },
)
def reactivate_organization(
    organization_id: str, db: DbDep, principal: PrincipalDep
) -> OrganizationResponse:
    """§31, a deactivated school cannot be reached through the normal
    context-selection path (a deactivated org is rejected at context
    resolution), so this authenticates on the principal alone and checks
    ownership of the named school directly."""
    return service.reactivate_organization(db, principal, organization_id)
