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
