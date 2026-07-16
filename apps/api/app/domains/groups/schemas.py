from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domains.groups.enums import GroupCapacityMode


class CreateGroupRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    capacity_mode: GroupCapacityMode = GroupCapacityMode.UNLIMITED
    capacity: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _capacity_consistency(self) -> CreateGroupRequest:
        if self.capacity_mode is GroupCapacityMode.LIMITED and self.capacity is None:
            raise ValueError("capacity is required when capacity_mode is LIMITED")
        if self.capacity_mode is GroupCapacityMode.UNLIMITED and self.capacity is not None:
            raise ValueError("capacity must be null when capacity_mode is UNLIMITED")
        return self


class GroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    capacity_mode: GroupCapacityMode
    capacity: int | None


class AddGroupMemberRequest(BaseModel):
    person_id: str


class GroupMemberResponse(BaseModel):
    membership_id: str
    person_id: str
    display_name: str
