"""M05 §3.1 steps 4–5: what a person may actually do in a school.

The union of every binding held by every one of their active roles in the
active school, read from the one ACTIVE policy revision.

**Nothing is wired to this yet, and that is deliberate.** The live guard is
still `app.security.permissions`, whose per-area model this will eventually
replace. It cannot replace it today: revision 1.3 carries only the 38 keys
§3.3 determines, and the operational permissions — people, groups, scheduling,
attendance, finance — live in continuation registries that are undecidable
until F-30's two role groupings are defined. A resolver switched on now would
deny everything those routers guard.

So this is the mechanism, built and tested against what the registry actually
holds, waiting for the registry to be complete.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.errors import AppError
from app.domains.authorization.enums import DOMAIN_SCHOOL, PolicyRevisionStatus
from app.domains.authorization.models import (
    AuthorizationPolicyRevision,
    RolePermissionBinding,
)
from app.domains.identity.enums import RoleAssignmentStatus, RoleCode
from app.domains.identity.models import RoleAssignment


class RoleMappingUnavailableError(AppError):
    """This repo's role has no settled M05 counterpart, so no permission set
    can be computed for it (F-29).

    Loud rather than empty on purpose. Returning "no permissions" would look
    like a correct fail-closed answer while actually meaning "nobody has
    decided yet" — and the first caller to wire this up would silently strip
    every administrator, which is exactly the outcome F-29 exists to prevent.
    """

    status_code = 500
    code = "ROLE_MAPPING_UNAVAILABLE"


#: This repo's `RoleCode` against M05 §2.4's canonical keys, **for permissions**.
#:
#: Not the same question as the workspace map in `available_contexts`, and not
#: safe to share with it. There, `ADMIN` is unambiguous because §2.4 puts
#: `MANAGER` and `LIMITED_ADMIN` in the same `ADMIN` workspace. Here they are
#: as different as two roles get: `MANAGER` holds seven permissions in revision
#: 1.3 and `LIMITED_ADMIN` holds none. Reusing the workspace map would grant
#: `ADMIN` seven permissions on the strength of a mapping chosen for an
#: entirely different reason.
#:
#: So `ADMIN` and `STUDENT` are absent, and asking for them raises.
_CANONICAL_ROLE_KEY: dict[RoleCode, str] = {
    RoleCode.OWNER: "OWNER",
    RoleCode.MANAGER: "MANAGER",
    RoleCode.TRAINER: "INSTRUCTOR",
    RoleCode.PARENT: "GUARDIAN",
}


def canonical_role_key(role_code: RoleCode) -> str:
    """The M05 role key this repo's role becomes, or a refusal.

    `ADMIN` is F-29: mapping it to `MANAGER` preserves today's access while
    losing the distinction M05 draws, and mapping it to `LIMITED_ADMIN` strips
    every existing administrator. `STUDENT` has no counterpart at all.
    """
    key = _CANONICAL_ROLE_KEY.get(role_code)
    if key is None:
        raise RoleMappingUnavailableError(
            f"Uloga {role_code.value} još nema odlučeno M05 preslikavanje."
        )
    return key


def active_revision_id(db: Session) -> str:
    """The one ACTIVE policy revision, or fail closed.

    §3.1: an unavailable policy store is a deny. Returning an empty permission
    set instead would be indistinguishable from "this person may do nothing",
    and the two need very different handling.
    """
    revision_id = db.execute(
        select(AuthorizationPolicyRevision.id).where(
            AuthorizationPolicyRevision.status == PolicyRevisionStatus.ACTIVE
        )
    ).scalar_one_or_none()
    if revision_id is None:
        raise RoleMappingUnavailableError("Autorizaciona politika nije dostupna.")
    return revision_id


def permissions_for_role_keys(
    db: Session, *, role_keys: frozenset[str], domain: str = DOMAIN_SCHOOL
) -> frozenset[str]:
    """§3.1 step 5: the union of the bindings these roles hold.

    A union, never an intersection and never a rank lookup. §3.2 point 1 says
    effective permissions are the union of all of a person's active roles, and
    point 2 adds that administrative rank inherits nothing — so holding a
    senior role does not imply a junior one's permissions, and the only way to
    hold a permission is for some role to be bound to it.
    """
    if not role_keys:
        return frozenset()
    rows = db.execute(
        select(RolePermissionBinding.permission_key).where(
            RolePermissionBinding.policy_revision_id == active_revision_id(db),
            RolePermissionBinding.authorization_domain_key == domain,
            RolePermissionBinding.role_key.in_(role_keys),
        )
    ).scalars()
    return frozenset(rows)


def effective_permissions(
    db: Session, *, person_id: str, school_id: str
) -> frozenset[str]:
    """§3.1 steps 4–5 for one person in one school.

    Reads only *active* assignments in *this* school. It does not re-prove
    membership or the school's state: those are §8 steps 3–5, already done by
    the request guard before anything asks this question. Doing them again here
    would put the same decision in two places and let them drift.
    """
    role_codes = db.execute(
        select(RoleAssignment.role_code).where(
            RoleAssignment.person_id == person_id,
            RoleAssignment.school_id == school_id,
            RoleAssignment.status == RoleAssignmentStatus.ACTIVE,
        )
    ).scalars()
    keys = frozenset(canonical_role_key(code) for code in set(role_codes))
    return permissions_for_role_keys(db, role_keys=keys)
