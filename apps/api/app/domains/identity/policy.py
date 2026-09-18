"""Validation rules for invitations and role assignments.

Kept apart from ``service.py`` (which owns transactions/audit/outbox) purely to
stay under the service-size ratchet; these are pure functions plus read-only
lookups against sibling domains' models (allowed, only service/repository/
router/policy imports are forbidden across domains, never models/enums).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.common.errors import BadRequestError, ForbiddenError, NotFoundError
from app.domains.groups.models import Group
from app.domains.identity.enums import InvitationType, RoleCode, RoleScopeType
from app.domains.school.enums import SchoolStatus
from app.domains.school.models import School
from app.domains.structure.models import Location
from app.security.permissions import ROLE_DEFAULT_AREAS, effective_areas, parse_granted_areas

_STAFF_ROLE_CODES = frozenset({RoleCode.OWNER, RoleCode.MANAGER, RoleCode.ADMIN, RoleCode.TRAINER})


def role_code_for_invitation(inv_type: InvitationType, requested: RoleCode | None) -> RoleCode:
    """PARENT/STUDENT invites imply their own role; STAFF invites choose one of
    the staff-facing roles explicitly (never PARENT/STUDENT)."""
    if inv_type is InvitationType.PARENT:
        return RoleCode.PARENT
    if inv_type is InvitationType.STUDENT:
        return RoleCode.STUDENT
    if requested is None or requested not in _STAFF_ROLE_CODES:
        raise BadRequestError(
            "Potrebno je izabrati validnu ulogu osoblja (vlasnik/menadžer/admin/trener)."
        )
    return requested


def validate_scope(
    db: Session,
    school_id: str,
    role_code: RoleCode,
    scope_type: RoleScopeType,
    scope_ref_id: str | None,
) -> None:
    """A role's scope must be internally consistent and, when narrower than the
    whole school, point at a real branch/group inside THIS org (§19.3)."""
    if scope_type is RoleScopeType.SCHOOL:
        if scope_ref_id is not None:
            raise BadRequestError("Uloga na nivou organizacije ne sme imati dodatni obuhvat.")
        return

    if role_code is RoleCode.OWNER:
        raise BadRequestError("Vlasništvo mora biti na nivou cele organizacije.")
    if not scope_ref_id:
        raise BadRequestError("Ovaj obuhvat zahteva odabir ogranka ili grupe.")

    if scope_type is RoleScopeType.BRANCH:
        location = db.get(Location, scope_ref_id)
        if (
            location is None
            or location.school_id != school_id
            or location.record_status is RecordStatus.ARCHIVED
        ):
            raise NotFoundError("Ogranak nije pronađen.")
        return

    # GROUP, the trainer-scoped-to-a-group path (§19.3/M8).
    group = db.get(Group, scope_ref_id)
    if (
        group is None
        or group.school_id != school_id
        or group.record_status is RecordStatus.ARCHIVED
    ):
        raise NotFoundError("Grupa nije pronađena.")


def validate_granted_areas(
    role_code: RoleCode,
    granted_areas: list[str] | None,
    *,
    actor_role_code: RoleCode,
    actor_granted_areas: tuple[str, ...] | None,
) -> None:
    """A restriction can only narrow a role's default areas, never escalate
    (§19.2/§25.5), checked two ways:

    1. Every requested area must be one the target role could ever reach
       (reject areas outside the role's own defaults).
    2. For a STAFF-family target role (OWNER/MANAGER/ADMIN/TRAINER, the roles
       whose access is denominated in these areas at all), the resulting areas
       must never exceed what the ACTING context itself effectively holds , 
       otherwise a restricted admin could invite/assign someone (or edit their
       own assignment) into MORE access than they have, laundering a narrow
       grant into a broad one. An unrestricted actor's effective areas already
       cover every staff role's defaults, so this is a no-op for the common
       case. PARENT/STUDENT are a different axis entirely, becoming a parent
       or student isn't a point on the staff-area scale (no staff role's
       defaults include PARENTS), so granting those role kinds is data
       administration already gated by ROLES/PEOPLE, not an area escalation.
    """
    if granted_areas is not None:
        defaults = {a.value for a in ROLE_DEFAULT_AREAS.get(role_code, frozenset())}
        invalid = sorted(a for a in granted_areas if a not in defaults)
        if invalid:
            raise BadRequestError(
                f"Nedozvoljene oblasti za ovu ulogu: {', '.join(invalid)}.",
                details={"invalid_areas": invalid},
            )

    if role_code not in _STAFF_ROLE_CODES:
        return

    target_effective = effective_areas(role_code, parse_granted_areas(granted_areas))
    actor_effective = effective_areas(actor_role_code, parse_granted_areas(actor_granted_areas))
    excess = sorted(a.value for a in (target_effective - actor_effective))
    if excess:
        raise BadRequestError(
            f"Ne možete dodeliti oblasti koje sami nemate: {', '.join(excess)}.",
            details={"invalid_areas": excess},
        )


def ensure_invitation_allowed_during_onboarding(
    school: School, role_code: RoleCode
) -> None:
    """§13/M2 (guided onboarding), while a school is ``IN_PREPARATION``
    ("u pripremi"), the only invitation the owner may send is a co-owner
    invite (STAFF/OWNER). Every other invitation, another staff role, a
    parent, a student, is blocked until the school ``activate``-s out of
    onboarding, so a school-in-progress never accidentally onboards real
    members before its structure exists.
    """
    if (
        school.status is SchoolStatus.IN_PREPARATION
        and role_code is not RoleCode.OWNER
    ):
        raise ForbiddenError(
            "Škola je u pripremi. Dok se podešavanje ne završi, moguće je "
            "pozvati samo dodatnog vlasnika."
        )


__all__ = [
    "ensure_invitation_allowed_during_onboarding",
    "role_code_for_invitation",
    "validate_granted_areas",
    "validate_scope",
]
