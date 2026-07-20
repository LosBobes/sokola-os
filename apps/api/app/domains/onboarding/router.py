from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.domains.onboarding import service
from app.domains.onboarding.schemas import OnboardingProgressResponse
from app.security.deps import ContextDep, DbDep
from app.security.permissions import PermissionArea, require_permission

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

# Activation changes the school's lifecycle — organization-management authority.
_org_admin = require_permission(PermissionArea.ORGANIZATION)
OrgAdminContext = Annotated[ContextDep, Depends(_org_admin)]


@router.get(
    "/progress",
    response_model=OnboardingProgressResponse,
    operation_id="getOnboardingProgress",
)
def get_progress(db: DbDep, context: ContextDep) -> OnboardingProgressResponse:
    """Per-step guided-onboarding progress for the caller's active school
    (PRD 02 §24/§25) — what's done and what's left, including whether
    activation is currently possible."""
    return service.get_progress(db, context)


@router.post(
    "/activate",
    response_model=OnboardingProgressResponse,
    operation_id="activateOnboarding",
    responses={
        409: {"description": "Already active, or the minimum setup (a location) is missing."}
    },
)
def activate(db: DbDep, context: OrgAdminContext) -> OnboardingProgressResponse:
    """Leave "u pripremi": the school behaves normally from here on (§13)."""
    return service.activate(db, context)
