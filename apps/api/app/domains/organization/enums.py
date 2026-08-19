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


class OrgMemberType(enum.StrEnum):
    """What a person *is* to the school, independent of whether they can sign in.

    A school's headline "aktivni članovi" figure must count enrolled
    participants and nobody else, so an owner, a coach, a parent and an
    emergency contact all belong to the tenant without inflating it. That is
    what this field separates; :class:`app.domains.identity.enums.RoleCode`
    answers a different question (what may this account *do*), and many people
    here have no account at all.

    ``ATTENDEE`` is the default and the backfill value for pre-existing rows,
    except for people who already hold a staff role assignment.
    """

    #: Polaznik / član , the only type counted as an active member.
    ATTENDEE = "ATTENDEE"
    #: Trener, nastavnik, asistent, administracija.
    STAFF = "STAFF"
    #: Roditelj / staratelj.
    GUARDIAN = "GUARDIAN"
    #: Kontakt osoba (no participation, no account).
    CONTACT = "CONTACT"


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
    ``record_status`` (which is the soft-delete/deactivation axis, §31).

    A school created through ``POST /organizations`` starts ``IN_PREPARATION``
    ("u pripremi"): the owner may set up structure and invite a co-owner, but
    normal STAFF/PARENT/STUDENT invitations are blocked until ``ACTIVE`` (see
    ``app.domains.identity.policy.ensure_invitation_allowed_during_onboarding``).
    Legacy/seed rows default to ``ACTIVE`` so behaviour outside the real
    signup path is unchanged.
    """

    IN_PREPARATION = "IN_PREPARATION"
    ACTIVE = "ACTIVE"
