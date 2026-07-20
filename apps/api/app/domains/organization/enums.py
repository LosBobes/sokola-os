from __future__ import annotations

import enum


class OrganizationType(enum.StrEnum):
    SCHOOL = "SCHOOL"
    SPORTS_CLUB = "SPORTS_CLUB"
    DANCE_SCHOOL = "DANCE_SCHOOL"
    COURSE_PROVIDER = "COURSE_PROVIDER"
    EVENT_ORGANIZER = "EVENT_ORGANIZER"
    BUSINESS = "BUSINESS"
    OTHER = "OTHER"


class MembershipStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    # Temporarily inactive; membership may be resumed (§20/§21).
    SUSPENDED = "SUSPENDED"
    # Terminal. Reactivation is a new membership period, never a revived row.
    ENDED = "ENDED"


class MembershipPeriodStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"


class OrganizationLifecycleStatus(enum.StrEnum):
    """Where a school is in guided onboarding (PRD 02 §24/§25), independent of
    ``record_status`` (which is the soft-delete/deactivation axis — §31).

    A school created through ``POST /organizations`` starts ``IN_PREPARATION``
    ("u pripremi"): the owner may set up structure and invite a co-owner, but
    normal STAFF/PARENT/STUDENT invitations are blocked until ``ACTIVE`` (see
    ``app.domains.identity.policy.ensure_invitation_allowed_during_onboarding``).
    Legacy/seed rows default to ``ACTIVE`` so behaviour outside the real
    signup path is unchanged.
    """

    IN_PREPARATION = "IN_PREPARATION"
    ACTIVE = "ACTIVE"
