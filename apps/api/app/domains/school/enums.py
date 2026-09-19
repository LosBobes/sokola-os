from __future__ import annotations

import enum


class SchoolType(enum.StrEnum):
    SCHOOL = "SCHOOL"
    SPORTS_CLUB = "SPORTS_CLUB"
    DANCE_SCHOOL = "DANCE_SCHOOL"
    COURSE_PROVIDER = "COURSE_PROVIDER"
    EVENT_ORGANIZER = "EVENT_ORGANIZER"
    BUSINESS = "BUSINESS"
    OTHER = "OTHER"


class MembershipType(enum.StrEnum):
    """M06 §2.3. What a person *is* to the school, independent of whether they
    can sign in.

    A school's headline "aktivni članovi" figure must count enrolled
    participants and nobody else, so an owner, a coach, a parent and an
    emergency contact all belong to the tenant without inflating it. That is
    what this field separates; :class:`app.domains.identity.enums.RoleCode`
    answers a different question (what may this account *do*), and many people
    here have no account at all.

    §3.2: one person may hold several of these in one school — a parent who
    also coaches is both — and holding any of them in one school carries no
    right in another.
    """

    #: Polaznik / član, the only type counted as an active member.
    PARTICIPANT = "PARTICIPANT"
    #: Roditelj / staratelj.
    GUARDIAN = "GUARDIAN"
    #: Trener, nastavnik, asistent, administracija.
    STAFF = "STAFF"
    #: Kontakt osoba (no participation, no account).
    CONTACT = "CONTACT"


class MembershipStatus(enum.StrEnum):
    """M06 §2.3, §5.1.

    ``DRAFT`` exists so a membership can be prepared before it takes effect;
    §5.1 lets it be terminated straight from there, which is how you abandon a
    membership you never activated without pretending it was once real.

    ``TERMINATED`` is terminal. Coming back is a **new episode** — a new row —
    never a revived one: reusing the row would overwrite when the person was
    previously a member, and that history is what ``is_first_activation`` and
    every retrospective count depend on.
    """

    #: Prepared, not yet in effect.
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    #: Temporarily inactive. §3.8: immediately ineffective for M03/M05, even if
    #: an invalidation event is late.
    SUSPENDED = "SUSPENDED"
    TERMINATED = "TERMINATED"


class MembershipPeriodStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"


class SchoolStatus(enum.StrEnum):
    """M04 §2.2. The school's single lifecycle axis.

    This replaces the pair this repo used to carry — ``lifecycle_status``
    (IN_PREPARATION/ACTIVE) alongside ``record_status`` (ACTIVE/ARCHIVED as the
    deactivation switch). Two fields answering one question is how a guard ends
    up checking the wrong one and reading correct; §5.2 defines a single
    transition table, so there is a single column.

    The authority is :class:`app.domains.school.models.SchoolStatusTransition`,
    which is append-only. This column is its current projection, maintained in
    the same transaction as the transition that moved it.
    """

    #: „U pripremi”. Created, not yet operating. Structure setup and the owner
    #: invitation happen here; ordinary invitations are blocked.
    IN_PREPARATION = "IN_PREPARATION"
    ACTIVE = "ACTIVE"
    #: Platform-only, and reversible only through SCH-06. A deactivated school
    #: never returns to IN_PREPARATION (§5.2): unfinished is not a state you
    #: can be demoted back into.
    DEACTIVATED = "DEACTIVATED"


class SchoolKind(enum.StrEnum):
    """§2.2. What kind of organization the school is.

    Distinct from the older :class:`SchoolType`, which this repo uses for the
    same idea with a coarser list; the two are reconciled in the M04 migration.
    """

    PRIVATE_SCHOOL = "PRIVATE_SCHOOL"
    SPORTS_CLUB_ACADEMY = "SPORTS_CLUB_ACADEMY"
    DANCE_SCHOOL_STUDIO = "DANCE_SCHOOL_STUDIO"
    MUSIC_SCHOOL = "MUSIC_SCHOOL"
    ART_DRAMA_SCHOOL = "ART_DRAMA_SCHOOL"
    EDUCATION_LANGUAGE_CENTER = "EDUCATION_LANGUAGE_CENTER"
    ACTIVITY_WORKSHOP_CENTER = "ACTIVITY_WORKSHOP_CENTER"
    #: Requires ``school_kind_other_label``; the CHECK enforces the iff.
    OTHER = "OTHER"


class LocatorKind(enum.StrEnum):
    """§2.4. A locator is for navigation and branding. It is not a credential:
    knowing one creates no account, person, invitation, membership, role or
    tenant context."""

    SLUG = "SLUG"
    SCHOOL_CODE = "SCHOOL_CODE"


class LocatorStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class SchoolStatusReason(enum.StrEnum):
    """§8.1.2. Closed registry for :class:`SchoolStatusTransition.reason_code`.

    The first three are system codes the client never chooses; the rest are the
    SCH-05 / SCH-06 registries, which a platform actor must pick from.
    """

    SCHOOL_CREATED = "SCHOOL_CREATED"
    INITIAL_ACTIVATION = "INITIAL_ACTIVATION"
    INITIAL_OWNER_ACCEPTED = "INITIAL_OWNER_ACCEPTED"

    # SCH-05 deactivate
    PILOT_PAUSED = "PILOT_PAUSED"
    CONTRACT_TERMINATED = "CONTRACT_TERMINATED"
    SECURITY_INCIDENT = "SECURITY_INCIDENT"
    LEGAL_REQUEST = "LEGAL_REQUEST"
    CREATED_IN_ERROR = "CREATED_IN_ERROR"
    OPERATIONAL_PAUSE = "OPERATIONAL_PAUSE"

    # SCH-06 reactivate
    PILOT_RESUMED = "PILOT_RESUMED"
    CONTRACT_RESTORED = "CONTRACT_RESTORED"
    SECURITY_REMEDIATED = "SECURITY_REMEDIATED"
    LEGAL_RESTRICTION_LIFTED = "LEGAL_RESTRICTION_LIFTED"
    OPERATIONAL_RESUME = "OPERATIONAL_RESUME"


#: Which reasons each command may carry. A deactivation reading
#: ``PILOT_RESUMED`` is the kind of thing that only ever shows up in an audit
#: export months later, so the command rejects it at the boundary.
DEACTIVATION_REASONS = frozenset(
    {
        SchoolStatusReason.PILOT_PAUSED,
        SchoolStatusReason.CONTRACT_TERMINATED,
        SchoolStatusReason.SECURITY_INCIDENT,
        SchoolStatusReason.LEGAL_REQUEST,
        SchoolStatusReason.CREATED_IN_ERROR,
        SchoolStatusReason.OPERATIONAL_PAUSE,
    }
)
REACTIVATION_REASONS = frozenset(
    {
        SchoolStatusReason.PILOT_RESUMED,
        SchoolStatusReason.CONTRACT_RESTORED,
        SchoolStatusReason.SECURITY_REMEDIATED,
        SchoolStatusReason.LEGAL_RESTRICTION_LIFTED,
        SchoolStatusReason.OPERATIONAL_RESUME,
    }
)

#: §5.2, the whole table. Anything not listed here is
#: ``SCHOOL_STATUS_TRANSITION_INVALID``; note what is deliberately absent:
#: IN_PREPARATION -> DEACTIVATED (an unfinished school is cancelled, not
#: deactivated) and DEACTIVATED -> IN_PREPARATION.
ALLOWED_STATUS_TRANSITIONS: frozenset[tuple[SchoolStatus, SchoolStatus]] = frozenset(
    {
        (SchoolStatus.IN_PREPARATION, SchoolStatus.ACTIVE),
        (SchoolStatus.ACTIVE, SchoolStatus.DEACTIVATED),
        (SchoolStatus.DEACTIVATED, SchoolStatus.ACTIVE),
    }
)


#: How the coarse :class:`SchoolType` this repo already carried maps onto M04's
#: finer :class:`SchoolKind`. Every source value is covered, and the two that
#: have no faithful counterpart land on ``OTHER`` *with a label* rather than
#: being assigned a kind they are not — which also keeps the §2.2 "OTHER iff
#: label" CHECK satisfiable by construction.
#:
#: The M04 migration carries its own copy of this table on purpose: a migration
#: is pinned history, and importing this one would silently change what an
#: already-applied migration did if this table is ever edited.
TYPE_TO_KIND: dict[SchoolType, tuple[SchoolKind, str | None]] = {
    SchoolType.SCHOOL: (SchoolKind.PRIVATE_SCHOOL, None),
    SchoolType.SPORTS_CLUB: (SchoolKind.SPORTS_CLUB_ACADEMY, None),
    SchoolType.DANCE_SCHOOL: (SchoolKind.DANCE_SCHOOL_STUDIO, None),
    SchoolType.COURSE_PROVIDER: (SchoolKind.EDUCATION_LANGUAGE_CENTER, None),
    SchoolType.EVENT_ORGANIZER: (SchoolKind.OTHER, "Organizator događaja"),
    SchoolType.BUSINESS: (SchoolKind.OTHER, "Preduzeće"),
    SchoolType.OTHER: (SchoolKind.OTHER, "Ostalo"),
}


#: §5.1, the whole table. Anything not listed is refused; note especially that
#: nothing leaves ``TERMINATED``.
ALLOWED_MEMBERSHIP_TRANSITIONS: frozenset[tuple[MembershipStatus, MembershipStatus]] = (
    frozenset(
        {
            (MembershipStatus.DRAFT, MembershipStatus.ACTIVE),
            (MembershipStatus.DRAFT, MembershipStatus.TERMINATED),
            (MembershipStatus.ACTIVE, MembershipStatus.SUSPENDED),
            (MembershipStatus.ACTIVE, MembershipStatus.TERMINATED),
            (MembershipStatus.SUSPENDED, MembershipStatus.ACTIVE),
            (MembershipStatus.SUSPENDED, MembershipStatus.TERMINATED),
        }
    )
)
