"""Guided school onboarding (PRD 02 §24/§25, PRD 01 §13) — the Wave 1 capstone.

Design note (documented per the issue's "your call" points):

* Locations/rooms/programs are NOT duplicated behind onboarding-specific create
  endpoints. Structure setup during onboarding is just using the structure
  domain's own ``POST /locations`` / ``/rooms`` / ``/programs`` — this service
  only *reports* whether at least one active row of each exists for the school,
  read live off ``app.domains.structure.models`` (models may cross domains;
  service/repository/router may not — see ``scripts/check_architecture.py``).
* The "first invite" step is likewise read live: at least one invitation has
  ever been sent for the school. During ``IN_PREPARATION`` that can only be a
  co-owner (OWNER) invite — see
  ``app.domains.identity.policy.ensure_invitation_allowed_during_onboarding`` —
  so in practice this step tracks the first-owner invite path (§13/M3).
* ``school profile`` is satisfied the moment the organization exists (name/
  type/timezone are required at ``POST /organizations``), so it is always
  reported complete.
* Activation's minimum bar is "at least one active location" (per the issue).
  Rooms/programs/first-invite remain informational progress, not activation
  blockers — a school can activate having only set up its address.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass, RecordStatus
from app.common.errors import ConflictError
from app.domains.identity.models import Invitation
from app.domains.onboarding.enums import OnboardingStep
from app.domains.onboarding.models import OnboardingProgress
from app.domains.onboarding.schemas import OnboardingProgressResponse, OnboardingStepStatus
from app.domains.organization.enums import OrganizationLifecycleStatus
from app.domains.organization.models import Organization
from app.domains.structure.models import Location, Program, Room
from app.platform.audit.service import record_audit
from app.platform.outbox.service import enqueue
from app.security.context import RequestContext


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


def _get_or_create_progress(db: Session, organization_id: str) -> OnboardingProgress:
    row = db.execute(
        select(OnboardingProgress).where(OnboardingProgress.organization_id == organization_id)
    ).scalar_one_or_none()
    if row is None:
        row = OnboardingProgress(organization_id=organization_id)
        db.add(row)
        db.flush()
    return row


def _first_active_completed_at(
    db: Session, model: type[Any], organization_id: str
) -> dt.datetime | None:
    """The earliest ``created_at`` among the org's ACTIVE rows of ``model`` —
    i.e. when this step first became true. ``None`` if none exist (yet)."""
    return db.execute(
        select(func.min(model.created_at)).where(
            model.organization_id == organization_id,
            model.record_status == RecordStatus.ACTIVE,
        )
    ).scalar_one_or_none()


def _first_invitation_at(db: Session, organization_id: str) -> dt.datetime | None:
    return db.execute(
        select(func.min(Invitation.created_at)).where(
            Invitation.organization_id == organization_id
        )
    ).scalar_one_or_none()


def _minimum_activation_met(db: Session, organization_id: str) -> bool:
    return _first_active_completed_at(db, Location, organization_id) is not None


def _build_response(
    db: Session, org: Organization, progress: OnboardingProgress
) -> OnboardingProgressResponse:
    locations_at = _first_active_completed_at(db, Location, org.id)
    rooms_at = _first_active_completed_at(db, Room, org.id)
    programs_at = _first_active_completed_at(db, Program, org.id)
    invite_at = _first_invitation_at(db, org.id)

    steps = [
        OnboardingStepStatus(
            step=OnboardingStep.SCHOOL_PROFILE, completed=True, completed_at=org.created_at
        ),
        OnboardingStepStatus(
            step=OnboardingStep.LOCATIONS,
            completed=locations_at is not None,
            completed_at=locations_at,
        ),
        OnboardingStepStatus(
            step=OnboardingStep.ROOMS, completed=rooms_at is not None, completed_at=rooms_at
        ),
        OnboardingStepStatus(
            step=OnboardingStep.PROGRAMS,
            completed=programs_at is not None,
            completed_at=programs_at,
        ),
        OnboardingStepStatus(
            step=OnboardingStep.FIRST_INVITE,
            completed=invite_at is not None,
            completed_at=invite_at,
        ),
        OnboardingStepStatus(
            step=OnboardingStep.ACTIVATE,
            completed=progress.activated_at is not None,
            completed_at=progress.activated_at,
        ),
    ]
    remaining = [s.step for s in steps if not s.completed]
    can_activate = (
        org.lifecycle_status is OrganizationLifecycleStatus.IN_PREPARATION
        and locations_at is not None
    )
    return OnboardingProgressResponse(
        organization_id=org.id,
        lifecycle_status=org.lifecycle_status,
        steps=steps,
        remaining_steps=remaining,
        can_activate=can_activate,
        activated_at=progress.activated_at,
    )


def get_progress(db: Session, context: RequestContext) -> OnboardingProgressResponse:
    org = db.get(Organization, context.organization_id)
    assert org is not None  # context guarantees the active org exists
    progress = _get_or_create_progress(db, context.organization_id)
    return _build_response(db, org, progress)


def activate(db: Session, context: RequestContext) -> OnboardingProgressResponse:
    """Leave "u pripremi": the school starts behaving normally (every
    invitation type/role is reachable again, subject to the usual role/area
    rules)."""
    org = db.get(Organization, context.organization_id)
    assert org is not None
    if org.lifecycle_status is OrganizationLifecycleStatus.ACTIVE:
        raise ConflictError("Škola je već aktivna.")
    if not _minimum_activation_met(db, org.id):
        raise ConflictError("Potrebno je dodati bar jedan ogranak pre aktivacije.")

    progress = _get_or_create_progress(db, org.id)
    now = _now()
    progress.activated_at = now
    org.lifecycle_status = OrganizationLifecycleStatus.ACTIVE

    record_audit(
        db,
        data_class=AuditDataClass.OPERATIONAL,
        action="onboarding.activated",
        entity_type="organization",
        entity_id=org.id,
        summary=f"Škola „{org.name}“ je aktivirana nakon uvodnog podešavanja.",
        organization_id=org.id,
        actor_person_id=context.person_id,
    )
    enqueue(
        db,
        event_type="onboarding.activated",
        payload={"organization_id": org.id},
        organization_id=org.id,
    )
    db.commit()
    return _build_response(db, org, progress)
