from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.common.pagination import Page, PageParams, page_params
from app.domains.identity import roles_service, service
from app.domains.identity.schemas import (
    AcceptInvitationRequest,
    AcceptInvitationResponse,
    AssignRoleRequest,
    ContextSummary,
    CreateInvitationRequest,
    InvitationCreatedResponse,
    InvitationResponse,
    MeResponse,
    RevokeInvitationRequest,
    RoleAssignmentResponse,
    RoleTransitionRequest,
    TransferOwnershipRequest,
    TransferOwnershipResponse,
    UpdateGrantedAreasRequest,
)
from app.security.deps import ContextDep, DbDep, PrincipalDep
from app.security.permissions import PermissionArea, require_permission

router = APIRouter(tags=["me"])

# Invitation + role administration (§16-26, §14) is gated on the ROLES area.
_roles_admin = require_permission(PermissionArea.ROLES)
RolesContext = Annotated[ContextDep, Depends(_roles_admin)]
PageParamsDep = Annotated[PageParams, Depends(page_params)]


@router.get("/me", response_model=MeResponse, operation_id="getMe")
def get_me(db: DbDep, principal: PrincipalDep) -> MeResponse:
    """The authenticated person and the contexts they may act in. Called before a
    context is chosen, so it requires authentication but no active context."""
    return service.get_me(db, principal)


@router.get("/me/contexts", response_model=list[ContextSummary], operation_id="listMyContexts")
def list_my_contexts(db: DbDep, principal: PrincipalDep) -> list[ContextSummary]:
    return service.get_me(db, principal).contexts


# ---------------------------------------------------------------------------
# Invitations (§16-24, §19.3-19.5)
# ---------------------------------------------------------------------------


@router.post(
    "/invitations",
    response_model=InvitationCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="sendInvitation",
)
def send_invitation(
    body: CreateInvitationRequest, db: DbDep, context: RolesContext
) -> InvitationCreatedResponse:
    """Send an invitation. The raw token is returned exactly once, only its
    hash is ever persisted."""
    return service.send_invitation(db, context, body)


@router.get(
    "/invitations", response_model=Page[InvitationResponse], operation_id="listInvitations"
)
def list_invitations(
    db: DbDep, context: RolesContext, params: PageParamsDep
) -> Page[InvitationResponse]:
    return service.list_invitations(db, context, params)


@router.get(
    "/invitations/{invitation_id}",
    response_model=InvitationResponse,
    operation_id="getInvitation",
)
def get_invitation(invitation_id: str, db: DbDep, context: RolesContext) -> InvitationResponse:
    return service.get_invitation(db, context, invitation_id)


@router.post(
    "/invitations/{invitation_id}/revoke",
    response_model=InvitationResponse,
    operation_id="revokeInvitation",
    responses={409: {"description": "Only a PENDING invitation may be revoked."}},
)
def revoke_invitation(
    invitation_id: str, body: RevokeInvitationRequest, db: DbDep, context: RolesContext
) -> InvitationResponse:
    return service.revoke_invitation(db, context, invitation_id, body)


@router.post(
    "/invitations/{invitation_id}/reissue",
    response_model=InvitationCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="reissueInvitation",
    responses={409: {"description": "Only a PENDING/EXPIRED invitation may be reissued."}},
)
def reissue_invitation(
    invitation_id: str, db: DbDep, context: RolesContext
) -> InvitationCreatedResponse:
    return service.reissue_invitation(db, context, invitation_id)


@router.post(
    "/invitations/accept",
    response_model=AcceptInvitationResponse,
    operation_id="acceptInvitation",
    responses={
        403: {"description": "Invitation bound to a different account (§23)."},
        409: {"description": "Invitation expired/revoked/already used."},
    },
)
def accept_invitation(
    body: AcceptInvitationRequest, db: DbDep, principal: PrincipalDep
) -> AcceptInvitationResponse:
    """Accept an invitation as the already-authenticated caller, the same path
    for a brand-new sign-up and an existing person (§21/§22); no active context
    is required since acceptance is exactly how one is obtained."""
    return service.accept_invitation(db, principal, body)


# ---------------------------------------------------------------------------
# Role assignment + permission-change endpoints (§25/§26)
# ---------------------------------------------------------------------------


@router.post(
    "/roles",
    response_model=RoleAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="assignRole",
    responses={409: {"description": "Person already holds this exact role/scope."}},
)
def assign_role(
    body: AssignRoleRequest, db: DbDep, context: RolesContext
) -> RoleAssignmentResponse:
    return roles_service.assign_role(db, context, body)


@router.get(
    "/roles", response_model=Page[RoleAssignmentResponse], operation_id="listRoleAssignments"
)
def list_role_assignments(
    db: DbDep, context: RolesContext, params: PageParamsDep
) -> Page[RoleAssignmentResponse]:
    return roles_service.list_role_assignments(db, context, params)


@router.patch(
    "/roles/{assignment_id}/granted-areas",
    response_model=RoleAssignmentResponse,
    operation_id="updateGrantedAreas",
)
def update_granted_areas(
    assignment_id: str, body: UpdateGrantedAreasRequest, db: DbDep, context: RolesContext
) -> RoleAssignmentResponse:
    return roles_service.update_granted_areas(db, context, assignment_id, body)


@router.post(
    "/roles/{assignment_id}/suspend",
    response_model=RoleAssignmentResponse,
    operation_id="suspendRoleAssignment",
    responses={409: {"description": "Not active, or the school's last active owner."}},
)
def suspend_role_assignment(
    assignment_id: str, body: RoleTransitionRequest, db: DbDep, context: RolesContext
) -> RoleAssignmentResponse:
    return roles_service.suspend_assignment(db, context, assignment_id, body)


@router.post(
    "/roles/{assignment_id}/revoke",
    response_model=RoleAssignmentResponse,
    operation_id="revokeRoleAssignment",
    responses={409: {"description": "Already revoked, or the school's last active owner."}},
)
def revoke_role_assignment(
    assignment_id: str, body: RoleTransitionRequest, db: DbDep, context: RolesContext
) -> RoleAssignmentResponse:
    return roles_service.revoke_assignment(db, context, assignment_id, body)


# ---------------------------------------------------------------------------
# Ownership add/transfer (§14)
# ---------------------------------------------------------------------------


@router.post(
    "/roles/ownership/transfer",
    response_model=TransferOwnershipResponse,
    operation_id="transferOwnership",
    responses={409: {"description": "Already an owner, or would leave the school ownerless."}},
)
def transfer_ownership(
    body: TransferOwnershipRequest, db: DbDep, context: RolesContext
) -> TransferOwnershipResponse:
    return roles_service.transfer_ownership(db, context, body)
