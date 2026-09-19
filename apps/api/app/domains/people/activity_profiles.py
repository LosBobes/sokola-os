"""Participant and staff profiles, and the merge history (M06 §2.5–2.7).

These three tables share one property worth naming: each hangs off something
else and has **no status of its own**. §5's last line says profiles follow the
membership's effectiveness, so a suspended member's participant profile is not
separately "suspended" — there is one answer to "is this person active here",
and it lives on the membership.

The composite foreign keys do the work the prose would otherwise have to be
trusted for. A participant profile references
``(school_id, school_membership_id, membership_type='PARTICIPANT')``, so a row
pointing at a STAFF membership, or at another school's membership, cannot be
written at all — §2.5 and §2.6 both require that, and §6's
``M06_PROFILE_TYPE_MISMATCH`` is what it would otherwise be caught as, later.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.people.profile_enums import (
    DisciplineCategory,
    EngagementType,
    PersonMergeReason,
)

#: §2.6. A cap, not a guess: fifty specializations is already far past what any
#: real coach carries, and an unbounded array is a denial-of-service surface.
MAX_SPECIALIZATION_CODES = 50


class ParticipantProfile(Base, TimestampMixin):
    """§2.5. What a school records about someone *as a participant*."""

    __tablename__ = "participant_profile"
    __table_args__ = (
        # The membership must be this school's *and* of type PARTICIPANT. Naming
        # the type in the key is what makes a profile on a STAFF membership
        # impossible rather than merely incorrect.
        ForeignKeyConstraint(
            ["school_id", "school_membership_id", "membership_type"],
            [
                "school_membership.school_id",
                "school_membership.id",
                "school_membership.membership_type",
            ],
            name="fk_participant_profile_membership",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "school_id", "school_membership_id", name="uq_participant_profile_membership"
        ),
        CheckConstraint(
            "membership_type = 'PARTICIPANT'", name="ck_participant_profile_type"
        ),
        CheckConstraint(
            "prior_experience_note IS NULL OR length(prior_experience_note) <= 500",
            name="ck_participant_profile_note_length",
        ),
        CheckConstraint("version >= 1", name="ck_participant_profile_version"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("pcp"))
    school_id: Mapped[str] = mapped_column(String(64), nullable=False)
    school_membership_id: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Denormalized solely so the composite FK above can pin it. Never read as
    #: the authority for anything; the membership is.
    membership_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default="PARTICIPANT"
    )
    discipline_category: Mapped[DisciplineCategory | None] = mapped_column(
        enum_type(DisciplineCategory), nullable=True
    )
    #: Tenant-local display level. Explicitly not a global standard: one
    #: school's "II grupa" means nothing in another, and §2.5 says so.
    level_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: §2.5: no health or identifying data. Free text a school controls.
    prior_experience_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: §2.5: the minimum needed to run an activity safely, encrypted at the
    #: field, and §3.12 keeps it out of the general profile response — reading
    #: it takes its own permission and its own audit entry.
    safety_note_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


class StaffProfile(Base, TimestampMixin):
    """§2.6. What a school records about someone *as staff*.

    Not an employment record: §2.6 forbids salary, bank account and national id
    here. A row that starts collecting them has become an HR system, which is a
    different product with different obligations.
    """

    __tablename__ = "staff_profile"
    __table_args__ = (
        ForeignKeyConstraint(
            ["school_id", "school_membership_id", "membership_type"],
            [
                "school_membership.school_id",
                "school_membership.id",
                "school_membership.membership_type",
            ],
            name="fk_staff_profile_membership",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "school_id", "school_membership_id", name="uq_staff_profile_membership"
        ),
        CheckConstraint("membership_type = 'STAFF'", name="ck_staff_profile_type"),
        CheckConstraint(
            f"specialization_codes IS NULL OR "
            f"array_length(specialization_codes, 1) <= {MAX_SPECIALIZATION_CODES}",
            name="ck_staff_profile_specialization_count",
        ),
        CheckConstraint(
            "qualification_note IS NULL OR length(qualification_note) <= 500",
            name="ck_staff_profile_note_length",
        ),
        CheckConstraint("version >= 1", name="ck_staff_profile_version"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("stp"))
    school_id: Mapped[str] = mapped_column(String(64), nullable=False)
    school_membership_id: Mapped[str] = mapped_column(String(64), nullable=False)
    membership_type: Mapped[str] = mapped_column(String(40), nullable=False, default="STAFF")
    engagement_type: Mapped[EngagementType | None] = mapped_column(
        enum_type(EngagementType), nullable=True
    )
    #: Sorted and deduplicated on write (§2.6), so two profiles listing the same
    #: specializations in different orders compare and read as equal.
    specialization_codes: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(64)), nullable=True
    )
    qualification_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)


class PersonMergeHistoryEntry(Base):
    """§2.7. That two people were merged, and by whom. Immutable.

    Tenant-local in H0: §3.14 refuses a merge where either side has a
    dependency in another school, so the history belongs to the school that
    performed it. No ``updated_at`` and no version — there is nothing here to
    change, and a correctable merge record would be worse than none.
    """

    __tablename__ = "person_merge_history_entry"
    __table_args__ = (
        CheckConstraint(
            "surviving_person_id <> merged_person_id", name="ck_person_merge_distinct"
        ),
        Index("ix_person_merge_history_school", "school_id", "merged_at"),
        Index("ix_person_merge_history_merged", "merged_person_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("pmh"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False
    )
    surviving_person_id: Mapped[str] = mapped_column(String(64), nullable=False)
    merged_person_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_code: Mapped[PersonMergeReason] = mapped_column(
        enum_type(PersonMergeReason), nullable=False
    )
    merged_by_account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    merged_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
