from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.progress.enums import ProgressLevel


class ProgressNote(Base, TimestampMixin):
    """A trainer or staff member's note on one student's progress in one group
    (PRD 06). Append-only like :class:`AttendanceRecord`, a correction is a new
    note, never an edit of history, so the record stays honest.

    ``session_id`` is set when the note was written as part of taking attendance
    for a session (M2) and ``NULL`` for a standalone note (M1); either way the
    note is anchored to ``group_id`` so "notes for this person in this group" is
    always answerable without joining through scheduling.
    """

    __tablename__ = "progress_note"
    __table_args__ = (
        Index("ix_progress_note_org_person", "organization_id", "person_id"),
        Index("ix_progress_note_group", "group_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("prg"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    group_id: Mapped[str] = mapped_column(
        ForeignKey("group.id", ondelete="CASCADE"), nullable=False
    )
    author_person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("session.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[ProgressLevel | None] = mapped_column(enum_type(ProgressLevel), nullable=True)
