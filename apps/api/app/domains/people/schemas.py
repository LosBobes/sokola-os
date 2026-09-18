from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domains.identity.enums import PersonIdentityStatus, PersonMergeStatus
from app.domains.people.enums import GuardianAccessStatus, GuardianRelationshipType
from app.domains.school.enums import MembershipStatus, OrgMemberType


class CreatePersonRequest(BaseModel):
    given_name: str = Field(min_length=1, max_length=120)
    family_name: str = Field(min_length=1, max_length=120)
    # What this person is to the school. Defaults to ATTENDEE (polaznik) because
    # that is who a school adds most often; staff, guardians and plain contacts
    # are recorded with their own type so they are never counted as members.
    member_type: OrgMemberType = OrgMemberType.ATTENDEE
    # Safety branch: creating a likely duplicate must be a deliberate, reasoned act.
    allow_possible_duplicate: bool = False
    duplicate_reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def _require_reason_when_overriding(self) -> CreatePersonRequest:
        if self.allow_possible_duplicate and not (self.duplicate_reason or "").strip():
            raise ValueError("duplicate_reason is required when allow_possible_duplicate is true")
        return self


class PersonSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str
    identity_status: PersonIdentityStatus
    member_type: OrgMemberType


class PersonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    given_name: str
    family_name: str
    display_name: str
    identity_status: PersonIdentityStatus


class DuplicateCandidate(BaseModel):
    person_id: str
    display_name: str


# ---------------------------------------------------------------------------
# Membership lifecycle (§16/§19/§20/§21) and school-local data (§8/§9/§10)
# ---------------------------------------------------------------------------


class MembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    person_id: str
    status: MembershipStatus
    member_type: OrgMemberType
    local_member_code: str | None
    admin_note: str | None


class MembershipTransitionRequest(BaseModel):
    """Optional operator note explaining an end/suspend/resume."""

    reason: str | None = Field(default=None, max_length=500)


class UpdateMemberDataRequest(BaseModel):
    """School-local member data. Only fields present in the request body are
    changed; omit a field to leave it untouched, send ``null`` to clear it.

    ``member_type`` is not school-local trivia , moving someone in or out of
    ATTENDEE changes the school's active-member figure , so it is settable here
    but never nullable."""

    local_member_code: str | None = Field(default=None, max_length=60)
    admin_note: str | None = Field(default=None, max_length=2000)
    member_type: OrgMemberType | None = None


# ---------------------------------------------------------------------------
# Guardian management (§25 primary contact, §30 revoke access)
# ---------------------------------------------------------------------------


class GuardianContactResponse(BaseModel):
    guardian_person_id: str
    display_name: str
    relationship_type: GuardianRelationshipType
    access_status: GuardianAccessStatus
    is_primary_contact: bool


class RevokeGuardianAccessRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


# ---------------------------------------------------------------------------
# Duplicate detection + review (§13–15)
# ---------------------------------------------------------------------------


class DuplicateCluster(BaseModel):
    given_name: str
    family_name: str
    candidates: list[DuplicateCandidate]


class CreateMergeReviewRequest(BaseModel):
    source_person_id: str = Field(min_length=1)
    target_person_id: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=500)


class MergeReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source_person_id: str
    target_person_id: str
    status: PersonMergeStatus
    reason: str


class MergeDecisionRequest(BaseModel):
    decision: Literal["MERGE", "DISMISS"]
    reason: str = Field(min_length=1, max_length=500)
