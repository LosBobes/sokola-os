from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domains.school.enums import SchoolKind, SchoolStatus, SchoolType


class CreateSchoolRequest(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    type: SchoolType = SchoolType.OTHER
    timezone: str = "Europe/Belgrade"


class SchoolResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str | None
    type: SchoolType
    timezone: str
    school_kind: SchoolKind
    status: SchoolStatus


class TenantPublic(BaseModel):
    """Public tenant discovery result, the minimum needed to route a login to
    the right school. Reveals no member data."""

    school_id: str
    name: str
    slug: str
