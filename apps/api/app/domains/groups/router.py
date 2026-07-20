from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.common.pagination import Page, PageParams, page_params
from app.domains.groups import service
from app.domains.groups.schemas import (
    AddGroupMemberRequest,
    CreateGroupRequest,
    EndGroupMembershipRequest,
    GroupMemberResponse,
    GroupMembershipTransitionRequest,
    GroupResponse,
    SetMembershipDiscountRequest,
    UpdateGroupRequest,
)
from app.security.deps import ContextDep, DbDep
from app.security.permissions import PermissionArea, require_permission

router = APIRouter(tags=["groups"])

_staff = require_permission(PermissionArea.GROUPS)
StaffContext = Annotated[ContextDep, Depends(_staff)]


@router.post(
    "/groups",
    response_model=GroupResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createGroup",
    responses={404: {"description": "Program or location not found in this school."}},
)
def create_group(body: CreateGroupRequest, db: DbDep, context: StaffContext) -> GroupResponse:
    return service.create_group(db, context, body)


@router.get("/groups", response_model=Page[GroupResponse], operation_id="listGroups")
def list_groups(
    db: DbDep, context: ContextDep, params: Annotated[PageParams, Depends(page_params)]
) -> Page[GroupResponse]:
    return service.list_groups(db, context, params)


@router.patch(
    "/groups/{group_id}",
    response_model=GroupResponse,
    operation_id="updateGroup",
    responses={404: {"description": "Group, program, or location not found in this school."}},
)
def update_group(
    group_id: str, body: UpdateGroupRequest, db: DbDep, context: StaffContext
) -> GroupResponse:
    return service.update_group(db, context, group_id, body)


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


@router.post(
    "/groups/{group_id}/members/{membership_id}/suspend",
    response_model=GroupMemberResponse,
    operation_id="suspendGroupMembership",
    responses={409: {"description": "Invalid transition for the current state."}},
)
def suspend_group_membership(
    group_id: str,
    membership_id: str,
    body: GroupMembershipTransitionRequest,
    db: DbDep,
    context: StaffContext,
) -> GroupMemberResponse:
    return service.suspend_membership(db, context, group_id, membership_id, body)


@router.post(
    "/groups/{group_id}/members/{membership_id}/resume",
    response_model=GroupMemberResponse,
    operation_id="resumeGroupMembership",
    responses={409: {"description": "Invalid transition for the current state."}},
)
def resume_group_membership(
    group_id: str,
    membership_id: str,
    body: GroupMembershipTransitionRequest,
    db: DbDep,
    context: StaffContext,
) -> GroupMemberResponse:
    return service.resume_membership(db, context, group_id, membership_id, body)


@router.post(
    "/groups/{group_id}/members/{membership_id}/end",
    response_model=GroupMemberResponse,
    operation_id="endGroupMembership",
    responses={409: {"description": "Membership already ended."}},
)
def end_group_membership(
    group_id: str,
    membership_id: str,
    body: EndGroupMembershipRequest,
    db: DbDep,
    context: StaffContext,
) -> GroupMemberResponse:
    return service.end_membership(db, context, group_id, membership_id, body)


@router.patch(
    "/groups/{group_id}/members/{membership_id}/discount",
    response_model=GroupMemberResponse,
    operation_id="setGroupMembershipDiscount",
)
def set_group_membership_discount(
    group_id: str,
    membership_id: str,
    body: SetMembershipDiscountRequest,
    db: DbDep,
    context: StaffContext,
) -> GroupMemberResponse:
    return service.set_membership_discount(db, context, group_id, membership_id, body)
