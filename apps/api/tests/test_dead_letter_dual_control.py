"""Dead-letter dual control: one person asks, a different person decides.

A dead-lettered message is one automated delivery already gave up on, so both
ways out are lossy: replaying risks a duplicate side effect, discarding drops
the event for good. The invariant under test is that no single person can do
either, and that whichever happens leaves evidence.
"""

from __future__ import annotations

import pytest
from app.common.errors import ConflictError, ForbiddenError, NotFoundError
from app.platform.audit.models import AuditLog
from app.platform.audit.service import verify_chain
from app.platform.outbox import dead_letter, service
from app.platform.outbox.enums import (
    DeadLetterAction,
    DeadLetterReviewStatus,
    OutboxStatus,
)
from app.platform.outbox.models import OutboxMessage
from sqlalchemy import select
from sqlalchemy.orm import Session

ORG = "org_dead_letter"
ASKER = "per_asker"
APPROVER = "per_approver"


def _dead_lettered(db: Session) -> OutboxMessage:
    message = service.enqueue(db, event_type="test.dl", payload={}, organization_id=ORG)
    message.status = OutboxStatus.DEAD_LETTER
    message.attempts = 10
    message.last_error = "RuntimeError: provider down"
    db.commit()
    return message


def test_replay_needs_a_second_person(db: Session) -> None:
    message = _dead_lettered(db)
    review = dead_letter.request_review(
        db,
        message_id=message.id,
        action=DeadLetterAction.REPLAY,
        requested_by_person_id=ASKER,
        reason="Provajder je ponovo dostupan.",
    )
    db.commit()

    assert review.status is DeadLetterReviewStatus.PENDING
    db.expire_all()
    assert db.get(OutboxMessage, message.id).status is OutboxStatus.DEAD_LETTER  # type: ignore[union-attr]

    with pytest.raises(ForbiddenError, match="druga osoba"):
        dead_letter.approve(db, review_id=review.id, approver_person_id=ASKER)
    db.rollback()

    dead_letter.approve(db, review_id=review.id, approver_person_id=APPROVER)
    db.commit()

    db.expire_all()
    stored = db.get(OutboxMessage, message.id)
    assert stored is not None
    assert stored.status is OutboxStatus.PENDING
    assert stored.attempts == 0, "the retry budget starts over"
    assert stored.locked_by is None
    assert stored.last_error is not None, "why it dead-lettered is still worth keeping"


def test_an_approved_replay_is_actually_redelivered(db: Session) -> None:
    """The point of a replay is that the worker picks it up again."""
    seen: list[str] = []
    from app.platform.outbox import worker

    worker._HANDLERS.clear()
    worker.register_handler("test.dl", lambda _db, m: seen.append(m.id))

    message = _dead_lettered(db)
    review = dead_letter.request_review(
        db,
        message_id=message.id,
        action=DeadLetterAction.REPLAY,
        requested_by_person_id=ASKER,
        reason="Ponovni pokušaj.",
    )
    dead_letter.approve(db, review_id=review.id, approver_person_id=APPROVER)
    db.commit()

    worker.process_available("w1")

    assert seen == [message.id]
    db.expire_all()
    assert db.get(OutboxMessage, message.id).status is OutboxStatus.DELIVERED  # type: ignore[union-attr]
    worker._HANDLERS.clear()


def test_discard_needs_a_second_person_too(db: Session) -> None:
    message = _dead_lettered(db)
    review = dead_letter.request_review(
        db,
        message_id=message.id,
        action=DeadLetterAction.DISCARD,
        requested_by_person_id=ASKER,
        reason="Događaj više nije relevantan.",
    )
    db.commit()

    with pytest.raises(ForbiddenError):
        dead_letter.approve(db, review_id=review.id, approver_person_id=ASKER)
    db.rollback()

    dead_letter.approve(db, review_id=review.id, approver_person_id=APPROVER)
    db.commit()

    db.expire_all()
    assert db.get(OutboxMessage, message.id).status is OutboxStatus.DISCARDED  # type: ignore[union-attr]


def test_a_discarded_message_is_never_claimed_again(db: Session) -> None:
    message = _dead_lettered(db)
    review = dead_letter.request_review(
        db,
        message_id=message.id,
        action=DeadLetterAction.DISCARD,
        requested_by_person_id=ASKER,
        reason="Napušteno.",
    )
    dead_letter.approve(db, review_id=review.id, approver_person_id=APPROVER)
    db.commit()

    from app.platform.outbox import worker

    assert worker.process_available("w1") == 0


def test_a_rejection_leaves_the_message_dead_lettered(db: Session) -> None:
    message = _dead_lettered(db)
    review = dead_letter.request_review(
        db,
        message_id=message.id,
        action=DeadLetterAction.REPLAY,
        requested_by_person_id=ASKER,
        reason="Molim ponovni pokušaj.",
    )
    dead_letter.reject(
        db, review_id=review.id, approver_person_id=APPROVER, reason="Rizik od duplog naplaćivanja."
    )
    db.commit()

    db.expire_all()
    assert db.get(OutboxMessage, message.id).status is OutboxStatus.DEAD_LETTER  # type: ignore[union-attr]
    assert review.status is DeadLetterReviewStatus.REJECTED
    assert review.decision_reason == "Rizik od duplog naplaćivanja."


def test_only_one_request_can_be_open_per_message(db: Session) -> None:
    """Two open requests would let two approvers apply two different actions."""
    message = _dead_lettered(db)
    dead_letter.request_review(
        db,
        message_id=message.id,
        action=DeadLetterAction.REPLAY,
        requested_by_person_id=ASKER,
        reason="Prvi zahtev.",
    )
    db.commit()

    with pytest.raises(ConflictError, match="već postoji"):
        dead_letter.request_review(
            db,
            message_id=message.id,
            action=DeadLetterAction.DISCARD,
            requested_by_person_id="per_treci",
            reason="Drugi zahtev.",
        )


def test_a_new_request_is_allowed_once_the_previous_one_is_decided(db: Session) -> None:
    message = _dead_lettered(db)
    first = dead_letter.request_review(
        db,
        message_id=message.id,
        action=DeadLetterAction.REPLAY,
        requested_by_person_id=ASKER,
        reason="Prvi.",
    )
    dead_letter.reject(db, review_id=first.id, approver_person_id=APPROVER, reason="Ne sada.")
    db.commit()

    second = dead_letter.request_review(
        db,
        message_id=message.id,
        action=DeadLetterAction.DISCARD,
        requested_by_person_id=ASKER,
        reason="Onda odbaci.",
    )
    db.commit()
    assert second.status is DeadLetterReviewStatus.PENDING


def test_only_a_dead_lettered_message_can_be_reviewed(db: Session) -> None:
    message = service.enqueue(db, event_type="test.dl", payload={}, organization_id=ORG)
    db.commit()

    with pytest.raises(ConflictError, match="dead-letter"):
        dead_letter.request_review(
            db,
            message_id=message.id,
            action=DeadLetterAction.REPLAY,
            requested_by_person_id=ASKER,
            reason="Prerano.",
        )


def test_a_decided_request_cannot_be_decided_twice(db: Session) -> None:
    message = _dead_lettered(db)
    review = dead_letter.request_review(
        db,
        message_id=message.id,
        action=DeadLetterAction.REPLAY,
        requested_by_person_id=ASKER,
        reason="Jednom.",
    )
    dead_letter.approve(db, review_id=review.id, approver_person_id=APPROVER)
    db.commit()

    with pytest.raises(ConflictError, match="već odlučeno"):
        dead_letter.approve(db, review_id=review.id, approver_person_id="per_cetvrti")


def test_an_unknown_request_is_not_found(db: Session) -> None:
    with pytest.raises(NotFoundError):
        dead_letter.approve(db, review_id="dlr_nepostojeci", approver_person_id=APPROVER)


def test_both_the_request_and_the_decision_are_audited(db: Session) -> None:
    """The evidence has to survive, and it lands in the sealed chain."""
    message = _dead_lettered(db)
    review = dead_letter.request_review(
        db,
        message_id=message.id,
        action=DeadLetterAction.REPLAY,
        requested_by_person_id=ASKER,
        reason="Provajder vraćen.",
    )
    dead_letter.approve(db, review_id=review.id, approver_person_id=APPROVER)
    db.commit()

    actions = (
        db.execute(
            select(AuditLog.action, AuditLog.actor_person_id)
            .where(AuditLog.entity_id == message.id)
            .order_by(AuditLog.sequence_no)
        )
        .all()
    )
    assert [a for a, _ in actions] == [
        "outbox.dead_letter.review_requested",
        "outbox.dead_letter.review_approved",
    ]
    assert [p for _, p in actions] == [ASKER, APPROVER]
    assert verify_chain(db, ORG).ok
