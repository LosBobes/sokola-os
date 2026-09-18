from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.common.base import Base, TimestampMixin
from app.common.columns import enum_type
from app.common.ids import new_id
from app.platform.outbox.enums import DeadLetterAction, DeadLetterReviewStatus, OutboxStatus


class OutboxMessage(Base, TimestampMixin):
    """A domain event written in the same transaction as the business change.

    A worker delivers it *after* commit. Side effects (email, read-model rebuild,
    partner calls) never ride inside the primary business transaction.
    """

    __tablename__ = "outbox_message"
    __table_args__ = (
        Index("ix_outbox_claimable", "status", "available_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("obx"))
    organization_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    status: Mapped[OutboxStatus] = mapped_column(
        enum_type(OutboxStatus), nullable=False, default=OutboxStatus.PENDING
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    available_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # Monotonic sequence for stable FIFO ordering of same-instant events.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), unique=True, nullable=False)

    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class DeadLetterReview(Base, TimestampMixin):
    """A request to replay or discard a dead-lettered message, and its approval.

    Dual control (M21): whoever asks for a dead-lettered event to be replayed or
    abandoned cannot be the one who approves it. A dead-lettered message is, by
    definition, one where automated handling has already failed, so the decision
    to re-fire it (a duplicate side effect) or drop it (a lost one) is exactly
    the kind that should not rest with one person.

    The record is kept after the fact: it is the evidence of who asked, who
    agreed, and why.
    """

    __tablename__ = "outbox_dead_letter_review"
    __table_args__ = (
        # One open request per message: a second one would let two approvers
        # apply two different actions to the same message.
        Index(
            "uq_dead_letter_open_review",
            "message_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("dlr"))
    message_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("outbox_message.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    action: Mapped[DeadLetterAction] = mapped_column(enum_type(DeadLetterAction), nullable=False)
    status: Mapped[DeadLetterReviewStatus] = mapped_column(
        enum_type(DeadLetterReviewStatus), nullable=False, default=DeadLetterReviewStatus.PENDING
    )

    requested_by_person_id: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    request_reason: Mapped[str] = mapped_column(Text, nullable=False)

    decided_by_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
