from __future__ import annotations

import enum


class GroupCapacityMode(enum.StrEnum):
    UNLIMITED = "UNLIMITED"
    LIMITED = "LIMITED"


class GroupMembershipEndReason(enum.StrEnum):
    LEFT = "LEFT"
    MOVED = "MOVED"
    REMOVED = "REMOVED"
    SEASON_END = "SEASON_END"


class GroupMembershipStatus(enum.StrEnum):
    """Mirrors :class:`app.domains.organization.enums.MembershipStatus` at group
    scope. ``ENDED`` is terminal, re-joining creates a brand-new membership row,
    never a revived one (the unique constraint on ``(group_id, person_id)`` would
    otherwise collide with history)."""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ENDED = "ENDED"


class GroupMemberRole(enum.StrEnum):
    """Why a person is attached to a group.

    Attaching a trainer to a group is not the same act as enrolling a child in
    it, and conflating the two is what makes staff show up on attendance sheets
    and membership invoices. Only :attr:`MEMBER` is a *polaznik*: the attendance
    roster and every billing run filter to it, so staff are never charged a
    membership fee nor counted as members.

    ``MEMBER`` is the default, which is what every row created before this enum
    existed is backfilled to (those rosters were participants by construction:
    they were already being billed and marked present).
    """

    MEMBER = "MEMBER"
    TRAINER = "TRAINER"
    ASSISTANT = "ASSISTANT"
    OTHER_STAFF = "OTHER_STAFF"
