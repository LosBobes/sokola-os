"""M05 §3 / M04 §3.6: school de- and reactivation by a platform actor.

Lives in the application layer because answering this needs two domains at
once — the authorization domain decides whether the caller holds a platform
permission, and the school domain performs the status transition. A domain may
not reach into another domain's service; this layer may.

**Both paths, deliberately.** M04 §3.6 makes de/reactivation platform-only,
and this repository has always let an active owner do it
(`POST /schools/current/deactivate`). Those owner routes are untouched here.
The product owner chose to run both authorities during the transition rather
than take the capability away before anyone holds a platform role — which,
with no platform assignment existing anywhere yet, would have meant nobody
could deactivate a school at all. F-41 therefore stays open: this adds the
contract's path without removing the repo's.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.common.errors import ConflictError, NotFoundError
from app.common.ids import new_id
from app.domains.authorization.platform_roles import require_platform_permission
from app.domains.school import anchor
from app.domains.school.enums import SchoolStatus, SchoolStatusReason
from app.domains.school.models import School
from app.domains.school.schemas import SchoolResponse
from app.security.deps import DbDep, PrincipalDep

router = APIRouter(prefix="/platform/schools", tags=["platform"])

#: §2's permission for this command, bound in the registry to
#: `PLATFORM_OPERATIONS_ADMIN` alone.
MANAGE_SCHOOL_LIFECYCLE = "platform.schools.lifecycle.manage"

#: The SCH-05 and SCH-06 reason registries a platform actor may choose from.
#: System codes (`SCHOOL_CREATED`, `INITIAL_ACTIVATION`,
#: `INITIAL_OWNER_ACCEPTED`) are excluded: those are written by the
#: provisioning path, and a platform actor claiming one would put a false
#: account of what happened into an append-only history.
DEACTIVATE_REASONS = frozenset(
    {
        SchoolStatusReason.PILOT_PAUSED,
        SchoolStatusReason.CONTRACT_TERMINATED,
        SchoolStatusReason.SECURITY_INCIDENT,
        SchoolStatusReason.LEGAL_REQUEST,
        SchoolStatusReason.CREATED_IN_ERROR,
        SchoolStatusReason.OPERATIONAL_PAUSE,
    }
)
REACTIVATE_REASONS = frozenset(
    {
        SchoolStatusReason.PILOT_RESUMED,
        SchoolStatusReason.CONTRACT_RESTORED,
        SchoolStatusReason.SECURITY_REMEDIATED,
        SchoolStatusReason.LEGAL_RESTRICTION_LIFTED,
        SchoolStatusReason.OPERATIONAL_RESUME,
    }
)


class PlatformLifecycleRequest(BaseModel):
    """§8.1.2: a platform lifecycle change names its reason and its case.

    Both are mandatory. A platform actor turning a school off without saying
    which registry reason applies, and under which case, is the thing the
    status history exists to make impossible.
    """

    reason_code: SchoolStatusReason
    case_reference: str = Field(min_length=1, max_length=100)
    reason_note: str | None = Field(default=None, max_length=500)


def _school_for_platform(db: Session, school_id: str) -> School:
    """Load the school, or a plain not-found.

    Not safe-not-found: a platform operations admin is allowed to know which
    schools exist — that is the scope of the permission they hold. §8's
    enumeration rule protects tenants from *each other*, not the platform from
    its own operators.
    """
    school = db.get(School, school_id)
    if school is None:
        raise NotFoundError("Škola nije pronađena.")
    return school


@router.post(
    "/{school_id}/deactivate",
    response_model=SchoolResponse,
    operation_id="platformDeactivateSchool",
    responses={
        403: {"description": "Caller holds no platform lifecycle permission."},
        404: {"description": "School not found."},
        409: {"description": "Already deactivated, or reason outside SCH-05."},
    },
)
def platform_deactivate_school(
    school_id: str, body: PlatformLifecycleRequest, db: DbDep, principal: PrincipalDep
) -> SchoolResponse:
    """SCH-05 as §3.6 describes it: performed by the platform, not the school.

    The TEN-04 access-version bump rides along inside
    `anchor.transition_status`, in the same transaction, so there is no window
    where the school reads DEACTIVATED while issued contexts still resolve
    against it.
    """
    require_platform_permission(
        db,
        user_account_id=principal.user_account_id,
        permission_key=MANAGE_SCHOOL_LIFECYCLE,
    )
    if body.reason_code not in DEACTIVATE_REASONS:
        raise ConflictError("Razlog nije iz SCH-05 registra.")

    school = _school_for_platform(db, school_id)
    if school.status is SchoolStatus.DEACTIVATED:
        raise ConflictError("Škola je već deaktivirana.")

    anchor.transition_status(
        db,
        school=school,
        to_status=SchoolStatus.DEACTIVATED,
        reason_code=body.reason_code,
        reason_note=body.reason_note,
        actor_ref=principal.user_account_id or "platform",
        correlation_id=new_id("corr"),
    )
    db.commit()
    return SchoolResponse.model_validate(school)


@router.post(
    "/{school_id}/reactivate",
    response_model=SchoolResponse,
    operation_id="platformReactivateSchool",
    responses={
        403: {"description": "Caller holds no platform lifecycle permission."},
        404: {"description": "School not found."},
        409: {"description": "Already active, or reason outside SCH-06."},
    },
)
def platform_reactivate_school(
    school_id: str, body: PlatformLifecycleRequest, db: DbDep, principal: PrincipalDep
) -> SchoolResponse:
    """SCH-06. Coming back is as much a security boundary as going away:
    `transition_status` bumps the tenant access version here too, so contexts
    built while the school was off do not simply resume."""
    require_platform_permission(
        db,
        user_account_id=principal.user_account_id,
        permission_key=MANAGE_SCHOOL_LIFECYCLE,
    )
    if body.reason_code not in REACTIVATE_REASONS:
        raise ConflictError("Razlog nije iz SCH-06 registra.")

    school = _school_for_platform(db, school_id)
    if school.status is not SchoolStatus.DEACTIVATED:
        raise ConflictError("Škola nije deaktivirana.")

    anchor.transition_status(
        db,
        school=school,
        to_status=SchoolStatus.ACTIVE,
        reason_code=body.reason_code,
        reason_note=body.reason_note,
        actor_ref=principal.user_account_id or "platform",
        correlation_id=new_id("corr"),
    )
    db.commit()
    return SchoolResponse.model_validate(school)
