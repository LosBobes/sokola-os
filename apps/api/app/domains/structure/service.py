from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass, RecordStatus
from app.common.errors import ConflictError, NotFoundError
from app.common.pagination import Page, PageParams
from app.domains.structure import repository
from app.domains.structure.models import Category, Location, Program, Room
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
from app.platform.audit.service import record_audit
from app.security.context import RequestContext

_CODE_CONFLICT = "Interna šifra se već koristi u ovoj školi."


def _clean_code(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


# ---------------------------------------------------------------------------
# Response mappers
# ---------------------------------------------------------------------------


def _category_response(row: Category) -> CategoryResponse:
    return CategoryResponse(id=row.id, name=row.name, status=row.record_status)


def _program_response(row: Program) -> ProgramResponse:
    return ProgramResponse(
        id=row.id,
        name=row.name,
        category_id=row.category_id,
        internal_code=row.internal_code,
        status=row.record_status,
    )


def _location_response(row: Location) -> LocationResponse:
    return LocationResponse(
        id=row.id,
        name=row.name,
        kind=row.kind,
        address=row.address,
        internal_code=row.internal_code,
        status=row.record_status,
    )


def _room_response(row: Room) -> RoomResponse:
    return RoomResponse(
        id=row.id,
        location_id=row.location_id,
        name=row.name,
        capacity=row.capacity,
        internal_code=row.internal_code,
        status=row.record_status,
    )


def _audit_deactivation(
    db: Session, context: RequestContext, *, entity_type: str, entity_id: str, name: str
) -> None:
    record_audit(
        db,
        data_class=AuditDataClass.OPERATIONAL,
        action=f"structure.{entity_type}.deactivated",
        entity_type=f"structure_{entity_type}",
        entity_id=entity_id,
        summary=f"Deaktivirano: „{name}“.",
        organization_id=context.organization_id,
        actor_person_id=context.person_id,
    )


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------


def create_category(
    db: Session, context: RequestContext, req: CreateCategoryRequest
) -> CategoryResponse:
    category = Category(organization_id=context.organization_id, name=req.name.strip())
    db.add(category)
    db.commit()
    return _category_response(category)


def list_categories(
    db: Session, context: RequestContext, params: PageParams
) -> Page[CategoryResponse]:
    rows, total = repository.list_org_categories(db, context.organization_id, params)
    return Page.build([_category_response(r) for r in rows], total, params)


def get_category(db: Session, context: RequestContext, category_id: str) -> CategoryResponse:
    row = repository.get_org_category(db, context.organization_id, category_id)
    if row is None:
        raise NotFoundError("Kategorija nije pronađena.")
    return _category_response(row)


def update_category(
    db: Session, context: RequestContext, category_id: str, req: UpdateCategoryRequest
) -> CategoryResponse:
    row = repository.get_org_category(db, context.organization_id, category_id)
    if row is None:
        raise NotFoundError("Kategorija nije pronađena.")
    if "name" in req.model_fields_set and req.name is not None:
        row.name = req.name.strip()
    db.commit()
    return _category_response(row)


def deactivate_category(
    db: Session, context: RequestContext, category_id: str
) -> CategoryResponse:
    row = repository.get_org_category(db, context.organization_id, category_id)
    if row is None:
        raise NotFoundError("Kategorija nije pronađena.")
    row.record_status = RecordStatus.ARCHIVED
    _audit_deactivation(
        db, context, entity_type="category", entity_id=row.id, name=row.name
    )
    db.commit()
    return _category_response(row)


# ---------------------------------------------------------------------------
# Program
# ---------------------------------------------------------------------------


def _resolve_category(db: Session, context: RequestContext, category_id: str | None) -> str | None:
    if category_id is None:
        return None
    category = repository.get_org_category(db, context.organization_id, category_id)
    if category is None:
        raise NotFoundError("Kategorija nije pronađena.")
    return category.id


def create_program(
    db: Session, context: RequestContext, req: CreateProgramRequest
) -> ProgramResponse:
    code = _clean_code(req.internal_code)
    category_id = _resolve_category(db, context, req.category_id)
    if code is not None and repository.program_code_taken(db, context.organization_id, code):
        raise ConflictError(_CODE_CONFLICT)
    program = Program(
        organization_id=context.organization_id,
        category_id=category_id,
        name=req.name.strip(),
        internal_code=code,
    )
    db.add(program)
    db.commit()
    return _program_response(program)


def list_programs(
    db: Session, context: RequestContext, params: PageParams
) -> Page[ProgramResponse]:
    rows, total = repository.list_org_programs(db, context.organization_id, params)
    return Page.build([_program_response(r) for r in rows], total, params)


def get_program(db: Session, context: RequestContext, program_id: str) -> ProgramResponse:
    row = repository.get_org_program(db, context.organization_id, program_id)
    if row is None:
        raise NotFoundError("Program nije pronađen.")
    return _program_response(row)


def update_program(
    db: Session, context: RequestContext, program_id: str, req: UpdateProgramRequest
) -> ProgramResponse:
    row = repository.get_org_program(db, context.organization_id, program_id)
    if row is None:
        raise NotFoundError("Program nije pronađen.")
    if "name" in req.model_fields_set and req.name is not None:
        row.name = req.name.strip()
    if "category_id" in req.model_fields_set:
        row.category_id = _resolve_category(db, context, req.category_id)
    if "internal_code" in req.model_fields_set:
        code = _clean_code(req.internal_code)
        if code is not None and repository.program_code_taken(
            db, context.organization_id, code, exclude_id=row.id
        ):
            raise ConflictError(_CODE_CONFLICT)
        row.internal_code = code
    db.commit()
    return _program_response(row)


def deactivate_program(
    db: Session, context: RequestContext, program_id: str
) -> ProgramResponse:
    row = repository.get_org_program(db, context.organization_id, program_id)
    if row is None:
        raise NotFoundError("Program nije pronađen.")
    row.record_status = RecordStatus.ARCHIVED
    _audit_deactivation(db, context, entity_type="program", entity_id=row.id, name=row.name)
    db.commit()
    return _program_response(row)


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------


def create_location(
    db: Session, context: RequestContext, req: CreateLocationRequest
) -> LocationResponse:
    code = _clean_code(req.internal_code)
    if code is not None and repository.location_code_taken(db, context.organization_id, code):
        raise ConflictError(_CODE_CONFLICT)
    location = Location(
        organization_id=context.organization_id,
        name=req.name.strip(),
        kind=req.kind,
        address=req.address.strip() if req.address is not None else None,
        internal_code=code,
    )
    db.add(location)
    db.commit()
    return _location_response(location)


def list_locations(
    db: Session, context: RequestContext, params: PageParams
) -> Page[LocationResponse]:
    rows, total = repository.list_org_locations(db, context.organization_id, params)
    return Page.build([_location_response(r) for r in rows], total, params)


def get_location(db: Session, context: RequestContext, location_id: str) -> LocationResponse:
    row = repository.get_org_location(db, context.organization_id, location_id)
    if row is None:
        raise NotFoundError("Ogranak nije pronađen.")
    return _location_response(row)


def update_location(
    db: Session, context: RequestContext, location_id: str, req: UpdateLocationRequest
) -> LocationResponse:
    row = repository.get_org_location(db, context.organization_id, location_id)
    if row is None:
        raise NotFoundError("Ogranak nije pronađen.")
    if "name" in req.model_fields_set and req.name is not None:
        row.name = req.name.strip()
    if "kind" in req.model_fields_set and req.kind is not None:
        row.kind = req.kind
    if "address" in req.model_fields_set:
        row.address = req.address.strip() if req.address is not None else None
    if "internal_code" in req.model_fields_set:
        code = _clean_code(req.internal_code)
        if code is not None and repository.location_code_taken(
            db, context.organization_id, code, exclude_id=row.id
        ):
            raise ConflictError(_CODE_CONFLICT)
        row.internal_code = code
    db.commit()
    return _location_response(row)


def deactivate_location(
    db: Session, context: RequestContext, location_id: str
) -> LocationResponse:
    row = repository.get_org_location(db, context.organization_id, location_id)
    if row is None:
        raise NotFoundError("Ogranak nije pronađen.")
    row.record_status = RecordStatus.ARCHIVED
    _audit_deactivation(db, context, entity_type="location", entity_id=row.id, name=row.name)
    db.commit()
    return _location_response(row)


# ---------------------------------------------------------------------------
# Room
# ---------------------------------------------------------------------------


def create_room(db: Session, context: RequestContext, req: CreateRoomRequest) -> RoomResponse:
    location = repository.get_org_location(db, context.organization_id, req.location_id)
    if location is None:
        raise NotFoundError("Ogranak nije pronađen.")
    code = _clean_code(req.internal_code)
    if code is not None and repository.room_code_taken(db, context.organization_id, code):
        raise ConflictError(_CODE_CONFLICT)
    room = Room(
        organization_id=context.organization_id,
        location_id=location.id,
        name=req.name.strip(),
        capacity=req.capacity,
        internal_code=code,
    )
    db.add(room)
    db.commit()
    return _room_response(room)


def list_rooms(
    db: Session,
    context: RequestContext,
    params: PageParams,
    *,
    location_id: str | None = None,
) -> Page[RoomResponse]:
    rows, total = repository.list_org_rooms(
        db, context.organization_id, params, location_id=location_id
    )
    return Page.build([_room_response(r) for r in rows], total, params)


def get_room(db: Session, context: RequestContext, room_id: str) -> RoomResponse:
    row = repository.get_org_room(db, context.organization_id, room_id)
    if row is None:
        raise NotFoundError("Prostor nije pronađen.")
    return _room_response(row)


def update_room(
    db: Session, context: RequestContext, room_id: str, req: UpdateRoomRequest
) -> RoomResponse:
    row = repository.get_org_room(db, context.organization_id, room_id)
    if row is None:
        raise NotFoundError("Prostor nije pronađen.")
    if "name" in req.model_fields_set and req.name is not None:
        row.name = req.name.strip()
    if "capacity" in req.model_fields_set:
        row.capacity = req.capacity
    if "internal_code" in req.model_fields_set:
        code = _clean_code(req.internal_code)
        if code is not None and repository.room_code_taken(
            db, context.organization_id, code, exclude_id=row.id
        ):
            raise ConflictError(_CODE_CONFLICT)
        row.internal_code = code
    db.commit()
    return _room_response(row)


def deactivate_room(db: Session, context: RequestContext, room_id: str) -> RoomResponse:
    row = repository.get_org_room(db, context.organization_id, room_id)
    if row is None:
        raise NotFoundError("Prostor nije pronađen.")
    row.record_status = RecordStatus.ARCHIVED
    _audit_deactivation(db, context, entity_type="room", entity_id=row.id, name=row.name)
    db.commit()
    return _room_response(row)
