"""Identity & access enums.

``RoleCode`` is a **closed access-template facade**. It expresses what a person is
allowed to do inside one organization — never a profile, credential, or job-title
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


class RoleCode(enum.StrEnum):
    OWNER = "OWNER"
    MANAGER = "MANAGER"
    ADMIN = "ADMIN"
    TRAINER = "TRAINER"
    PARENT = "PARENT"
    STUDENT = "STUDENT"


class RoleScopeType(enum.StrEnum):
    ORGANIZATION = "ORGANIZATION"
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
