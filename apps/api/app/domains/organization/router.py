from __future__ import annotations

from fastapi import APIRouter, status

from app.domains.organization import service
from app.domains.organization.schemas import (
    CreateOrganizationRequest,
    OrganizationResponse,
    TenantPublic,
)
from app.security.deps import ContextDep, DbDep, PrincipalDep

router = APIRouter(tags=["organizations"])


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
