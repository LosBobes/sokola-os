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
