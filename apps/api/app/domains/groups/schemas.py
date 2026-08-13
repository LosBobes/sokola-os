from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domains.groups.enums import (
    GroupCapacityMode,
    GroupMembershipEndReason,
    GroupMembershipStatus,
)


class CreateGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    capacity_mode: GroupCapacityMode = GroupCapacityMode.UNLIMITED
    capacity: int | None = Field(default=None, ge=1)
    program_id: str | None = None
    location_id: str | None = None
    base_monthly_price_minor: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _capacity_consistency(self) -> CreateGroupRequest:
        if self.capacity_mode is GroupCapacityMode.LIMITED and self.capacity is None:
            raise ValueError("capacity is required when capacity_mode is LIMITED")
        if self.capacity_mode is GroupCapacityMode.UNLIMITED and self.capacity is not None:
            raise ValueError("capacity must be null when capacity_mode is UNLIMITED")
        return self


class UpdateGroupRequest(BaseModel):
    """Partial update. Only fields present in the request body are changed , 
    send ``null`` for ``program_id``/``location_id``/``base_monthly_price_minor``
    to clear that link/price, omit a field entirely to leave it untouched."""

    program_id: str | None = None
    location_id: str | None = None
    base_monthly_price_minor: int | None = Field(default=None, ge=0)


class GroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    capacity_mode: GroupCapacityMode
    capacity: int | None
    program_id: str | None
    location_id: str | None
    base_monthly_price_minor: int | None


class AddGroupMemberRequest(BaseModel):
    person_id: str


class GroupMemberResponse(BaseModel):
    membership_id: str
    person_id: str
    display_name: str
    status: GroupMembershipStatus
    discount_minor: int
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
    ``base_monthly_price_minor``, see :class:`app.domains.groups.models.
    GroupMembership` for why this is absolute rather than a percentage."""

    discount_minor: int = Field(ge=0)
