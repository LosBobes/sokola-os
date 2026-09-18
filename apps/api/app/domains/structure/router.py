from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.common.pagination import Page, PageParams, page_params
from app.domains.identity.enums import RoleCode
from app.domains.structure import service
from app.domains.structure.schemas import (
    CategoryResponse,
    CreateCategoryRequest,
    CreateLocationRequest,
    CreateProgramRequest,
    CreateRoomRequest,
    LocationResponse,
    ProgramResponse,
    RoomResponse,
    UpdateCategoryRequest,
    UpdateLocationRequest,
    UpdateProgramRequest,
    UpdateRoomRequest,
)
from app.security.deps import ContextDep, DbDep, require_roles

router = APIRouter(tags=["structure"])

# Structural setup is school management: only owners/managers/admins write.
_staff = require_roles(RoleCode.OWNER, RoleCode.MANAGER, RoleCode.ADMIN)
StaffContext = Annotated[ContextDep, Depends(_staff)]
PageParamsDep = Annotated[PageParams, Depends(page_params)]


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------


@router.post(
    "/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createCategory",
)
def create_category(
    body: CreateCategoryRequest, db: DbDep, context: StaffContext
) -> CategoryResponse:
    return service.create_category(db, context, body)


@router.get(
    "/categories", response_model=Page[CategoryResponse], operation_id="listCategories"
)
def list_categories(
    db: DbDep, context: ContextDep, params: PageParamsDep
) -> Page[CategoryResponse]:
    return service.list_categories(db, context, params)


@router.get(
    "/categories/{category_id}",
    response_model=CategoryResponse,
    operation_id="getCategory",
)
def get_category(category_id: str, db: DbDep, context: ContextDep) -> CategoryResponse:
    return service.get_category(db, context, category_id)


@router.patch(
    "/categories/{category_id}",
    response_model=CategoryResponse,
    operation_id="updateCategory",
)
def update_category(
    category_id: str, body: UpdateCategoryRequest, db: DbDep, context: StaffContext
) -> CategoryResponse:
    return service.update_category(db, context, category_id, body)


@router.post(
    "/categories/{category_id}/deactivate",
    response_model=CategoryResponse,
    operation_id="deactivateCategory",
)
def deactivate_category(
    category_id: str, db: DbDep, context: StaffContext
) -> CategoryResponse:
    return service.deactivate_category(db, context, category_id)


# ---------------------------------------------------------------------------
# Program
# ---------------------------------------------------------------------------


@router.post(
    "/programs",
    response_model=ProgramResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createProgram",
)
def create_program(
    body: CreateProgramRequest, db: DbDep, context: StaffContext
) -> ProgramResponse:
    return service.create_program(db, context, body)


@router.get("/programs", response_model=Page[ProgramResponse], operation_id="listPrograms")
def list_programs(
    db: DbDep, context: ContextDep, params: PageParamsDep
) -> Page[ProgramResponse]:
    return service.list_programs(db, context, params)


@router.get(
    "/programs/{program_id}", response_model=ProgramResponse, operation_id="getProgram"
)
def get_program(program_id: str, db: DbDep, context: ContextDep) -> ProgramResponse:
    return service.get_program(db, context, program_id)


@router.patch(
    "/programs/{program_id}", response_model=ProgramResponse, operation_id="updateProgram"
)
def update_program(
    program_id: str, body: UpdateProgramRequest, db: DbDep, context: StaffContext
) -> ProgramResponse:
    return service.update_program(db, context, program_id, body)


@router.post(
    "/programs/{program_id}/deactivate",
    response_model=ProgramResponse,
    operation_id="deactivateProgram",
)
def deactivate_program(
    program_id: str, db: DbDep, context: StaffContext
) -> ProgramResponse:
    return service.deactivate_program(db, context, program_id)


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------


@router.post(
    "/locations",
    response_model=LocationResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createLocation",
)
def create_location(
    body: CreateLocationRequest, db: DbDep, context: StaffContext
) -> LocationResponse:
    return service.create_location(db, context, body)


@router.get(
    "/locations", response_model=Page[LocationResponse], operation_id="listLocations"
)
def list_locations(
    db: DbDep, context: ContextDep, params: PageParamsDep
) -> Page[LocationResponse]:
    return service.list_locations(db, context, params)


@router.get(
    "/locations/{location_id}",
    response_model=LocationResponse,
    operation_id="getLocation",
)
def get_location(location_id: str, db: DbDep, context: ContextDep) -> LocationResponse:
    return service.get_location(db, context, location_id)


@router.patch(
    "/locations/{location_id}",
    response_model=LocationResponse,
    operation_id="updateLocation",
)
def update_location(
    location_id: str, body: UpdateLocationRequest, db: DbDep, context: StaffContext
) -> LocationResponse:
    return service.update_location(db, context, location_id, body)


@router.post(
    "/locations/{location_id}/deactivate",
    response_model=LocationResponse,
    operation_id="deactivateLocation",
)
def deactivate_location(
    location_id: str, db: DbDep, context: StaffContext
) -> LocationResponse:
    return service.deactivate_location(db, context, location_id)


# ---------------------------------------------------------------------------
# Room
# ---------------------------------------------------------------------------


@router.post(
    "/rooms",
    response_model=RoomResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createRoom",
)
def create_room(body: CreateRoomRequest, db: DbDep, context: StaffContext) -> RoomResponse:
    return service.create_room(db, context, body)


@router.get("/rooms", response_model=Page[RoomResponse], operation_id="listRooms")
def list_rooms(
    db: DbDep,
    context: ContextDep,
    params: PageParamsDep,
    location_id: Annotated[str | None, Query()] = None,
) -> Page[RoomResponse]:
    return service.list_rooms(db, context, params, location_id=location_id)


@router.get("/rooms/{room_id}", response_model=RoomResponse, operation_id="getRoom")
def get_room(room_id: str, db: DbDep, context: ContextDep) -> RoomResponse:
    return service.get_room(db, context, room_id)


@router.patch("/rooms/{room_id}", response_model=RoomResponse, operation_id="updateRoom")
def update_room(
    room_id: str, body: UpdateRoomRequest, db: DbDep, context: StaffContext
) -> RoomResponse:
    return service.update_room(db, context, room_id, body)


@router.post(
    "/rooms/{room_id}/deactivate",
    response_model=RoomResponse,
    operation_id="deactivateRoom",
)
def deactivate_room(room_id: str, db: DbDep, context: StaffContext) -> RoomResponse:
    return service.deactivate_room(db, context, room_id)
