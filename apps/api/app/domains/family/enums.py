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


class PayerBasisKind(enum.StrEnum):
    """§2.5. On what grounds this adult is paying for this child.

    Not a permission and not a relationship: §3.7 is emphatic that a payer link
    "ne daje pristup rasporedu, prisustvu, dokumentima, zdravlju, komunikaciji
    ili profilu deteta". The basis says why the school accepted the financial
    link, and §3.1's edge-case table uses it to separate the ordinary case —
    an adult in the child's family — from a sponsor the school verified
    separately, which is the one route by which someone outside the family may
    pay at all.
    """

    #: An adult who is in the same family grouping as the child.
    FAMILY_ADULT = "FAMILY_ADULT"
    #: §3.1: the explicit, separately verified sponsor process — the only way a
    #: payer in family A may pay for a child in family B.
    SPONSOR_VERIFIED = "SPONSOR_VERIFIED"
    OTHER_VERIFIED = "OTHER_VERIFIED"


#: The membership types a payer may hold (§2.5). Unlike the guardian link's
#: single pinned value this is a pair, because a payer need not be a guardian
#: at all — that is the whole point of the entity — and a school records a
#: non-guardian payer as a `CONTACT`.
PAYER_MEMBERSHIP_TYPES = ("CONTACT", "GUARDIAN")


class LinkKind(enum.StrEnum):
    """§2.4. Which kind of link a verification record proves.

    Two kinds rather than one table each, because the *evidence* is the same
    shape whichever link it supports — a method, a moment, an authorized
    verifier and a policy version — while what it proves is not. Keeping them
    in one table with a discriminator is what lets §5.3's "tačno jedan
    verification record" be a single partial unique index rather than an
    invariant spread over two places.
    """

    GUARDIAN_CHILD = "GUARDIAN_CHILD"
    PAYER_CHILD = "PAYER_CHILD"


class VerificationMethod(enum.StrEnum):
    """§2.4. How the school satisfied itself, recorded as a category only.

    None of these stores what was seen. §2.4 is explicit for the document case:
    "čuva se samo činjenica provere i opcioni keyed case digest; nema slike,
    broja ili običnog hash-a dokumenta u M07". A school that checked an ID
    records *that* it checked one.
    """

    #: The school already held the relationship in its own records.
    SCHOOL_RECORD = "SCHOOL_RECORD"
    #: Someone presented a document in person and a school actor looked at it.
    IN_PERSON_DOCUMENT_CHECK = "IN_PERSON_DOCUMENT_CHECK"
    SIGNED_DECLARATION = "SIGNED_DECLARATION"
    #: Carried over from a prior system by an operator-directed migration.
    MIGRATION_VERIFIED = "MIGRATION_VERIFIED"


class DesignationStatus(enum.StrEnum):
    """§2.6, §5.4. The lifecycle of "this is the one the school calls first".

    Both terminal states exist because the two ways a primacy ends mean
    different things. `SUPERSEDED` is an ordinary replacement — someone else is
    primary now — and `REVOKED` is the primacy being withdrawn with nothing put
    in its place, which §3.1 says happens the moment the underlying link is
    revoked. Collapsing them would lose the difference between "the other
    parent is primary now" and "this child currently has no primary contact",
    and §3.1 is explicit that the latter is allowed: "primarni kontakt može
    privremeno biti nula, nikad stale".
    """

    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    REVOKED = "REVOKED"


#: The membership type each side of a guardian link must hold (§2.3). Stored on
#: the row and pinned by a CHECK so the composite foreign key can require it:
#: without the type in the key, a guardian link could name the same person's
#: STAFF membership and read as valid.
GUARDIAN_MEMBERSHIP_TYPE = "GUARDIAN"
CHILD_MEMBERSHIP_TYPE = "PARTICIPANT"

#: §7.3's only FAM outbox event. The membership commands emit none: nothing
#: downstream acts on a household composition change, and an event carrying
#: who lives with whom, consumed by nobody, is a privacy cost with no buyer.
FAMILY_ARCHIVED_EVENT = "m07.family.archived"

#: §7.3's guardian-link events. The version in the payload is the link's own
#: `version`, which §2.3 calls the "authorization version" — that is the
#: invalidation signal §3.10 asks for. A tenant-wide bump would be the wrong
#: instrument: it logs out every user of the school because one family's
#: arrangement changed.
GUARDIAN_LINK_ACTIVATED_EVENT = "m07.guardian_link.activated"
GUARDIAN_LINK_REVOKED_EVENT = "m07.guardian_link.revoked"
PRIMARY_GUARDIAN_CHANGED_EVENT = "m07.primary_guardian.changed"

#: §7.3's payer-link events. `basis_kind` is deliberately absent from their
#: payloads: "this adult pays for this child because they are family" is a
#: statement about the relationship, and §4 keeps those out of events.
PAYER_LINK_ACTIVATED_EVENT = "m07.payer_link.activated"
PAYER_LINK_REVOKED_EVENT = "m07.payer_link.revoked"
PRIMARY_PAYER_CHANGED_EVENT = "m07.primary_payer.changed"
