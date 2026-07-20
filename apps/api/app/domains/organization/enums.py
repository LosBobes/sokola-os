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
