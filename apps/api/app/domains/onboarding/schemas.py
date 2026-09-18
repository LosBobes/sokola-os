from __future__ import annotations

import datetime as dt

from pydantic import BaseModel

from app.domains.onboarding.enums import OnboardingStep
from app.domains.school.enums import SchoolLifecycleStatus


class OnboardingStepStatus(BaseModel):
    step: OnboardingStep
    completed: bool
    completed_at: dt.datetime | None


class OnboardingProgressResponse(BaseModel):
    school_id: str
    lifecycle_status: SchoolLifecycleStatus
    steps: list[OnboardingStepStatus]
    remaining_steps: list[OnboardingStep]
    # Whether ``POST /onboarding/activate`` would currently succeed, i.e. the
    # school is IN_PREPARATION and its minimum activation bar (at least one
    # active location) is met.
    can_activate: bool
    activated_at: dt.datetime | None
