from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domains.identity.enums import PersonIdentityStatus


class CreatePersonRequest(BaseModel):
    given_name: str = Field(min_length=1, max_length=120)
    family_name: str = Field(min_length=1, max_length=120)
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
