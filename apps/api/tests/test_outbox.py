from __future__ import annotations

import pytest
from app.platform.outbox import service, worker
from app.platform.outbox.enums import OutboxStatus
from app.platform.outbox.models import OutboxMessage
from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def _reset_handlers() -> None:
    worker._HANDLERS.clear()


def test_enqueued_event_is_delivered(db: Session) -> None:
    seen: list[str] = []
    worker.register_handler("test.delivered", lambda _db, m: seen.append(m.id))

    msg = service.enqueue(
        db, event_type="test.delivered", payload={"a": 1}, school_id="org_1"
    )
    db.commit()

    handled = worker.process_available("w1")

    assert handled == 1
    assert seen == [msg.id]
    db.expire_all()
    stored = db.get(OutboxMessage, msg.id)
    assert stored is not None
    assert stored.status is OutboxStatus.DELIVERED


def test_failing_handler_dead_letters_after_max_attempts(db: Session) -> None:
    def boom(_db: Session, _message: OutboxMessage) -> None:
        raise RuntimeError("provider down")

    worker.register_handler("test.fail", boom)

    msg = service.enqueue(db, event_type="test.fail", payload={}, school_id="org_1")
    msg.max_attempts = 1
    db.commit()

    worker.process_available("w1")

    db.expire_all()
    stored = db.get(OutboxMessage, msg.id)
    assert stored is not None
    assert stored.status is OutboxStatus.DEAD_LETTER
    assert stored.attempts == 1
    assert stored.last_error is not None


def test_transient_failure_reschedules_before_dead_letter(db: Session) -> None:
    def boom(_db: Session, _message: OutboxMessage) -> None:
        raise RuntimeError("temporary")

    worker.register_handler("test.retry", boom)

    msg = service.enqueue(db, event_type="test.retry", payload={}, school_id="org_1")
    msg.max_attempts = 5
    db.commit()

    worker.process_available("w1")

    db.expire_all()
    stored = db.get(OutboxMessage, msg.id)
    assert stored is not None
    assert stored.status is OutboxStatus.FAILED
    assert stored.attempts == 1
    # Backed off into the future, so a second immediate poll does not re-claim it.
    assert worker.process_available("w1") == 0
