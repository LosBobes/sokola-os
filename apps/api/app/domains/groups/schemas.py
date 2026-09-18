from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.common.money import MoneyAmount
from app.domains.groups.enums import (
    GroupCapacityMode,
    GroupMemberRole,
    GroupMembershipEndReason,
    GroupMembershipStatus,
)


class CreateGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    capacity_mode: GroupCapacityMode = GroupCapacityMode.UNLIMITED
    capacity: int | None = Field(default=None, ge=1)
    program_id: str | None = None
    location_id: str | None = None
    base_monthly_price: MoneyAmount | None = Field(default=None, ge=0)
    default_trainer_person_id: str | None = None
    default_location_id: str | None = None

    @model_validator(mode="after")
    def _capacity_consistency(self) -> CreateGroupRequest:
        if self.capacity_mode is GroupCapacityMode.LIMITED and self.capacity is None:
            raise ValueError("capacity is required when capacity_mode is LIMITED")
        if self.capacity_mode is GroupCapacityMode.UNLIMITED and self.capacity is not None:
            raise ValueError("capacity must be null when capacity_mode is UNLIMITED")
        return self


class UpdateGroupRequest(BaseModel):
    """Partial update. Only fields present in the request body are changed , 
    send ``null`` for any nullable field to clear that link/price/default, omit
    a field entirely to leave it untouched.

    Changing a default only affects sessions created *after* the change:
    defaults are copied onto a session at create time, never read through.
    """

    program_id: str | None = None
    location_id: str | None = None
    base_monthly_price: MoneyAmount | None = Field(default=None, ge=0)
    default_trainer_person_id: str | None = None
    default_location_id: str | None = None


class GroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    capacity_mode: GroupCapacityMode
    capacity: int | None
    program_id: str | None
    location_id: str | None
    base_monthly_price: MoneyAmount | None
    default_trainer_person_id: str | None
    default_location_id: str | None


class AddGroupMemberRequest(BaseModel):
    """Attach a person to a group. ``role`` says in what capacity , defaults to
    ``MEMBER`` (polaznik), the only role that is rostered and billed."""

    person_id: str
    role: GroupMemberRole = GroupMemberRole.MEMBER


class SetGroupMemberRoleRequest(BaseModel):
    role: GroupMemberRole


class GroupMemberResponse(BaseModel):
    membership_id: str
    person_id: str
    display_name: str
    role: GroupMemberRole
    status: GroupMembershipStatus
    discount: MoneyAmount
    joined_at: dt.datetime
    ended_at: dt.datetime | None
    end_reason: GroupMembershipEndReason | None


class GroupMembershipTransitionRequest(BaseModel):
    """Optional operator note explaining a suspend/resume."""

    reason: str | None = Field(default=None, max_length=500)


class EndGroupMembershipRequest(BaseModel):
    end_reason: GroupMembershipEndReason
    reason: str | None = Field(default=None, max_length=500)


class SetMembershipDiscountRequest(BaseModel):
    """Absolute discount in minor currency units against the group's
    ``base_monthly_price``, see :class:`app.domains.groups.models.
    GroupMembership` for why this is absolute rather than a percentage."""

    discount: MoneyAmount = Field(ge=0)
