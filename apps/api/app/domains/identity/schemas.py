from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from app.domains.identity.enums import PersonIdentityStatus, RoleCode, RoleScopeType


class ContextSummary(BaseModel):
    """One selectable acting context = an active role in one organization."""

    model_config = ConfigDict(from_attributes=True)

    role_assignment_id: str
    organization_id: str
    organization_name: str
    role_code: RoleCode
    scope_type: RoleScopeType
    scope_ref_id: str | None


class MeResponse(BaseModel):
    person_id: str
    display_name: str
    identity_status: PersonIdentityStatus
    contexts: list[ContextSummary]
