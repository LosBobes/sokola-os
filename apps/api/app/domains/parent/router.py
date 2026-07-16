"""Parent-facing read endpoints. Parent/child surfaces never reveal staff notes,
another child's data, or raw internal identifiers beyond what the parent needs."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.domains.identity.enums import RoleCode
from app.domains.identity.models import Person
from app.domains.people.enums import GuardianAccessStatus
from app.domains.people.models import GuardianOrganizationAccess
from app.security.context import RequestContext
from app.security.deps import ContextDep, DbDep, require_roles

router = APIRouter(tags=["parent"])

_parent = require_roles(RoleCode.PARENT)
ParentContext = Annotated[ContextDep, Depends(_parent)]


class ChildSummary(BaseModel):
    person_id: str
    display_name: str


def _children(db: Session, context: RequestContext) -> list[ChildSummary]:
    stmt = (
        select(Person)
        .join(
            GuardianOrganizationAccess,
            GuardianOrganizationAccess.child_person_id == Person.id,
        )
        .where(
            GuardianOrganizationAccess.organization_id == context.organization_id,
            GuardianOrganizationAccess.guardian_person_id == context.person_id,
            GuardianOrganizationAccess.status == GuardianAccessStatus.ACTIVE,
            Person.record_status == RecordStatus.ACTIVE,
        )
        .order_by(Person.display_name)
    )
    return [
        ChildSummary(person_id=p.id, display_name=p.display_name)
        for p in db.execute(stmt).scalars().all()
    ]


@router.get("/parent/children", response_model=list[ChildSummary], operation_id="listMyChildren")
def list_my_children(db: DbDep, context: ParentContext) -> list[ChildSummary]:
    return _children(db, context)
