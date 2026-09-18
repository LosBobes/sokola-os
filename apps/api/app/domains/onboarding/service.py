"""Guided school onboarding (PRD 02 §24/§25, PRD 01 §13), the Wave 1 capstone.

Design note (documented per the issue's "your call" points):

* Locations/rooms/programs are NOT duplicated behind onboarding-specific create
  endpoints. Structure setup during onboarding is just using the structure
  domain's own ``POST /locations`` / ``/rooms`` / ``/programs``, this service
  only *reports* whether at least one active row of each exists for the school,
  read live off ``app.domains.structure.models`` (models may cross domains;
  service/repository/router may not, see ``scripts/check_architecture.py``).
* The "first invite" step is likewise read live: at least one invitation has
  ever been sent for the school. During ``IN_PREPARATION`` that can only be a
  co-owner (OWNER) invite, see
  ``app.domains.identity.policy.ensure_invitation_allowed_during_onboarding`` , 
  so in practice this step tracks the first-owner invite path (§13/M3).
* ``school profile`` is satisfied the moment the school exists (name/
  type/timezone are required at ``POST /schools``), so it is always
  reported complete.
* Activation's minimum bar is "at least one active location" (per the issue).
  Rooms/programs/first-invite remain informational progress, not activation
  blockers, a school can activate having only set up its address.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass, RecordStatus
from app.common.errors import ConflictError
from app.common.ids import new_id
from app.domains.identity.models import Invitation
from app.domains.onboarding.enums import OnboardingStep
from app.domains.onboarding.models import OnboardingProgress
from app.domains.onboarding.schemas import OnboardingProgressResponse, OnboardingStepStatus
from app.domains.school import anchor
from app.domains.school.enums import SchoolStatus, SchoolStatusReason
from app.domains.school.models import School
from app.domains.structure.models import Location, Program, Room
from app.platform import clock
from app.platform.audit.service import record_audit
from app.platform.outbox.service import enqueue
from app.security.context import RequestContext


def _now() -> dt.datetime:
    return clock.now()


def _get_or_create_progress(db: Session, school_id: str) -> OnboardingProgress:
    row = db.execute(
        select(OnboardingProgress).where(OnboardingProgress.school_id == school_id)
    ).scalar_one_or_none()
    if row is None:
        row = OnboardingProgress(school_id=school_id)
        db.add(row)
        db.flush()
    return row


def _first_active_completed_at(
    db: Session, model: type[Any], school_id: str
) -> dt.datetime | None:
    """The earliest ``created_at`` among the org's ACTIVE rows of ``model`` , 
    i.e. when this step first became true. ``None`` if none exist (yet)."""
    return db.execute(
        select(func.min(model.created_at)).where(
            model.school_id == school_id,
            model.record_status == RecordStatus.ACTIVE,
        )
    ).scalar_one_or_none()


def _first_invitation_at(db: Session, school_id: str) -> dt.datetime | None:
    return db.execute(
        select(func.min(Invitation.created_at)).where(
            Invitation.school_id == school_id
        )
    ).scalar_one_or_none()


def _minimum_activation_met(db: Session, school_id: str) -> bool:
    return _first_active_completed_at(db, Location, school_id) is not None


def _build_response(
    db: Session, org: School, progress: OnboardingProgress
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
        org.status is SchoolStatus.IN_PREPARATION
        and locations_at is not None
    )
    return OnboardingProgressResponse(
        school_id=org.id,
        status=org.status,
        steps=steps,
        remaining_steps=remaining,
        can_activate=can_activate,
        activated_at=progress.activated_at,
    )


def get_progress(db: Session, context: RequestContext) -> OnboardingProgressResponse:
    org = db.get(School, context.school_id)
    assert org is not None  # context guarantees the active org exists
    progress = _get_or_create_progress(db, context.school_id)
    return _build_response(db, org, progress)


def activate(db: Session, context: RequestContext) -> OnboardingProgressResponse:
    """Leave "u pripremi": the school starts behaving normally (every
    invitation type/role is reachable again, subject to the usual role/area
    rules)."""
    org = db.get(School, context.school_id)
    assert org is not None
    if org.status is SchoolStatus.ACTIVE:
        raise ConflictError("Škola je već aktivna.")
    if not _minimum_activation_met(db, org.id):
        raise ConflictError("Potrebno je dodati bar jedan ogranak pre aktivacije.")

    progress = _get_or_create_progress(db, org.id)
    now = _now()
    progress.activated_at = now
    # Through the anchor, never by assigning the column: M04 §2.5 makes the
    # append-only transition the authority and the column its projection, and a
    # direct assignment would leave a school ACTIVE with no record of when or by
    # whom — which is precisely the history a deactivation later has to be read
    # against.
    anchor.transition_status(
        db,
        school=org,
        to_status=SchoolStatus.ACTIVE,
        reason_code=SchoolStatusReason.INITIAL_ACTIVATION,
        actor_ref=context.person_id,
        correlation_id=new_id("corr"),
    )

    record_audit(
        db,
        data_class=AuditDataClass.OPERATIONAL,
        action="onboarding.activated",
        entity_type="school",
        entity_id=org.id,
        summary=f"Škola „{org.name}“ je aktivirana nakon uvodnog podešavanja.",
        school_id=org.id,
        actor_person_id=context.person_id,
    )
    enqueue(
        db,
        event_type="onboarding.activated",
        payload={"school_id": org.id},
        school_id=org.id,
    )
    db.commit()
    return _build_response(db, org, progress)
