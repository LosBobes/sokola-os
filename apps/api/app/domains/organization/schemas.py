from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domains.organization.enums import OrganizationType


class CreateOrganizationRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    type: OrganizationType = OrganizationType.OTHER
    timezone: str = "Europe/Belgrade"


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    type: OrganizationType
    timezone: str
