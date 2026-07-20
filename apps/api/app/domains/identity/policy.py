"""Validation rules for invitations and role assignments.

Kept apart from ``service.py`` (which owns transactions/audit/outbox) purely to
stay under the service-size ratchet; these are pure functions plus read-only
lookups against sibling domains' models (allowed — only service/repository/
router/policy imports are forbidden across domains, never models/enums).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.common.enums import RecordStatus
from app.common.errors import BadRequestError, NotFoundError
from app.domains.groups.models import Group
from app.domains.identity.enums import InvitationType, RoleCode, RoleScopeType
from app.domains.structure.models import Location
from app.security.permissions import ROLE_DEFAULT_AREAS

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
    organization_id: str,
    role_code: RoleCode,
    scope_type: RoleScopeType,
    scope_ref_id: str | None,
) -> None:
    """A role's scope must be internally consistent and, when narrower than the
    whole organization, point at a real branch/group inside THIS org (§19.3)."""
    if scope_type is RoleScopeType.ORGANIZATION:
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
            or location.organization_id != organization_id
            or location.record_status is RecordStatus.ARCHIVED
        ):
            raise NotFoundError("Ogranak nije pronađen.")
        return

    # GROUP — the trainer-scoped-to-a-group path (§19.3/M8).
    group = db.get(Group, scope_ref_id)
    if (
        group is None
        or group.organization_id != organization_id
        or group.record_status is RecordStatus.ARCHIVED
    ):
        raise NotFoundError("Grupa nije pronađena.")


def validate_granted_areas(role_code: RoleCode, granted_areas: list[str] | None) -> None:
    """A restriction can only narrow a role's default areas, never escalate
    (§19.2/§25.5) — reject areas the role could never reach at write time."""
    if granted_areas is None:
        return
    defaults = {a.value for a in ROLE_DEFAULT_AREAS.get(role_code, frozenset())}
    invalid = sorted(a for a in granted_areas if a not in defaults)
    if invalid:
        raise BadRequestError(
            f"Nedozvoljene oblasti za ovu ulogu: {', '.join(invalid)}.",
            details={"invalid_areas": invalid},
        )


__all__ = ["role_code_for_invitation", "validate_granted_areas", "validate_scope"]
