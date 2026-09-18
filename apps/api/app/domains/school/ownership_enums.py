"""Ownership designations (M04 §2.6–2.7).

Kept out of ``school/enums.py`` so the anchor's vocabulary and ownership's stay
separable: the anchor says what a school *is*, this says who answers for it.
"""

from __future__ import annotations

import enum


class OwnerNominationKind(enum.StrEnum):
    """§2.6. Which question the nomination answers.

    The distinction is not cosmetic. An ``INITIAL_PRIMARY_OWNER`` acceptance
    creates the school's first primary term; an ``ADDITIONAL_OWNER`` acceptance
    adds an OWNER role and explicitly does **not** touch who is primary (§3.4.4).
    """

    INITIAL_PRIMARY_OWNER = "INITIAL_PRIMARY_OWNER"
    ADDITIONAL_OWNER = "ADDITIONAL_OWNER"


class OwnerNominationStatus(enum.StrEnum):
    """``FULFILLED`` and ``CANCELLED`` are both terminal (§2.6).

    An expired or revoked invitation is neither: it leaves the nomination
    ``PENDING`` so a new invitation can be issued against the same intent. A
    nomination that died with its invitation would make "we invited the wrong
    person" and "the email bounced" the same event.
    """

    PENDING = "PENDING"
    FULFILLED = "FULFILLED"
    CANCELLED = "CANCELLED"


class OwnerNominationCancelReason(enum.StrEnum):
    """§8.1.2, OWN-02. Closed registry."""

    WRONG_PERSON = "WRONG_PERSON"
    REQUEST_WITHDRAWN = "REQUEST_WITHDRAWN"
    SCHOOL_PROVISIONING_CANCELLED = "SCHOOL_PROVISIONING_CANCELLED"


class PrimaryOwnerTermReason(enum.StrEnum):
    """§2.7 ``reason_code``.

    ``INITIAL_OWNER_ACCEPTED`` is a system code written by the acceptance path.
    ``PLATFORM_LEGAL_OVERRIDE`` additionally requires a ``case_reference``
    (§3.4.7): a platform actor taking ownership away from someone has to leave
    the evidence behind, under their own identity and not a borrowed session.
    """

    INITIAL_OWNER_ACCEPTED = "INITIAL_OWNER_ACCEPTED"
    OWNER_TRANSFER = "OWNER_TRANSFER"
    PLATFORM_LEGAL_OVERRIDE = "PLATFORM_LEGAL_OVERRIDE"


#: §8.1.2, OWN-04. What a *person-initiated* transfer may say. The platform
#: override reason is deliberately not in this set: it is not something the
#: current owner can claim about their own transfer.
TRANSFER_REASONS = frozenset(
    {
        PrimaryOwnerTermReason.OWNER_TRANSFER,
        PrimaryOwnerTermReason.PLATFORM_LEGAL_OVERRIDE,
    }
)
