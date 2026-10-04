"""Identity & access enums.

``RoleCode`` is a **closed access-template facade**. It expresses what a person is
allowed to do inside one school, never a profile, credential, or job-title
taxonomy. New capabilities do not get new role codes; they get policy rules.
"""

from __future__ import annotations

import enum


class PersonIdentityStatus(enum.StrEnum):
    PROVISIONAL = "PROVISIONAL"  # created by staff, not yet claimed
    CLAIMED = "CLAIMED"  # linked to an external identity
    VERIFIED = "VERIFIED"  # identity proven
    MERGED = "MERGED"  # folded into another Person (see PersonMergeRecord)
    ARCHIVED = "ARCHIVED"


class PersonMergeStatus(enum.StrEnum):
    """Lifecycle of a duplicate-review case (§13–15).

    A case is FLAGGED at intake, then a reviewer either MERGED it (folding the
    source into the target) or DISMISSED it (the two are genuinely distinct).
    """

    FLAGGED = "FLAGGED"
    MERGED = "MERGED"
    DISMISSED = "DISMISSED"


class RoleCode(enum.StrEnum):
    OWNER = "OWNER"
    MANAGER = "MANAGER"
    ADMIN = "ADMIN"
    TRAINER = "TRAINER"
    PARENT = "PARENT"
    STUDENT = "STUDENT"


class RoleScopeType(enum.StrEnum):
    SCHOOL = "SCHOOL"
    BRANCH = "BRANCH"
    GROUP = "GROUP"


class RoleAssignmentStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


#: The statuses an assignment can still be acted on in. `REVOKED` is terminal
#: (§5.2), so it is absent — and `uq_role_assignment_open` is defined over
#: exactly this set, which is what lets a revoked row stay as history beside a
#: later grant of the same role.
OPEN_ROLE_ASSIGNMENT_STATUSES = (
    RoleAssignmentStatus.ACTIVE,
    RoleAssignmentStatus.SUSPENDED,
)


# ---------------------------------------------------------------------------
# M05 §2.10 — the closed reason registries for role transitions
#
# Each list is verbatim from the contract's table, which is the point: a reason
# that can be anything is a reason that cannot be aggregated, filtered or
# audited, and `RoleTransitionRequest.reason` was `str | None` with a length
# limit and nothing else (F-49). Measured before this change: suspending with
# `NIJE_IZ_VOKABULARA_XYZ` returned 200.
#
# Reactivation has its own vocabulary even though this repo reaches it through
# `POST /roles` rather than a distinct command — the codes are what §2.10 lists
# for "School role reactivate", and reusing the suspend list would let a role
# come back for a reason that only makes sense for taking it away.
# ---------------------------------------------------------------------------


class RoleSuspendReason(enum.StrEnum):
    SECURITY_REVIEW = "SECURITY_REVIEW"
    TEMPORARY_LEAVE = "TEMPORARY_LEAVE"
    ACCESS_PAUSE = "ACCESS_PAUSE"
    MEMBERSHIP_SUSPENDED = "MEMBERSHIP_SUSPENDED"


class RoleReactivateReason(enum.StrEnum):
    SECURITY_CLEARED = "SECURITY_CLEARED"
    RETURNED_TO_DUTY = "RETURNED_TO_DUTY"
    ACCESS_RESTORED = "ACCESS_RESTORED"


class RoleRevokeReason(enum.StrEnum):
    MEMBERSHIP_ENDED = "MEMBERSHIP_ENDED"
    RESPONSIBILITY_ENDED = "RESPONSIBILITY_ENDED"
    ROLE_REPLACED = "ROLE_REPLACED"
    SECURITY_REVOKE = "SECURITY_REVOKE"
    OWNER_TRANSFER = "OWNER_TRANSFER"


#: The codes §2.10 marks with `*`: a free-text note is mandatory alongside them.
#:
#: They are the ones where the code alone does not say enough for whoever reads
#: the trail later — "security review" and "access pause" describe a decision
#: someone took for a reason, and without the note the record says a decision
#: happened and not why. The unmarked codes are self-explanatory by
#: construction: `MEMBERSHIP_ENDED` means the membership ended.
REASON_NOTE_REQUIRED: frozenset[str] = frozenset(
    {
        RoleSuspendReason.SECURITY_REVIEW.value,
        RoleSuspendReason.ACCESS_PAUSE.value,
        RoleReactivateReason.SECURITY_CLEARED.value,
        RoleReactivateReason.ACCESS_RESTORED.value,
        RoleRevokeReason.SECURITY_REVOKE.value,
    }
)


class InvitationType(enum.StrEnum):
    STAFF = "STAFF"
    PARENT = "PARENT"
    STUDENT = "STUDENT"


class InvitationStatus(enum.StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    REISSUED = "REISSUED"


class PersonDedupeStatus(enum.StrEnum):
    """M06 §2.1, §5.2. Whether this Person might be someone the system already knows.

    Deliberately advisory, not an action. §3.4 is emphatic that a matching email
    or phone *never* auto-links an account or merges two people: two real people
    genuinely do share a family address, and a system that merges them has
    destroyed a person's records to save an operator one click.

    ``MERGED`` is terminal, and the only status that fills
    ``merged_into_person_id``.
    """

    #: No candidate found.
    CLEAR = "CLEAR"
    #: A candidate matched on a blind index. A flag for a human, nothing more.
    POTENTIAL_DUPLICATE = "POTENTIAL_DUPLICATE"
    #: A human looked and said these are different people. Sticky, so the same
    #: pair is not re-raised every time either record is touched.
    REVIEWED_DISTINCT = "REVIEWED_DISTINCT"
    MERGED = "MERGED"
