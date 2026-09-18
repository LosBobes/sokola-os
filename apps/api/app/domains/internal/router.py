"""Dev-only bootstrap endpoints.

These exist solely to make local onboarding and end-to-end tests possible (create
a first identity before any school exists). They are hidden unless the
insecure dev-auth adapter is enabled, and that flag is refused in production.
"""

from __future__ import annotations

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.common.errors import NotFoundError
from app.domains.identity.enums import PersonIdentityStatus
from app.domains.identity.models import Person
from app.security.deps import DbDep, SettingsDep

router = APIRouter(tags=["internal"])


class CreateDevIdentityRequest(BaseModel):
    given_name: str = Field(min_length=1, max_length=120)
    family_name: str = Field(min_length=1, max_length=120)


class DevIdentityResponse(BaseModel):
    person_id: str
    display_name: str


@router.post(
    "/internal/dev/identities",
    response_model=DevIdentityResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createDevIdentity",
)
def create_dev_identity(
    body: CreateDevIdentityRequest, db: DbDep, settings: SettingsDep
) -> DevIdentityResponse:
    if not settings.allow_insecure_dev_auth:
        # Hide the endpoint entirely when the dev adapter is off.
        raise NotFoundError("Not found.")
    given = body.given_name.strip()
    family = body.family_name.strip()
    person = Person(
        given_name=given,
        family_name=family,
        display_name=f"{given} {family}",
        identity_status=PersonIdentityStatus.CLAIMED,
    )
    db.add(person)
    db.commit()
    return DevIdentityResponse(person_id=person.id, display_name=person.display_name)
