from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.common.pagination import Page, PageParams, page_params
from app.domains.people import service
from app.domains.people.schemas import CreatePersonRequest, PersonResponse, PersonSummary
from app.security.deps import ContextDep, DbDep
from app.security.permissions import PermissionArea, require_permission

router = APIRouter(tags=["people"])

# Staff who may manage the roster.
_staff = require_permission(PermissionArea.PEOPLE)
StaffContext = Annotated[ContextDep, Depends(_staff)]


@router.post(
    "/people",
    response_model=PersonResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createPerson",
    responses={409: {"description": "Possible duplicate; confirm to override."}},
)
def create_person(
    body: CreatePersonRequest, db: DbDep, context: StaffContext
) -> PersonResponse:
    return service.create_provisional_person(db, context, body)


@router.get("/people", response_model=Page[PersonSummary], operation_id="listPeople")
def list_people(
    db: DbDep,
    context: ContextDep,
    params: Annotated[PageParams, Depends(page_params)],
) -> Page[PersonSummary]:
    return service.list_people(db, context, params)


@router.get("/people/{person_id}", response_model=PersonResponse, operation_id="getPerson")
def get_person(person_id: str, db: DbDep, context: ContextDep) -> PersonResponse:
    return service.get_person(db, context, person_id)
