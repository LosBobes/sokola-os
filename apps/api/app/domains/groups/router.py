from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.common.pagination import Page, PageParams, page_params
from app.domains.groups import service
from app.domains.groups.schemas import (
    AddGroupMemberRequest,
    CreateGroupRequest,
    GroupMemberResponse,
    GroupResponse,
)
from app.domains.identity.enums import RoleCode
from app.security.deps import ContextDep, DbDep, require_roles

router = APIRouter(tags=["groups"])

_staff = require_roles(RoleCode.OWNER, RoleCode.MANAGER, RoleCode.ADMIN)
StaffContext = Annotated[ContextDep, Depends(_staff)]


@router.post(
    "/groups",
    response_model=GroupResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createGroup",
)
def create_group(body: CreateGroupRequest, db: DbDep, context: StaffContext) -> GroupResponse:
    return service.create_group(db, context, body)


@router.get("/groups", response_model=Page[GroupResponse], operation_id="listGroups")
def list_groups(
    db: DbDep, context: ContextDep, params: Annotated[PageParams, Depends(page_params)]
) -> Page[GroupResponse]:
    return service.list_groups(db, context, params)


@router.post(
    "/groups/{group_id}/members",
    response_model=GroupMemberResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="addGroupMember",
)
def add_group_member(
    group_id: str, body: AddGroupMemberRequest, db: DbDep, context: StaffContext
) -> GroupMemberResponse:
    return service.add_member(db, context, group_id, body.person_id)


@router.get(
    "/groups/{group_id}/members",
    response_model=list[GroupMemberResponse],
    operation_id="listGroupMembers",
)
def list_group_members(
    group_id: str, db: DbDep, context: ContextDep
) -> list[GroupMemberResponse]:
    return service.list_members(db, context, group_id)
