"""Product entitlements (M04 §2.8).

The vocabulary of *commercial availability*, which §2.8 is emphatic is not the
vocabulary of access. Evaluation stays four separate layers —
``environment → product entitlement → tenant allowlist → capability flag →
M05 permission → M03/M07 guard`` — and an entitlement answers only the second.
Collapsing any two of them is how "they paid for it" starts meaning "they may
see it", which is a different question with a different answer.
"""

from __future__ import annotations

import enum


class CapabilityKey(enum.StrEnum):
    """§2.8. Not a free string from the API: a new key needs a policy/catalog
    review and an owning-module contract first (§2.0)."""

    #: The core product. Never created automatically from an organization link
    #: (§2.8): being held by an organization is not the same as being sold to.
    CORE_MVP = "CORE_MVP"
    #: M28. Absent unless explicitly granted.
    MYSOKOLA_BASIC = "MYSOKOLA_BASIC"
    #: Absent unless explicitly granted.
    OPERATIONS = "OPERATIONS"


class EntitlementStatus(enum.StrEnum):
    """``REVOKED`` and ``EXPIRED`` are terminal; a new grant is a new row (§5.5).

    ``EXPIRED`` is a *materialization* of something already true. Read-time
    expiry is the authority (§3.8.3), so a grant past ``valid_until`` is
    ineffective whether or not a job has got round to stamping it.
    """

    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class EntitlementGrantReason(enum.StrEnum):
    """§8.1.2, ENT-01."""

    CONTRACT_ACTIVATED = "CONTRACT_ACTIVATED"
    PILOT_APPROVED = "PILOT_APPROVED"
    PLAN_CHANGED = "PLAN_CHANGED"
    ORGANIZATION_TRANSFER = "ORGANIZATION_TRANSFER"
    #: System code: written when a new grant supersedes a previous one.
    REPLACED = "REPLACED"


class EntitlementRevokeReason(enum.StrEnum):
    """§8.1.2, ENT-02, plus the two system codes §8.1.2 lists separately."""

    CONTRACT_SUSPENDED = "CONTRACT_SUSPENDED"
    CONTRACT_ENDED = "CONTRACT_ENDED"
    PILOT_ENDED = "PILOT_ENDED"
    PLAN_CHANGED = "PLAN_CHANGED"
    ORGANIZATION_TRANSFER = "ORGANIZATION_TRANSFER"
    SECURITY_RESTRICTION = "SECURITY_RESTRICTION"
    #: System codes, never chosen by a client.
    REPLACED = "REPLACED"
    ENTITLEMENT_EXPIRED = "ENTITLEMENT_EXPIRED"


#: What an ENT-02 caller may say. The two system codes are excluded: a revoke
#: that claims to be a replacement, without a replacement existing, is a lie the
#: audit trail would carry forever.
REVOCATION_REASONS = frozenset(
    {
        EntitlementRevokeReason.CONTRACT_SUSPENDED,
        EntitlementRevokeReason.CONTRACT_ENDED,
        EntitlementRevokeReason.PILOT_ENDED,
        EntitlementRevokeReason.PLAN_CHANGED,
        EntitlementRevokeReason.ORGANIZATION_TRANSFER,
        EntitlementRevokeReason.SECURITY_RESTRICTION,
    }
)
