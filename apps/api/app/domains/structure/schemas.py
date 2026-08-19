from __future__ import annotations

from pydantic import BaseModel, Field

from app.common.enums import RecordStatus
from app.domains.structure.enums import LocationKind

# ---------------------------------------------------------------------------
# Category (kategorija programa)
# ---------------------------------------------------------------------------


class CreateCategoryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class UpdateCategoryRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)


class CategoryResponse(BaseModel):
    id: str
    name: str
    status: RecordStatus


# ---------------------------------------------------------------------------
# Program
# ---------------------------------------------------------------------------


class CreateProgramRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    category_id: str | None = None
    internal_code: str | None = Field(default=None, min_length=1, max_length=60)


class UpdateProgramRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category_id: str | None = None
    internal_code: str | None = Field(default=None, min_length=1, max_length=60)


class ProgramResponse(BaseModel):
    id: str
    name: str
    category_id: str | None
    internal_code: str | None
    status: RecordStatus


# ---------------------------------------------------------------------------
# Location (ogranak / branch)
# ---------------------------------------------------------------------------


class CreateLocationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    kind: LocationKind = LocationKind.OTHER
    address: str | None = Field(default=None, min_length=1, max_length=400)
    internal_code: str | None = Field(default=None, min_length=1, max_length=60)


class UpdateLocationRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    kind: LocationKind | None = None
    address: str | None = Field(default=None, min_length=1, max_length=400)
    internal_code: str | None = Field(default=None, min_length=1, max_length=60)


class LocationResponse(BaseModel):
    id: str
    name: str
    kind: LocationKind
    address: str | None
    internal_code: str | None
    status: RecordStatus


# ---------------------------------------------------------------------------
# Room (prostor / space)
# ---------------------------------------------------------------------------


class CreateRoomRequest(BaseModel):
    location_id: str
    name: str = Field(min_length=1, max_length=160)
    capacity: int | None = Field(default=None, ge=0)
    internal_code: str | None = Field(default=None, min_length=1, max_length=60)


class UpdateRoomRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    capacity: int | None = Field(default=None, ge=0)
    internal_code: str | None = Field(default=None, min_length=1, max_length=60)


class RoomResponse(BaseModel):
    id: str
    location_id: str
    name: str
    capacity: int | None
    internal_code: str | None
    status: RecordStatus
