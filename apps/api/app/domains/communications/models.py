from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.communications.enums import AnnouncementStatus, AnnouncementTargetType


class Announcement(Base, TimestampMixin):
    """A published message to a snapshotted set of recipients. Publish succeeds
    only if the recipient snapshot still matches what the author reviewed."""

    __tablename__ = "announcement"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("ann"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[AnnouncementTargetType] = mapped_column(
        enum_type(AnnouncementTargetType), nullable=False
    )
    target_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[AnnouncementStatus] = mapped_column(
        enum_type(AnnouncementStatus), nullable=False, default=AnnouncementStatus.PUBLISHED
    )
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    published_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AnnouncementRecipient(Base, TimestampMixin):
    """A snapshotted recipient at publish time (the delivery ledger)."""

    __tablename__ = "announcement_recipient"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("arc"))
    announcement_id: Mapped[str] = mapped_column(
        ForeignKey("announcement.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
