"""Dead-letter dual control (M21).

A dead-lettered message is one where automated delivery has already given up.
Whatever happens next is a judgement call with a cost either way: replaying it
risks a duplicate side effect, discarding it means an event is lost for good.
So neither is one person's call. Someone requests, a *different* someone
approves, and the record of both survives.

This module owns the state machine and the invariant. It deliberately has no
HTTP surface yet: binding it to an operator endpoint needs the M05 support /
break-glass access model, which does not exist in this repository yet, and
inventing a permission here would be exactly the parallel authorization the
architecture mandate forbids. The mechanism is complete and tested; the
authorization binding is M05/M21 integration work.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.enums import AuditDataClass
from app.common.errors import ConflictError, ForbiddenError, NotFoundError
from app.platform import clock
from app.platform.audit.service import record_audit
from app.platform.outbox.enums import (
    DeadLetterAction,
    DeadLetterReviewStatus,
    OutboxStatus,
)
from app.platform.outbox.models import DeadLetterReview, OutboxMessage


def request_review(
    session: Session,
    *,
    message_id: str,
    action: DeadLetterAction,
    requested_by_person_id: str,
    reason: str,
) -> DeadLetterReview:
    """Ask for a dead-lettered message to be replayed or discarded."""
    message = session.get(OutboxMessage, message_id, with_for_update=True)
    if message is None:
        raise NotFoundError("Poruka nije pronađena.")
    if message.status is not OutboxStatus.DEAD_LETTER:
        raise ConflictError("Samo poruka u dead-letter stanju može ići na odobrenje.")
    if _open_review(session, message_id) is not None:
        raise ConflictError("Za ovu poruku već postoji zahtev koji čeka odobrenje.")
    if not reason.strip():
        raise ConflictError("Obrazloženje je obavezno.")

    review = DeadLetterReview(
        message_id=message_id,
        school_id=message.school_id,
        action=action,
        status=DeadLetterReviewStatus.PENDING,
        requested_by_person_id=requested_by_person_id,
        requested_at=clock.now(),
        request_reason=reason,
    )
    session.add(review)
    session.flush()

    record_audit(
        session,
        data_class=AuditDataClass.OPERATIONAL,
        action="outbox.dead_letter.review_requested",
        entity_type="outbox_message",
        entity_id=message_id,
        summary=f"Zatražen {action.value} za dead-letter poruku.",
        school_id=message.school_id,
        actor_person_id=requested_by_person_id,
        context={"action": action.value, "review_id": review.id},
    )
    return review


def approve(session: Session, *, review_id: str, approver_person_id: str) -> DeadLetterReview:
    """Approve a pending request and apply it.

    Refuses an approver who is the requester: that is the whole point of dual
    control, and it is enforced here rather than left to whoever calls this.
    """
    review = _pending_review(session, review_id)
    if approver_person_id == review.requested_by_person_id:
        raise ForbiddenError("Zahtev mora odobriti druga osoba, ne onaj ko ga je podneo.")

    message = session.get(OutboxMessage, review.message_id, with_for_update=True)
    if message is None:
        raise NotFoundError("Poruka nije pronađena.")
    if message.status is not OutboxStatus.DEAD_LETTER:
        raise ConflictError("Poruka više nije u dead-letter stanju.")

    if review.action is DeadLetterAction.REPLAY:
        # Back to the front of the queue, with the attempt counter cleared so the
        # retry budget starts over. last_error is kept: it is why we are here.
        message.status = OutboxStatus.PENDING
        message.attempts = 0
        message.available_at = clock.now()
        message.locked_by = None
        message.locked_at = None
    else:
        message.status = OutboxStatus.DISCARDED

    review.status = DeadLetterReviewStatus.APPROVED
    review.decided_by_person_id = approver_person_id
    review.decided_at = clock.now()
    session.flush()

    record_audit(
        session,
        data_class=AuditDataClass.OPERATIONAL,
        action="outbox.dead_letter.review_approved",
        entity_type="outbox_message",
        entity_id=review.message_id,
        summary=f"Odobren {review.action.value} za dead-letter poruku.",
        school_id=review.school_id,
        actor_person_id=approver_person_id,
        context={
            "action": review.action.value,
            "review_id": review.id,
            "requested_by": review.requested_by_person_id,
        },
    )
    return review


def reject(
    session: Session, *, review_id: str, approver_person_id: str, reason: str
) -> DeadLetterReview:
    """Refuse a pending request. The message stays dead-lettered."""
    review = _pending_review(session, review_id)
    if approver_person_id == review.requested_by_person_id:
        raise ForbiddenError("Zahtev mora odlučiti druga osoba, ne onaj ko ga je podneo.")

    review.status = DeadLetterReviewStatus.REJECTED
    review.decided_by_person_id = approver_person_id
    review.decided_at = clock.now()
    review.decision_reason = reason
    session.flush()

    record_audit(
        session,
        data_class=AuditDataClass.OPERATIONAL,
        action="outbox.dead_letter.review_rejected",
        entity_type="outbox_message",
        entity_id=review.message_id,
        summary=f"Odbijen {review.action.value} za dead-letter poruku.",
        school_id=review.school_id,
        actor_person_id=approver_person_id,
        context={"action": review.action.value, "review_id": review.id},
    )
    return review


def _open_review(session: Session, message_id: str) -> DeadLetterReview | None:
    return session.execute(
        select(DeadLetterReview).where(
            DeadLetterReview.message_id == message_id,
            DeadLetterReview.status == DeadLetterReviewStatus.PENDING,
        )
    ).scalar_one_or_none()


def _pending_review(session: Session, review_id: str) -> DeadLetterReview:
    review = session.get(DeadLetterReview, review_id, with_for_update=True)
    if review is None:
        raise NotFoundError("Zahtev nije pronađen.")
    if review.status is not DeadLetterReviewStatus.PENDING:
        raise ConflictError("O ovom zahtevu je već odlučeno.")
    return review
