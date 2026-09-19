"""Participant and staff profile vocabulary (M06 §2.5–2.6)."""

from __future__ import annotations

import enum


class DisciplineCategory(enum.StrEnum):
    """§2.5. A coarse grouping for a participant's activity.

    Coarse on purpose: the *real* answer is the M08 program a participant is
    enrolled in, and this is a hint for a UI that has not loaded one yet. A
    school with a finer taxonomy should not be encouraged to encode it here,
    where nothing else reads it.
    """

    SPORT = "SPORT"
    DANCE = "DANCE"
    DRAMA = "DRAMA"
    MUSIC = "MUSIC"
    EDUCATION = "EDUCATION"
    OTHER = "OTHER"


class EngagementType(enum.StrEnum):
    """§2.6. How a staff member is engaged.

    Not an employment record and not a pay grade: §2.6 forbids salary, bank
    account and national id on this row. It exists so a school can tell a
    volunteer from a contractor when scheduling, nothing more.
    """

    EMPLOYEE = "EMPLOYEE"
    CONTRACTOR = "CONTRACTOR"
    VOLUNTEER = "VOLUNTEER"
    OTHER = "OTHER"


#: §2.7. Closed registry for why two people were merged.
class PersonMergeReason(enum.StrEnum):
    DUPLICATE_DATA_ENTRY = "DUPLICATE_DATA_ENTRY"
    DUPLICATE_FROM_IMPORT = "DUPLICATE_FROM_IMPORT"
    SAME_PERSON_CONFIRMED_BY_SCHOOL = "SAME_PERSON_CONFIRMED_BY_SCHOOL"
