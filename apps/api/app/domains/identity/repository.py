from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.domains.identity.enums import RoleAssignmentStatus
from app.domains.identity.models import Person, RoleAssignment
from app.domains.organization.models import Organization


def get_person(db: Session, person_id: str) -> Person | None:
    return db.get(Person, person_id)


def list_active_contexts(db: Session, person_id: str) -> list[tuple[RoleAssignment, Organization]]:
    """Active role assignments for a person, paired with their organization.

    This is the only source of a person's selectable contexts; a person is never
    granted access just because an organization exists.
    """
    stmt = (
        select(RoleAssignment, Organization)
        .join(Organization, Organization.id == RoleAssignment.organization_id)
        .where(
            RoleAssignment.person_id == person_id,
            RoleAssignment.status == RoleAssignmentStatus.ACTIVE,
            RoleAssignment.record_status == RecordStatus.ACTIVE,
            Organization.record_status == RecordStatus.ACTIVE,
        )
        .order_by(Organization.name, RoleAssignment.role_code)
    )
    return [tuple(row) for row in db.execute(stmt).all()]
