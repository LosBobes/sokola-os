"""The inbox: at-least-once delivery becomes exactly-once effects.

What is actually being tested is the transaction boundary. The claim and the
handler's writes have to land together, so that a replay either finds the claim
and does nothing, or finds neither and safely does the work again. A claim that
survived a failed handler would silently swallow the message; effects that
survived without a claim would duplicate on replay. Both are checked.
"""

from __future__ import annotations

import datetime as dt

import pytest
from app.platform.inbox import service as inbox
from app.platform.inbox.models import InboxRecord
from app.platform.outbox import service, worker
from app.platform.outbox.enums import OutboxStatus
from app.platform.outbox.models import OutboxMessage
from sqlalchemy import select, text
from sqlalchemy.orm import Session

ORG = "org_inbox_test"


@pytest.fixture(autouse=True)
def _reset_handlers() -> None:
    worker._HANDLERS.clear()


def _enqueue(db: Session, event_type: str) -> OutboxMessage:
    message = service.enqueue(db, event_type=event_type, payload={}, organization_id=ORG)
    db.commit()
    return message


def test_delivery_records_an_inbox_claim(db: Session) -> None:
    worker.register_handler("test.claimed", lambda _db, _m: None)
    message = _enqueue(db, "test.claimed")

    worker.process_available("w1")

    assert inbox.was_processed(db, consumer="test.claimed", message_id=message.id)


def test_a_replay_does_not_run_the_handler_again(db: Session) -> None:
    runs: list[str] = []
    worker.register_handler("test.replay", lambda _db, m: runs.append(m.id))
    message = _enqueue(db, "test.replay")

    worker.process_available("w1")
    assert runs == [message.id]

    # Put the message back as if the worker had died before writing DELIVERED.
    db.execute(
        text("UPDATE outbox_message SET status = 'PENDING', locked_by = NULL WHERE id = :id"),
        {"id": message.id},
    )
    db.commit()

    worker.process_available("w2")

    assert runs == [message.id], "the handler ran a second time on replay"
    db.expire_all()
    stored = db.get(OutboxMessage, message.id)
    assert stored is not None
    assert stored.status is OutboxStatus.DELIVERED


def test_a_failed_handler_leaves_no_claim_behind(db: Session) -> None:
    """Otherwise the retry would find a claim and skip work that never happened."""

    def boom(_db: Session, _message: OutboxMessage) -> None:
        raise RuntimeError("provider down")

    worker.register_handler("test.failing", boom)
    message = _enqueue(db, "test.failing")

    worker.process_available("w1")

    db.expire_all()
    assert not inbox.was_processed(db, consumer="test.failing", message_id=message.id)
    stored = db.get(OutboxMessage, message.id)
    assert stored is not None
    assert stored.status is OutboxStatus.FAILED


def test_a_failed_handler_rolls_back_its_own_writes(db: Session) -> None:
    """The handler's partial work must not commit alongside the failure record."""

    def write_then_fail(session: Session, message: OutboxMessage) -> None:
        session.add(
            InboxRecord(
                consumer="side-effect",
                message_id=message.id,
                organization_id=ORG,
                event_type="marker",
                processed_at=dt.datetime.now(tz=dt.UTC),
            )
        )
        session.flush()
        raise RuntimeError("fails after writing")

    worker.register_handler("test.partial", write_then_fail)
    message = _enqueue(db, "test.partial")

    worker.process_available("w1")

    db.expire_all()
    leftover = db.execute(
        select(InboxRecord).where(InboxRecord.consumer == "side-effect")
    ).scalars().all()
    assert leftover == [], "a failed handler's writes were committed"
    stored = db.get(OutboxMessage, message.id)
    assert stored is not None
    assert stored.status is OutboxStatus.FAILED
    assert stored.attempts == 1


def test_claims_are_per_consumer(db: Session) -> None:
    """A second consumer on the same message is not a replay of the first."""
    message = _enqueue(db, "test.fanout")

    assert inbox.claim(db, consumer="consumer-a", message=message) is True
    assert inbox.claim(db, consumer="consumer-b", message=message) is True
    assert inbox.claim(db, consumer="consumer-a", message=message) is False
    db.commit()

    assert inbox.was_processed(db, consumer="consumer-a", message_id=message.id)
    assert inbox.was_processed(db, consumer="consumer-b", message_id=message.id)


def test_a_losing_claim_leaves_the_transaction_usable(db: Session) -> None:
    """The savepoint is the point: a duplicate claim must not poison the caller's
    transaction, or the business writes around it would be lost too."""
    message = _enqueue(db, "test.savepoint")

    assert inbox.claim(db, consumer="c", message=message) is True
    db.commit()

    assert inbox.claim(db, consumer="c", message=message) is False
    # The session still works after the unique violation.
    still_usable = db.execute(select(InboxRecord.consumer)).scalars().all()
    assert "c" in still_usable
    db.commit()


def test_an_unregistered_event_type_is_not_claimed(db: Session) -> None:
    """Nothing handled it, so a later handler must still get the chance."""
    message = _enqueue(db, "test.unhandled")

    worker.process_available("w1")

    assert not inbox.was_processed(db, consumer="test.unhandled", message_id=message.id)
    db.expire_all()
    stored = db.get(OutboxMessage, message.id)
    assert stored is not None
    assert stored.status is OutboxStatus.DELIVERED


def test_a_custom_consumer_name_keys_the_claim(db: Session) -> None:
    worker.register_handler("test.named", lambda _db, _m: None, consumer="notifications")
    message = _enqueue(db, "test.named")

    worker.process_available("w1")

    assert inbox.was_processed(db, consumer="notifications", message_id=message.id)
    assert not inbox.was_processed(db, consumer="test.named", message_id=message.id)
