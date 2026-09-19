"""M07 enums: proven relationships between adults and children.

A guardian link is a *school's verification*, not a fact about two people. Two
schools can reach different conclusions about the same pair, and each keeps its
own — which is why every one of these lives next to a `school_id`.
"""

from __future__ import annotations

import enum


class RelationshipKind(enum.StrEnum):
    """§2.3. What the adult is to the child, as the school recorded it.

    Deliberately not a legal taxonomy — §1.2 says M07 "ne predstavlja pravno
    utvrđivanje starateljstva", it records a school's check and an operational
    right of access.
    """

    PARENT = "PARENT"
    LEGAL_GUARDIAN = "LEGAL_GUARDIAN"
    #: Someone the school has verified may collect and be contacted about the
    #: child without being a parent or legal guardian.
    AUTHORIZED_CAREGIVER = "AUTHORIZED_CAREGIVER"
    OTHER_VERIFIED = "OTHER_VERIFIED"


class LinkStatus(enum.StrEnum):
    """§2.3, §5.3. The lifecycle of one school's verification.

    `REJECTED` and `REVOKED` are terminal: §5.3 says a fresh check is a new
    row with a new id, never a revived one. That is what keeps the history
    honest — "this link was revoked in March and a new one approved in June"
    is two rows, not one row that changed its mind.
    """

    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"


class FamilyStatus(enum.StrEnum):
    """§2.1, §5.1. `ARCHIVED` is terminal in H0 — a family that re-forms is a
    new id, not a revived row.

    That matters more here than it looks: a `Family` is a grouping a school
    recorded at a moment, and §3.1 says nothing is derived from it. Reviving
    one would silently reattach whatever the school archived it away from.
    """

    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class MemberKind(enum.StrEnum):
    """§2.2. What someone is *in this family grouping*, and nothing else.

    The contract is explicit that this "nije role/permission". It does not
    decide what anyone may see or do — M05 does that, and M07's guardian link
    decides which adult may act for which child. An `ADULT` in a family holds
    no right over a `DEPENDENT` in the same family by virtue of the grouping.
    """

    ADULT = "ADULT"
    DEPENDENT = "DEPENDENT"


class FamilyMembershipStatus(enum.StrEnum):
    """§2.2, §5.2. `ENDED` is terminal; coming back is a new row.

    Named in full rather than `MembershipStatus`, which M06 already uses for a
    school membership. The two are genuinely different facts — one is whether
    the school has this person on its books, the other whether the school
    groups them into this household — and a file that imported both under one
    name would make mixing them up the easy mistake.
    """

    ACTIVE = "ACTIVE"
    ENDED = "ENDED"


#: The membership type each side of a guardian link must hold (§2.3). Stored on
#: the row and pinned by a CHECK so the composite foreign key can require it:
#: without the type in the key, a guardian link could name the same person's
#: STAFF membership and read as valid.
GUARDIAN_MEMBERSHIP_TYPE = "GUARDIAN"
CHILD_MEMBERSHIP_TYPE = "PARTICIPANT"
