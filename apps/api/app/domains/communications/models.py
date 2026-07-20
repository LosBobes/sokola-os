from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.domains.communications.enums import (
    AnnouncementStatus,
    AnnouncementTargetType,
    NotificationDeliveryStatus,
)


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


class Notification(Base, TimestampMixin):
    """An in-app inbox item for one person, produced by an outbox consumer
    reacting to a domain event elsewhere in the system (PRD 08 M1/M2/M3).

    ``source_message_id`` is the id of the :class:`OutboxMessage
    <app.platform.outbox.models.OutboxMessage>` that produced this row. Outbox
    delivery is at-least-once, so the (``source_message_id``, ``person_id``)
    pair is the idempotency key a handler checks before inserting — the same
    event redelivered to the same person must never duplicate their inbox item.

    See :class:`app.domains.communications.enums.NotificationDeliveryStatus`
    for what ``delivery_status`` means in the absence of a real external
    channel.
    """

    __tablename__ = "notification"
    __table_args__ = (
        UniqueConstraint(
            "source_message_id", "person_id", name="uq_notification_source_person"
        ),
        Index("ix_notification_inbox", "organization_id", "person_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("ntf"))
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organization.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="CASCADE"), nullable=False
    )
    # The outbox event_type that produced this notification, e.g. "session.cancelled".
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    # The business record this notification is about, for the client to deep-link.
    entity_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_status: Mapped[NotificationDeliveryStatus] = mapped_column(
        enum_type(NotificationDeliveryStatus),
        nullable=False,
        default=NotificationDeliveryStatus.DELIVERED,
    )
    # The outbox message that produced this row; not a hard FK (outbox rows are
    # operational/transient plumbing, not a business entity to reference).
    source_message_id: Mapped[str] = mapped_column(String(64), nullable=False)
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
