from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.ids import new_id


class InboxRecord(Base, TimestampMixin):
    """Proof that one consumer has already handled one outbox message.

    Delivery is at-least-once: a handler can succeed and the process die before
    the status is written, and the next worker will replay the message. The
    record is written in the *same transaction* as the handler's effects, so
    either both land or neither does, and the replay finds the record and stops.

    Keyed per consumer, not per message, so that fanning a message out to a
    second consumer later does not look like a replay of the first.
    """

    __tablename__ = "inbox_record"
    __table_args__ = (
        UniqueConstraint("consumer", "message_id", name="uq_inbox_consumer_message"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("inb"))
    consumer: Mapped[str] = mapped_column(String(120), nullable=False)
    message_id: Mapped[str] = mapped_column(String(64), nullable=False)

    # Carried for operator queries ("what did this school's consumers do?"); the
    # uniqueness that makes the record useful is on (consumer, message_id) alone.
    organization_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    processed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
