"""Inbox port: the consumer half of the transactional outbox.

The outbox guarantees a message is delivered *at least* once. The inbox is what
turns that into "exactly once" for the effects that matter: a consumer claims a
message before doing its work, in the same transaction as the work, so a replay
either sees the claim and stops, or rolls back with the work and retries.
"""

from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.platform import clock
from app.platform.inbox.models import InboxRecord
from app.platform.outbox.models import OutboxMessage


def claim(session: Session, *, consumer: str, message: OutboxMessage) -> bool:
    """Claim ``message`` for ``consumer``; ``False`` if it was already handled.

    The insert runs inside a savepoint so that losing the race (or replaying)
    leaves the caller's transaction usable instead of poisoned: without it, the
    unique violation would force the whole transaction to roll back, taking the
    business effects with it.
    """
    record = InboxRecord(
        consumer=consumer,
        message_id=message.id,
        school_id=message.school_id,
        event_type=message.event_type,
        processed_at=clock.now(),
    )
    try:
        with session.begin_nested():
            session.add(record)
            session.flush()
    except IntegrityError:
        return False
    return True


def was_processed(session: Session, *, consumer: str, message_id: str) -> bool:
    """Whether ``consumer`` already handled ``message_id``. For operators/tests."""
    return (
        session.query(InboxRecord)
        .filter(InboxRecord.consumer == consumer, InboxRecord.message_id == message_id)
        .first()
        is not None
    )
