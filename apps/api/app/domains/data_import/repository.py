from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.common.pagination import PageParams
from app.domains.data_import.models import ImportBatch, ImportRow
from app.domains.groups.models import Group
from app.domains.identity.models import Person
from app.domains.school.models import SchoolMembership


def get_school_batch(db: Session, school_id: str, batch_id: str) -> ImportBatch | None:
    stmt = select(ImportBatch).where(
        ImportBatch.id == batch_id, ImportBatch.school_id == school_id
    )
    return db.execute(stmt).scalar_one_or_none()


def list_school_batches(
    db: Session, school_id: str, params: PageParams
) -> tuple[list[ImportBatch], int]:
    base = select(ImportBatch).where(ImportBatch.school_id == school_id)
    total = db.execute(
        select(func.count()).select_from(base.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(
            base.order_by(ImportBatch.created_at.desc())
            .limit(params.limit)
            .offset(params.offset)
        )
        .scalars()
        .all()
    )
    return list(rows), total


def list_rows(db: Session, batch_id: str) -> list[ImportRow]:
    stmt = (
        select(ImportRow)
        .where(ImportRow.batch_id == batch_id)
        .order_by(ImportRow.row_number)
    )
    return list(db.execute(stmt).scalars().all())


def find_group_by_name(db: Session, school_id: str, name: str) -> Group | None:
    """Case/whitespace-insensitive lookup, import never creates groups, only
    links rows to ones that already exist in this org (§ import v1 scope)."""
    stmt = select(Group).where(
        Group.school_id == school_id,
        Group.record_status == RecordStatus.ACTIVE,
        func.lower(func.trim(Group.name)) == name.strip().lower(),
    )
    return db.execute(stmt).scalar_one_or_none()


def find_local_code_owner(
    db: Session, school_id: str, local_member_code: str
) -> SchoolMembership | None:
    """An existing member in this org already holding ``local_member_code``
    (§9), mirrors ``app.domains.people.repository.find_local_code_owner``,
    minus the ``exclude_person_id`` (import rows describe brand-new people, so
    there is no existing membership row of their own to exclude)."""
    stmt = select(SchoolMembership).where(
        SchoolMembership.school_id == school_id,
        SchoolMembership.local_member_code == local_member_code,
        SchoolMembership.record_status == RecordStatus.ACTIVE,
    )
    return db.execute(stmt).scalar_one_or_none()


def find_duplicate_people(
    db: Session, school_id: str, given_name: str, family_name: str
) -> list[Person]:
    """People already in THIS school whose name matches (case-insensitive).

    Mirrors the shape of ``app.domains.people.repository.find_duplicate_
    candidates`` (added in #6 / ``GET /people/duplicates``), reimplemented
    here directly against the shared Person/SchoolMembership models
    rather than importing the people domain's repository, which the
    architecture gate forbids across domains.
    """
    stmt = (
        select(Person)
        .join(SchoolMembership, SchoolMembership.person_id == Person.id)
        .where(
            SchoolMembership.school_id == school_id,
            SchoolMembership.record_status == RecordStatus.ACTIVE,
            func.lower(Person.given_name) == given_name.strip().lower(),
            func.lower(Person.family_name) == family_name.strip().lower(),
            Person.record_status == RecordStatus.ACTIVE,
        )
        .order_by(Person.display_name)
    )
    return list(db.execute(stmt).scalars().all())
