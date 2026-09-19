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


#: The membership type each side of a guardian link must hold (§2.3). Stored on
#: the row and pinned by a CHECK so the composite foreign key can require it:
#: without the type in the key, a guardian link could name the same person's
#: STAFF membership and read as valid.
GUARDIAN_MEMBERSHIP_TYPE = "GUARDIAN"
CHILD_MEMBERSHIP_TYPE = "PARTICIPANT"
