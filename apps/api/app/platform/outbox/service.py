"""Transactional outbox: enqueue events, and claim/deliver them from a worker."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.platform.outbox.enums import OutboxStatus
from app.platform.outbox.models import OutboxMessage

# Transient failures back off; a claimed message whose lease is older than this is
# considered abandoned and may be re-claimed by another worker.
LEASE_SECONDS = 60
_BACKOFF_BASE_SECONDS = 5


def enqueue(
    session: Session,
    *,
    event_type: str,
    payload: dict[str, Any],
    organization_id: str | None = None,
    event_version: int = 1,
) -> OutboxMessage:
    """Add an event to the current transaction. The caller commits it together
    with the business change, never separately."""
    message = OutboxMessage(
        organization_id=organization_id,
        event_type=event_type,
        event_version=event_version,
        payload=payload,
    )
    session.add(message)
    return message


def _now() -> dt.datetime:
    return dt.datetime.now(tz=dt.UTC)


def claim_batch(session: Session, *, worker_id: str, limit: int = 20) -> list[OutboxMessage]:
    """Claim a batch of deliverable messages with ``FOR UPDATE SKIP LOCKED``.

    Deliverable = PENDING/FAILED past ``available_at``, or PROCESSING whose lease
    has expired (stale-lease takeover). Rows are locked so concurrent workers
    never claim the same message.
    """
    now = _now()
    lease_cutoff = now - dt.timedelta(seconds=LEASE_SECONDS)
    stmt = (
        select(OutboxMessage)
        .where(
            OutboxMessage.status.in_(
                [OutboxStatus.PENDING, OutboxStatus.FAILED, OutboxStatus.PROCESSING]
            ),
            OutboxMessage.available_at <= now,
        )
        .where(
            (OutboxMessage.status != OutboxStatus.PROCESSING)
            | (OutboxMessage.locked_at < lease_cutoff)
        )
        .order_by(OutboxMessage.seq)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    messages = list(session.execute(stmt).scalars().all())
    for message in messages:
        message.status = OutboxStatus.PROCESSING
        message.locked_by = worker_id
        message.locked_at = now
    session.flush()
    return messages


def mark_delivered(session: Session, message: OutboxMessage) -> None:
    message.status = OutboxStatus.DELIVERED
    message.locked_by = None
    message.locked_at = None
    message.last_error = None


def mark_failed(session: Session, message: OutboxMessage, error: str) -> None:
    """Record a transient failure; dead-letter once attempts are exhausted."""
    message.attempts += 1
    message.last_error = error[:2000]
    message.locked_by = None
    message.locked_at = None
    if message.attempts >= message.max_attempts:
        message.status = OutboxStatus.DEAD_LETTER
        return
    message.status = OutboxStatus.FAILED
    backoff = _BACKOFF_BASE_SECONDS * (2 ** min(message.attempts, 10))
    message.available_at = _now() + dt.timedelta(seconds=backoff)
