from __future__ import annotations

import enum


class OutboxStatus(enum.StrEnum):
    PENDING = "PENDING"  # awaiting delivery (respect available_at)
    PROCESSING = "PROCESSING"  # claimed by a worker (respect lease)
    DELIVERED = "DELIVERED"  # handled successfully
    FAILED = "FAILED"  # transient failure, will retry
    DEAD_LETTER = "DEAD_LETTER"  # exhausted attempts, needs operator attention
    DISCARDED = "DISCARDED"  # dead-lettered and deliberately abandoned, under dual control


class DeadLetterAction(enum.StrEnum):
    """What an operator wants done with a dead-lettered message."""

    REPLAY = "REPLAY"  # put it back in the queue for another attempt
    DISCARD = "DISCARD"  # abandon it; the event will never be delivered


class DeadLetterReviewStatus(enum.StrEnum):
    PENDING = "PENDING"  # requested, awaiting a second person
    APPROVED = "APPROVED"  # approved and applied
    REJECTED = "REJECTED"  # refused by the second person
