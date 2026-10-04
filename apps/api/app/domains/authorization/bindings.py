"""M05 §3.1 steps 4–5, the half that is purely about the policy registry.

What a set of role keys is bound to, under the one ACTIVE revision. Every
table this reads — `AuthorizationPolicyRevision`, `RolePermissionBinding` — is
this domain's own, which is why it lives here.

It was previously in `app/application/effective_permissions.py`, which was the
wrong layer and only became visible when a second caller appeared: the
platform-role guard is a domain module, and a domain may not import the
application layer. The application layer still owns the *other* half — turning
a person's `RoleAssignment` rows into role keys — because that genuinely spans
two domains.
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


class PermissionsUnavailableError(AppError):
    """§3.1: when a permission set cannot be computed, the answer is a refusal
    — never an empty set.

    An empty set would be indistinguishable from "this person may do nothing",
    and the two need very different handling: one is a correct answer, the
    other is an outage or an undecided mapping.

    This base exists so a caller wiring the resolver into a guard can catch
    *every* "I cannot answer" in one place. The subclasses say which condition
    it was, because the remedies differ — one is operational, the other is a
    decision nobody has taken — but no caller should have to enumerate them to
    fail closed. Catching only one and letting the other escape as a bare 500
    is the drift this prevents.
    """

    status_code = 500
    code = "PERMISSIONS_UNAVAILABLE"


class PolicyUnavailableError(PermissionsUnavailableError):
    """The policy store has no ACTIVE revision: an outage, not an answer."""

    code = "AUTHORIZATION_POLICY_UNAVAILABLE"


def active_revision_id(db: Session) -> str:
    """The one ACTIVE policy revision, or fail closed."""
    revision_id = db.execute(
        select(AuthorizationPolicyRevision.id).where(
            AuthorizationPolicyRevision.status == PolicyRevisionStatus.ACTIVE
        )
    ).scalar_one_or_none()
    if revision_id is None:
        raise PolicyUnavailableError("Autorizaciona politika nije dostupna.")
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
