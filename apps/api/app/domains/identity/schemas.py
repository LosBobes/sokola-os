from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domains.identity.enums import (
    InvitationStatus,
    InvitationType,
    PersonIdentityStatus,
    RoleAssignmentStatus,
    RoleCode,
    RoleScopeType,
)


class ContextSummary(BaseModel):
    """One selectable acting context = an active role in one school."""

    model_config = ConfigDict(from_attributes=True)

    role_assignment_id: str
    school_id: str
    school_name: str
    role_code: RoleCode
    scope_type: RoleScopeType
    scope_ref_id: str | None


class MeResponse(BaseModel):
    person_id: str
    display_name: str
    identity_status: PersonIdentityStatus
    contexts: list[ContextSummary]


# ---------------------------------------------------------------------------
# Invitations (§16-24, §19.3-19.5), M1/M2/M7/M8
# ---------------------------------------------------------------------------


def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    if "@" not in value or len(value) < 3:
        raise ValueError("target_email must be a valid email address")
    return value


class CreateInvitationRequest(BaseModel):
    type: InvitationType
    target_email: str = Field(min_length=3, max_length=320)
    # STAFF invites choose a role explicitly; PARENT/STUDENT invites imply their
    # own role code and this field is ignored if sent.
    role_code: RoleCode | None = None
    scope_type: RoleScopeType = RoleScopeType.SCHOOL
    scope_ref_id: str | None = Field(default=None, max_length=64)
    # A per-invite area restriction (e.g. "ADMIN for finances only", §19.2/§25.5).
    granted_areas: list[str] | None = None
    # PARENT invites only (§19.4/19.5): the child this guardian will be linked to.
    target_child_person_id: str | None = Field(default=None, max_length=64)

    @field_validator("target_email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        return _normalize_email(value)


class InvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    school_id: str
    type: InvitationType
    status: InvitationStatus
    target_email: str | None
    person_id: str | None
    role_code: RoleCode
    scope_type: RoleScopeType
    scope_ref_id: str | None
    granted_areas: list[str] | None
    target_child_person_id: str | None
    invited_by_person_id: str | None
    reissued_from_invitation_id: str | None
    expires_at: dt.datetime
    accepted_at: dt.datetime | None
    created_at: dt.datetime


class InvitationCreatedResponse(BaseModel):
    """Send/reissue response. ``token`` is shown exactly once, only its hash is
    ever persisted (see ``invite_tokens.py``)."""

    invitation: InvitationResponse
    token: str


class RevokeInvitationRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class AcceptInvitationRequest(BaseModel):
    token: str = Field(min_length=1)


class AcceptInvitationResponse(BaseModel):
    context: ContextSummary


# ---------------------------------------------------------------------------
# Role assignment + permission-change endpoints (§25/§26), M3/M4/M8
# ---------------------------------------------------------------------------


class AssignRoleRequest(BaseModel):
    person_id: str = Field(min_length=1)
    role_code: RoleCode
    scope_type: RoleScopeType = RoleScopeType.SCHOOL
    scope_ref_id: str | None = Field(default=None, max_length=64)
    granted_areas: list[str] | None = None


class UpdateGrantedAreasRequest(BaseModel):
    """``null`` clears the restriction back to the role's full default areas."""

    granted_areas: list[str] | None = None


class RoleTransitionRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class RoleAssignmentResponse(BaseModel):
    id: str
    person_id: str
    display_name: str
    school_id: str
    role_code: RoleCode
    scope_type: RoleScopeType
    scope_ref_id: str | None
    granted_areas: list[str] | None
    status: RoleAssignmentStatus


# ---------------------------------------------------------------------------
# Ownership add/transfer (§14), M5
# ---------------------------------------------------------------------------


class TransferOwnershipRequest(BaseModel):
    new_owner_person_id: str = Field(min_length=1)
    # If set, that person's OWNER assignment is revoked once the new owner is
    # in place (never leaving the school without an owner, even transiently).
    revoke_from_person_id: str | None = Field(default=None, min_length=1)


class TransferOwnershipResponse(BaseModel):
    new_owner: RoleAssignmentResponse
    revoked_owner: RoleAssignmentResponse | None
