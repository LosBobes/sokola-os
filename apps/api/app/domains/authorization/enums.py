"""M05 authorization registry enums (§2.2–2.4).

Everything here describes *policy*, not a person's access. A revision is a
published catalogue of what permissions exist and which roles hold them; who
holds a role is M05 §2.5's `RoleAssignment`, which this repo already has.
"""

from __future__ import annotations

import enum


class PolicyRevisionStatus(enum.StrEnum):
    """§2.2. Exactly one revision is `ACTIVE`, and a published one is
    immutable — a correction is a new revision, never an edit."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REJECTED = "REJECTED"


class PolicyChangeReason(enum.StrEnum):
    """§2.2's closed reason registry for why a revision exists."""

    INITIAL_PUBLICATION = "INITIAL_PUBLICATION"
    PERMISSION_ADDED = "PERMISSION_ADDED"
    BINDING_CHANGED = "BINDING_CHANGED"
    SECURITY_CORRECTION = "SECURITY_CORRECTION"
    MODULE_ONBOARDING = "MODULE_ONBOARDING"


class AuthorizationDomainStatus(enum.StrEnum):
    """§2.2.1. `RESERVED` and `RETIRED` are both deny.

    A reserved domain is one the contract names but no module owns yet; it
    must carry no active role, permission, binding or assignment.
    """

    ACTIVE = "ACTIVE"
    RESERVED = "RESERVED"
    RETIRED = "RETIRED"


class RiskLevel(enum.StrEnum):
    """§2.3. `HIGH` and `CRITICAL` always require step-up."""

    LOW = "LOW"
    ELEVATED = "ELEVATED"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DelegationClass(enum.StrEnum):
    """§2.3. Whether a permission can be handed on by a direct grant at all,
    and the anti-escalation rule that goes with it (§3.2 point 8)."""

    #: Only a role binding may carry it. No direct grant, ever.
    ROLE_ONLY = "ROLE_ONLY"
    DIRECT_DELEGABLE = "DIRECT_DELEGABLE"
    #: Server-internal; never reachable from a request.
    INTERNAL_ONLY = "INTERNAL_ONLY"
    NON_DELEGABLE = "NON_DELEGABLE"


class OfflinePolicy(enum.StrEnum):
    """§2.3. Default `DENY`: an offline client proves nothing about freshness,
    so a permission is unavailable offline unless it says otherwise."""

    DENY = "DENY"
    READ_CACHE_ALLOWED = "READ_CACHE_ALLOWED"
    QUEUE_ALLOWED = "QUEUE_ALLOWED"


class ChildDataClass(enum.StrEnum):
    """§2.3. How much a permission can expose about a child, so masking and
    retention rules have something to read rather than guessing from the key."""

    NONE = "NONE"
    IDENTIFIER_ONLY = "IDENTIFIER_ONLY"
    ROSTER_MINIMAL = "ROSTER_MINIMAL"
    STANDARD_CHILD = "STANDARD_CHILD"
    SPECIAL_CATEGORY = "SPECIAL_CATEGORY"


class PermissionStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class AssignmentPolicy(enum.StrEnum):
    """§2.4. Who may hand out a role — fixed per role key in H0, and not
    derivable from administrative rank, which grants nothing by itself."""

    M04_M02_ONLY = "M04_M02_ONLY"
    OWNER_MANAGED = "OWNER_MANAGED"
    OWNER_OR_MANAGER_MANAGED = "OWNER_OR_MANAGER_MANAGED"
    M07_ONLY = "M07_ONLY"
    PLATFORM_SECURITY_MANAGED = "PLATFORM_SECURITY_MANAGED"
    OWNER_MODULE_MANAGED = "OWNER_MODULE_MANAGED"


class RoleDefinitionStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


#: §2.2.1. The four domain keys, as *values* rather than a closed database
#: enum: the contract says in so many words that the physical store "ne sme
#: koristiti zatvoren `SCHOOL|PLATFORM` enum koji zahteva prepisivanje
#: postojećih redova da bi se bezbedno dodao novi domen".
DOMAIN_SCHOOL = "SCHOOL"
DOMAIN_PLATFORM = "PLATFORM"
DOMAIN_EVENT_ORGANIZER_WORKSPACE = "EVENT_ORGANIZER_WORKSPACE"
DOMAIN_VENUE_OPERATOR_WORKSPACE = "VENUE_OPERATOR_WORKSPACE"
