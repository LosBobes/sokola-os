from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.ids import new_id


class OnboardingProgress(Base, TimestampMixin):
    """Guided-setup state for one school (PRD 02 §24/§25). One row per
    school, created lazily on first read/write.

    Most steps (locations/rooms/programs/first-invite) are derived live from
    the school's own data (see ``app.domains.onboarding.service``), so
    this row only needs to remember the one fact nothing else can reconstruct:
    the moment the school left "u pripremi" and became active.
    """

    __tablename__ = "onboarding_progress"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("onb"))
    school_id: Mapped[str] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    activated_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
