from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.common.pagination import PageParams
from app.domains.structure.models import Category, Location, Program, Room

# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------


def get_school_category(db: Session, school_id: str, category_id: str) -> Category | None:
    stmt = select(Category).where(
        Category.id == category_id,
        Category.school_id == school_id,
        Category.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_school_categories(
    db: Session, school_id: str, params: PageParams
) -> tuple[list[Category], int]:
    base = select(Category).where(
        Category.school_id == school_id,
        Category.record_status == RecordStatus.ACTIVE,
    )
    total = db.execute(
        select(func.count()).select_from(base.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(base.order_by(Category.name).limit(params.limit).offset(params.offset))
        .scalars()
        .all()
    )
    return list(rows), total


# ---------------------------------------------------------------------------
# Program
# ---------------------------------------------------------------------------


def get_school_program(db: Session, school_id: str, program_id: str) -> Program | None:
    stmt = select(Program).where(
        Program.id == program_id,
        Program.school_id == school_id,
        Program.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_school_programs(
    db: Session, school_id: str, params: PageParams
) -> tuple[list[Program], int]:
    base = select(Program).where(
        Program.school_id == school_id,
        Program.record_status == RecordStatus.ACTIVE,
    )
    total = db.execute(
        select(func.count()).select_from(base.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(base.order_by(Program.name).limit(params.limit).offset(params.offset))
        .scalars()
        .all()
    )
    return list(rows), total


def program_code_taken(
    db: Session, school_id: str, internal_code: str, *, exclude_id: str | None = None
) -> bool:
    stmt = select(Program.id).where(
        Program.school_id == school_id,
        Program.internal_code == internal_code,
        Program.record_status == RecordStatus.ACTIVE,
    )
    if exclude_id is not None:
        stmt = stmt.where(Program.id != exclude_id)
    return db.execute(stmt.limit(1)).first() is not None


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------


def get_school_location(db: Session, school_id: str, location_id: str) -> Location | None:
    stmt = select(Location).where(
        Location.id == location_id,
        Location.school_id == school_id,
        Location.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_school_locations(
    db: Session, school_id: str, params: PageParams
) -> tuple[list[Location], int]:
    base = select(Location).where(
        Location.school_id == school_id,
        Location.record_status == RecordStatus.ACTIVE,
    )
    total = db.execute(
        select(func.count()).select_from(base.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(base.order_by(Location.name).limit(params.limit).offset(params.offset))
        .scalars()
        .all()
    )
    return list(rows), total


def location_code_taken(
    db: Session, school_id: str, internal_code: str, *, exclude_id: str | None = None
) -> bool:
    stmt = select(Location.id).where(
        Location.school_id == school_id,
        Location.internal_code == internal_code,
        Location.record_status == RecordStatus.ACTIVE,
    )
    if exclude_id is not None:
        stmt = stmt.where(Location.id != exclude_id)
    return db.execute(stmt.limit(1)).first() is not None


# ---------------------------------------------------------------------------
# Room
# ---------------------------------------------------------------------------


def get_school_room(db: Session, school_id: str, room_id: str) -> Room | None:
    stmt = select(Room).where(
        Room.id == room_id,
        Room.school_id == school_id,
        Room.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def list_school_rooms(
    db: Session, school_id: str, params: PageParams, *, location_id: str | None = None
) -> tuple[list[Room], int]:
    base = select(Room).where(
        Room.school_id == school_id,
        Room.record_status == RecordStatus.ACTIVE,
    )
    if location_id is not None:
        base = base.where(Room.location_id == location_id)
    total = db.execute(
        select(func.count()).select_from(base.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(base.order_by(Room.name).limit(params.limit).offset(params.offset))
        .scalars()
        .all()
    )
    return list(rows), total


def room_code_taken(
    db: Session, school_id: str, internal_code: str, *, exclude_id: str | None = None
) -> bool:
    stmt = select(Room.id).where(
        Room.school_id == school_id,
        Room.internal_code == internal_code,
        Room.record_status == RecordStatus.ACTIVE,
    )
    if exclude_id is not None:
        stmt = stmt.where(Room.id != exclude_id)
    return db.execute(stmt.limit(1)).first() is not None
