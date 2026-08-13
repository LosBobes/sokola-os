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
