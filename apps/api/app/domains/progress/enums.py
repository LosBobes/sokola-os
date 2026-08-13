from __future__ import annotations

import enum


class ProgressLevel(enum.StrEnum):
    """A coarse, honest read on where a student is, not a graded score. Optional:
    many notes are just prose with no level attached."""

    NOVICE = "NOVICE"
    DEVELOPING = "DEVELOPING"
    PROFICIENT = "PROFICIENT"
    ADVANCED = "ADVANCED"
